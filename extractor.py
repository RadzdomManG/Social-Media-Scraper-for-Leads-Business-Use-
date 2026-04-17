from __future__ import annotations

import re

from config import (
    DETAILS_ADDRESS_SELECTORS,
    DETAILS_CATEGORY_SELECTORS,
    DETAILS_HOURS_BUTTON_SELECTORS,
    DETAILS_HOURS_ROW_SELECTOR,
    DETAILS_NAME_SELECTORS,
    DETAILS_PHONE_SELECTORS,
    DETAILS_PLUS_CODE_SELECTORS,
    DETAILS_PRICE_SELECTORS,
    DETAILS_RATING_SELECTORS,
    DETAILS_REVIEWS_SELECTORS,
    DETAILS_STATUS_SELECTORS,
    DETAILS_WEBSITE_SELECTORS,
)
from utils import (
    build_social_media_category_value,
    classify_social_url,
    clean_label,
    choose_best_email,
    clean_extracted_text,
    extract_email_addresses,
    fetch_public_contact_data,
    now_string,
    parse_float,
    parse_int,
    sanitize_phone_number,
)


def _extract_price_token(text: str) -> str:
    match = re.search(r"([A-Z]*\s*)?([$]|PHP|USD|EUR|GBP|JPY|AUD|CAD|SGD|HKD|INR)(\s*\d+)?", text or "", re.I)
    if match:
        return re.sub(r"\s+", " ", match.group(0)).strip()
    fallback = re.search(r"([$]{1,4})", text or "")
    if fallback:
        return fallback.group(1)
    return ""


async def extract_listing_details(browser, listing_url: str, logger) -> dict[str, object]:
    await browser.goto(listing_url)
    await browser.handle_captcha_if_needed()
    await browser.wait_random(0.35, 0.8)

    data: dict[str, object] = {}
    page_text = ""

    try:
        data["Business Name"] = await browser.text_content(DETAILS_NAME_SELECTORS)
    except Exception:  # noqa: BLE001
        data["Business Name"] = ""

    try:
        category_text = await browser.text_content(DETAILS_CATEGORY_SELECTORS)
        data["Category"] = clean_label(category_text, ["Category"])
    except Exception:  # noqa: BLE001
        data["Category"] = ""

    try:
        address_text = await browser.text_content(DETAILS_ADDRESS_SELECTORS)
        data["Address"] = clean_label(address_text, ["Address"])
    except Exception:  # noqa: BLE001
        data["Address"] = ""

    try:
        phone_text = await browser.text_content(DETAILS_PHONE_SELECTORS)
        data["Phone Number"] = sanitize_phone_number(clean_label(phone_text, ["Phone"]))
    except Exception:  # noqa: BLE001
        data["Phone Number"] = ""

    try:
        page_text = await browser.page_text()
        direct_emails = extract_email_addresses(clean_extracted_text(page_text))
        data["Email"] = choose_best_email(direct_emails)
    except Exception:  # noqa: BLE001
        data["Email"] = ""

    try:
        data["Website"] = await browser.attribute_value(DETAILS_WEBSITE_SELECTORS, "href")
    except Exception:  # noqa: BLE001
        data["Website"] = ""
    original_website_url = str(data.get("Website", ""))

    try:
        platform, social_url = classify_social_url(original_website_url)
        if platform and social_url:
            data["Website"] = ""
    except Exception:  # noqa: BLE001
        pass

    try:
        data["Social Media Category"] = build_social_media_category_value(page_text, original_website_url)
    except Exception:  # noqa: BLE001
        data["Social Media Category"] = ""

    try:
        if data.get("Website") and not data.get("Email"):
            contact_data = fetch_public_contact_data(
                str(data["Website"]),
                user_agent=getattr(browser, "user_agent", ""),
            )
            if not data.get("Email"):
                data["Email"] = contact_data.get("email", "")
    except Exception:  # noqa: BLE001
        pass

    try:
        rating_text = await browser.text_content(DETAILS_RATING_SELECTORS)
        data["Rating"] = parse_float(rating_text)
    except Exception:  # noqa: BLE001
        data["Rating"] = ""

    try:
        reviews_text = await browser.text_content(DETAILS_REVIEWS_SELECTORS)
        data["Total Reviews"] = parse_int(reviews_text)
    except Exception:  # noqa: BLE001
        data["Total Reviews"] = ""

    try:
        status_text = await browser.text_content(DETAILS_STATUS_SELECTORS)
        data["Business Status"] = status_text.strip()
    except Exception:  # noqa: BLE001
        data["Business Status"] = ""

    try:
        hour_rows = await browser.all_text_contents(DETAILS_HOURS_ROW_SELECTOR)
        if hour_rows:
            data["Opening Hours"] = " | ".join(hour_rows)
        else:
            hours_button = await browser.attribute_value(DETAILS_HOURS_BUTTON_SELECTORS, "aria-label")
            data["Opening Hours"] = clean_label(hours_button, ["Hours"])
    except Exception:  # noqa: BLE001
        data["Opening Hours"] = ""

    try:
        price_text = await browser.text_content(DETAILS_PRICE_SELECTORS)
        data["Price Range"] = _extract_price_token(price_text)
    except Exception:  # noqa: BLE001
        data["Price Range"] = ""

    try:
        plus_code_text = await browser.text_content(DETAILS_PLUS_CODE_SELECTORS)
        data["Plus Code"] = clean_label(plus_code_text, ["Plus code"])
    except Exception:  # noqa: BLE001
        data["Plus Code"] = ""

    try:
        data["Google Maps URL"] = await browser.current_url()
    except Exception:  # noqa: BLE001
        data["Google Maps URL"] = listing_url

    try:
        data["Date Scraped"] = now_string()
    except Exception:  # noqa: BLE001
        data["Date Scraped"] = ""

    try:
        data["Name"] = ""
    except Exception:  # noqa: BLE001
        data["Name"] = ""

    try:
        data["Company"] = data.get("Business Name", "")
    except Exception:  # noqa: BLE001
        data["Company"] = ""

    try:
        data["Phone number"] = data.get("Phone Number", "")
    except Exception:  # noqa: BLE001
        data["Phone number"] = ""

    if not data.get("Business Name"):
        logger.debug("Listing returned without business name: %s", listing_url)

    return data
