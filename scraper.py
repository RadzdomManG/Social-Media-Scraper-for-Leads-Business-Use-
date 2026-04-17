from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from typing import Callable

from dotenv import load_dotenv

from browser import create_browser_session
from config import (
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_LANGUAGE,
    DEFAULT_LIMIT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MIN_RATING,
    DEFAULT_MIN_REVIEWS,
    DEFAULT_RETRIES,
    DEFAULT_SCROLL_PAUSE,
    DEFAULT_SOURCE_MODE,
    MAX_LIMIT,
    SOURCE_MODE_OPTIONS,
)
from exporter import ExportResult, export_workbook
from extractor import extract_listing_details
from scroller import collect_listing_urls
from social_search import discover_social_profiles, discover_web_and_directory_results
from utils import (
    CaptchaDetectedError,
    build_default_output_filename,
    filter_lead,
    log_listing_failure,
    now_string,
    print_finish_banner,
    print_progress,
    print_start_banner,
    retry_async,
    sanitize_output_filename,
    setup_logging,
)


@dataclass
class ScrapeSettings:
    query: str
    location: str
    source_mode: str = DEFAULT_SOURCE_MODE
    limit: int = DEFAULT_LIMIT
    output: str = ""
    visible: bool = False
    append: bool = False
    delay_min: float = DEFAULT_DELAY_MIN
    delay_max: float = DEFAULT_DELAY_MAX
    scroll_pause: float = DEFAULT_SCROLL_PAUSE
    retries: int = DEFAULT_RETRIES
    language: str = DEFAULT_LANGUAGE
    log_level: str = DEFAULT_LOG_LEVEL
    min_rating: float = DEFAULT_MIN_RATING
    min_reviews: int = DEFAULT_MIN_REVIEWS
    require_phone: bool = False
    require_website: bool = False
    website_mode: str = "both"
    only_open_now: bool = False
    category_include: str = ""
    category_exclude: str = ""
    name_include: str = ""
    include_keywords: str = ""
    exclude_keywords: str = ""
    output_dir: str = ""


@dataclass
class ScrapeResult:
    exit_code: int
    export: ExportResult | None
    leads: list[dict[str, object]]
    social_rows: list[dict[str, object]]
    universal_rows: list[dict[str, object]]
    filtered_out: int
    errors: int
    collected_urls: int


@dataclass
class ScrapeCallbacks:
    on_status: Callable[[str], None] | None = None
    on_progress: Callable[[int, int, str], None] | None = None
    on_lead: Callable[[dict[str, object]], None] | None = None
    on_urls_collected: Callable[[int], None] | None = None
    on_public_search_state: Callable[[str], None] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Google Maps lead scraper")
    parser.add_argument("--query", help="Business type to search")
    parser.add_argument("--location", help="City, country or area")
    parser.add_argument(
        "--source-mode",
        default=DEFAULT_SOURCE_MODE,
        choices=SOURCE_MODE_OPTIONS,
        help="Choose where to collect leads from",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max number of leads to scrape")
    parser.add_argument("--output", default="", help="Output Excel filename")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--append", action="store_true", help="Append to existing Excel file")
    parser.add_argument("--delay-min", type=float, default=DEFAULT_DELAY_MIN, help="Minimum delay between actions")
    parser.add_argument("--delay-max", type=float, default=DEFAULT_DELAY_MAX, help="Maximum delay between actions")
    parser.add_argument("--scroll-pause", type=float, default=DEFAULT_SCROLL_PAUSE, help="Pause between each scroll")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per listing on failure")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="Google Maps language")
    parser.add_argument("--min-rating", type=float, default=DEFAULT_MIN_RATING, help="Minimum rating filter")
    parser.add_argument("--min-reviews", type=int, default=DEFAULT_MIN_REVIEWS, help="Minimum reviews filter")
    parser.add_argument("--require-phone", action="store_true", help="Keep only leads with phone number")
    parser.add_argument("--require-website", action="store_true", help="Keep only leads with website")
    parser.add_argument(
        "--website-mode",
        default="both",
        choices=["both", "with_website", "without_website"],
        help="Filter leads by website availability",
    )
    parser.add_argument("--only-open-now", action="store_true", help="Keep only leads marked open")
    parser.add_argument("--category-include", default="", help="Category must include this text")
    parser.add_argument("--category-exclude", default="", help="Category must not include this text")
    parser.add_argument("--name-include", default="", help="Business name must include this text")
    parser.add_argument("--include-keywords", default="", help="Comma-separated public profile keywords to include")
    parser.add_argument("--exclude-keywords", default="", help="Comma-separated public profile keywords to exclude")
    parser.add_argument("--gui", action="store_true", help="Launch the desktop app")
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING"],
        help="Logging verbosity",
    )
    return parser.parse_args()


