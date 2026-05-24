#!/usr/bin/env python3
"""
give.do NGO Profile Scraper
============================
Looks up one or more NGOs by name in the Combined tab of the scraper sheet,
fetches each NGO's give.do profile page, and appends a research row to the
"NGO Research" tab of the research Google Sheet.

Existing rows are NOT overwritten — re-running the same name is a no-op.

Usage:
  python3 give_do_profile_scraper.py "NGO Name"
  python3 give_do_profile_scraper.py "NGO A" "NGO B" "NGO C"

Setup:
  Requires 'research_sheet_id' in workdocs/bizdev/districts.json.
  Both sheets must be shared with the service account (Editor role).
  The scraper sheet must have a 'Combined' tab (run give_do_scraper.py first).
"""

import argparse
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

HERE = Path(__file__).parent
CONFIG_FILE = HERE.parent / "workdocs" / "bizdev" / "districts.json"

import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

MAX_RETRIES   = 3
RETRY_BACKOFF = 2   # seconds; doubles each attempt

# ── Taxonomy ───────────────────────────────────────────────────────────────────
# Source: give.do/discover/ (41 sectors total); top 10 by prevalence among
# Indian urban NGOs, verified May 2026.
GIVE_DO_SECTORS = [
    "Education",
    "Health",
    "Child & Youth Development",
    "Livelihoods",
    "Skill Development",
    "Gender",
    "Energy & Environment",
    "Food & Nutrition",
    "Human Rights",
    "Disaster Management",
]

INDIA_STATES = [
    "Andaman & Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh",
    "Assam", "Bihar", "Chandigarh", "Chhattisgarh", "Dadra & Nagar Haveli",
    "Daman & Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
    "Jammu & Kashmir", "Jharkhand", "Karnataka", "Kerala", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]

RESEARCH_TAB = "NGO Research"

RESEARCH_HEADER = (
    ["NGO Name", "Profile URL", "Org Website", "HQ City", "Overview", "Programs"]
    + [f"[Cause] {s}" for s in GIVE_DO_SECTORS]
    + [f"[State] {s}" for s in INDIA_STATES]
    + [
        "Budget ₹",
        "Leader 1 Name", "Leader 1 Role", "Leader 1 LinkedIn",
        "Leader 2 Name", "Leader 2 Role", "Leader 2 LinkedIn",
        "Leader 3 Name", "Leader 3 Role", "Leader 3 LinkedIn",
    ]
)


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG & AUTH
# ══════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_FILE}")
    return json.loads(CONFIG_FILE.read_text())


def get_credentials(sa_file: str) -> Credentials:
    return Credentials.from_service_account_file(sa_file, scopes=SCOPES)


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP (with retry)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_soup(url: str) -> BeautifulSoup:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code < 500:
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "lxml")
            raise requests.exceptions.HTTPError(
                f"HTTP {resp.status_code}", response=resp
            )
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * (2 ** (attempt - 1))
                print(f"   ⚠  Attempt {attempt} failed ({exc}). Retrying in {wait}s …")
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
#  COMBINED TAB LOOKUP
# ══════════════════════════════════════════════════════════════════════════════

def lookup_from_combined(
    ngo_names: list[str],
    sheet_id: str,
    creds: Credentials,
) -> dict[str, dict]:
    """
    Reads the Combined tab of the scraper sheet and returns a dict keyed by
    normalised NGO name (lower-stripped) with 'name', 'url', and 'budget'.
    Only names present in ngo_names are returned.
    """
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    try:
        ws = sh.worksheet("Combined")
    except gspread.WorksheetNotFound:
        print("❌  'Combined' tab not found in scraper sheet.")
        print("   Run the district scraper first: bash scripts/run_scraper.sh")
        return {}

    records = ws.get_all_values()
    if not records:
        return {}

    header = [h.strip().lower() for h in records[0]]
    try:
        name_col = header.index("ngo name")
        url_col  = header.index("profile url")
        rev_col  = header.index("total revenue (fy) ₹")
    except ValueError as e:
        print(f"❌  Combined tab is missing expected column: {e}")
        return {}

    query = {n.strip().lower(): n for n in ngo_names}
    results: dict[str, dict] = {}

    for row in records[1:]:
        if len(row) <= max(name_col, url_col, rev_col):
            continue
        key = row[name_col].strip().lower()
        if key in query and key not in results:
            rev_raw = row[rev_col].strip()
            results[key] = {
                "name":   query[key],
                "url":    row[url_col].strip(),
                "budget": int(rev_raw) if rev_raw.isdigit() else None,
            }

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE SCRAPING
#
#  give.do profile page structure (verified 2026-05, bosconet example):
#    - Overview:  first <p> after the <h1> NGO name
#    - HQ City:   <p> starting with "Headquarters: City, State"
#    - Website:   first <a href="http..."> that is not give.do
#    - Programs:  <h3> tags inside the "Programs" section
#    - Causes:    <a href="/discover/sector/..."> link texts
#    - States:    <a href="/discover/state/..."> link texts
#    - Leadership:<p> tags matching "Name - Role" pattern (max 3)
# ══════════════════════════════════════════════════════════════════════════════

