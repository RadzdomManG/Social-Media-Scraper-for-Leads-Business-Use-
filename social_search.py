from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import SOCIAL_SEARCH_CACHE_FILE, SOCIAL_SEARCH_COLUMNS
from utils import now_string

SOURCE_MODE_TO_PLATFORMS = {
    "social_search": ["Reddit", "YouTube", "Facebook", "Instagram", "LinkedIn", "TikTok", "Telegram"],
    "all_public_sources": ["Reddit", "YouTube", "Facebook", "Instagram", "LinkedIn", "TikTok", "Telegram"],
    "universal_lead_finder": ["Reddit", "YouTube", "Facebook", "Instagram", "LinkedIn", "TikTok", "Telegram"],
    "facebook_public": ["Facebook"],
    "instagram_public": ["Instagram"],
    "linkedin_public": ["LinkedIn"],
}

PLATFORM_FALLBACKS = {
    "linkedin_public": ["Facebook", "Instagram", "Reddit", "YouTube", "TikTok", "Telegram"],
    "facebook_public": ["Instagram", "LinkedIn", "Reddit", "YouTube"],
    "instagram_public": ["Facebook", "LinkedIn", "YouTube", "Reddit"],
    "universal_lead_finder": ["Facebook", "Instagram", "LinkedIn", "Reddit", "YouTube", "TikTok", "Telegram"],
}

DIRECTORY_HINTS = {
    "yelp.com": "Yelp",
    "yellowpages.com": "Yellow Pages",
    "tripadvisor.com": "Tripadvisor",
    "mapquest.com": "MapQuest",
    "foursquare.com": "Foursquare",
    "angieslist.com": "Angi",
    "bbb.org": "BBB",
    "findglocal.com": "FindGlocal",
    "zaubee.com": "Zaubee",
    "loc8nearme.com": "Loc8NearMe",
}

EXCLUDED_SEARCH_HOSTS = {
    "google.com",
    "bing.com",
    "search.brave.com",
    "duckduckgo.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "t.me",
    "telegram.me",
}

CONTENT_SPAM_HOSTS = {
    "baidu.com",
    "zhidao.baidu.com",
    "zhihu.com",
    "zhuanlan.zhihu.com",
    "quora.com",
    "reddit.com",
    "medium.com",
    "substack.com",
    "pinterest.com",
    "wikipedia.org",
    "wikihow.com",
}

SPAM_PATH_HINTS = {
    "/question/",
    "/questions/",
    "/answer/",
    "/answers/",
    "/topic/",
    "/topics/",
    "/tag/",
    "/tags/",
    "/article/",
    "/articles/",
    "/magazine",
    "/latest",
}

POSITION_EXPANSIONS = {
    "teacher": ["educator", "professor", "instructor", "tutor"],
    "doctor": ["physician", "md", "medical doctor", "surgeon"],
    "dentist": ["dental surgeon", "orthodontist", "dental doctor"],
    "lawyer": ["attorney", "legal counsel", "law firm partner"],
    "video editor": ["editor", "post production editor", "content editor"],
    "virtual assistant": ["executive assistant", "remote assistant", "admin assistant", "va"],
    "business owner": ["founder", "entrepreneur", "ceo", "proprietor", "co-owner"],
    "yoga instructor": ["yoga teacher", "yoga coach", "fitness instructor"],
    "graphic designer": ["visual designer", "brand designer", "creative designer"],
    "real estate agent": ["realtor", "property consultant", "real estate broker"],
}


def _cache_key(
    query: str,
    location: str,
    source_mode: str,
    include_keywords: str,
    exclude_keywords: str,
) -> str:
    return " | ".join(
        [
            source_mode.strip().casefold(),
            query.strip().casefold(),
            location.strip().casefold(),
            include_keywords.strip().casefold(),
            exclude_keywords.strip().casefold(),
        ]
    )


