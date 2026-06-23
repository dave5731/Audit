#!/usr/bin/env python3
"""
Standalone webpage SEO checks.

Usage:
    python codexTest/page_seo_checker.py https://example.com
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


SEARCH_ENGINE_META_NAMES = {
    "robots",
    "googlebot",
    "googlebot-news",
    "bingbot",
    "slurp",
    "duckduckbot",
    "baiduspider",
    "yandex",
    "yandexbot",
}

REQUEST_TIMEOUT = 15


class PageSEOParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1_texts: list[str] = []
        self.canonical_url = ""
        self.meta_description = ""
        self.description = ""
        self.noindex_sources: list[dict[str, str]] = []
        self.visible_text_parts: list[str] = []
        self.phone_numbers: list[str] = []
        self.address_parts: list[str] = []
        self.images_missing_alt: list[str] = []
        self.privacy_policy_urls: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._hidden_depth = 0
        self._hidden_tag_stack: list[str] = []
        self._current_h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): (value or "").strip() for name, value in attrs}
        tag = tag.lower()

        is_hidden_element = (
            "hidden" in attr_map
            or attr_map.get("aria-hidden", "").lower() == "true"
            or "display:none" in attr_map.get("style", "").lower().replace(" ", "")
            or "visibility:hidden" in attr_map.get("style", "").lower().replace(" ", "")
        )
        if tag in {"script", "style", "noscript", "template", "svg", "head"} or is_hidden_element:
            self._hidden_depth += 1
            self._hidden_tag_stack.append(tag)

        if tag == "title":
            self._in_title = True
            return

        if tag == "h1":
            self._in_h1 = True
            self._current_h1_parts = []
            return

        rel_values = attr_map.get("rel", "").lower().split()
        if tag == "link" and "canonical" in rel_values:
            self.canonical_url = attr_map.get("href", "")
            return

        if tag == "meta":
            self._handle_meta(attr_map)

        if tag == "a":
            href = attr_map.get("href", "")
            if href.lower().startswith("tel:"):
                self.phone_numbers.append(href[4:])
            if "privacy" in href.lower():
                self.privacy_policy_urls.append(href)

        itemprop = attr_map.get("itemprop", "").lower()
        if itemprop in {"streetaddress", "addresslocality", "addressregion", "postalcode"}:
            content = attr_map.get("content", "")
            if content:
                self.address_parts.append(content)

        if tag == "img" and not attr_map.get("alt", "").strip():
            image_url = (
                attr_map.get("src")
                or attr_map.get("data-src")
                or attr_map.get("data-lazy-src")
                or ""
            )
            self.images_missing_alt.append(image_url or "[image source missing]")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
            h1_text = " ".join("".join(self._current_h1_parts).split())
            if h1_text:
                self.h1_texts.append(h1_text)
            self._current_h1_parts = []

        if self._hidden_tag_stack and self._hidden_tag_stack[-1] == tag:
            self._hidden_tag_stack.pop()
            self._hidden_depth = max(0, self._hidden_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._in_h1:
            self._current_h1_parts.append(data)
        if self._hidden_depth == 0 and data.strip():
            self.visible_text_parts.append(data)

    def _handle_meta(self, attrs: dict[str, str]) -> None:
        content = attrs.get("content", "").strip()
        name = attrs.get("name", "").lower()
        prop = attrs.get("property", "").lower()

        if name == "description":
            self.meta_description = content
            self.description = self.description or content
        elif prop in {"og:description", "twitter:description"}:
            self.description = self.description or content

        if name in SEARCH_ENGINE_META_NAMES and has_noindex_directive(content):
            self.noindex_sources.append(
                {
                    "source": f"meta name={name}",
                    "directive": content,
                }
            )


def has_noindex_directive(value: str) -> bool:
    directives = [part for part in re.split(r"[\s,;:]+", value.lower()) if part]
    return "noindex" in directives or "none" in directives


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an http or https URL.")
    return url


def site_root(url: str, scheme: str | None = None) -> str:
    parsed = urlparse(url)
    if scheme is not None:
        parsed = parsed._replace(scheme=scheme)
    return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))


def url_with_scheme(url: str, scheme: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(scheme=scheme))


def fetch_url(url: str, timeout: int) -> tuple[str, dict[str, str], int, str]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
            )
        },
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        headers = {key.lower(): value for key, value in response.headers.items()}
        return body, headers, response.status, response.geturl()


def fetch_status(url: str, timeout: int) -> tuple[int | None, str, str]:
    try:
        _body, _headers, status_code, final_url = fetch_url(url, timeout)
        return status_code, final_url, ""
    except HTTPError as exc:
        return exc.code, exc.geturl(), f"{exc.code} {exc.reason}"
    except (URLError, TimeoutError) as exc:
        return None, url, str(exc)


def find_header_noindex(headers: dict[str, str]) -> list[dict[str, str]]:
    found = []
    x_robots = headers.get("x-robots-tag", "")
    if has_noindex_directive(x_robots):
        found.append({"source": "X-Robots-Tag header", "directive": x_robots})
    return found


def has_google_analytics(html: str) -> bool:
    patterns = [
        r"google-analytics\.com/analytics\.js",
        r"google-analytics\.com/ga\.js",
        r"googletagmanager\.com/gtag/js\?id=(?:G|UA|AW)-[A-Z0-9-]+",
        r"\bG-[A-Z0-9]{6,}\b",
        r"\bUA-\d+-\d+\b",
        r"gtag\(\s*['\"]config['\"]\s*,\s*['\"](?:G|UA|AW)-[A-Z0-9-]+['\"]",
        r"GoogleAnalyticsObject",
    ]
    return any(re.search(pattern, html, re.IGNORECASE) for pattern in patterns)


def visible_text(text_parts: list[str]) -> str:
    return " ".join(" ".join(text_parts).split())


def first_regex_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0).strip(" ,.;") if match else ""


def clean_phone_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return value.strip()


def contact_info_result(parser: PageSEOParser, url: str) -> dict[str, Any]:
    text = visible_text(parser.visible_text_parts)
    phone = clean_phone_number(parser.phone_numbers[0]) if parser.phone_numbers else ""
    phone = phone or first_regex_match(
        r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}",
        text,
    )
    address = " ".join(parser.address_parts).strip()
    address = address or first_regex_match(
        (
            r"\b\d{1,6}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,5}\s+"
            r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|"
            r"Drive|Dr\.?|Lane|Ln\.?|Court|Ct\.?|Place|Pl\.?|Way|Circle|"
            r"Cir\.?|Highway|Hwy\.?|Parkway|Pkwy\.?)\b[^\n,;]{0,80}"
        ),
        text,
    )
    privacy_url = parser.privacy_policy_urls[0] if parser.privacy_policy_urls else ""
    has_privacy_policy = bool(privacy_url) or "privacy policy" in text.lower()

    return {
        "phone": {
            "exists": bool(phone),
            "value": phone,
        },
        "address": {
            "exists": bool(address),
            "value": address,
        },
        "privacy_policy": {
            "exists": has_privacy_policy,
            "url": urljoin(url, privacy_url) if privacy_url else "",
        },
    }


def check_ssl(url: str, timeout: int) -> dict[str, Any]:
    https_url = url_with_scheme(url, "https")
    status_code, final_url, error = fetch_status(https_url, timeout)
    return {
        "checked_url": https_url,
        "has_ssl": status_code is not None,
        "status_code": status_code,
        "final_url": final_url,
        "error": error,
    }


def check_sitemap(url: str, timeout: int) -> dict[str, Any]:
    candidates = [
        urljoin(site_root(url, "https"), "sitemap.xml"),
        urljoin(site_root(url, "https"), "sitemap_index.xml"),
    ]

    checked = []
    for sitemap_url in candidates:
        status_code, final_url, error = fetch_status(sitemap_url, timeout)
        checked.append(
            {
                "url": sitemap_url,
                "status_code": status_code,
                "final_url": final_url,
                "error": error,
            }
        )
        if status_code is not None and 200 <= status_code < 400:
            return {"exists": True, "url": final_url, "checked": checked}

    return {"exists": False, "url": "", "checked": checked}


def check_llms_txt(url: str, timeout: int) -> dict[str, Any]:
    llms_url = urljoin(site_root(url, "https"), "llms.txt")
    status_code, final_url, error = fetch_status(llms_url, timeout)
    return {
        "exists": status_code is not None and 200 <= status_code < 400,
        "url": final_url if status_code is not None and 200 <= status_code < 400 else "",
        "checked_url": llms_url,
        "status_code": status_code,
        "final_url": final_url,
        "error": error,
    }


def analyze_html(html: str, headers: dict[str, str], url: str, status_code: int) -> dict[str, Any]:
    parser = PageSEOParser()
    parser.feed(html)

    parser.title = " ".join(parser.title.split())
    parser.noindex_sources.extend(find_header_noindex(headers))

    checks = {
        "title": bool(parser.title),
        "description": bool(parser.description),
        "canonical_url": bool(parser.canonical_url),
        "h1_tag": bool(parser.h1_texts),
        "meta_description_tag": bool(parser.meta_description),
    }

    return {
        "url": url,
        "status_code": status_code,
        "checks": checks,
        "noindex": {
            "is_noindex": bool(parser.noindex_sources),
            "sources": parser.noindex_sources,
        },
        "contact": contact_info_result(parser, url),
        "images_missing_alt": [
            {
                "url": (
                    urljoin(url, image_url)
                    if image_url != "[image source missing]"
                    else image_url
                ),
                "page_url": url,
            }
            for image_url in parser.images_missing_alt
        ],
        "google_analytics_present": has_google_analytics(html),
        "values": {
            "title": parser.title,
            "description": parser.description,
            "canonical_url": parser.canonical_url,
            "h1_tags": parser.h1_texts,
            "meta_description": parser.meta_description,
        },
    }


def run_audit(url: str, timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    normalized_url = normalize_url(url)
    html, headers, status_code, final_url = fetch_url(normalized_url, timeout)
    result = analyze_html(html, headers, final_url, status_code)
    result["ssl"] = check_ssl(normalized_url, timeout)
    result["sitemap"] = check_sitemap(normalized_url, timeout)
    result["llms_txt"] = check_llms_txt(normalized_url, timeout)
    return result


def print_summary(result: dict[str, Any]) -> None:
    print(f"URL: {result['url']}")
    print(f"HTTP status: {result['status_code']}")
    print()
    print("Required checks:")
    for label, present in result["checks"].items():
        print(f"  {label}: {'YES' if present else 'NO'}")
    print(f"  ssl: {'YES' if result['ssl']['has_ssl'] else 'NO'}")
    print(f"  sitemap_exists: {'YES' if result['sitemap']['exists'] else 'NO'}")
    print(f"  llms_txt_exists: {'YES' if result['llms_txt']['exists'] else 'NO'}")
    print(f"  phone_exists: {'YES' if result['contact']['phone']['exists'] else 'NO'}")
    print(f"  address_exists: {'YES' if result['contact']['address']['exists'] else 'NO'}")
    print(
        "  privacy_policy_exists: "
        f"{'YES' if result['contact']['privacy_policy']['exists'] else 'NO'}"
    )
    print(
        "  google_analytics_present: "
        f"{'YES' if result['google_analytics_present'] else 'NO'}"
    )
    print()
    print(f"SSL checked URL: {result['ssl']['checked_url']}")
    print(f"SSL final URL: {result['ssl']['final_url']}")
    if result["ssl"]["error"]:
        print(f"SSL error: {result['ssl']['error']}")
    print()
    print(f"Sitemap URL: {result['sitemap']['url'] or 'Not found'}")
    print(f"LLMs.txt URL: {result['llms_txt']['url'] or 'Not found'}")
    print(f"Phone: {result['contact']['phone']['value'] or 'Not found'}")
    print(f"Address: {result['contact']['address']['value'] or 'Not found'}")
    print(
        "Privacy policy URL: "
        f"{result['contact']['privacy_policy']['url'] or 'Not found'}"
    )
    print()
    print(f"Noindex: {'YES' if result['noindex']['is_noindex'] else 'NO'}")
    for source in result["noindex"]["sources"]:
        print(f"  {source['source']}: {source['directive']}")
    print()
    print(f"Images missing alt text: {len(result['images_missing_alt'])}")
    for image in result["images_missing_alt"]:
        print(f"  {image['url']} found on {image['page_url']}")


def main() -> int:

    try:
        result = run_audit("https://www.nauticalagency.com", 30)
    except ValueError as exc:
        print(f"Invalid URL: {exc}", file=sys.stderr)
        return 2
    except HTTPError as exc:
        print(f"HTTP error while fetching URL: {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Network error while fetching URL: {exc.reason}", file=sys.stderr)
        return 1
    except TimeoutError:
        print("Network error while fetching URL: request timed out", file=sys.stderr)
        return 1

    print_summary(result)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
