"""
scrape_canton.py
================
Scrape cantonecosystem.com → entities.json + logos/
Usage:
    python scrape_canton.py               # full run
    python scrape_canton.py --diff        # only new entities vs existing JSON

Output:
    canton-ecosystem/entities.json
    canton-ecosystem/logos/<slug>.png
"""

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# ── Playwright async API ──────────────────────────────────────────────────────
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL      = "https://www.cantonecosystem.com"
LIST_URL      = BASE_URL
DETAIL_PREFIX = BASE_URL + "/ecosystem/"
OUT_DIR       = Path("canton-ecosystem")
LOGOS_DIR     = OUT_DIR / "logos"
JSON_PATH     = OUT_DIR / "entities.json"
DIFF_MODE     = "--diff" in sys.argv

# How long to wait for JS to render the full entity list (ms)
LIST_WAIT_MS  = 8_000
# Delay between detail page requests (seconds) — be polite
DETAIL_DELAY  = 0.6


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """'BNP Paribas' → 'bnp-paribas'"""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def download_logo(url: str, slug: str) -> str | None:
    """Download logo, return local relative path or None on failure."""
    if not url or "placeholder" in url:
        return None
    ext = url.split("?")[0].split(".")[-1]
    if ext not in ("png", "jpg", "jpeg", "svg", "webp"):
        ext = "png"
    dest = LOGOS_DIR / f"{slug}.{ext}"
    if dest.exists():
        return str(dest.relative_to(OUT_DIR)).replace("/", "\\")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            dest.write_bytes(r.read())
        print(f"    ↓ logo saved: {dest.name}")
        return str(dest.relative_to(OUT_DIR)).replace("/", "\\")
    except Exception as e:
        print(f"    ⚠ logo failed ({slug}): {e}")
        return None


# ── Step 1 : scrape the listing page ─────────────────────────────────────────

async def scrape_listing(page) -> list[dict]:
    """
    Returns a list of dicts:
      { name, slug, logo_cdn_url, short_desc, roles[], utilities[] }
    """
    print(f"\n📄 Loading listing page…")
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(12_000)  # wait for Webflow JS to render all cards

    # Each entity card — Webflow CMS collection items
    # Structure observed:
    #   div.ecosystem-card (or similar) > img (logo) + h3 (name) + p (desc) + tags
    # We'll use a broad selector and adapt
    cards = await page.query_selector_all("[class*='ecosystem'] [class*='card'], "
                                          "[class*='partner'], "
                                          ".w-dyn-item")

    # Fallback: grab all cards that contain an h3 and a 'More' link
    if not cards:
        cards = await page.query_selector_all(".w-dyn-item")

    print(f"   Found {len(cards)} raw cards")
    entities = []

    for card in cards:
        try:
            # Name
            h3 = await card.query_selector("h3")
            if not h3:
                continue
            name = (await h3.inner_text()).strip()
            if not name:
                continue

            # Short description — try multiple selectors Webflow might use
            desc = ""
            for sel in ["p", "[class*='desc']", "[class*='text']", "[class*='body']", "[class*='summary']"]:
                p_el = await card.query_selector(sel)
                if p_el:
                    t = (await p_el.inner_text()).strip()
                    if t and len(t) > 20 and t != name:
                        desc = t
                        break

            # Logo — second img (first is the blank placeholder)
            imgs = await card.query_selector_all("img")
            logo_url = ""
            for img in imgs:
                src = await img.get_attribute("src") or ""
                if src and "placeholder" not in src and "blank" not in src:
                    logo_url = src
                    break

            # Tags (roles + utilities) — all visible tag text nodes
            tag_els = await card.query_selector_all(
                "[class*='tag'], [class*='badge'], [class*='label'], [class*='role']"
            )
            tags = []
            for t in tag_els:
                txt = (await t.inner_text()).strip()
                if txt and txt not in tags:
                    tags.append(txt)

            slug = slugify(name)
            entities.append({
                "name":      name,
                "slug":      slug,
                "logo_cdn":  logo_url,
                "short_desc": desc,
                "tags":      tags,
            })
        except Exception as e:
            print(f"   ⚠ card parse error: {e}")
            continue

    # De-duplicate by slug
    seen = set()
    unique = []
    for e in entities:
        if e["slug"] not in seen:
            seen.add(e["slug"])
            unique.append(e)

    print(f"   ✓ {len(unique)} unique entities parsed")
    return unique


# ── Step 2 : scrape detail page for each entity ───────────────────────────────