def _section(soup: BeautifulSoup, h2_text: str):
    """Return the section container whose h2 matches h2_text (class-based fallback)."""
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == h2_text:
            # Walk up to the section wrapper (OverviewTabContentouter or similar)
            node = h2.parent
            for _ in range(4):
                if node is None:
                    break
                node = node.parent
            return node
    return None


def _extract_website(soup: BeautifulSoup) -> str:
    """First external link (not give.do) on the page."""
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") and "give.do" not in href:
            return href
    return ""


def _extract_overview(soup: BeautifulSoup) -> str:
    """Mission/about text — first <p> immediately after the <h1>."""
    h1 = soup.find("h1")
    if h1:
        p = h1.find_next_sibling("p")
        if p:
            return p.get_text(strip=True)
    return ""


def _extract_hq_city(soup: BeautifulSoup) -> str:
    """Extract city from '<p>Headquarters: City, State</p>'."""
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text.startswith("Headquarters:"):
            _, _, location = text.partition(":")
            city = location.strip().split(",")[0].strip()
            return city
    return ""


def _extract_program_names(soup: BeautifulSoup) -> list[str]:
    """Program names from <h3> tags inside the Programs section."""
    sec = _section(soup, "Programs")
    if sec:
        names = [h3.get_text(strip=True) for h3 in sec.find_all("h3")]
        if names:
            return names
    # Fallback: any <h3> in the page (give.do uses h3 only for programs)
    return [h3.get_text(strip=True) for h3 in soup.find_all("h3") if h3.get_text(strip=True)]


def _extract_cause_areas(soup: BeautifulSoup) -> list[str]:
    """All cause areas via /discover/sector/ links (deduplicated, order-preserved)."""
    areas = []
    for a in soup.find_all("a", href=re.compile(r"/discover/sector/")):
        text = a.get_text(strip=True)
        if text:
            areas.append(text)
    return list(dict.fromkeys(areas))


def _extract_operational_states(soup: BeautifulSoup) -> list[str]:
    """All operational states via /discover/state/ links (deduplicated)."""
    states = []
    for a in soup.find_all("a", href=re.compile(r"/discover/state/")):
        text = a.get_text(strip=True)
        if text:
            states.append(text)
    return list(dict.fromkeys(states))


def _extract_leadership(soup: BeautifulSoup) -> list[dict]:
    """
    Parse <p> tags matching "Name - Role" pattern.
    Returns up to 3 dicts with keys: name, role, linkedin.
    """
    leaders: list[dict] = []
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if " - " not in text or len(text) > 120:
            continue
        parts = text.split(" - ", 1)
        name, role = parts[0].strip(), parts[1].strip()
        if not name or not role:
            continue
        linkedin_a = p.find("a", href=re.compile(r"linkedin\.com/in/", re.I))
        linkedin = linkedin_a["href"].strip() if linkedin_a else ""
        leaders.append({"name": name, "role": role, "linkedin": linkedin})
        if len(leaders) == 3:
            break
    return leaders


