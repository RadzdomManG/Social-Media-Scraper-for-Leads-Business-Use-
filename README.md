# Radz Scraper for all Social Media

Radz Scraper for all Social Media is a local Google Maps lead collection tool built with async Playwright first and automatic Selenium `undetected-chromedriver` fallback. It accepts a query and location, scrolls Google Maps results, extracts listing details, applies lead filters, and exports a formatted Excel workbook with lead data and a scrape summary. It now includes a branded desktop launcher with settings, filters, run/stop controls, live logs, lead preview, and auto-save workbook naming based on your business query.

## Prerequisites

- Python 3.10 or newer
- `pip`
- `git`
- Google Chrome or Chromium installed locally

## Installation

```bash
git clone <your-repo-url>
cd google-maps-scraper
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Launch the desktop app:

```bash
python scraper.py
```

## Beginner Quick Start

If you are new, use the desktop app.

1. Run:

```bash
python scraper.py
```

2. In `Business Type`, enter what you want to find.
   Example: `dentists`

3. In `City / Area`, enter where to search.
   Example: `Cebu City, Philippines`

4. In `How Many Leads`, start with `10` or `25`.

5. Leave filters empty for your first test.

6. Keep `Show browser while scraping` enabled.

7. Click `Start Scraping`.

8. When the run finishes, click `Open Last Excel`.

If you do not type a custom Excel file name, the app automatically uses your business query.
Example: searching `Salon` saves as `Salon.xlsx`.

Your Excel file will contain:

- `Leads` for the styled working view
- `Upload Ready` for cleaner handoff/import use
- `Summary` for totals and scrape info

Optional environment file:

```bash
copy .env.example .env
```

On macOS/Linux use:

```bash
cp .env.example .env
```

## How To Run

Basic search:

```bash
python scraper.py --query "law firms" --location "Cebu City, Philippines"
```

Auto-name the workbook from the business query:

```bash
python scraper.py --query "Salon" --location "Cebu City, Philippines" --limit 50
```

Live visible test:

```bash
python scraper.py --query "Salon" --location "Cebu City, Philippines" --limit 3 --output "Salon_live_test.xlsx" --visible
```

Launch the desktop app explicitly:

```bash
python scraper.py --gui
```

Show the browser so you can watch the automation:

```bash
python scraper.py --query "dentists" --location "Manila, Philippines" --visible
```

Increase the result cap and write to a custom file:

```bash
python scraper.py --query "coffee shops" --location "Quezon City, Philippines" --limit 150 --output qc_coffee.xlsx
```

Append into an existing workbook and deduplicate automatically:

```bash
python scraper.py --query "real estate agents" --location "Davao City, Philippines" --append --output davao_agents.xlsx
```

Tune delay and retry settings for slower, more human-like runs:

```bash
python scraper.py --query "marketing agencies" --location "Makati, Philippines" --delay-min 2.0 --delay-max 5.0 --scroll-pause 3.0 --retries 4
```

Switch language and logging level:

```bash
python scraper.py --query "hardware stores" --location "Cebu Province, Philippines" --language en --log-level DEBUG
```

Run with filters:

```bash
python scraper.py --query "dentists" --location "Cebu City, Philippines" --min-rating 4.2 --min-reviews 20 --require-phone --require-website --only-open-now
```

## CLI Arguments

| Argument | Default | Description |
|---|---:|---|
| `--query` | required | Business type to search |
| `--location` | required | City, country, or area |
| `--limit` | `50` | Maximum number of listings to scrape |
| `--output` | query-based name such as `Salon.xlsx` | Output workbook name |
| `--visible` | `False` | Show browser window instead of headless |
| `--append` | `False` | Append to an existing workbook |
| `--delay-min` | `1.5` | Minimum delay between actions |
| `--delay-max` | `4.0` | Maximum delay between actions |
| `--scroll-pause` | `2.0` | Pause between results-panel scrolls |
| `--retries` | `3` | Retries per listing before skip |
| `--language` | `en` | Google Maps language |
| `--min-rating` | `0.0` | Keep only businesses at or above this rating |
| `--min-reviews` | `0` | Keep only businesses at or above this review count |
| `--require-phone` | `False` | Keep only businesses with a phone number |
| `--require-website` | `False` | Keep only businesses with a website |
| `--only-open-now` | `False` | Keep only businesses that appear open |
| `--category-include` | empty | Category must contain this text |
| `--category-exclude` | empty | Category must not contain this text |
| `--name-include` | empty | Business name must contain this text |
| `--gui` | `False` | Launch the desktop interface |
| `--log-level` | `INFO` | `DEBUG`, `INFO`, or `WARNING` |

## Output Workbook

The scraper writes a styled Excel file with three sheets.

### `Leads`

| Column | Meaning |
|---|---|
| `Lead Status` | Review dropdown such as `Pending`, `Approved`, `Declined`, `Follow Up`, `Contacted`, or `No Response` |
| `Business Name` | Listing title shown in Google Maps |
| `Category` | Business category label |
| `Address` | Full address pulled from the listing |
| `Phone Number` | Cleaned contact number |
| `Website` | Business website URL when available |
| `Rating` | Numeric star rating |
| `Total Reviews` | Review count |
| `Business Status` | Open/closed/temporary status text |
| `Opening Hours` | Weekly schedule when available |
| `Price Range` | Price band such as `₱₱` or `$$$` |
| `Plus Code` | Google Maps plus code |
| `Google Maps URL` | Direct listing URL |
| `Coordinates` | Latitude and longitude parsed from the URL |
| `Date Scraped` | Local scrape timestamp |

Formatting included:

- Dark navy header with white bold text
- Alternating row colors
- Status dropdown with color-coded review states
- Auto-fit column widths
- Frozen header row
- Excel filters
- Clickable hyperlinks for `Website` and `Google Maps URL`
- Numeric formatting for `Rating` and `Total Reviews`
- Styled summary and upload-ready tabs for easier review

### `Summary`

The summary sheet records:

- Search query
- Location
- Scrape date/time
- Total results found
- Lead row counts per sheet
- Duplicates removed
- Total errors
- Script version

### `Upload Ready`

This sheet is meant for easier sharing or uploading:

- Same column order every time
- Cleaned values
- Filters enabled
- Wrapped text for long addresses and hours
- Ready to sort, copy, or import into another tool

## Troubleshooting

1. `ModuleNotFoundError: playwright`
   Fix: run `pip install -r requirements.txt`.
2. Playwright launches but Chromium is missing
   Fix: run `python -m playwright install chromium`.
3. Selenium fallback fails on startup
   Fix: update local Chrome to the latest stable version and rerun.
4. The scraper stops on a CAPTCHA in headless mode
   Fix: rerun with `--visible`, solve the challenge manually, then continue.
5. The search opens but no results are collected
   Fix: use a more specific `--location` and reduce the query ambiguity.
6. Only a few results appear before stopping
   Fix: lower the speed with larger `--delay-min`, `--delay-max`, and `--scroll-pause` values.
7. The output file is open in Excel and cannot be overwritten
   Fix: close the workbook in Excel, then rerun the scraper.
8. `PermissionError` when saving
   Fix: save to a writable path or run the command from a directory you own.
9. Some fields are blank for valid businesses
   Fix: this is normal for listings that do not expose that field publicly in Google Maps.
10. The browser window appears then closes immediately
    Fix: review the terminal logs and rerun with `--log-level DEBUG` for more detail.
11. The scraper is too slow
    Fix: keep headless mode enabled, lower the result limit, and avoid large geographic areas.
12. Duplicate businesses remain after append mode
    Fix: verify the listings have a phone number or address; deduplication uses `Business Name + Phone Number` and `Business Name + Address`.

## Tips For Best Results

- Use query phrases that match how businesses label themselves, such as `family dentist`, `civil law firm`, or `coworking space`.
- Keep locations specific. `Cebu City, Philippines` is better than just `Philippines`.
- Start with limits between `25` and `100` when testing.
- Use `--visible` for the first run in a region so you can catch any challenge pages.
- Append multiple neighborhood runs into one workbook with `--append` to build larger datasets gradually.

## Live Progress

The terminal prints a startup banner, a per-listing status line, and a final summary. Failed listings are logged to `scraper_errors.log` and skipped instead of crashing the run. If you interrupt with `Ctrl+C`, the scraper exports whatever it has already collected before exiting.

## Desktop App

Running `python scraper.py` opens a local desktop app where you can:

- Fill in a simple step-by-step form
- Set business type, location, and how many leads you want
- Use optional filters only if needed
- Auto-save the Excel file using your business query, or enter a custom filename
- Choose the save folder
- Start the run with one `Start Scraping` button
- Stop safely with one click
- Watch a live activity log and lead preview
- Reuse saved settings automatically on the next launch
- Open a built-in quick tutorial from the app header
- Use the branded Radz Scraper dashboard interface

## Legal And Ethical Notice

Use this tool responsibly and only where you have the right to collect and process the data. Review Google Maps terms, local privacy law, and any downstream usage requirements before running large-scale scraping jobs. Respect website limits, avoid abusive automation patterns, and do not use the output for spam or unlawful contact.