async def scrape_detail(page, slug: str) -> dict:
    """
    Returns { detail_text, roles[], utilities[], logo_cdn (from detail) }
    """
    url = DETAIL_PREFIX + slug
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2_500)

        # Detail description — skip if 404 page
        page_text = await page.inner_text("body")
        if "Page Not Found" in page_text or "doesn't exist or has been moved" in page_text:
            print(f"   ⚠ 404 page: {slug} — will use short_desc from listing")
            return {"detail_text": "", "tags_detail": [], "logo_cdn_detail": ""}

        # Longest meaningful paragraph
        paras = await page.query_selector_all("p, [class*='body'], [class*='description']")
        texts = []
        for p in paras:
            t = (await p.inner_text()).strip()
            if len(t) > 60:
                texts.append(t)
        detail_text = max(texts, key=len) if texts else ""

        # Logo from detail page (higher res)
        logo_cdn = ""
        imgs = await page.query_selector_all("img")
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if src and "placeholder" not in src and "blank" not in src and "logo" not in src.lower():
                # Skip nav/UI images; take first content image
                if "website-files.com/696a7c" in src:   # entity logos CDN path
                    logo_cdn = src
                    break

        # Roles + utilities from detail
        tag_els = await page.query_selector_all(
            "[class*='tag'], [class*='badge'], [class*='role'], [class*='utility']"
        )
        tags = []
        for t in tag_els:
            txt = (await t.inner_text()).strip()
            if txt and txt not in tags:
                tags.append(txt)

        return {"detail_text": detail_text, "tags_detail": tags, "logo_cdn_detail": logo_cdn}

    except PWTimeout:
        print(f"   ⏱ timeout: {slug}")
        return {}
    except Exception as e:
        print(f"   ⚠ detail error ({slug}): {e}")
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    OUT_DIR.mkdir(exist_ok=True)
    LOGOS_DIR.mkdir(exist_ok=True)

    # Load existing data if diff mode
    existing = {}
    if DIFF_MODE and JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        existing = {e["slug"]: e for e in data}
        print(f"🔄 Diff mode — {len(existing)} existing entities loaded")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # ── 1. Get listing ────────────────────────────────────────────────────
        entities = await scrape_listing(page)

        if not entities:
            print("\n❌ No entities found — the page structure may have changed.")
            print("   Open cantonecosystem.com in DevTools and check the card selector.")
            await browser.close()
            return

        # Filter to new only if diff mode
        if DIFF_MODE:
            new_entities = [e for e in entities if e["slug"] not in existing]
            print(f"   → {len(new_entities)} new entities to process")
            entities_to_process = new_entities
        else:
            entities_to_process = entities

        # ── 2. Get details + download logos ───────────────────────────────────
        total = len(entities_to_process)
        for i, entity in enumerate(entities_to_process, 1):
            slug = entity["slug"]
            print(f"\n[{i}/{total}] {entity['name']} ({slug})")

            # Detail page — fallback to short_desc if 404
            detail = await scrape_detail(page, slug)
            detail_text = detail.get("detail_text", "")
            entity["detail_text"] = detail_text if detail_text else entity.get("short_desc", "")

            # Merge tags
            all_tags = list(dict.fromkeys(entity.get("tags", []) + detail.get("tags_detail", [])))
            entity["tags"] = all_tags

            # Best logo URL
            logo_cdn = detail.get("logo_cdn_detail") or entity.get("logo_cdn", "")
            entity["logo_cdn"] = logo_cdn

            # Download logo locally
            entity["logo_local"] = download_logo(logo_cdn, slug)

            time.sleep(DETAIL_DELAY)

        await browser.close()

    # ── 3. Merge + save JSON ──────────────────────────────────────────────────
    if DIFF_MODE and existing:
        # Merge: new entities take priority, keep old ones
        merged = {**existing}
        for e in entities_to_process:
            merged[e["slug"]] = e
        final = list(merged.values())
    else:
        final = entities

    # Sort alphabetically
    final.sort(key=lambda x: x["name"].lower())

    JSON_PATH.write_text(
        json.dumps(final, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n✅ Done — {len(final)} entities saved to {JSON_PATH}")
    print(f"   Logos in: {LOGOS_DIR}")

    # ── 4. Detect missing entities (in existing JSON but not on site anymore) ──
    if DIFF_MODE and existing:
        scraped_slugs = {e["slug"] for e in entities}
        missing = [e for slug, e in existing.items() if slug not in scraped_slugs]
        MISSING_PATH = OUT_DIR / "canton_missing_entities.txt"

        if missing:
            lines = [
                "Canton Ecosystem — Entities not found on cantonecosystem.com",
                f"Checked: {__import__('datetime').date.today()}",
                f"Count: {len(missing)}",
                "",
                "These entities exist in entities.json but were NOT found during scrape.",
                "Please check manually — remove from entities.json if confirmed gone.",
                "",
            ]
            for e in sorted(missing, key=lambda x: x["name"].lower()):
                lines.append(f"- {e['name']} (slug: {e['slug']})")

            MISSING_PATH.write_text("\n".join(lines), encoding="utf-8")

            print(f"\n⚠️  {len(missing)} entities not found on site — see {MISSING_PATH.name}:")
            for e in missing:
                print(f"   - {e['name']} ({e['slug']})")
        else:
            # Clean up file if no missing entities
            if MISSING_PATH.exists():
                MISSING_PATH.unlink()
            print(f"\n✓ No missing entities — all existing entries found on site")


if __name__ == "__main__":
    asyncio.run(main())
