"""
scrape_cips.py
==============
Scrape https://github.com/canton-foundation/cips -> cips.json

Usage:
    python scrape_cips.py               # normal daily run
    python scrape_cips.py --bootstrap   # one-time: fetch abstract + approved for ALL entries

Logic (normal mode):
    - Strictly filters CIP-0[digits] folders — rejects CIP-XXXX drafts
    - Detects new CIPs not yet in cips.json, adds them with abstract as description
    - Skips frozen statuses (Final/Replaced/Rejected/Obsolete/Withdrawn)
    - Updates status and approved date for non-frozen existing CIPs
    - Writes HANDLE-THIS-BEFORE-PULL/complete-cip-learnbox.txt if new CIPs found

Logic (bootstrap mode):
    - Fetches abstract + approved date for ALL existing CIPs
    - Run once after initial deployment to populate all descriptions
"""

import json, os, re, sys, time, urllib.request
from datetime import date
from pathlib import Path

FOUNDATION_REPO = "canton-foundation/cips"
API_BASE        = "https://api.github.com"
CIPS_JSON       = Path("canton-ecosystem/cips.json")
HANDLE_DIR      = Path("HANDLE-THIS-BEFORE-PULL")
NOTICE_FILE     = HANDLE_DIR / "complete-cip-learnbox.txt"
BOOTSTRAP_MODE  = "--bootstrap" in sys.argv

# Strict: CIP-0 followed by digits only
CIP_FOLDER_RE   = re.compile(r'^CIP-0\d+$')
FROZEN_STATUSES = {"Final", "Replaced", "Rejected", "Obsolete", "Withdrawn"}
GH_TOKEN        = os.environ.get("GH_TOKEN", "")


