from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable

from config import EXCLUDED_EXPORT_SOCIAL_PLATFORMS, LOG_FILE, OUTPUT_COLUMNS

SOCIAL_PATTERNS: dict[str, str] = {
    "Facebook": r"https?://(?:www\.)?facebook\.com/[^\s\"'<>]+",
    "Instagram": r"https?://(?:www\.)?instagram\.com/[^\s\"'<>]+",
    "LinkedIn": r"https?://(?:www\.)?linkedin\.com/[^\s\"'<>]+",
    "X": r"https?://(?:www\.)?x\.com/[^\s\"'<>]+",
    "Twitter": r"https?://(?:www\.)?twitter\.com/[^\s\"'<>]+",
    "TikTok": r"https?://(?:www\.)?tiktok\.com/[^\s\"'<>]+",
    "YouTube": r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s\"'<>]+",
    "WhatsApp": r"https?://(?:wa\.me|api\.whatsapp\.com)/[^\s\"'<>]+",
    "Telegram": r"https?://(?:t\.me|telegram\.me)/[^\s\"'<>]+",
    "Viber": r"https?://(?:invite\.viber\.com|vb\.me|viber\.com)/[^\s\"'<>]+",
}

SOCIAL_HOST_HINTS: dict[str, str] = {
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn",
    "x.com": "X",
    "twitter.com": "Twitter",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "wa.me": "WhatsApp",
    "api.whatsapp.com": "WhatsApp",
    "t.me": "Telegram",
    "telegram.me": "Telegram",
    "invite.viber.com": "Viber",
    "vb.me": "Viber",
    "viber.com": "Viber",
}


class CaptchaDetectedError(Exception):
    """Raised when Google blocks the session and manual solving is not possible."""


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("google_maps_scraper")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