def namespace_to_settings(args: argparse.Namespace) -> ScrapeSettings:
    return ScrapeSettings(
        query=(args.query or "").strip(),
        location=(args.location or "").strip(),
        source_mode=args.source_mode,
        limit=args.limit,
        output=args.output or "",
        visible=args.visible,
        append=args.append,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        scroll_pause=args.scroll_pause,
        retries=args.retries,
        language=args.language,
        log_level=args.log_level,
        min_rating=args.min_rating,
        min_reviews=args.min_reviews,
        require_phone=args.require_phone,
        require_website=args.require_website,
        website_mode="with_website" if args.require_website and getattr(args, "website_mode", "both") == "both" else args.website_mode,
        only_open_now=args.only_open_now,
        category_include=args.category_include,
        category_exclude=args.category_exclude,
        name_include=args.name_include,
        include_keywords=args.include_keywords,
        exclude_keywords=args.exclude_keywords,
    )


def validate_settings(settings: ScrapeSettings) -> None:
    if not settings.query:
        raise ValueError("Query is required.")
    if not settings.location:
        raise ValueError("Location is required.")
    if settings.delay_min <= 0 or settings.delay_max <= 0:
        raise ValueError("Delay values must be positive numbers.")
    if settings.delay_min > settings.delay_max:
        raise ValueError("Minimum delay cannot be greater than maximum delay.")
    if settings.limit <= 0:
        raise ValueError("Lead limit must be greater than 0.")
    if settings.limit > MAX_LIMIT:
        raise ValueError(f"Lead limit must be between 1 and {MAX_LIMIT}.")
    if settings.retries <= 0:
        raise ValueError("Retries must be greater than 0.")
    if settings.min_rating < 0:
        raise ValueError("Minimum rating cannot be negative.")
    if settings.min_reviews < 0:
        raise ValueError("Minimum reviews cannot be negative.")
    if settings.source_mode not in set(SOURCE_MODE_OPTIONS):
        raise ValueError("Invalid source mode.")
    if settings.website_mode not in {"both", "with_website", "without_website"}:
        raise ValueError("Invalid website filter mode.")


def resolve_output_path(settings: ScrapeSettings) -> str:
    if settings.output:
        filename = settings.output
    else:
        filename = build_default_output_filename(settings.query)
    filename = sanitize_output_filename(filename)
    if settings.output_dir:
        from pathlib import Path

        return str(Path(settings.output_dir).expanduser() / filename)
    return filename


def _is_people_role_query(query: str, include_keywords: str) -> bool:
    haystack = f"{query} {include_keywords}".casefold()
    role_terms = {
        "owner",
        "founder",
        "entrepreneur",
        "ceo",
        "teacher",
        "doctor",
        "dentist",
        "lawyer",
        "instructor",
        "coach",
        "editor",
        "assistant",
        "manager",
        "agent",
        "broker",
        "designer",
    }
    business_terms = {
        "shop",
        "store",
        "restaurant",
        "cafe",
        "coffee",
        "clinic",
        "salon",
        "spa",
        "hotel",
        "agency",
        "company",
        "service",
        "school",
        "office",
        "center",
    }
    return any(term in haystack for term in role_terms) and not any(term in haystack for term in business_terms)


def _maps_quality_score(lead: dict[str, object]) -> int:
    score = 45
    if lead.get("Website"):
        score += 15
    if lead.get("Email"):
        score += 15
    if lead.get("Phone Number") or lead.get("Phone number"):
        score += 10
    if lead.get("Social media"):
        score += 5
    rating = lead.get("Rating")
    if isinstance(rating, (int, float)) and rating:
        score += 10
    return min(score, 100)


