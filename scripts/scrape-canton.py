from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = "https://www.cantonecosystem.com/"
PAGE_PARAM = "23102b98_page"
MAX_PAGES = 50
REQUEST_TIMEOUT = 30
PLAYWRIGHT_TIMEOUT_MS = 90000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 CantonScraper/1.0"
)

# Paths assume the script lives in /scripts inside your repo.
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "api" / "ecosystem"
RAW_DIR = DATA_DIR / "raw_pages"
LOGO_DIR = REPO_ROOT / "assets" / "ecosystem" / "logos"

RAW_JSON_PATH = DATA_DIR / "canton-entities-raw.json"
CLEAN_JSON_PATH = DATA_DIR / "canton-entities.json"
CSV_PATH = DATA_DIR / "canton-entities.csv"
LOG_PATH = DATA_DIR / "scrape-log.json"


KNOWN_ROLES = {
    "Apps (All)",
    "Apps (Featured)",
    "Canton Foundation Member",
    "Financial Institutions",
    "Industry Bodies",
    "Market Infrastructure",
    "Service Provider",
    "Super Validator",
    "Validator",
}

KNOWN_NETWORK_UTILITIES = {
    "Compliance",
    "Custody",
    "Data & Analytics",
    "Developer Tools",
    "Exchanges",
    "Financing",
    "Forensics & Security",
    "Interoperability",
    "Liquidity",
    "NaaS",
    "Payments",
    "Stablecoins",
    "Tokenized Assets",
    "Wallets",
}


@dataclass
class RawEntity:
    name: str
    slug: str
    detail_url: str | None = None
    external_website: str | None = None
    logo_url: str | None = None
    logo_local_path: str | None = None
    short_description: str | None = None
    long_description: str | None = None
    raw_text: str | None = None
    roles: list[str] = field(default_factory=list)
    network_utilities: list[str] = field(default_factory=list)
    source_page_url: str | None = None
    page_number: int | None = None
    extraction_method: str | None = None


@dataclass
class ScrapeLog:
    started_at: float
    finished_at: float | None = None
    pages_scraped: int = 0
    rows_before_dedupe: int = 0
    rows_after_dedupe: int = 0
    logos_downloaded: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOGO_DIR.mkdir(parents=True, exist_ok=True)


def page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_URL
    return f"{BASE_URL}?{PAGE_PARAM}={page_number}"


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def normalize_name(text: str) -> str:
    text = normalize_whitespace(text) or ""
    return text.casefold()