def _load_cache() -> dict[str, list[dict[str, str]]]:
    if not os.path.exists(SOCIAL_SEARCH_CACHE_FILE):
        return {}
    try:
        with open(SOCIAL_SEARCH_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            normalized_cache: dict[str, list[dict[str, str]]] = {}
            for key, value in payload.items():
                if not isinstance(value, list):
                    continue
                normalized_rows = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    normalized = _normalize_cached_row(item)
                    if _cached_row_is_usable(normalized):
                        normalized_rows.append(normalized)
                normalized_cache[str(key)] = normalized_rows
            return normalized_cache
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _save_cache(cache: dict[str, list[dict[str, str]]]) -> None:
    try:
        with open(SOCIAL_SEARCH_CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        return


def _normalize_cached_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {column: row.get(column, "") for column in SOCIAL_SEARCH_COLUMNS}
    if not normalized.get("Profile Name") and not normalized.get("Company / Business"):
        profile_name, company_name = _extract_profile_and_company(
            normalized.get("Platform", ""),
            normalized.get("Result Title", ""),
            normalized.get("Profile URL", ""),
        )
        normalized["Profile Name"] = profile_name
        normalized["Company / Business"] = company_name
    return normalized


def _cached_row_is_usable(row: dict[str, str]) -> bool:
    url = row.get("Profile URL", "")
    title = row.get("Result Title", "")
    snippet = row.get("Result Snippet", "")
    location = row.get("Location", "")
    if _looks_like_spam_result(url, title, snippet):
        return False
    if row.get("Platform") not in {"Facebook", "Instagram", "LinkedIn", "Reddit", "YouTube", "TikTok", "Telegram"}:
        if not _looks_like_business_lead(url, title, snippet, location):
            return False
    return True


def _clean_html_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_html(url: str, user_agent: str = "") -> str:
    headers = {
        "User-Agent": user_agent
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    if last_error is not None:
        raise last_error
    return ""


def _bing_rss_search(query: str, user_agent: str = "") -> list[dict[str, str]]:
    encoded_query = urllib.parse.urlencode({"q": query, "format": "rss"})
    url = f"https://www.bing.com/search?{encoded_query}"
    headers = {
        "User-Agent": user_agent
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="ignore")

    root = ET.fromstring(body)
    results: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title = _clean_html_text(item.findtext("title", default=""))
        snippet = _clean_html_text(item.findtext("description", default=""))
        url_text = item.findtext("link", default="").strip()
        if not url_text:
            continue
        results.append({"title": title, "snippet": snippet, "url": url_text})
    return results


def _brave_html_search(query: str, user_agent: str = "") -> list[dict[str, str]]:
    url = "https://search.brave.com/search?q=" + urllib.parse.quote(query)
    body = _fetch_html(url, user_agent=user_agent)
    soup = BeautifulSoup(body, "html.parser")

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for wrapper in soup.select("div.result-wrapper"):
        anchor = wrapper.select_one("a[href]")
        if not anchor:
            continue
        url_text = (anchor.get("href") or "").strip()
        if not url_text or not url_text.startswith("http"):
            continue

        title_node = wrapper.select_one(".title")
        title = _clean_html_text(title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True))
        snippet_node = wrapper.select_one(".snippet-description, .description, .snippet")
        snippet = _clean_html_text(snippet_node.get_text(" ", strip=True) if snippet_node else "")

        if not title:
            title = url_text
        if url_text in seen_urls:
            continue
        seen_urls.add(url_text)
        results.append({"title": title, "snippet": snippet, "url": url_text})

    return results


def _split_keywords(value: str) -> list[str]:
    return [part.strip().casefold() for part in value.split(",") if part.strip()]


def _build_query_variants(query: str, include_keywords: str) -> list[str]:
    raw_query = query.strip()
    if not raw_query:
        return []

    variants: list[str] = [raw_query]
    lowered = raw_query.casefold()

    for key, expansions in POSITION_EXPANSIONS.items():
        if key in lowered:
            variants.extend(expansions)
            variants.extend([f"{raw_query} {expansion}" for expansion in expansions[:2]])

    variants.extend([keyword.strip() for keyword in include_keywords.split(",") if keyword.strip()])

    cleaned_variants: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        normalized = re.sub(r"\s+", " ", variant).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned_variants.append(normalized)
    return cleaned_variants


def _location_tokens(location: str) -> list[str]:
    stop_words = {
        "city",
        "province",
        "state",
        "region",
        "philippines",
        "central",
        "visayas",
        "metro",
        "the",
        "of",
    }
    tokens = re.findall(r"[a-z0-9]+", location.casefold())
    return [token for token in tokens if len(token) >= 4 and token not in stop_words]


def _match_keywords(title: str, snippet: str, include_keywords: str, exclude_keywords: str) -> tuple[bool, str]:
    haystack = f"{title} {snippet}".casefold()
    include = _split_keywords(include_keywords)
    exclude = _split_keywords(exclude_keywords)

    for blocked in exclude:
        if blocked in haystack:
            return False, ""

    if not include:
        return True, ""

    matches = [keyword for keyword in include if keyword in haystack]
    if matches:
        return True, ", ".join(matches)
    return False, ""


def _extract_profile_and_company(platform: str, title: str, url: str) -> tuple[str, str]:
    cleaned_title = re.sub(r"\s*\|\s*LinkedIn\s*$", "", title or "", flags=re.I).strip()
    cleaned_title = re.sub(r"\s*\|\s*Facebook\s*$", "", cleaned_title, flags=re.I).strip()
    cleaned_title = re.sub(r"\s*\|\s*Instagram\s*$", "", cleaned_title, flags=re.I).strip()
    cleaned_title = re.sub(r"\s*\|\s*TikTok\s*$", "", cleaned_title, flags=re.I).strip()
    cleaned_title = re.sub(r"\s*\|\s*YouTube\s*$", "", cleaned_title, flags=re.I).strip()

    profile_name = cleaned_title
    company_name = ""

    if platform == "LinkedIn":
        if "/company/" in url or "/school/" in url:
            company_name = cleaned_title
        elif " - " in cleaned_title:
            parts = [part.strip() for part in cleaned_title.split(" - ") if part.strip()]
            if parts:
                profile_name = parts[0]
            if len(parts) >= 3:
                company_name = parts[2]
            elif len(parts) >= 2:
                company_name = parts[1]
        return profile_name, company_name

    if " - " in cleaned_title:
        parts = [part.strip() for part in cleaned_title.split(" - ") if part.strip()]
        if parts:
            profile_name = parts[0]
        if len(parts) >= 2:
            company_name = parts[1]
    return profile_name, company_name


def _clean_host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _directory_label_from_url(url: str) -> tuple[str, str]:
    host = _clean_host(url)
    for hint, label in DIRECTORY_HINTS.items():
        if host == hint or host.endswith(f".{hint}"):
            return "Directory", label
    return "Website", host or "Website"


def _website_quality_score(row: dict[str, str], location: str) -> int:
    score = 35
    title = row.get("Result Title", "").casefold()
    snippet = row.get("Result Snippet", "").casefold()
    url = row.get("Profile URL", "").casefold()
    haystack = f"{title} {snippet} {url}"
    if any(token in haystack for token in _location_tokens(location)):
        score += 20
    if row.get("Keyword Match"):
        score += 15
    if row.get("Source Type") == "Directory":
        score += 10
    if row.get("Company / Business"):
        score += 10
    return min(score, 100)


def _looks_like_spam_result(url: str, title: str, snippet: str) -> bool:
    host = _clean_host(url)
    lowered_url = url.casefold()
    lowered_title = title.casefold()
    lowered_snippet = snippet.casefold()

    if any(host == blocked or host.endswith(f".{blocked}") for blocked in CONTENT_SPAM_HOSTS):
        return True
    if any(hint in lowered_url for hint in SPAM_PATH_HINTS):
        return True
    if "question" in lowered_title or "question" in lowered_snippet:
        return True
    if "what is " in lowered_title or "how to " in lowered_title:
        return True
    if re.search(r"[\u4e00-\u9fff]", title + snippet):
        return True
    return False


def _looks_like_business_lead(url: str, title: str, snippet: str, location: str) -> bool:
    host = _clean_host(url)
    lowered_url = url.casefold()
    lowered_title = title.casefold()
    lowered_snippet = snippet.casefold()
    haystack = f"{lowered_title} {lowered_snippet} {lowered_url}"
    location_match = any(token in haystack for token in _location_tokens(location))

    business_hints = (
        "contact",
        "about",
        "services",
        "team",
        "company",
        "official",
        "business",
        "owner",
        "founder",
        "ceo",
        "address",
        "phone",
        "email",
    )

    if any(host == blocked or host.endswith(f".{blocked}") for blocked in DIRECTORY_HINTS):
        return True
    if location_match and any(hint in haystack for hint in business_hints):
        return True
    if location_match and host and "." in host and len(host.split(".")[0]) > 2:
        return True
    return False


def _normalize_row(
    platform: str,
    query: str,
    location: str,
    keyword_match: str,
    title: str,
    snippet: str,
    url: str,
) -> dict[str, str]:
    profile_name, company_name = _extract_profile_and_company(platform, title, url)
    row = {
        "Platform": platform,
        "Profile Name": profile_name,
        "Company / Business": company_name,
        "Keyword Match": keyword_match,
        "Result Title": title,
        "Result Snippet": snippet,
        "Profile URL": url,
        "Search Query": query,
        "Location": location,
        "Date Scraped": now_string(),
    }
    return {column: row.get(column, "") for column in SOCIAL_SEARCH_COLUMNS}


def _discover_reddit(query: str, location: str, include_keywords: str, exclude_keywords: str, user_agent: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for query_variant in _build_query_variants(query, include_keywords)[:8]:
        search_query = f'site:reddit.com "{query_variant}" "{location}"'
        try:
            results = _bing_rss_search(search_query, user_agent=user_agent)
        except Exception:
            results = []
        for result in results:
            url = result.get("url", "")
            if "reddit.com" not in url.lower() or url in seen_urls:
                continue
            allowed, keyword_match = _match_keywords(result.get("title", ""), result.get("snippet", ""), include_keywords, exclude_keywords)
            if not allowed:
                continue
            seen_urls.add(url)
            rows.append(_normalize_row("Reddit", query, location, keyword_match, result.get("title", ""), result.get("snippet", ""), url))
    return rows


def _discover_youtube(query: str, location: str, include_keywords: str, exclude_keywords: str, user_agent: str = "") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for query_variant in _build_query_variants(query, include_keywords)[:8]:
        search_query = f'site:youtube.com "{query_variant}" "{location}"'
        try:
            results = _bing_rss_search(search_query, user_agent=user_agent)
        except Exception:
            results = []
        for result in results:
            url = result.get("url", "")
            lowered = url.lower()
            if ("youtube.com" not in lowered and "youtu.be" not in lowered) or url in seen_urls:
                continue
            allowed, keyword_match = _match_keywords(result.get("title", ""), result.get("snippet", ""), include_keywords, exclude_keywords)
            if not allowed:
                continue
            seen_urls.add(url)
            rows.append(_normalize_row("YouTube", query, location, keyword_match, result.get("title", ""), result.get("snippet", ""), url))
    return rows


def discover_web_and_directory_results(
    query: str,
    location: str,
    limit: int,
    include_keywords: str,
    exclude_keywords: str,
    user_agent: str = "",
) -> list[dict[str, str]]:
    query_variants = _build_query_variants(query, include_keywords)[:12]
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for query_variant in query_variants:
        search_queries = [
            f'"{query_variant}" "{location}"',
            f'"{query_variant}" "{location}" business',
            f'"{query_variant}" "{location}" directory',
            f'"{query_variant}" "{location}" service',
        ]
        search_results: list[dict[str, str]] = []
        for search_query in search_queries:
            try:
                search_results.extend(_bing_rss_search(search_query, user_agent=user_agent))
            except Exception:
                continue

        for result in search_results:
            url = result.get("url", "")
            if not url:
                continue
            host = _clean_host(url)
            if not host or any(host == blocked or host.endswith(f".{blocked}") for blocked in EXCLUDED_SEARCH_HOSTS):
                continue
            if _looks_like_spam_result(url, result.get("title", ""), result.get("snippet", "")):
                continue
            if not _looks_like_business_lead(url, result.get("title", ""), result.get("snippet", ""), location):
                continue
            if url in seen_urls:
                continue
            allowed, keyword_match = _match_keywords(
                result.get("title", ""),
                result.get("snippet", ""),
                include_keywords,
                exclude_keywords,
            )
            if not allowed:
                continue
            source_type, source_platform = _directory_label_from_url(url)
            profile_name, company_name = _extract_profile_and_company(source_platform, result.get("title", ""), url)
            row = {
                "Platform": source_platform,
                "Profile Name": profile_name,
                "Company / Business": company_name or profile_name,
                "Keyword Match": keyword_match,
                "Result Title": result.get("title", ""),
                "Result Snippet": result.get("snippet", ""),
                "Profile URL": url,
                "Search Query": query,
                "Location": location,
                "Date Scraped": now_string(),
                "Source Type": source_type,
                "Source Platform": source_platform,
            }
            row["Quality Score"] = _website_quality_score(row, location)
            seen_urls.add(url)
            rows.append(row)
            if len(rows) >= limit:
                return rows
    return rows


def _discover_public_profiles(
    query: str,
    location: str,
    platform: str,
    site_filters: list[str],
    include_keywords: str,
    exclude_keywords: str,
    limit: int,
    user_agent: str = "",
) -> list[dict[str, str]]:
    query_variants = _build_query_variants(query, include_keywords)
    keyword_terms = [keyword.strip() for keyword in include_keywords.split(",") if keyword.strip()]

    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    location_tokens = _location_tokens(location)

    for site_filter in site_filters:
        for query_variant in query_variants[:5]:
            search_results: list[dict[str, str]] = []
            search_terms = [query_variant, location.strip(), *keyword_terms[:3]]
            quoted_terms = " ".join(f'"{term}"' for term in search_terms if term)
            plain_terms = " ".join(term for term in search_terms if term)
            search_queries = [
                f"{site_filter} {quoted_terms}".strip(),
                f"{site_filter} {plain_terms}".strip(),
            ]
            for search_query in search_queries:
                try:
                    search_results = _brave_html_search(search_query, user_agent=user_agent)
                except Exception:
                    search_results = []
                if search_results:
                    break
                try:
                    search_results = _bing_rss_search(search_query, user_agent=user_agent)
                except Exception:
                    search_results = []
                if search_results:
                    break
            for result in search_results:
                url = result.get("url", "")
                if not url:
                    continue
                normalized_url = url.lower()
                if site_filter.replace("site:", "").split()[0].replace('"', "") not in normalized_url:
                    continue
                if normalized_url in seen_urls:
                    continue
                allowed, keyword_match = _match_keywords(
                    result.get("title", ""),
                    result.get("snippet", ""),
                    include_keywords,
                    exclude_keywords,
                )
                if not allowed:
                    continue
                seen_urls.add(normalized_url)
                rows.append(
                    _normalize_row(
                        platform,
                        query,
                        location,
                        keyword_match,
                        result.get("title", ""),
                        result.get("snippet", ""),
                        url,
                    )
                )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    if location_tokens:
        rows.sort(
            key=lambda candidate: 0
            if any(
                token in f'{candidate.get("Result Title", "")} {candidate.get("Result Snippet", "")} {candidate.get("Profile URL", "")}'.casefold()
                for token in location_tokens
            )
            else 1
        )
    return rows


def discover_social_profiles(
    query: str,
    location: str,
    limit: int,
    source_mode: str,
    include_keywords: str,
    exclude_keywords: str,
    logger: Any,
    user_agent: str = "",
    on_cache_used: Any | None = None,
) -> list[dict[str, str]]:
    cache_key = _cache_key(query, location, source_mode, include_keywords, exclude_keywords)
    cache = _load_cache()
    requested_platforms = SOURCE_MODE_TO_PLATFORMS.get(source_mode, SOURCE_MODE_TO_PLATFORMS["social_search"])
    collectors = {
        "Reddit": lambda: _discover_reddit(query, location, include_keywords, exclude_keywords, user_agent=user_agent),
        "YouTube": lambda: _discover_youtube(query, location, include_keywords, exclude_keywords, user_agent=user_agent),
        "Facebook": lambda: _discover_public_profiles(query, location, "Facebook", ["site:facebook.com"], include_keywords, exclude_keywords, limit, user_agent=user_agent),
        "Instagram": lambda: _discover_public_profiles(query, location, "Instagram", ["site:instagram.com"], include_keywords, exclude_keywords, limit, user_agent=user_agent),
        "LinkedIn": lambda: _discover_public_profiles(
            query,
            location,
            "LinkedIn",
            ["site:linkedin.com/in", "site:linkedin.com/company", "site:linkedin.com/school"],
            include_keywords,
            exclude_keywords,
            limit,
            user_agent=user_agent,
        ),
        "TikTok": lambda: _discover_public_profiles(query, location, "TikTok", ["site:tiktok.com"], include_keywords, exclude_keywords, limit, user_agent=user_agent),
        "Telegram": lambda: _discover_public_profiles(query, location, "Telegram", ["site:t.me"], include_keywords, exclude_keywords, limit, user_agent=user_agent),
    }

    platform_rows: dict[str, list[dict[str, str]]] = {}
    for platform in requested_platforms:
        collector = collectors[platform]
        try:
            rows = collector()
            platform_rows[platform] = rows
            logger.info("Collected %s public social rows for %s.", len(rows), platform)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Social search failed for %s: %s", platform, exc)
            platform_rows[platform] = []

    if not any(platform_rows.values()) and source_mode in PLATFORM_FALLBACKS:
        fallback_platforms = PLATFORM_FALLBACKS[source_mode]
        logger.info("No rows found for %s. Trying broader public-platform fallback.", source_mode)
        for platform in fallback_platforms:
            collector = collectors.get(platform)
            if collector is None:
                continue
            try:
                rows = collector()
                platform_rows[platform] = rows
                logger.info("Fallback collected %s public social rows for %s.", len(rows), platform)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallback social search failed for %s: %s", platform, exc)
                platform_rows[platform] = []

    combined: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    platform_names = list(platform_rows.keys())
    index = 0
    while len(combined) < limit:
        progressed = False
        for platform in platform_names:
            rows = platform_rows[platform]
            if index >= len(rows):
                continue
            candidate = rows[index]
            url = candidate.get("Profile URL", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            combined.append(candidate)
            progressed = True
            if len(combined) >= limit:
                break
        if not progressed:
            break
        index += 1
    if combined:
        if on_cache_used is not None:
            on_cache_used("Fresh public results")
        cache[cache_key] = combined
        _save_cache(cache)
        return combined

    cached_rows = cache.get(cache_key, [])
    if cached_rows:
        logger.info("Using %s cached public social rows for %s.", min(len(cached_rows), limit), source_mode)
        if on_cache_used is not None:
            on_cache_used("Using cached public results")
        return cached_rows[:limit]
    return combined
