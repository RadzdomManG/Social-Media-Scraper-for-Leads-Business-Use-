from __future__ import annotations

import random
import re
from typing import Callable

from config import (
    END_OF_RESULTS_TEXT,
    LISTING_CARD_SELECTORS,
    RESULTS_PANEL_SELECTOR,
    RESULTS_PANEL_SELECTORS,
)


def _simplify_location_part(value: str) -> str:
    simplified = re.sub(
        r"\b(city|province|municipality|district|region|barangay|metro)\b",
        "",
        value,
        flags=re.I,
    )
    simplified = re.sub(r"\s+", " ", simplified).strip(" ,")
    return simplified or value.strip()


def _build_location_expansions(location: str) -> list[str]:
    raw_parts = [part.strip() for part in location.split(",") if part.strip()]
    if not raw_parts:
        return []

    expansions: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        normalized = re.sub(r"\s+", " ", candidate).strip(" ,")
        if normalized and normalized.casefold() != location.strip().casefold() and normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            expansions.append(normalized)

    if raw_parts:
        simplified_first = _simplify_location_part(raw_parts[0])
        if simplified_first.casefold() != raw_parts[0].casefold():
            _add(", ".join([simplified_first, *raw_parts[1:]]))
            _add(simplified_first)

    for start_index in range(1, len(raw_parts)):
        _add(", ".join(raw_parts[start_index:]))

    if len(raw_parts) >= 2:
        _add(", ".join(raw_parts[-2:]))
    _add(raw_parts[-1])
    return expansions


async def _collect_for_search_text(
    browser,
    search_text: str,
    limit: int,
    scroll_pause: float,
    logger,
    listing_urls: list[str],
    seen_urls: set[str],
) -> str:
    await browser.open_maps_home()
    await browser.submit_search(search_text)

    search_results_url = await browser.current_url()
    stuck_attempts = 0
    scroll_target_selector = RESULTS_PANEL_SELECTOR

    try:
        scroll_target_selector = await browser.resolve_first_visible_selector(RESULTS_PANEL_SELECTORS)
    except Exception:  # noqa: BLE001
        logger.info("Falling back to default results panel selector for scrolling.")

    while len(listing_urls) < limit:
        await browser.handle_captcha_if_needed()

        hrefs = await browser.list_attributes(LISTING_CARD_SELECTORS, "href")
        normalized_hrefs = [
            href.split("&authuser=")[0]
            for href in hrefs
            if href and "/maps/place/" in href
        ]

        before = len(listing_urls)
        for href in normalized_hrefs:
            if href not in seen_urls:
                seen_urls.add(href)
                listing_urls.append(href)
                if len(listing_urls) >= limit:
                    break

        if len(listing_urls) >= limit:
            break

        page_text = await browser.page_text()
        if page_text and END_OF_RESULTS_TEXT.casefold() in page_text.casefold():
            logger.info("Google Maps reported end of results for '%s'.", search_text)
            break

        if len(listing_urls) == before:
            stuck_attempts += 1
        else:
            stuck_attempts = 0

        if stuck_attempts >= 3:
            logger.info("Results panel looks stuck. Clicking the feed and trying another scroll.")
            try:
                await browser.click_selector([scroll_target_selector])
            except Exception:  # noqa: BLE001
                await browser.scroll_page(random.randint(500, 900))
            stuck_attempts = 0

        try:
            await browser.scroll_selector(scroll_target_selector, random.randint(900, 1600))
        except Exception:  # noqa: BLE001
            await browser.scroll_page(random.randint(900, 1600))
        await browser.wait_random(scroll_pause * 0.8, scroll_pause * 1.25)

    return search_results_url


async def collect_listing_urls(
    browser,
    query: str,
    location: str,
    limit: int,
    scroll_pause: float,
    logger,
    on_status: Callable[[str], None] | None = None,
) -> tuple[list[str], str]:
    listing_urls: list[str] = []
    seen_urls: set[str] = set()
    primary_search_text = f"{query} {location}".strip()
    search_results_url = await _collect_for_search_text(
        browser=browser,
        search_text=primary_search_text,
        limit=limit,
        scroll_pause=scroll_pause,
        logger=logger,
        listing_urls=listing_urls,
        seen_urls=seen_urls,
    )

    if len(listing_urls) < limit:
        for expanded_location in _build_location_expansions(location):
            if len(listing_urls) >= limit:
                break
            expanded_search_text = f"{query} {expanded_location}".strip()
            logger.info(
                "Only found %s listings in '%s'. Expanding search to '%s'.",
                len(listing_urls),
                location,
                expanded_location,
            )
            if on_status:
                on_status(f"Only found {len(listing_urls)} results. Expanding area to {expanded_location}...")
            search_results_url = await _collect_for_search_text(
                browser=browser,
                search_text=expanded_search_text,
                limit=limit,
                scroll_pause=scroll_pause,
                logger=logger,
                listing_urls=listing_urls,
                seen_urls=seen_urls,
            )

    return listing_urls[:limit], search_results_url