async def random_delay(delay_min: float, delay_max: float) -> None:
    await asyncio.sleep(random.uniform(delay_min, delay_max))


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_phone_number(value: str) -> str:
    cleaned = re.sub(r"(?<!^)\+", "", value or "")
    cleaned = re.sub(r"[^\d+\-\s()]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_float(value: str) -> float | str:
    match = re.search(r"(\d+(?:\.\d+)?)", value.replace(",", "."))
    if not match:
        return ""
    try:
        return float(match.group(1))
    except ValueError:
        return ""


def parse_int(value: str) -> int | str:
    match = re.search(r"(\d[\d,\.]*)", value or "")
    if not match:
        return ""
    digits = re.sub(r"[^\d]", "", match.group(1))
    if not digits:
        return ""
    try:
        return int(digits)
    except ValueError:
        return ""


def clean_label(value: str, labels: Iterable[str]) -> str:
    result = value or ""
    for label in labels:
        result = re.sub(rf"^{re.escape(label)}\s*:?\s*", "", result, flags=re.I)
    return re.sub(r"\s+", " ", result).strip()


def clean_extracted_text(value: str) -> str:
    text = value or ""
    text = re.sub(r"[\uE000-\uF8FF]", " ", text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_email_addresses(text: str) -> list[str]:
    if not text:
        return []
    matches = re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, flags=re.I)
    normalized: list[str] = []
    seen: set[str] = set()
    for match in matches:
        email = match.strip(".,;:()[]{}<>\"'").lower()
        if email and email not in seen:
            seen.add(email)
            normalized.append(email)
    return normalized


def choose_best_email(emails: list[str], domain: str = "") -> str:
    if not emails:
        return ""
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    preferred = [email for email in emails if domain and email.endswith(f"@{domain}")]
    if preferred:
        return preferred[0]
    return emails[0]


def extract_social_links(text: str) -> list[str]:
    return list(extract_social_profiles(text).values())


def extract_social_profiles(text: str) -> dict[str, str]:
    if not text:
        return {}
    values: list[str] = []
    seen: set[str] = set()
    profiles: dict[str, str] = {}
    for platform, pattern in SOCIAL_PATTERNS.items():
        for match in re.findall(pattern, text, flags=re.I):
            normalized = match.strip(".,;:()[]{}<>\"'")
            if normalized and normalized not in seen:
                seen.add(normalized)
                values.append(normalized)
                profiles.setdefault(platform, normalized)
    return profiles


def filter_export_social_profiles(profiles: dict[str, str]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for platform, url in profiles.items():
        if platform in EXCLUDED_EXPORT_SOCIAL_PLATFORMS:
            continue
        filtered[platform] = url
    return filtered


def build_social_media_value(profiles: dict[str, str]) -> str:
    return " | ".join(filter_export_social_profiles(profiles).values())


def filter_social_media_text(value: str) -> str:
    filtered_links: list[str] = []
    for link in extract_social_links(value):
        platform, normalized_url = classify_social_url(link)
        if platform and platform in EXCLUDED_EXPORT_SOCIAL_PLATFORMS:
            continue
        if normalized_url and normalized_url not in filtered_links:
            filtered_links.append(normalized_url)
    return " | ".join(filtered_links)


def build_social_media_category_value(page_text: str = "", website_url: str = "") -> str:
    social_links: list[str] = []
    if page_text:
        for url in filter_export_social_profiles(extract_social_profiles(page_text)).values():
            if url not in social_links:
                social_links.append(url)
    if website_url:
        platform, normalized_url = classify_social_url(website_url)
        if platform and normalized_url not in social_links:
            social_links.append(normalized_url)
    return " | ".join(social_links)


def classify_social_url(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    try:
        host = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return "", ""
    for hint, platform in SOCIAL_HOST_HINTS.items():
        if host == hint or host.endswith(f".{hint}"):
            return platform, url
    return "", ""


def fetch_public_contact_data(website_url: str, user_agent: str = "") -> dict[str, Any]:
    if not website_url:
        return {"email": "", "social_media": "", "profiles": {}}

    platform, platform_url = classify_social_url(website_url)
    if platform:
        profiles = filter_export_social_profiles({platform: platform_url})
        return {"email": "", "social_media": build_social_media_value(profiles), "profiles": profiles}

    headers = {
        "User-Agent": user_agent
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    }
    visited: set[str] = set()
    candidates = [website_url]

    try:
        parsed = urllib.parse.urlparse(website_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        candidates.extend(
            [
                urllib.parse.urljoin(base, "/contact"),
                urllib.parse.urljoin(base, "/contact-us"),
                urllib.parse.urljoin(base, "/about"),
            ]
        )
        domain = parsed.netloc
    except Exception:
        domain = ""

    social_values: list[str] = []
    social_profiles: dict[str, str] = {}

    for candidate in candidates[:4]:
        if not candidate or candidate in visited:
            continue
        visited.add(candidate)
        request = urllib.request.Request(candidate, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    continue
                body = response.read(400000).decode("utf-8", errors="ignore")
                emails = extract_email_addresses(body)
                for platform, social_url in extract_social_profiles(body).items():
                    social_profiles.setdefault(platform, social_url)
                    if social_url not in social_values:
                        social_values.append(social_url)
                best_email = choose_best_email(emails, domain=domain)
                filtered_profiles = filter_export_social_profiles(social_profiles)
                if best_email:
                    return {
                        "email": best_email,
                        "social_media": build_social_media_value(filtered_profiles),
                        "profiles": filtered_profiles,
                    }
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        except Exception:
            continue
    filtered_profiles = filter_export_social_profiles(social_profiles)
    return {"email": "", "social_media": build_social_media_value(filtered_profiles), "profiles": filtered_profiles}


def fetch_public_website_email(website_url: str, user_agent: str = "") -> str:
    return str(fetch_public_contact_data(website_url, user_agent=user_agent).get("email", ""))


def parse_coordinates_from_url(url: str) -> str:
    url = url or ""
    patterns = [
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f"{match.group(1)}, {match.group(2)}"
    return ""


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def deduplicate_leads(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen_primary: set[tuple[str, str]] = set()
    seen_secondary: set[tuple[str, str]] = set()
    unique_rows: list[dict[str, Any]] = []
    removed = 0

    for row in rows:
        name = normalize_text(str(row.get("Business Name", "")))
        phone = normalize_text(str(row.get("Phone Number", "")))
        address = normalize_text(str(row.get("Address", "")))
        primary_key = (name, phone)
        secondary_key = (name, address)

        duplicate = False
        if name and phone and primary_key in seen_primary:
            duplicate = True
        if not duplicate and name and address and secondary_key in seen_secondary:
            duplicate = True

        if duplicate:
            removed += 1
            continue

        if name and phone:
            seen_primary.add(primary_key)
        if name and address:
            seen_secondary.add(secondary_key)

        normalized_row = {
            "Lead Status": row.get("Lead Status", ""),
            "Business / Company Name": row.get("Business / Company Name") or row.get("Business Name", "") or row.get("Company", ""),
            "Category": row.get("Category", ""),
            "Email": row.get("Email", ""),
            "Phone Number": row.get("Phone Number", "") or row.get("Phone number", ""),
            "Address": row.get("Address", ""),
            "Website": row.get("Website", ""),
            "Social Media Category": row.get("Social Media Category", ""),
            "Google Maps URL": row.get("Google Maps URL", ""),
            "Plus Code": row.get("Plus Code", ""),
        }
        unique_rows.append(normalized_row)

    return unique_rows, removed


async def retry_async(
    operation: Callable[[], Awaitable[Any]],
    retries: int,
    logger: logging.Logger,
    description: str,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await operation()
        except CaptchaDetectedError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "%s failed on attempt %s/%s: %s",
                description,
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                await asyncio.sleep(2**attempt)
    if last_error:
        raise last_error
    raise RuntimeError(f"{description} failed without an exception")


def log_listing_failure(logger: logging.Logger, listing_url: str, error: Exception) -> None:
    logger.error("Listing failed after retries | url=%s | error=%s", listing_url, error)


def ensure_parent_dir(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _format_query_filename(query: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", query or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    parts = []
    for token in cleaned.split(" "):
        parts.append(token if token.isupper() else token.capitalize())
    return " ".join(parts)


def build_default_output_filename(query: str = "") -> str:
    query_name = _format_query_filename(query)
    if query_name:
        return f"{query_name}.xlsx"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"leads_{timestamp}.xlsx"


def sanitize_output_filename(filename: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", filename.strip())
    if not cleaned:
        return build_default_output_filename("")
    if not cleaned.lower().endswith(".xlsx"):
        cleaned = f"{cleaned}.xlsx"
    return cleaned


def lead_matches_keyword(value: Any, keyword: str) -> bool:
    if not keyword.strip():
        return True
    return normalize_text(keyword) in normalize_text(str(value))


def filter_lead(lead: dict[str, Any], settings: dict[str, Any]) -> bool:
    rating = lead.get("Rating", "")
    reviews = lead.get("Total Reviews", "")
    status = normalize_text(str(lead.get("Business Status", "")))
    category = str(lead.get("Category", ""))
    name = str(lead.get("Business Name", ""))

    min_rating = float(settings.get("min_rating", 0) or 0)
    min_reviews = int(settings.get("min_reviews", 0) or 0)
    website_mode = str(settings.get("website_mode", "both") or "both").strip().casefold()
    has_website = bool(str(lead.get("Website", "")).strip())

    if rating == "" and min_rating > 0:
        return False
    if isinstance(rating, (int, float)) and float(rating) < min_rating:
        return False
    if reviews == "" and min_reviews > 0:
        return False
    if isinstance(reviews, int) and reviews < min_reviews:
        return False
    if settings.get("require_phone") and not str(lead.get("Phone Number", "")).strip():
        return False
    if settings.get("require_website") and not str(lead.get("Website", "")).strip():
        return False
    if website_mode == "with_website" and not has_website:
        return False
    if website_mode == "without_website" and has_website:
        return False
    if settings.get("only_open_now") and "open" not in status:
        return False
    if settings.get("category_include") and not lead_matches_keyword(category, str(settings["category_include"])):
        return False
    if settings.get("category_exclude") and lead_matches_keyword(category, str(settings["category_exclude"])):
        return False
    if settings.get("name_include") and not lead_matches_keyword(name, str(settings["name_include"])):
        return False
    return True


def save_json_file(path: str, payload: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def load_json_file(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def print_start_banner(query: str, location: str, limit: int, output: str) -> None:
    line = "=" * 44
    safe_print(line)
    safe_print(" Radz Scraper for all Social Media - Starting...")
    safe_print(line)
    safe_print(f" Query    : {query}")
    safe_print(f" Location : {location}")
    safe_print(f" Limit    : {limit}")
    safe_print(f" Output   : {output}")
    safe_print(line)


def print_progress(index: int, limit: int, message: str) -> None:
    safe_print(f"[{index}/{limit}]  {message}")


def print_finish_banner(saved: int, output: str, duplicates: int, errors: int) -> None:
    line = "=" * 44
    safe_print(line)
    safe_print(f" Done! {saved} leads saved to {output}")
    safe_print(f" Duplicates removed : {duplicates}")
    safe_print(f" Errors logged      : {errors} (see {LOG_FILE})")
    safe_print(line)


def safe_print(text: str) -> None:
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    sanitized = clean_extracted_text(str(text))
    stream.write(sanitized.encode(encoding, errors="replace").decode(encoding, errors="replace") + "\n")
    stream.flush()
