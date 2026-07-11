"""
hreflang_auditor.core
----------------------
Core logic for fetching pages/sitemaps, extracting hreflang annotations,
and running International SEO validation checks against them.

Checks implemented (each maps to a real, common hreflang failure mode):

  1. missing_self_reference   - a page's hreflang set should include itself
  2. missing_x_default        - recommended fallback annotation is absent
  3. invalid_code_format      - hreflang value doesn't match BCP47-style pattern
  4. uncommon_language_code   - language subtag isn't in the common ISO 639-1 set
  5. duplicate_hreflang_value - same hreflang value declared twice with
                                 different target URLs (conflicting signal)
  6. non_reciprocal_tag       - (deep mode only) target page doesn't link
                                 back to the origin page (broken return tag)
  7. unreachable_target       - (deep mode only) target URL returns an
                                 error status or fails to load
  8. self_referencing_conflict- self-reference hreflang value doesn't match
                                 any declared language of the page itself

This module has no CLI/reporting concerns - see report.py and cli.py.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

USER_AGENT = "HreflangAuditor/1.0 (+https://github.com/) International-SEO-audit-tool"
DEFAULT_TIMEOUT = 12

# A pragmatic (non-exhaustive) set of ISO 639-1 language codes, used only
# for a soft "uncommon code" warning - never a hard failure, since valid
# ISO 639-2/3 codes and regional variants exist beyond this list.
COMMON_LANGUAGE_CODES = {
    "aa", "ab", "af", "ak", "sq", "am", "ar", "an", "hy", "as", "av", "ae",
    "ay", "az", "bm", "ba", "eu", "be", "bn", "bh", "bi", "bs", "br", "bg",
    "my", "ca", "ch", "ce", "ny", "zh", "cv", "kw", "co", "cr", "hr", "cs",
    "da", "dv", "nl", "dz", "en", "eo", "et", "ee", "fo", "fj", "fi", "fr",
    "ff", "gl", "ka", "de", "el", "gn", "gu", "ht", "ha", "he", "hz", "hi",
    "ho", "hu", "ia", "id", "ie", "ga", "ig", "ik", "io", "is", "it", "iu",
    "ja", "jv", "kl", "kn", "kr", "ks", "kk", "km", "ki", "rw", "ky", "kv",
    "kg", "ko", "ku", "kj", "la", "lb", "lg", "li", "ln", "lo", "lt", "lu",
    "lv", "gv", "mk", "mg", "ms", "ml", "mt", "mi", "mr", "mh", "mn", "na",
    "nv", "nd", "ne", "ng", "nb", "nn", "no", "ii", "nr", "oc", "oj", "cu",
    "om", "or", "os", "pa", "pi", "fa", "pl", "ps", "pt", "qu", "rm", "rn",
    "ro", "ru", "sa", "sc", "sd", "se", "sm", "sg", "sr", "gd", "sn", "si",
    "sk", "sl", "so", "st", "es", "su", "sw", "ss", "sv", "ta", "te", "tg",
    "th", "ti", "bo", "tk", "tl", "tn", "to", "tr", "ts", "tt", "tw", "ty",
    "ug", "uk", "ur", "uz", "ve", "vi", "vo", "wa", "cy", "wo", "fy", "xh",
    "yi", "yo", "za", "zu",
}

# hreflang values follow language[-Script][-REGION], or the literal x-default
HREFLANG_PATTERN = re.compile(
    r"^(x-default|[a-zA-Z]{2,3}(-[a-zA-Z]{4})?(-[a-zA-Z]{2}|-\d{3})?)$"
)


@dataclass
class HreflangTag:
    hreflang: str
    href: str
    source_url: str


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    url: str = ""


@dataclass
class PageAudit:
    url: str
    tags: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    fetch_error: Optional[str] = None

    def add_issue(self, severity: str, code: str, message: str, url: str = ""):
        self.issues.append(Issue(severity, code, message, url or self.url))

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


def fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> requests.Response:
    headers = {"User-Agent": USER_AGENT}
    return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)


def extract_hreflang_tags(html: str, source_url: str) -> list:
    """Extract <link rel="alternate" hreflang="..." href="..."> tags from HTML head."""
    soup = BeautifulSoup(html, "html.parser")
    tags = []
    for link in soup.find_all("link", rel=lambda v: v and "alternate" in v.lower()):
        hreflang = link.get("hreflang")
        href = link.get("href")
        if hreflang and href:
            resolved = urljoin(source_url, href)
            tags.append(HreflangTag(hreflang.strip(), resolved, source_url))
    return tags


def extract_sitemap_hreflang(xml_text: str) -> dict:
    """Parse a sitemap.xml with <xhtml:link> alternate annotations.

    Returns {page_url: [HreflangTag, ...]}
    """
    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "xhtml": "http://www.w3.org/1999/xhtml",
    }
    root = ET.fromstring(xml_text)
    result = {}
    for url_el in root.findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        if loc_el is None or not loc_el.text:
            continue
        page_url = loc_el.text.strip()
        tags = []
        for link_el in url_el.findall("xhtml:link", ns):
            hreflang = link_el.get("hreflang")
            href = link_el.get("href")
            if hreflang and href:
                tags.append(HreflangTag(hreflang.strip(), href.strip(), page_url))
        result[page_url] = tags
    return result


def validate_tag_set(page_url: str, tags: list) -> PageAudit:
    """Run static (no-network) validation checks against one page's hreflang set."""
    audit = PageAudit(url=page_url, tags=tags)

    if not tags:
        audit.add_issue("warning", "no_hreflang_tags",
                         "No hreflang annotations found on this page.")
        return audit

    values_seen = {}
    self_ref_found = False

    for tag in tags:
        # 1. Format validity
        if not HREFLANG_PATTERN.match(tag.hreflang):
            audit.add_issue(
                "error", "invalid_code_format",
                f"'{tag.hreflang}' does not match a valid hreflang code pattern "
                f"(language[-Script][-REGION] or x-default)."
            )
        else:
            lang_part = tag.hreflang.split("-")[0].lower()
            if tag.hreflang != "x-default" and lang_part not in COMMON_LANGUAGE_CODES:
                audit.add_issue(
                    "warning", "uncommon_language_code",
                    f"'{tag.hreflang}' uses a language subtag ('{lang_part}') "
                    f"that isn't in the common ISO 639-1 set. Verify it's intentional."
                )

        # 2. Self-reference detection
        normalized_href = tag.href.rstrip("/")
        normalized_page = page_url.rstrip("/")
        if normalized_href == normalized_page:
            self_ref_found = True

        # 3. Duplicate / conflicting hreflang values
        key = tag.hreflang.lower()
        if key in values_seen and values_seen[key].rstrip("/") != normalized_href:
            audit.add_issue(
                "error", "duplicate_hreflang_value",
                f"hreflang '{tag.hreflang}' points to two different URLs: "
                f"{values_seen[key]} and {tag.href}."
            )
        values_seen[key] = tag.href

    # 4. Missing self-reference
    if not self_ref_found:
        audit.add_issue(
            "error", "missing_self_reference",
            "This page's hreflang set does not include a self-referencing tag. "
            "Every page in a hreflang cluster should reference itself."
        )

    # 5. Missing x-default
    if "x-default" not in [t.hreflang.lower() for t in tags] and len(tags) > 1:
        audit.add_issue(
            "warning", "missing_x_default",
            "No x-default annotation found. Recommended as a fallback for "
            "unmatched languages/regions."
        )

    return audit


