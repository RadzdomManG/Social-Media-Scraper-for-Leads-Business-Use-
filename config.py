from __future__ import annotations

GOOGLE_MAPS_URL = "https://www.google.com/maps"
DEFAULT_LIMIT = 50
MAX_LIMIT = 5000
DEFAULT_DELAY_MIN = 0.35
DEFAULT_DELAY_MAX = 0.9
DEFAULT_SCROLL_PAUSE = 0.6
DEFAULT_RETRIES = 3
DEFAULT_LANGUAGE = "en"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MIN_RATING = 0.0
DEFAULT_MIN_REVIEWS = 0
DEFAULT_VIEWPORT = {"width": 1366, "height": 768}
APP_TITLE = "Radz Scraper for all Social Media"
APP_SETTINGS_FILE = "app_settings.json"
DEFAULT_OUTPUT_DIR = ""
DEFAULT_SOURCE_MODE = "google_maps"

SOURCE_MODE_OPTIONS = [
    "google_maps",
    "social_search",
    "both",
    "universal_lead_finder",
    "facebook_public",
    "instagram_public",
    "linkedin_public",
    "all_public_sources",
]

SEARCH_INPUT_SELECTOR = "input[name='q']"
SEARCH_BUTTON_SELECTOR = "button#searchbox-searchbutton"
RESULTS_PANEL_SELECTOR = "div[role='feed']"
LISTING_CARD_SELECTOR = "a.hfpxzc"
RESULTS_PANEL_SELECTORS = [
    "div[role='feed']",
    "div[aria-label][role='feed']",
    "div[role='main'] div[role='feed']",
    "div[role='article']",
    "div.Nv2PK",
]
LISTING_CARD_SELECTORS = [
    "a.hfpxzc",
    "a[href*='/maps/place/']",
    "div[role='feed'] a[href*='/maps/place/']",
    "div[role='article'] a[href*='/maps/place/']",
]
END_OF_RESULTS_TEXT = "You've reached the end of the list"
CAPTCHA_TEXT_PATTERNS = [
    "unusual traffic",
    "not a robot",
    "captcha",
    "sorry, but your computer or network may be sending automated queries",
]

DETAILS_NAME_SELECTORS = [
    "h1.DUwDvf",
    "h1.fontHeadlineLarge",
]
DETAILS_CATEGORY_SELECTORS = [
    "button[jsaction*='pane.rating.category']",
    "button.DkEaL",
    "div.DkEaL",
]
DETAILS_ADDRESS_SELECTORS = [
    "button[data-item-id='address']",
    "button[data-item-id*='address']",
]
DETAILS_PHONE_SELECTORS = [
    "button[data-item-id^='phone:tel:']",
    "button[data-tooltip='Copy phone number']",
]
DETAILS_WEBSITE_SELECTORS = [
    "a[data-item-id='authority']",
    "a[data-tooltip='Open website']",
]
DETAILS_RATING_SELECTORS = [
    "div.F7nice span[aria-hidden='true']",
    "span.ceNzKf",
    "div[role='main'] span[aria-label*='stars']",
]
DETAILS_REVIEWS_SELECTORS = [
    "button[jsaction*='pane.reviewChart.moreReviews']",
    "button[aria-label*='reviews']",
    "div.F7nice span[aria-label*='reviews']",
]
DETAILS_STATUS_SELECTORS = [
    "span.ZDu9vd",
    "div.Io6YTe.fontBodyMedium.kR99db",
    "div.t39EBf span",
]
DETAILS_HOURS_BUTTON_SELECTORS = [
    "button[data-item-id='oh']",
    "div[aria-label*='Hours']",
]
DETAILS_HOURS_ROW_SELECTOR = "table.eK4R0e tr"
DETAILS_PRICE_SELECTORS = [
    "span[aria-label*='Price']",
    "span[aria-label*='price']",
    "div[role='main'] span",
]
DETAILS_PLUS_CODE_SELECTORS = [
    "button[data-item-id='oloc']",
    "button[data-item-id*='oloc']",
]

OUTPUT_COLUMNS = [
    "Lead Status",
    "Business / Company Name",
    "Category",
    "Email",
    "Phone Number",
    "Address",
    "Website",
    "Social Media Category",
    "Google Maps URL",
    "Plus Code",
]

EXCLUDED_EXPORT_SOCIAL_PLATFORMS = {
    "Facebook",
    "Instagram",
    "LinkedIn",
    "X",
    "Twitter",
    "TikTok",
    "Reddit",
}

EXCEL_HEADER_COLOR = "1F3864"
EXCEL_HEADER_FONT_COLOR = "FFFFFF"
EXCEL_ROW_ALT_COLOR = "EFF3F8"
EXCEL_ROW_BASE_COLOR = "FFFFFF"
SUMMARY_SHEET_NAME = "Summary"
LEADS_SHEET_NAME = "Leads"
UPLOAD_READY_SHEET_NAME = "Upload Ready"
SOCIAL_SEARCH_SHEET_NAME = "Social Search"
UNIVERSAL_FINDER_SHEET_NAME = "Universal Finder"

SOCIAL_SEARCH_PLATFORMS = {
    "Facebook": "site:facebook.com",
    "Instagram": "site:instagram.com",
    "LinkedIn": "site:linkedin.com",
    "X": "site:x.com",
    "Twitter": "site:twitter.com",
    "TikTok": "site:tiktok.com",
    "YouTube": "site:youtube.com",
    "Telegram": "site:t.me OR site:telegram.me",
    "Reddit": "site:reddit.com",
}

SOCIAL_SEARCH_COLUMNS = [
    "Platform",
    "Profile Name",
    "Company / Business",
    "Keyword Match",
    "Result Title",
    "Result Snippet",
    "Profile URL",
    "Search Query",
    "Location",
    "Date Scraped",
]

UNIVERSAL_FINDER_COLUMNS = [
    "Display Name",
    "Company / Business",
    "Source Type",
    "Source Platform",
    "Quality Score",
    "Position / Category",
    "Email",
    "Phone",
    "Website",
    "Profile URL",
    "Social media",
    "Address",
    "Business Status",
    "Rating",
    "Total Reviews",
    "Keyword Match",
    "Result Title",
    "Result Snippet",
    "Search Query",
    "Location",
    "Date Scraped",
]

LOG_FILE = "scraper_errors.log"
VERSION = "1.1.0"
SOCIAL_SEARCH_CACHE_FILE = "social_search_cache.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.141 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.6834.160 Safari/537.36 Edg/132.0.2957.140",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.265 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
]