def scrape_profile(url: str) -> dict:
    print(f"   🌐  Fetching: {url}")
    soup = fetch_soup(url)
    return {
        "website":    _extract_website(soup),
        "overview":   _extract_overview(soup),
        "hq_city":    _extract_hq_city(soup),
        "programs":   _extract_program_names(soup),
        "causes":     _extract_cause_areas(soup),
        "states":     _extract_operational_states(soup),
        "leadership": _extract_leadership(soup),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  RESEARCH SHEET WRITER
# ══════════════════════════════════════════════════════════════════════════════

def _get_or_create_research_ws(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    """Return the NGO Research worksheet, creating it with headers if needed."""
    try:
        return sh.worksheet(RESEARCH_TAB)
    except gspread.WorksheetNotFound:
        pass

    # May already exist server-side with stale client cache
    try:
        ws = sh.add_worksheet(
            title=RESEARCH_TAB,
            rows=5000,
            cols=len(RESEARCH_HEADER) + 5,
        )
    except gspread.exceptions.APIError as e:
        if "already exists" in str(e):
            sh.fetch_sheet_metadata()
            ws = sh.worksheet(RESEARCH_TAB)
        else:
            raise

    ws.update([RESEARCH_HEADER], "A1", value_input_option="USER_ENTERED")
    print(f"   Created tab '{RESEARCH_TAB}' with headers")
    return ws


def _get_existing_names(ws: gspread.Worksheet) -> set[str]:
    records = ws.get_all_values()
    if len(records) < 2:
        return set()
    return {row[0].strip().lower() for row in records[1:] if row and row[0].strip()}


def append_research_row(
    ngo_name: str,
    profile_url: str,
    data: dict,
    budget: int | None,
    research_sheet_id: str,
    creds: Credentials,
) -> bool:
    """
    Appends a new research row.  Returns True if appended, False if skipped.
    """
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(research_sheet_id)
    ws = _get_or_create_research_ws(sh)

    if ngo_name.strip().lower() in _get_existing_names(ws):
        return False

    cause_flags = ["TRUE" if c in data["causes"] else "" for c in GIVE_DO_SECTORS]
    state_flags = ["TRUE" if s in data["states"] else "" for s in INDIA_STATES]

    leaders_flat: list[str] = []
    for i in range(3):
        ldr = data["leadership"][i] if i < len(data["leadership"]) else {}
        leaders_flat += [ldr.get("name", ""), ldr.get("role", ""), ldr.get("linkedin", "")]

    row = (
        [
            ngo_name,
            profile_url,
            data["website"],
            data["hq_city"],
            data["overview"],
            ", ".join(data["programs"]),
        ]
        + cause_flags
        + state_flags
        + [budget if budget is not None else ""]
        + leaders_flat
    )

    ws.append_row(row, value_input_option="USER_ENTERED")
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research one or more NGOs from their give.do profiles"
    )
    parser.add_argument(
        "ngo_names",
        nargs="+",
        help="NGO name(s) exactly as they appear in the Combined tab",
    )
    args = parser.parse_args()

    config = load_config()
    sheet_id          = config["sheet_id"]
    research_sheet_id = config.get("research_sheet_id")
    sa_file           = str(HERE / config["service_account_file"])

    if not research_sheet_id:
        print("❌  'research_sheet_id' not set in workdocs/bizdev/districts.json")
        print("   Add: \"research_sheet_id\": \"<your-sheet-id>\"")
        return

    creds = get_credentials(sa_file)

    # ── Step 1: batch lookup from Combined tab ─────────────────────────────
    print(f"\n🔍  Looking up {len(args.ngo_names)} NGO(s) in Combined tab …")
    found = lookup_from_combined(args.ngo_names, sheet_id, creds)

    not_found = [n for n in args.ngo_names if n.strip().lower() not in found]
    if not_found:
        print(f"⚠   Not found in Combined tab ({len(not_found)}): {not_found}")
        print("    Run the scraper first: bash scripts/run_scraper.sh")

    if not found:
        return

    # ── Step 2: scrape profiles & write to research sheet ─────────────────
    print(f"\n{'='*52}")
    print(f"  Researching {len(found)} NGO(s)")
    print(f"{'='*52}")

    added = skipped = errors = 0

    for key, meta in found.items():
        print(f"\n📋  {meta['name']}")
        try:
            data = scrape_profile(meta["url"])
            appended = append_research_row(
                meta["name"],
                meta["url"],
                data,
                meta["budget"],
                research_sheet_id,
                creds,
            )
            if appended:
                added += 1
                leaders = ", ".join(
                    ldr["name"] for ldr in data["leadership"]
                ) or "N/A"
                print(f"   ✓  Added")
                print(f"      Website:  {data['website'] or 'N/A'}")
                print(f"      HQ City:  {data['hq_city'] or 'N/A'}")
                print(f"      Causes:   {', '.join(data['causes']) or 'N/A'}")
                print(f"      States:   {len(data['states'])} state(s)")
                print(f"      Programs: {len(data['programs'])} program(s)")
                print(f"      Leaders:  {leaders}")
            else:
                skipped += 1
                print(f"   —  Skipped (already in NGO Research)")
        except Exception as exc:
            errors += 1
            print(f"   ❌  Error: {exc}")

    # ── Step 3: summary ───────────────────────────────────────────────────
    print(f"\n{'='*52}")
    print(
        f"  Done — {added} added, {skipped} skipped, "
        f"{errors} error(s), {len(not_found)} not found"
    )
    print(f"  Sheet: https://docs.google.com/spreadsheets/d/{research_sheet_id}/")


if __name__ == "__main__":
    main()