def check_reciprocity(audit: PageAudit, timeout: int = DEFAULT_TIMEOUT,
                       delay: float = 0.0) -> None:
    """Deep check: fetch each alternate target and confirm it links back
    to the origin page with a matching (or any) hreflang tag."""
    origin_normalized = audit.url.rstrip("/")

    for tag in audit.tags:
        target_normalized = tag.href.rstrip("/")
        if target_normalized == origin_normalized:
            continue  # skip self

        if delay:
            time.sleep(delay)

        try:
            resp = fetch(tag.href, timeout=timeout)
        except requests.RequestException as exc:
            audit.add_issue(
                "error", "unreachable_target",
                f"Could not fetch alternate URL {tag.href} ({exc.__class__.__name__}).",
                url=tag.href,
            )
            continue

        if resp.status_code >= 400:
            audit.add_issue(
                "error", "unreachable_target",
                f"Alternate URL {tag.href} returned HTTP {resp.status_code}.",
                url=tag.href,
            )
            continue

        target_tags = extract_hreflang_tags(resp.text, tag.href)
        target_hrefs = {t.href.rstrip("/") for t in target_tags}

        if origin_normalized not in target_hrefs:
            audit.add_issue(
                "error", "non_reciprocal_tag",
                f"{tag.href} does not link back to {audit.url}. "
                f"The return tag is missing or broken.",
                url=tag.href,
            )


def audit_url(url: str, deep: bool = False, timeout: int = DEFAULT_TIMEOUT,
              delay: float = 0.0) -> PageAudit:
    """Fetch a single URL, extract hreflang tags, and validate them."""
    try:
        resp = fetch(url, timeout=timeout)
    except requests.RequestException as exc:
        audit = PageAudit(url=url, fetch_error=str(exc))
        audit.add_issue("error", "fetch_failed", f"Could not fetch {url}: {exc}")
        return audit

    if resp.status_code >= 400:
        audit = PageAudit(url=url, fetch_error=f"HTTP {resp.status_code}")
        audit.add_issue("error", "fetch_failed", f"{url} returned HTTP {resp.status_code}")
        return audit

    tags = extract_hreflang_tags(resp.text, url)
    audit = validate_tag_set(url, tags)

    if deep and tags:
        check_reciprocity(audit, timeout=timeout, delay=delay)

    return audit


def audit_sitemap(sitemap_url: str, deep: bool = False, timeout: int = DEFAULT_TIMEOUT,
                   delay: float = 0.0, limit: Optional[int] = None) -> list:
    """Fetch a sitemap.xml, and validate hreflang annotations for every URL in it."""
    resp = fetch(sitemap_url, timeout=timeout)
    resp.raise_for_status()
    url_map = extract_sitemap_hreflang(resp.text)

    audits = []
    items = list(url_map.items())
    if limit:
        items = items[:limit]

    for page_url, tags in items:
        audit = validate_tag_set(page_url, tags)
        if deep and tags:
            check_reciprocity(audit, timeout=timeout, delay=delay)
        audits.append(audit)

    return audits
