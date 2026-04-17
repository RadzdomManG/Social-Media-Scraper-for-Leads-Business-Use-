from __future__ import annotations

import asyncio
import os
import queue
import threading
import tkinter as tk
import webbrowser
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config import (
    APP_SETTINGS_FILE,
    APP_TITLE,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SCROLL_PAUSE,
    MAX_LIMIT,
    SOURCE_MODE_OPTIONS,
)
from scraper import ScrapeCallbacks, ScrapeSettings, run_scraper_job
from utils import build_default_output_filename, load_json_file, save_json_file


class ScraperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1280x860")
        self.root.minsize(1100, 760)
        self.style = ttk.Style(self.root)

        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.latest_output_path = ""
        self.is_running = False
        self._last_auto_output = ""

        self.settings_path = str(Path(__file__).with_name(APP_SETTINGS_FILE))
        self.saved_settings = self._load_saved_settings()
        self.variables = self._build_variables()
        self.header_intro_var = tk.StringVar()
        self.header_detail_var = tk.StringVar()
        self.search_help_var = tk.StringVar()
        self.source_help_var = tk.StringVar()
        self.control_help_var = tk.StringVar()
        self.activity_help_var = tk.StringVar()
        self.brand_badge_var = tk.StringVar(value="Lead capture dashboard")
        self.hero_mode_var = tk.StringVar(value="Basic flow")
        self.hero_save_var = tk.StringVar(value="Query-based Excel naming")
        self.settings_canvas: tk.Canvas | None = None
        self.settings_inner: ttk.Frame | None = None

        self._configure_styles()
        self.variables["query"].trace_add("write", self._handle_query_change)
        self._build_layout()
        self._load_variables_into_form()
        self._set_status("Ready")
        self.root.after(200, self._process_events)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

    def _load_saved_settings(self) -> dict[str, object]:
        defaults = asdict(
            ScrapeSettings(
                query="",
                location="",
                output=build_default_output_filename(""),
                output_dir=DEFAULT_OUTPUT_DIR,
            )
        )
        defaults.update(load_json_file(self.settings_path))
        return defaults

    def _build_variables(self) -> dict[str, tk.Variable]:
        return {
            "query": tk.StringVar(),
            "location": tk.StringVar(),
            "source_mode": tk.StringVar(value="google_maps"),
            "limit": tk.IntVar(value=50),
            "output": tk.StringVar(),
            "output_dir": tk.StringVar(),
            "basic_mode": tk.BooleanVar(value=True),
            "visible": tk.BooleanVar(value=True),
            "append": tk.BooleanVar(value=False),
            "delay_min": tk.DoubleVar(value=DEFAULT_DELAY_MIN),
            "delay_max": tk.DoubleVar(value=DEFAULT_DELAY_MAX),
            "scroll_pause": tk.DoubleVar(value=DEFAULT_SCROLL_PAUSE),
            "retries": tk.IntVar(value=3),
            "language": tk.StringVar(value="en"),
            "log_level": tk.StringVar(value="INFO"),
            "min_rating": tk.DoubleVar(value=0.0),
            "min_reviews": tk.IntVar(value=0),
            "require_phone": tk.BooleanVar(value=False),
            "require_website": tk.BooleanVar(value=False),
            "website_mode": tk.StringVar(value="both"),
            "only_open_now": tk.BooleanVar(value=False),
            "category_include": tk.StringVar(),
            "category_exclude": tk.StringVar(),
            "name_include": tk.StringVar(),
            "include_keywords": tk.StringVar(),
            "exclude_keywords": tk.StringVar(),
        }

    def _load_variables_into_form(self) -> None:
        for key, variable in self.variables.items():
            if key in self.saved_settings:
                variable.set(self.saved_settings[key])
        suggested_output = build_default_output_filename(self.variables["query"].get().strip())
        current_output = self.variables["output"].get().strip()
        if not current_output:
            self.variables["output"].set(suggested_output)
            self._last_auto_output = suggested_output
        elif current_output == suggested_output:
            self._last_auto_output = current_output
        else:
            self._last_auto_output = ""
        if hasattr(self, "section_cards"):
            self._toggle_basic_mode()

    def _configure_styles(self) -> None:
        self.style.theme_use("clam")
        self.root.configure(bg="#0b1220")
        self.style.configure(".", font=("Segoe UI", 10))
        self.style.configure("App.TFrame", background="#eef4f8")
        self.style.configure("Hero.TFrame", background="#0f172a")
        self.style.configure("Surface.TFrame", background="#ffffff")
        self.style.configure("HeroTitle.TLabel", background="#0f172a", foreground="#f8fafc", font=("Segoe UI", 20, "bold"))
        self.style.configure("HeroBadge.TLabel", background="#0f172a", foreground="#67e8f9", font=("Segoe UI", 10, "bold"))
        self.style.configure("HeroSub.TLabel", background="#0f172a", foreground="#cbd5e1", font=("Segoe UI", 10))
        self.style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        self.style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#0f172a", font=("Segoe UI", 10, "bold"))
        self.style.configure("Section.TLabel", background="#ffffff", foreground="#334155")
        self.style.configure("SummaryValue.TLabel", background="#ffffff", foreground="#0f172a", font=("Segoe UI", 10, "bold"))
        self.style.configure("Field.TEntry", fieldbackground="#f8fafc", bordercolor="#d7e3f1")
        self.style.configure("Field.TCombobox", fieldbackground="#f8fafc", arrowsize=14)
        self.style.configure("Field.TSpinbox", arrowsize=14)
        self.style.configure("TCheckbutton", background="#ffffff", foreground="#334155")
        self.style.configure("Accent.TButton", background="#0ea5a4", foreground="#ffffff", borderwidth=0, focusthickness=3, focuscolor="#99f6e4")
        self.style.map("Accent.TButton", background=[("active", "#14b8a6"), ("pressed", "#0f766e")], foreground=[("disabled", "#d1d5db")])
        self.style.configure("Secondary.TButton", background="#e2e8f0", foreground="#0f172a")
        self.style.map("Secondary.TButton", background=[("active", "#cbd5e1"), ("pressed", "#94a3b8")])
        self.style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground="#0f172a", rowheight=28, bordercolor="#d9e2ec")
        self.style.configure("Treeview.Heading", background="#dff6fd", foreground="#0f172a", font=("Segoe UI", 10, "bold"))

    def _handle_query_change(self, *_args) -> None:
        current_output = self.variables["output"].get().strip()
        suggested_output = build_default_output_filename(self.variables["query"].get().strip())
        if not current_output or current_output == self._last_auto_output:
            self.variables["output"].set(suggested_output)
            self._last_auto_output = suggested_output

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=18, style="Hero.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(3, weight=0)
        ttk.Label(header, textvariable=self.brand_badge_var, style="HeroBadge.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=APP_TITLE, style="HeroTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            header,
            textvariable=self.header_intro_var,
            style="HeroSub.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            header,
            textvariable=self.header_detail_var,
            style="HeroSub.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            header,
            text="Basic Mode",
            variable=self.variables["basic_mode"],
            command=self._toggle_basic_mode,
        ).grid(row=0, column=1, rowspan=2, sticky="ne", padx=(0, 8))
        ttk.Button(header, text="Quick Tutorial", command=self._show_tutorial, style="Secondary.TButton").grid(row=0, column=2, rowspan=2, sticky="ne")
        hero_stats = ttk.Frame(header, style="Hero.TFrame")
        hero_stats.grid(row=0, column=3, rowspan=4, sticky="ne", padx=(18, 0))
        self._create_hero_chip(hero_stats, "MODE", self.hero_mode_var, "#082f49", "#7dd3fc").grid(row=0, column=0, sticky="e", pady=(0, 8))
        self._create_hero_chip(hero_stats, "SAVE", self.hero_save_var, "#0f3d2e", "#86efac").grid(row=1, column=0, sticky="e")

        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        left = ttk.Frame(main, padding=0, style="App.TFrame")
        right = ttk.Frame(main, padding=12, style="App.TFrame")
        main.add(left, weight=2)
        main.add(right, weight=3)

        self._build_scrollable_settings_panel(left)
        self._build_activity_panel(right)

    def _build_scrollable_settings_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        canvas = tk.Canvas(parent, background="#eef4f8", highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = ttk.Frame(canvas, padding=12, style="App.TFrame")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _fit_inner_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", _sync_scroll_region)
        canvas.bind("<Configure>", _fit_inner_width)

        self.settings_canvas = canvas
        self.settings_inner = inner
        self._build_settings_panel(inner)
        self._bind_mousewheel_scroll(inner, canvas)

    def _bind_mousewheel_scroll(self, widget, canvas: tk.Canvas) -> None:
        def _on_mousewheel(event) -> None:
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        widget.bind("<Enter>", lambda _event: canvas.focus_set(), add="+")
        for target in (widget, canvas):
            target.bind("<MouseWheel>", _on_mousewheel, add="+")
            target.bind("<Button-4>", _on_mousewheel, add="+")
            target.bind("<Button-5>", _on_mousewheel, add="+")

    def _build_settings_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0

        self.section_cards: dict[str, ttk.LabelFrame] = {}
        sections = {
            "search": ("Step 1 - What To Search", self._build_search_section),
            "filters": ("Step 2 - Optional Filters", self._build_filter_section),
            "automation": ("Step 3 - Browser And Speed", self._build_automation_section),
            "output": ("Step 4 - Save File", self._build_output_section),
            "controls": ("Step 5 - Start Or Stop", self._build_control_section),
        }
        for key, (title, builder) in sections.items():
            card = ttk.LabelFrame(parent, text=title, padding=10, style="Card.TLabelframe")
            card.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
            card.columnconfigure(1, weight=1)
            builder(card)
            self.section_cards[key] = card
            row += 1
        self._toggle_basic_mode()

    def _create_hero_chip(self, parent, title: str, value_var: tk.StringVar, bg: str, accent: str):
        frame = tk.Frame(parent, bg=bg, padx=12, pady=8, bd=0, highlightthickness=1, highlightbackground=accent)
        tk.Label(frame, text=title, bg=bg, fg=accent, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=value_var, bg=bg, fg="#f8fafc", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(2, 0))
        return frame

    def _create_metric_card(self, parent, title: str, variable: tk.StringVar, bg: str, fg: str):
        frame = tk.Frame(parent, bg=bg, padx=12, pady=10, bd=0, highlightthickness=1, highlightbackground="#d7e3f1")
        tk.Label(frame, text=title, bg=bg, fg="#475569", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=variable, bg=bg, fg=fg, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(4, 0))
        return frame

    def _build_search_section(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="Business Type").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["query"], style="Field.TEntry").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="City / Area").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["location"], style="Field.TEntry").grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Source").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.variables["source_mode"],
            values=SOURCE_MODE_OPTIONS,
            state="readonly",
            style="Field.TCombobox",
            width=18,
        ).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(parent, text="How Many Leads").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=1, to=MAX_LIMIT, textvariable=self.variables["limit"], width=10, style="Field.TSpinbox").grid(
            row=3, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent,
            textvariable=self.search_help_var,
            style="Section.TLabel",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(
            parent,
            textvariable=self.source_help_var,
            style="Section.TLabel",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(
            parent,
            text="Examples: choose 'linkedin_public' or 'universal_lead_finder' with words like doctor, teacher, business owner, or video editor.",
            style="Section.TLabel",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _build_filter_section(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="Minimum Rating").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=0, to=5, increment=0.1, textvariable=self.variables["min_rating"], width=10).grid(
            row=0, column=1, sticky="w", pady=4
        )
        ttk.Label(parent, text="Minimum Reviews").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=0, to=100000, textvariable=self.variables["min_reviews"], width=10).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(parent, text="Business Name Contains").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["name_include"], style="Field.TEntry").grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Category Must Include").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["category_include"], style="Field.TEntry").grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Category Must Not Include").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["category_exclude"], style="Field.TEntry").grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(parent, text="Only keep leads with phone number", variable=self.variables["require_phone"]).grid(
            row=5, column=0, sticky="w", pady=4
        )
        ttk.Label(parent, text="Website Filter").grid(row=5, column=1, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.variables["website_mode"],
            values=["both", "with_website", "without_website"],
            state="readonly",
            style="Field.TCombobox",
            width=16,
        ).grid(row=6, column=1, sticky="w", pady=4)
        ttk.Checkbutton(parent, text="Only keep businesses that look open now", variable=self.variables["only_open_now"]).grid(
            row=6, column=0, sticky="w", pady=4
        )
        ttk.Label(parent, text="Include Keywords").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["include_keywords"], style="Field.TEntry").grid(row=7, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Exclude Keywords").grid(row=8, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["exclude_keywords"], style="Field.TEntry").grid(row=8, column=1, sticky="ew", pady=4)

    def _build_automation_section(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="Minimum Delay").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=0.2, to=30, increment=0.1, textvariable=self.variables["delay_min"], width=10).grid(
            row=0, column=1, sticky="w", pady=4
        )
        ttk.Label(parent, text="Maximum Delay").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=0.2, to=30, increment=0.1, textvariable=self.variables["delay_max"], width=10).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(parent, text="Pause Between Scrolls").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=0.2, to=30, increment=0.1, textvariable=self.variables["scroll_pause"], width=10).grid(
            row=2, column=1, sticky="w", pady=4
        )
        ttk.Label(parent, text="Retry Attempts").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(parent, from_=1, to=10, textvariable=self.variables["retries"], width=10).grid(
            row=3, column=1, sticky="w", pady=4
        )
        ttk.Label(parent, text="Language Code").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["language"], style="Field.TEntry").grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Log Detail").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            parent,
            textvariable=self.variables["log_level"],
            values=["DEBUG", "INFO", "WARNING"],
            state="readonly",
            style="Field.TCombobox",
            width=12,
        ).grid(row=5, column=1, sticky="w", pady=4)
        ttk.Checkbutton(parent, text="Show browser while scraping", variable=self.variables["visible"]).grid(
            row=6, column=0, sticky="w", pady=4
        )
        ttk.Checkbutton(parent, text="Add to existing Excel file", variable=self.variables["append"]).grid(
            row=6, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent,
            text="Tip: beginners should keep the browser visible.",
            style="Section.TLabel",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _toggle_basic_mode(self) -> None:
        basic_mode = bool(self.variables["basic_mode"].get())
        for key in ("filters", "automation"):
            card = self.section_cards.get(key)
            if card is None:
                continue
            if basic_mode:
                card.grid_remove()
            else:
                card.grid()
        if basic_mode:
            self.brand_badge_var.set("Radz lead capture dashboard")
            self.hero_mode_var.set("Basic flow")
            self.hero_save_var.set("Auto file naming on")
            self.header_intro_var.set("Pick a business type, enter a city, choose 1 to 5000 leads, and press Start Scraping.")
            self.header_detail_var.set("Basic Mode keeps Radz Scraper simple, polished, and ready to auto-save Excel files using your business query name.")
            self.search_help_var.set('Fast example: "dentists" in "Cebu City, Philippines"')
            self.source_help_var.set("Quick tip: use 'google_maps' for a simple business list, or 'universal_lead_finder' for a wider public lead search.")
            self.control_help_var.set("Easy flow: fill Step 1, pick your lead count, then click Start Scraping.")
            self.activity_help_var.set("The bot preview updates live, and the saved Excel workbook comes from the same run with auto-save naming based on your business type.")
        else:
            self.brand_badge_var.set("Radz growth workflow")
            self.hero_mode_var.set("Advanced workflow")
            self.hero_save_var.set("Filters + export controls")
            self.header_intro_var.set("Type what kind of business you want, choose a location, then click Start Scraping.")
            self.header_detail_var.set("Radz Scraper for all Social Media searches Google Maps and saves a clean Excel workbook with business details plus allowed public contact links when available.")
            self.search_help_var.set('Example: "dentists" and "Cebu City, Philippines"')
            self.source_help_var.set("Use 'universal_lead_finder' for the broadest mix of businesses, public profiles, websites, and directories.")
            self.control_help_var.set("Simple flow: fill Step 1, choose how many leads, then click Start Scraping.")
            self.activity_help_var.set("Captured data includes business details plus allowed public contact links, and the workbook auto-saves using your business query when you do not enter a custom file name.")
        if self.settings_canvas is not None:
            self.root.after(10, lambda: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))

    def _build_output_section(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="Excel File Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["output"]).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Use Business Name", command=self._refresh_output_name, style="Secondary.TButton").grid(row=0, column=2, sticky="ew", padx=(8, 0))
        ttk.Label(parent, text="Where To Save").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=self.variables["output_dir"]).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Browse", command=self._choose_output_dir, style="Secondary.TButton").grid(row=1, column=2, sticky="ew", padx=(8, 0))
        ttk.Button(parent, text="Open Last Excel", command=self._open_last_excel, style="Secondary.TButton").grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Button(parent, text="Open Save Folder", command=self._open_output_folder, style="Secondary.TButton").grid(row=2, column=2, sticky="ew", padx=(8, 0), pady=(8, 0))

    def _build_control_section(self, parent: ttk.LabelFrame) -> None:
        self.run_button = ttk.Button(parent, text="Start Scraping", command=self._toggle_run, style="Accent.TButton")
        self.run_button.grid(row=0, column=0, sticky="ew", pady=4)
        self.stop_button = ttk.Button(parent, text="Stop Safely", command=self._request_stop, state="disabled", style="Secondary.TButton")
        self.stop_button.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Button(parent, text="Save Settings", command=self._save_settings, style="Secondary.TButton").grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(parent, text="Reset Form", command=self._reset_form, style="Secondary.TButton").grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Label(
            parent,
            textvariable=self.control_help_var,
            style="Section.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

    def _build_activity_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        summary = ttk.LabelFrame(parent, text="Scrape Summary", padding=10, style="Card.TLabelframe")
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for index in range(3):
            summary.columnconfigure(index, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        self.urls_var = tk.StringVar(value="0")
        self.saved_var = tk.StringVar(value="0")
        self.filtered_var = tk.StringVar(value="0")
        self.errors_var = tk.StringVar(value="0")
        self.progress_var = tk.StringVar(value="Waiting")
        self.public_search_var = tk.StringVar(value="Not used yet")

        metrics = ttk.Frame(summary, style="Surface.TFrame")
        metrics.grid(row=0, column=0, columnspan=3, sticky="ew")
        for index in range(3):
            metrics.columnconfigure(index, weight=1)
        self._create_metric_card(metrics, "Status", self.status_var, "#f8fafc", "#0f172a").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._create_metric_card(metrics, "URLs Collected", self.urls_var, "#f8fafc", "#0369a1").grid(row=0, column=1, sticky="ew", padx=4)
        self._create_metric_card(metrics, "Saved In Excel", self.saved_var, "#f8fafc", "#0f766e").grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self._create_metric_card(metrics, "Filtered Out", self.filtered_var, "#f8fafc", "#7c3aed").grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(8, 0))
        self._create_metric_card(metrics, "Errors", self.errors_var, "#f8fafc", "#dc2626").grid(row=1, column=1, sticky="ew", padx=4, pady=(8, 0))
        self._create_metric_card(metrics, "Progress", self.progress_var, "#f8fafc", "#1d4ed8").grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(summary, text="Public Search", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(summary, textvariable=self.public_search_var, style="SummaryValue.TLabel").grid(row=1, column=1, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(
            summary,
            textvariable=self.activity_help_var,
            style="Section.TLabel",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        log_frame = ttk.LabelFrame(parent, text="What The Bot Is Doing", padding=10, style="Card.TLabelframe")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=12, wrap="word", bg="#f8fafc", fg="#0f172a", insertbackground="#0f172a", relief="flat")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set, state="disabled")

        preview = ttk.LabelFrame(parent, text="Leads Found", padding=10, style="Card.TLabelframe")
        preview.grid(row=2, column=0, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)

        columns = ("Business Name", "Category", "Phone Number", "Website", "Social Media Category", "Address")
        self.preview_tree = ttk.Treeview(preview, columns=columns, show="headings", height=18)
        for column in columns:
            self.preview_tree.heading(column, text=column)
            width = 140
            if column == "Address":
                width = 240
            if column == "Social Media Category":
                width = 220
            self.preview_tree.column(column, width=width, anchor="w")
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview, orient="vertical", command=self.preview_tree.yview)
        preview_scroll.grid(row=0, column=1, sticky="ns")
        self.preview_tree.configure(yscrollcommand=preview_scroll.set)

    def _gather_settings(self) -> ScrapeSettings:
        return ScrapeSettings(
            query=self.variables["query"].get().strip(),
            location=self.variables["location"].get().strip(),
            source_mode=self.variables["source_mode"].get().strip(),
            limit=int(self.variables["limit"].get()),
            output=self.variables["output"].get().strip(),
            output_dir=self.variables["output_dir"].get().strip(),
            visible=bool(self.variables["visible"].get()),
            append=bool(self.variables["append"].get()),
            delay_min=float(self.variables["delay_min"].get()),
            delay_max=float(self.variables["delay_max"].get()),
            scroll_pause=float(self.variables["scroll_pause"].get()),
            retries=int(self.variables["retries"].get()),
            language=self.variables["language"].get().strip(),
            log_level=self.variables["log_level"].get().strip(),
            min_rating=float(self.variables["min_rating"].get()),
            min_reviews=int(self.variables["min_reviews"].get()),
            require_phone=bool(self.variables["require_phone"].get()),
            require_website=self.variables["website_mode"].get().strip() == "with_website",
            website_mode=self.variables["website_mode"].get().strip(),
            only_open_now=bool(self.variables["only_open_now"].get()),
            category_include=self.variables["category_include"].get().strip(),
            category_exclude=self.variables["category_exclude"].get().strip(),
            name_include=self.variables["name_include"].get().strip(),
            include_keywords=self.variables["include_keywords"].get().strip(),
            exclude_keywords=self.variables["exclude_keywords"].get().strip(),
        )

    def _save_settings(self) -> None:
        payload = {key: variable.get() for key, variable in self.variables.items()}
        save_json_file(self.settings_path, payload)
        self._append_log(f"Saved settings to {self.settings_path}")

    def _reset_form(self) -> None:
        self.saved_settings = self._load_saved_settings()
        self._load_variables_into_form()
        self.saved_var.set("0")
        self.filtered_var.set("0")
        self.errors_var.set("0")
        self.urls_var.set("0")
        self.progress_var.set("Waiting")
        self.public_search_var.set("Not used yet")
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        self._set_status("Ready")

    def _refresh_output_name(self) -> None:
        refreshed_output = build_default_output_filename(self.variables["query"].get().strip())
        self.variables["output"].set(refreshed_output)
        self._last_auto_output = refreshed_output

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Choose output folder")
        if selected:
            self.variables["output_dir"].set(selected)

    def _open_last_excel(self) -> None:
        if not self.latest_output_path or not os.path.exists(self.latest_output_path):
            messagebox.showinfo(APP_TITLE, "No completed Excel file is available yet.")
            return
        self._open_path(self.latest_output_path)

    def _open_output_folder(self) -> None:
        target = self.variables["output_dir"].get().strip() or os.getcwd()
        self._open_path(target)

    def _open_path(self, path: str) -> None:
        absolute = os.path.abspath(path)
        if os.name == "nt":
            os.startfile(absolute)  # type: ignore[attr-defined]
        else:
            webbrowser.open(f"file://{absolute}")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _toggle_run(self) -> None:
        if self.is_running:
            self._request_stop()
            return
        self._start_run()

    def _start_run(self) -> None:
        try:
            settings = self._gather_settings()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self._save_settings()
        self.stop_event.clear()
        self.is_running = True
        self.run_button.configure(text="Scraping...", state="disabled")
        self.stop_button.configure(state="normal")
        self.progress_var.set("Starting")
        self.saved_var.set("0")
        self.filtered_var.set("0")
        self.errors_var.set("0")
        self.urls_var.set("0")
        self.public_search_var.set("Not used yet" if settings.source_mode == "google_maps" else "Preparing public search")
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)

        callbacks = ScrapeCallbacks(
            on_status=lambda message: self.event_queue.put(("status", message)),
            on_progress=lambda index, total, message: self.event_queue.put(("progress", (index, total, message))),
            on_lead=lambda lead: self.event_queue.put(("lead", lead)),
            on_urls_collected=lambda count: self.event_queue.put(("urls", count)),
            on_public_search_state=lambda message: self.event_queue.put(("public_search", message)),
        )

        def _worker() -> None:
            try:
                result = asyncio.run(run_scraper_job(settings, callbacks=callbacks, stop_event=self.stop_event))
                self.event_queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                self.event_queue.put(("error", exc))

        self.worker_thread = threading.Thread(target=_worker, daemon=True)
        self.worker_thread.start()
        self._append_log("Scraping started.")
        self._set_status("Running")

    def _request_stop(self) -> None:
        if not self.is_running:
            return
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self._append_log("Stop requested. The bot will finish the current lead and save your file.")
        self._set_status("Stopping")

    def _process_events(self) -> None:
        try:
            while True:
                event_type, payload = self.event_queue.get_nowait()
                if event_type == "status":
                    self._set_status(str(payload))
                    self._append_log(str(payload))
                elif event_type == "progress":
                    index, total, message = payload
                    self.progress_var.set(f"{index}/{total}")
                    self._append_log(message)
                    if message.startswith("Filtered"):
                        self.filtered_var.set(str(int(self.filtered_var.get()) + 1))
                    elif message.startswith("Skipped"):
                        self.errors_var.set(str(int(self.errors_var.get()) + 1))
                elif event_type == "lead":
                    lead = payload
                    self.saved_var.set(str(int(self.saved_var.get()) + 1))
                    display_name = (
                        lead.get("Business Name")
                        or lead.get("Display Name")
                        or lead.get("Profile Name")
                        or lead.get("Company / Business")
                        or ""
                    )
                    display_category = (
                        lead.get("Category")
                        or lead.get("Position / Category")
                        or lead.get("Source Type")
                        or ""
                    )
                    display_phone = lead.get("Phone Number") or lead.get("Phone") or ""
                    display_website = lead.get("Website") or lead.get("Profile URL") or ""
                    display_social_category = lead.get("Social Media Category") or lead.get("Social media") or ""
                    display_address = (
                        lead.get("Address")
                        or lead.get("Company / Business")
                        or lead.get("Source Platform")
                        or ""
                    )
                    self.preview_tree.insert(
                        "",
                        0,
                        values=(
                            display_name,
                            display_category,
                            display_phone,
                            display_website,
                            display_social_category,
                            display_address,
                        ),
                    )
                elif event_type == "urls":
                    self.urls_var.set(str(payload))
                    self._append_log(f"Collected {payload} listing URLs.")
                elif event_type == "public_search":
                    self.public_search_var.set(str(payload))
                    self._append_log(str(payload))
                elif event_type == "done":
                    self._finish_run(payload)
                elif event_type == "error":
                    self._fail_run(payload)
        except queue.Empty:
            pass
        self.root.after(200, self._process_events)

    def _finish_run(self, result) -> None:
        self.is_running = False
        self.run_button.configure(text="Start Scraping", state="normal")
        self.stop_button.configure(state="disabled")
        self._set_status("Completed" if result.exit_code == 0 else "Finished with warnings")
        self.filtered_var.set(str(result.filtered_out))
        self.errors_var.set(str(result.errors))
        if result.export is not None:
            self.latest_output_path = result.export.output_path
            self.saved_var.set(str(result.export.total_saved))
            self._append_log(f"Excel saved to {result.export.output_path}")
            self._append_log(
                f"Workbook rows: Leads={len(result.leads)}, Social Search={len(result.social_rows)}, Universal Finder={len(result.universal_rows)}"
            )
        self._append_log(f"Run finished with exit code {result.exit_code}.")
        if result.exit_code not in (0, 2, 130):
            messagebox.showwarning(APP_TITLE, f"Run finished with exit code {result.exit_code}.")

    def _fail_run(self, exc: Exception) -> None:
        self.is_running = False
        self.run_button.configure(text="Start Scraping", state="normal")
        self.stop_button.configure(state="disabled")
        self._set_status("Error")
        self._append_log(f"Fatal error: {exc}")
        messagebox.showerror(APP_TITLE, str(exc))

    def _show_tutorial(self) -> None:
        tutorial = (
            "Quick Tutorial\n\n"
            "1. In 'Step 1 - What To Search', type the kind of business you want.\n"
            "   Example: dentists, coffee shops, law firms.\n\n"
            "2. In 'City / Area', type the place you want to search.\n"
            "   Example: Cebu City, Philippines.\n\n"
            "3. Set 'How Many Leads' to the number of businesses you want.\n"
            f"   You can choose from 1 to {MAX_LIMIT}. Beginners should start with 10 to 25.\n\n"
            "4. Filters are optional. Leave them blank if you want more results.\n\n"
            "   For public profile search, you can use Include Keywords like doctor, teacher, dentist, or coach.\n\n"
            "5. Keep 'Show browser while scraping' turned on for your first run.\n\n"
            "6. The Excel file name auto-follows your business query.\n"
            "   Example: if you search Salon, the workbook auto-saves as Salon.xlsx unless you enter a custom file name.\n\n"
            "7. Click 'Start Scraping'.\n\n"
            "8. When it finishes, click 'Open Last Excel' to open your file.\n\n"
            "Your Excel file will include:\n"
            "- Leads\n"
            "- Upload Ready\n"
            "- Summary\n"
            "- Social Search (when source is social_search or both)\n\n"
            "Important:\n"
            "- Source 'google_maps' uses Google Maps and website enrichment.\n"
            "- Source 'social_search' uses public web search to find profile/page results across major platforms.\n"
            "- Source 'universal_lead_finder' mixes Google Maps, public profiles, websites, and directories into one scored sheet.\n"
            "- Source 'facebook_public', 'instagram_public', and 'linkedin_public' focus on those public profile/page results only.\n"
            "- Include/Exclude Keywords help narrow results like doctor, teacher, salon owner, or dentist.\n"
            "- Source 'both' runs both workflows into one workbook."
        )
        messagebox.showinfo(APP_TITLE, tutorial)

    def _handle_close(self) -> None:
        if self.is_running and not messagebox.askyesno(
            APP_TITLE,
            "A run is still active. Do you want to request stop and close after it finishes?",
        ):
            return
        if self.is_running:
            self._request_stop()
        self._save_settings()
        self.root.destroy()


def launch_app() -> None:
    root = tk.Tk()
    ttk.Style(root).theme_use("vista" if os.name == "nt" else "clam")
    ScraperApp(root)
    root.mainloop()