def _social_quality_score(row: dict[str, object]) -> int:
    score = 35
    if row.get("Keyword Match"):
        score += 20
    if row.get("Profile Name"):
        score += 15
    if row.get("Company / Business"):
        score += 10
    url = str(row.get("Profile URL", "")).casefold()
    if "/company/" in url or "/school/" in url:
        score += 10
    return min(score, 100)


def _build_universal_rows(
    query: str,
    location: str,
    leads: list[dict[str, object]],
    social_rows: list[dict[str, object]],
    website_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for lead in leads:
        rows.append(
            {
                "Display Name": lead.get("Business Name", ""),
                "Company / Business": lead.get("Company") or lead.get("Business Name", ""),
                "Source Type": "Google Maps Business",
                "Source Platform": "Google Maps",
                "Quality Score": _maps_quality_score(lead),
                "Position / Category": lead.get("Category", ""),
                "Email": lead.get("Email", ""),
                "Phone": lead.get("Phone Number") or lead.get("Phone number", ""),
                "Website": lead.get("Website", ""),
                "Profile URL": lead.get("Google Maps URL", ""),
                "Social media": lead.get("Social media", ""),
                "Address": lead.get("Address", ""),
                "Business Status": lead.get("Business Status", ""),
                "Rating": lead.get("Rating", ""),
                "Total Reviews": lead.get("Total Reviews", ""),
                "Keyword Match": "",
                "Result Title": lead.get("Business Name", ""),
                "Result Snippet": "",
                "Search Query": query,
                "Location": location,
                "Date Scraped": lead.get("Date Scraped", now_string()),
            }
        )

    for row in social_rows:
        rows.append(
            {
                "Display Name": row.get("Profile Name", "") or row.get("Company / Business", ""),
                "Company / Business": row.get("Company / Business", ""),
                "Source Type": "Public Profile",
                "Source Platform": row.get("Platform", ""),
                "Quality Score": _social_quality_score(row),
                "Position / Category": row.get("Keyword Match", ""),
                "Email": "",
                "Phone": "",
                "Website": "",
                "Profile URL": row.get("Profile URL", ""),
                "Social media": row.get("Profile URL", ""),
                "Address": "",
                "Business Status": "",
                "Rating": "",
                "Total Reviews": "",
                "Keyword Match": row.get("Keyword Match", ""),
                "Result Title": row.get("Result Title", ""),
                "Result Snippet": row.get("Result Snippet", ""),
                "Search Query": row.get("Search Query", query),
                "Location": row.get("Location", location),
                "Date Scraped": row.get("Date Scraped", now_string()),
            }
        )

    for row in website_rows:
        rows.append(
            {
                "Display Name": row.get("Profile Name", "") or row.get("Company / Business", ""),
                "Company / Business": row.get("Company / Business", ""),
                "Source Type": row.get("Source Type", "Website"),
                "Source Platform": row.get("Source Platform", row.get("Platform", "")),
                "Quality Score": row.get("Quality Score", 35),
                "Position / Category": row.get("Keyword Match", ""),
                "Email": "",
                "Phone": "",
                "Website": row.get("Profile URL", ""),
                "Profile URL": row.get("Profile URL", ""),
                "Social media": "",
                "Address": "",
                "Business Status": "",
                "Rating": "",
                "Total Reviews": "",
                "Keyword Match": row.get("Keyword Match", ""),
                "Result Title": row.get("Result Title", ""),
                "Result Snippet": row.get("Result Snippet", ""),
                "Search Query": row.get("Search Query", query),
                "Location": row.get("Location", location),
                "Date Scraped": row.get("Date Scraped", now_string()),
            }
        )

    rows.sort(key=lambda item: int(item.get("Quality Score", 0) or 0), reverse=True)
    return rows


def _build_run_metadata(
    settings: ScrapeSettings,
    leads: list[dict[str, object]],
    social_rows: list[dict[str, object]],
    universal_rows: list[dict[str, object]],
    website_rows: list[dict[str, object]],
    errors: int,
    filtered_out: int,
) -> dict[str, object]:
    return {
        "query": settings.query,
        "location": settings.location,
        "scraped_at": now_string(),
        "total_results_found": max(len(universal_rows), len(leads) + len(social_rows) + len(website_rows)),
        "total_errors": errors,
        "total_filtered_out": filtered_out,
        "lead_rows": len(leads),
        "social_rows": len(social_rows),
        "universal_rows": len(universal_rows),
        "website_rows": len(website_rows),
    }


async def run_scraper_job(
    settings: ScrapeSettings,
    callbacks: ScrapeCallbacks | None = None,
    stop_event=None,
) -> ScrapeResult:
    load_dotenv()
    validate_settings(settings)

    logger = setup_logging(settings.log_level)
    output_path = resolve_output_path(settings)
    callbacks = callbacks or ScrapeCallbacks()

    if callbacks.on_status:
        callbacks.on_status("Preparing run...")

    print_start_banner(settings.query, settings.location, settings.limit, output_path)

    use_google_maps = settings.source_mode in {"google_maps", "both"}
    if settings.source_mode == "universal_lead_finder":
        use_google_maps = not _is_people_role_query(settings.query, settings.include_keywords)

    browser = None
    if use_google_maps:
        browser = await create_browser_session(
            visible=settings.visible,
            language=settings.language,
            delay_min=settings.delay_min,
            delay_max=settings.delay_max,
            logger=logger,
        )

    leads: list[dict[str, object]] = []
    social_rows: list[dict[str, object]] = []
    universal_rows: list[dict[str, object]] = []
    website_rows: list[dict[str, object]] = []
    errors = 0
    filtered_out = 0
    listing_urls: list[str] = []
    search_results_url = ""

    try:
        if use_google_maps and browser is not None:
            listing_urls, search_results_url = await collect_listing_urls(
                browser=browser,
                query=settings.query,
                location=settings.location,
                limit=settings.limit,
                scroll_pause=settings.scroll_pause,
                logger=logger,
                on_status=callbacks.on_status,
            )
            logger.info("Collected %s listing URLs from Google Maps.", len(listing_urls))
            if callbacks.on_urls_collected:
                callbacks.on_urls_collected(len(listing_urls))

            for index, listing_url in enumerate(listing_urls, start=1):
                if stop_event is not None and stop_event.is_set():
                    logger.warning("Stop requested. Ending after current lead.")
                    break

                if callbacks.on_status:
                    callbacks.on_status(f"Processing Google Maps lead {index} of {len(listing_urls)}")

                try:
                    lead = await retry_async(
                        lambda url=listing_url: extract_listing_details(browser, url, logger),
                        retries=settings.retries,
                        logger=logger,
                        description=f"Extract listing {listing_url}",
                    )
                    if filter_lead(lead, asdict(settings)):
                        leads.append(lead)
                        if callbacks.on_lead:
                            callbacks.on_lead(lead)
                        display_name = lead.get("Business Name") or "Unnamed listing"
                        display_address = lead.get("Address") or settings.location
                        message = f"OK Scraped : {display_name} - {display_address}"
                    else:
                        filtered_out += 1
                        display_name = lead.get("Business Name") or "Unnamed listing"
                        message = f"Filtered : {display_name}"

                    print_progress(index, len(listing_urls), message)
                    if callbacks.on_progress:
                        callbacks.on_progress(index, len(listing_urls), message)
                except CaptchaDetectedError:
                    logger.error("CAPTCHA blocked the session.")
                    raise
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    log_listing_failure(logger, listing_url, exc)
                    message = f"Skipped : Could not load listing (retry {settings.retries}/{settings.retries} failed)"
                    print_progress(index, len(listing_urls), message)
                    if callbacks.on_progress:
                        callbacks.on_progress(index, len(listing_urls), message)
                finally:
                    try:
                        if search_results_url:
                            await browser.go_back()
                    except Exception:  # noqa: BLE001
                        try:
                            await browser.goto(search_results_url)
                        except Exception:  # noqa: BLE001
                            pass

        if settings.source_mode == "universal_lead_finder" and not use_google_maps:
            if callbacks.on_status:
                callbacks.on_status("Searching websites and directories first...")
            website_rows = discover_web_and_directory_results(
                query=settings.query,
                location=settings.location,
                limit=settings.limit,
                include_keywords=settings.include_keywords,
                exclude_keywords=settings.exclude_keywords,
                user_agent=getattr(browser, "user_agent", "") if browser is not None else "",
            )
            logger.info("Collected %s website and directory rows.", len(website_rows))
            for row in website_rows:
                if callbacks.on_lead:
                    callbacks.on_lead(row)

        if settings.source_mode in {"social_search", "both", "facebook_public", "instagram_public", "linkedin_public", "all_public_sources", "universal_lead_finder"} and not (settings.source_mode == "universal_lead_finder" and len(website_rows) >= settings.limit and not use_google_maps):
            if callbacks.on_status:
                callbacks.on_status("Searching public social platforms...")
            social_rows = discover_social_profiles(
                query=settings.query,
                location=settings.location,
                limit=settings.limit,
                source_mode="all_public_sources" if settings.source_mode == "universal_lead_finder" else settings.source_mode,
                include_keywords=settings.include_keywords,
                exclude_keywords=settings.exclude_keywords,
                logger=logger,
                user_agent=getattr(browser, "user_agent", "") if browser is not None else "",
                on_cache_used=callbacks.on_public_search_state,
            )
            logger.info("Collected %s public social search rows.", len(social_rows))
            if settings.source_mode in {"social_search", "facebook_public", "instagram_public", "linkedin_public", "all_public_sources", "universal_lead_finder"}:
                for row in social_rows[: settings.limit]:
                    if callbacks.on_lead:
                        callbacks.on_lead(row)

        if settings.source_mode == "universal_lead_finder" and not website_rows:
            if callbacks.on_status:
                callbacks.on_status("Searching websites and directories...")
            website_rows = discover_web_and_directory_results(
                query=settings.query,
                location=settings.location,
                limit=settings.limit,
                include_keywords=settings.include_keywords,
                exclude_keywords=settings.exclude_keywords,
                user_agent=getattr(browser, "user_agent", "") if browser is not None else "",
            )
            for row in website_rows:
                row["Quality Score"] = row.get("Quality Score") or 35
            logger.info("Collected %s website and directory rows.", len(website_rows))
            for row in website_rows:
                if callbacks.on_lead:
                    callbacks.on_lead(row)

        if settings.source_mode == "universal_lead_finder":
            universal_rows = _build_universal_rows(settings.query, settings.location, leads, social_rows, website_rows)[: settings.limit]

    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received. Saving partial results.")
        metadata = _build_run_metadata(settings, leads, social_rows, universal_rows, website_rows, errors, filtered_out)
        export = export_workbook(leads, output_path, settings.append, metadata, logger, social_rows=social_rows, universal_rows=universal_rows)
        return ScrapeResult(130, export, leads, social_rows, universal_rows, filtered_out, errors, len(listing_urls))
    except CaptchaDetectedError:
        metadata = _build_run_metadata(settings, leads, social_rows, universal_rows, website_rows, errors, filtered_out)
        export = export_workbook(leads, output_path, settings.append, metadata, logger, social_rows=social_rows, universal_rows=universal_rows) if (leads or social_rows or universal_rows) else None
        return ScrapeResult(2, export, leads, social_rows, universal_rows, filtered_out, errors, len(listing_urls))
    finally:
        if browser is not None:
            await browser.close()

    metadata = _build_run_metadata(settings, leads, social_rows, universal_rows, website_rows, errors, filtered_out)
    export = export_workbook(leads, output_path, settings.append, metadata, logger, social_rows=social_rows, universal_rows=universal_rows)
    if export.total_saved < settings.limit:
        logger.warning(
            "Requested %s leads but only found %s real public results for this search.",
            settings.limit,
            export.total_saved,
        )
        if callbacks.on_status:
            callbacks.on_status(f"Found {export.total_saved} of {settings.limit}. Public sources were exhausted.")
    print_finish_banner(export.total_saved, export.output_path, export.duplicates_removed, errors)
    return ScrapeResult(0, export, leads, social_rows, universal_rows, filtered_out, errors, len(listing_urls))


async def run_scraper(args: argparse.Namespace) -> int:
    settings = namespace_to_settings(args)
    result = await run_scraper_job(settings)
    return result.exit_code


def launch_gui() -> None:
    from gui import launch_app

    launch_app()


def main() -> None:
    args = parse_args()
    if args.gui or not (args.query and args.location):
        launch_gui()
        return
    raise SystemExit(asyncio.run(run_scraper(args)))


if __name__ == "__main__":
    main()