def gh_get(path):
    url = f"{API_BASE}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if GH_TOKEN:
        req.add_header("Authorization", f"Bearer {GH_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"   API error ({path}): {e}")
        return None


def get_raw(path):
    url = f"https://raw.githubusercontent.com/{FOUNDATION_REPO}/main/{path}"
    req = urllib.request.Request(url)
    if GH_TOKEN:
        req.add_header("Authorization", f"Bearer {GH_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"   Raw fetch error ({path}): {e}")
        return None


def parse_md_header(text):
    result = {}
    for line in text.splitlines()[:30]:
        s = line.strip()
        if s == "---" or s.startswith("#") or s.startswith("*"):
            if result:
                break
            continue
        if ":" in s:
            key, _, val = s.partition(":")
            key = key.strip().lower().rstrip("(s)")
            val = val.strip()
            if key and val:
                result[key] = val
    return result


def parse_abstract(text):
    lines = text.splitlines()
    in_abstract = False
    abstract_lines = []
    for line in lines:
        if re.match(r'^##\s+Abstract', line, re.IGNORECASE):
            in_abstract = True
            continue
        if in_abstract:
            if re.match(r'^##\s+', line):
                break
            abstract_lines.append(line)
    abstract = "\n".join(abstract_lines).strip()
    return re.sub(r'\n{3,}', '\n\n', abstract)


def find_md_file(folder):
    items = gh_get(f"repos/{FOUNDATION_REPO}/contents/{folder}")
    if not items or not isinstance(items, list):
        return None, None
    for item in items:
        if re.match(r'cip-0\d+\.md$', item["name"].lower()):
            text = get_raw(f"{folder}/{item['name']}")
            return item["name"], text
    return None, None


def list_cip_folders():
    data = gh_get(f"repos/{FOUNDATION_REPO}/contents")
    if not data or not isinstance(data, list):
        return []
    folders, skipped = [], []
    for item in data:
        if item["type"] != "dir":
            continue
        name = item["name"]
        if CIP_FOLDER_RE.match(name):
            folders.append(name)
        elif re.match(r'^[Cc][Ii][Pp]-', name):
            skipped.append(name)
    folders.sort(key=lambda x: int(re.search(r'\d+', x).group()))
    if skipped:
        print(f"   Skipped non-standard folders: {skipped}")
    return folders


def main():
    HANDLE_DIR.mkdir(exist_ok=True)
    CIPS_JSON.parent.mkdir(exist_ok=True)

    if CIPS_JSON.exists():
        existing = json.loads(CIPS_JSON.read_text(encoding="utf-8"))
        print(f"Loaded {len(existing)} existing CIPs")
    else:
        existing = []
        print("No existing cips.json — starting fresh")

    existing_by_id = {e["id"]: e for e in existing}

    # ── BOOTSTRAP ─────────────────────────────────────────────────────────────
    if BOOTSTRAP_MODE:
        print("\nBootstrap mode — fetching abstract + approved for all CIPs...")
        updated_desc = updated_approved = 0
        for entry in existing:
            cip_id = entry["id"]
            print(f"  [{cip_id}]", end=" ", flush=True)
            _, text = find_md_file(cip_id)
            if not text:
                print("not found")
                time.sleep(0.3)
                continue
            abstract = parse_abstract(text)
            header   = parse_md_header(text)
            changed  = False
            if abstract and entry.get("description", "") != abstract:
                entry["description"] = abstract
                updated_desc += 1
                changed = True
            approved = header.get("approved", "").strip()
            if approved and entry.get("approved", "") != approved:
                entry["approved"] = approved
                updated_approved += 1
                changed = True
            print("updated" if changed else "no change")
            time.sleep(0.3)

        existing.sort(key=lambda x: x["number"])
        CIPS_JSON.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nBootstrap done — {updated_desc} abstracts, {updated_approved} approved dates updated")
        return

    # ── NORMAL DAILY RUN ──────────────────────────────────────────────────────
    print("\nListing CIP folders from foundation repo...")
    folders = list_cip_folders()
    print(f"Found {len(folders)} valid CIP-0XXX folders")
    if not folders:
        print("Could not list folders — check API access")
        return

    new_cips, status_updates = [], []

    for folder in folders:
        cip_id = folder.upper()
        entry  = existing_by_id.get(cip_id)

        if entry is None:
            # NEW CIP
            print(f"\n  New: {cip_id}")
            _, text = find_md_file(folder)
            if not text:
                print(f"    Could not read .md — skipping")
                continue
            header   = parse_md_header(text)
            abstract = parse_abstract(text)
            number   = int(re.search(r'\d+', cip_id).group())
            new_entry = {
                "id":          cip_id,
                "number":      number,
                "title":       header.get("title", ""),
                "type":        header.get("type", ""),
                "status":      header.get("status", ""),
                "created":     header.get("created", ""),
                "approved":    header.get("approved", ""),
                "description": abstract or ""
            }
            existing_by_id[cip_id] = new_entry
            new_cips.append(new_entry)
            print(f"    {new_entry['title'][:70]}")
            print(f"    Abstract: {len(abstract)} chars")
            time.sleep(0.3)

        else:
            # EXISTING — skip frozen
            if entry.get("status") in FROZEN_STATUSES:
                continue
            _, text = find_md_file(folder)
            if not text:
                continue
            header  = parse_md_header(text)
            changed = False
            new_status = header.get("status", "").strip()
            if new_status and new_status != entry.get("status", ""):
                print(f"  {cip_id}: status {entry['status']} -> {new_status}")
                entry["status"] = new_status
                changed = True
            new_approved = header.get("approved", "").strip()
            if new_approved and new_approved != entry.get("approved", ""):
                print(f"  {cip_id}: approved -> {new_approved}")
                entry["approved"] = new_approved
                changed = True
            if changed:
                status_updates.append(cip_id)
            time.sleep(0.2)

    # ── Save ──────────────────────────────────────────────────────────────────
    final = list(existing_by_id.values())
    final.sort(key=lambda x: x["number"])
    CIPS_JSON.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone — {len(final)} CIPs saved")
    if status_updates:
        print(f"Updated: {', '.join(status_updates)}")

    # ── Notice ────────────────────────────────────────────────────────────────
    if new_cips:
        lines = [
            "Canton CIPs — New entries added to cips.json",
            f"Generated: {date.today()}",
            f"Count: {len(new_cips)} new CIP(s)",
            "",
            "Abstract imported automatically from the .md file.",
            "Review description in canton-ecosystem/cips.json before pushing to main.",
            "",
        ]
        for c in new_cips:
            lines.append(f"- {c['id']}: {c['title']}")
            lines.append(f"  Status: {c['status']} | Type: {c['type']} | Created: {c['created']}")
            lines.append(f"  Abstract: {'yes (' + str(len(c['description'])) + ' chars)' if c['description'] else 'MISSING — check .md'}")
            lines.append("")
        NOTICE_FILE.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  {len(new_cips)} new CIP(s) — see {NOTICE_FILE}")
    else:
        if NOTICE_FILE.exists():
            NOTICE_FILE.unlink()
        print("No new CIPs")


if __name__ == "__main__":
    main()