def safe_filename(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return stem[:120] or "file"


def absolutize(base: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base, href)


def first(iterable: Iterable[Tag], default=None):
    for item in iterable:
        return item
    return default


def unique_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def text_from_tag(tag: Tag | None) -> str | None:
    if not tag:
        return None
    return normalize_whitespace(tag.get_text(" ", strip=True))


def find_best_image(tag: Tag | None, page_base_url: str) -> str | None:
    if not tag:
        return None

    img = tag.find("img") if isinstance(tag, Tag) else None
    if not img:
        return None

    for attr in ("src", "data-src", "data-wf-src"):
        candidate = img.get(attr)
        if candidate:
            return absolutize(page_base_url, candidate)

    srcset = img.get("srcset")
    if srcset:
        first_candidate = srcset.split(",")[0].strip().split(" ")[0]
        if first_candidate:
            return absolutize(page_base_url, first_candidate)

    return None


def guess_tags_from_text_blocks(texts: list[str]) -> tuple[list[str], list[str]]:
    roles: list[str] = []
    utilities: list[str] = []

    for text in texts:
        if text in KNOWN_ROLES:
            roles.append(text)
        if text in KNOWN_NETWORK_UTILITIES:
            utilities.append(text)

    return unique_keep_order(roles), unique_keep_order(utilities)


def harvest_links_for_details(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Builds a preliminary entity list from cards/anchors on a listing page.
    This is intentionally permissive because the site structure may evolve.
    """
    entities: list[dict] = []
    seen: set[tuple[str, str | None]] = set()

    anchors = soup.find_all("a", href=True)
    for anchor in anchors:
        href = anchor.get("href", "")
        absolute_href = absolutize(base_url, href)
        if not absolute_href:
            continue

        name = None
        heading = first(anchor.find_all(["h1", "h2", "h3", "h4"]))
        if heading:
            name = text_from_tag(heading)
        if not name:
            anchor_text = text_from_tag(anchor)
            if anchor_text and 1 <= len(anchor_text) <= 120:
                name = anchor_text

        if not name:
            continue

        # Skip UI and navigation junk.
        lowered = name.casefold()
        if lowered in {
            "next",
            "previous",
            "roles",
            "network utilities",
            "learn more",
            "text link",
            "read more",
        }:
            continue

        parent_texts: list[str] = []
        parent = anchor.parent if isinstance(anchor.parent, Tag) else None
        if parent:
            for child in parent.find_all(["p", "div", "span", "li"], recursive=True):
                text = text_from_tag(child)
                if text:
                    parent_texts.append(text)

        short_description = None
        for text in parent_texts:
            if text != name and len(text) > 30:
                short_description = text
                break

        roles, utilities = guess_tags_from_text_blocks(parent_texts)
        logo_url = find_best_image(anchor, base_url) or find_best_image(parent, base_url)

        key = (normalize_name(name), absolute_href)
        if key in seen:
            continue
        seen.add(key)

        entities.append(
            {
                "name": name,
                "slug": slugify(name),
                "detail_url": absolute_href,
                "short_description": short_description,
                "roles": roles,
                "network_utilities": utilities,
                "logo_url": logo_url,
            }
        )

    return entities


def extract_detail_page_fields(html: str, detail_url: str, fallback_name: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    heading = first(soup.find_all(["h1", "h2", "h3"]))
    name = text_from_tag(heading) or fallback_name

    external_website = None
    all_links = soup.find_all("a", href=True)
    for link in all_links:
        href = absolutize(detail_url, link.get("href"))
        if not href:
            continue
        if "cantonecosystem.com" not in href and "canton.network" not in href:
            external_website = href
            break

    paragraphs = [text_from_tag(p) for p in soup.find_all(["p", "li", "div", "span"])]
    paragraphs = [p for p in paragraphs if p]

    filtered_text_blocks: list[str] = []
    for text in paragraphs:
        lowered = text.casefold()
        if lowered in {
            "roles",
            "network utilities",
            "learn more",
            "text link",
            "previous",
            "next",
        }:
            continue
        filtered_text_blocks.append(text)

    long_description = None
    meaningful_candidates = [t for t in filtered_text_blocks if len(t) >= 60]
    if meaningful_candidates:
        long_description = max(meaningful_candidates, key=len)

    short_description = None
    for text in filtered_text_blocks:
        if text != name and 30 <= len(text) <= 260:
            short_description = text
            break

    roles: list[str] = []
    network_utilities: list[str] = []
    for text in filtered_text_blocks:
        if text in KNOWN_ROLES:
            roles.append(text)
        if text in KNOWN_NETWORK_UTILITIES:
            network_utilities.append(text)

    raw_text = normalize_whitespace("\n".join(unique_keep_order(filtered_text_blocks)))
    logo_url = find_best_image(soup, detail_url)

    return {
        "name": name,
        "slug": slugify(name),
        "external_website": external_website,
        "short_description": short_description,
        "long_description": long_description,
        "raw_text": raw_text,
        "roles": unique_keep_order(roles),
        "network_utilities": unique_keep_order(network_utilities),
        "logo_url": logo_url,
    }


def merge_entities(prelim: dict, detail: dict, source_page_url: str, page_number: int) -> RawEntity:
    name = detail.get("name") or prelim.get("name") or "Unknown"
    slug = detail.get("slug") or prelim.get("slug") or slugify(name)

    roles = unique_keep_order((prelim.get("roles") or []) + (detail.get("roles") or []))
    network_utilities = unique_keep_order(
        (prelim.get("network_utilities") or []) + (detail.get("network_utilities") or [])
    )

    short_description = detail.get("short_description") or prelim.get("short_description")
    long_description = detail.get("long_description") or short_description

    return RawEntity(
        name=name,
        slug=slug,
        detail_url=prelim.get("detail_url"),
        external_website=detail.get("external_website"),
        logo_url=detail.get("logo_url") or prelim.get("logo_url"),
        short_description=short_description,
        long_description=long_description,
        raw_text=detail.get("raw_text") or long_description or short_description,
        roles=roles,
        network_utilities=network_utilities,
        source_page_url=source_page_url,
        page_number=page_number,
        extraction_method="detail_page",
    )


def dedupe_entities(rows: list[RawEntity]) -> list[RawEntity]:
    merged: dict[tuple[str, str], RawEntity] = {}

    for row in rows:
        website_key = (row.external_website or "").strip().lower()
        key = (normalize_name(row.name), website_key)
        fallback_key = (normalize_name(row.name), "")
        chosen_key = key if website_key else fallback_key

        existing = merged.get(chosen_key)
        if not existing:
            merged[chosen_key] = row
            continue

        if (row.long_description or "") and len(row.long_description or "") > len(existing.long_description or ""):
            existing.long_description = row.long_description
        if (row.short_description or "") and len(row.short_description or "") > len(existing.short_description or ""):
            existing.short_description = row.short_description
        if (row.raw_text or "") and len(row.raw_text or "") > len(existing.raw_text or ""):
            existing.raw_text = row.raw_text

        if not existing.external_website and row.external_website:
            existing.external_website = row.external_website
        if not existing.logo_url and row.logo_url:
            existing.logo_url = row.logo_url
        if not existing.detail_url and row.detail_url:
            existing.detail_url = row.detail_url

        existing.roles = unique_keep_order(existing.roles + row.roles)
        existing.network_utilities = unique_keep_order(
            existing.network_utilities + row.network_utilities
        )

    return list(merged.values())


def download_file(url: str, destination: Path) -> bool:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        destination.write_bytes(response.content)
        return True
    except Exception:
        return False


def download_logos(rows: list[RawEntity], log: ScrapeLog) -> None:
    for row in rows:
        if not row.logo_url:
            continue

        parsed = urlparse(row.logo_url)
        suffix = Path(parsed.path).suffix or ".png"
        file_name = f"{safe_filename(row.slug)}{suffix}"
        destination = LOGO_DIR / file_name

        if destination.exists() and destination.stat().st_size > 0:
            row.logo_local_path = f"/assets/ecosystem/logos/{file_name}"
            continue

        success = False
        for attempt in range(3):
            if download_file(row.logo_url, destination):
                success = True
                break
            time.sleep(1 + attempt)

        if success:
            row.logo_local_path = f"/assets/ecosystem/logos/{file_name}"
            log.logos_downloaded += 1
        else:
            log.warnings.append(f"Logo download failed for {row.name}: {row.logo_url}")


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: list[RawEntity]) -> None:
    fieldnames = [
        "name",
        "slug",
        "detail_url",
        "external_website",
        "logo_url",
        "logo_local_path",
        "short_description",
        "long_description",
        "raw_text",
        "roles",
        "network_utilities",
        "source_page_url",
        "page_number",
        "extraction_method",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            data = asdict(row)
            data["roles"] = " | ".join(row.roles)
            data["network_utilities"] = " | ".join(row.network_utilities)
            writer.writerow(data)


def scrape() -> int:
    ensure_directories()
    log = ScrapeLog(started_at=time.time())
    raw_rows: list[RawEntity] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)

        try:
            for current_page in range(1, MAX_PAGES + 1):
                url = page_url(current_page)
                print(f"[LIST] Scraping page {current_page}: {url}")

                try:
                    page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    log.warnings.append(f"Timeout on listing page {url}")
                    continue

                html = page.content()
                (RAW_DIR / f"listing-page-{current_page}.html").write_text(html, encoding="utf-8")

                # Stop when pagination reaches a blank/non-result page.
                if "cantonecosystem" not in html.casefold() and current_page > 1:
                    log.warnings.append(f"Stopping pagination early at page {current_page}: no expected marker")
                    break

                soup = BeautifulSoup(html, "html.parser")
                preliminary_entities = harvest_links_for_details(soup, url)

                if current_page > 1 and not preliminary_entities:
                    print(f"[STOP] No entities detected on page {current_page}.")
                    break

                log.pages_scraped += 1

                for index, prelim in enumerate(preliminary_entities, start=1):
                    detail_url = prelim.get("detail_url")
                    if not detail_url:
                        log.warnings.append(f"No detail URL found for {prelim.get('name')}")
                        continue

                    print(f"  [DETAIL] {current_page}.{index} {prelim.get('name')} -> {detail_url}")
                    detail_html = None

                    try:
                        detail_page = browser.new_page(user_agent=USER_AGENT)
                        detail_page.goto(detail_url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
                        detail_html = detail_page.content()
                        detail_page.close()
                    except PlaywrightTimeoutError:
                        log.warnings.append(f"Timeout on detail page {detail_url}")
                        try:
                            detail_page.close()
                        except Exception:
                            pass
                        continue
                    except Exception as exc:
                        log.errors.append(f"Detail page failed for {detail_url}: {exc}")
                        try:
                            detail_page.close()
                        except Exception:
                            pass
                        continue

                    raw_name = safe_filename(prelim.get("slug") or prelim.get("name") or f"entity-{current_page}-{index}")
                    (RAW_DIR / f"detail-{raw_name}.html").write_text(detail_html, encoding="utf-8")

                    detail_fields = extract_detail_page_fields(
                        html=detail_html,
                        detail_url=detail_url,
                        fallback_name=prelim.get("name") or "Unknown",
                    )

                    merged = merge_entities(
                        prelim=prelim,
                        detail=detail_fields,
                        source_page_url=url,
                        page_number=current_page,
                    )
                    raw_rows.append(merged)

                    time.sleep(0.2)

                time.sleep(0.8)
        finally:
            browser.close()

    log.rows_before_dedupe = len(raw_rows)
    deduped_rows = dedupe_entities(raw_rows)
    log.rows_after_dedupe = len(deduped_rows)

    download_logos(deduped_rows, log)

    raw_payload = [asdict(row) for row in raw_rows]
    clean_payload = [asdict(row) for row in deduped_rows]

    write_json(RAW_JSON_PATH, raw_payload)
    write_json(CLEAN_JSON_PATH, clean_payload)
    write_csv(CSV_PATH, deduped_rows)

    log.finished_at = time.time()
    write_json(LOG_PATH, asdict(log))

    print("\nDone.")
    print(f"Listing pages scraped: {log.pages_scraped}")
    print(f"Rows before dedupe:   {log.rows_before_dedupe}")
    print(f"Rows after dedupe:    {log.rows_after_dedupe}")
    print(f"Logos downloaded:     {log.logos_downloaded}")
    print(f"Raw JSON:             {RAW_JSON_PATH}")
    print(f"Clean JSON:           {CLEAN_JSON_PATH}")
    print(f"CSV:                  {CSV_PATH}")
    print(f"Log file:             {LOG_PATH}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(scrape())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130)
