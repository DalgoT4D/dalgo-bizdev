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

def _normalise(name: str) -> str:
    """Lowercase, strip both '&' and standalone 'and', collapse spaces — for state matching."""
    s = name.lower().replace("&", " ").replace("-", " ")
    s = re.sub(r"\band\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

_STATE_NORM: dict[str, str] = {_normalise(s): s for s in INDIA_STATES}

_HIGHCHARTS_OVERRIDES: dict[str, str] = {
    "nct-of-delhi":        "Delhi",
    "andaman-and-nicobar": "Andaman & Nicobar Islands",
}


def _class_to_state(suffix: str) -> str | None:
    """Convert Highcharts class suffix 'tamil-nadu' → canonical 'Tamil Nadu'."""
    if suffix in _HIGHCHARTS_OVERRIDES:
        return _HIGHCHARTS_OVERRIDES[suffix]
    return _STATE_NORM.get(_normalise(suffix))


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

    combined_ws = next(
        (ws for ws in sh.worksheets() if ws.title.lower() == "combined"), None
    )
    if combined_ws is None:
        print("❌  'Combined' tab not found in scraper sheet.")
        print("   Run the district scraper first: bash scripts/run_scraper.sh")
        return {}
    ws = combined_ws

    records = ws.get_all_values()
    if not records:
        return {}

    header = [h.strip().lower() for h in records[0]]
    try:
        name_col = header.index("ngo name")
        url_col  = header.index("profile url")
        rev_col  = next(i for i, h in enumerate(header) if h.startswith("total revenue"))
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
    """Org website from the dedicated 'Website' section (h2 + detailstabfield)."""
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == "Website":
            for sib in h2.parent.find_all_next("div", class_="detailstabfield"):
                a = sib.find("a", class_="text-red")
                if a and a.get("href", "").startswith("http"):
                    return a["href"].strip()
    return ""


def _extract_overview(soup: BeautifulSoup) -> str:
    """Org vision/mission from <div class='vision-mission-content'>."""
    div = soup.find("div", class_="vision-mission-content")
    if div:
        p = div.find("p")
        if p:
            return p.get_text(strip=True)
    # Fallback: first <p> after <h1>
    h1 = soup.find("h1")
    if h1:
        p = h1.find_next_sibling("p")
        if p:
            return p.get_text(strip=True)
    return ""


def _extract_hq_city(soup: BeautifulSoup) -> str:
    """Extract city from <p class='office-address'> — city is second-to-last comma token."""
    p = soup.find("p", class_="office-address")
    if p:
        parts = [x.strip() for x in p.get_text(separator=" ").split(",") if x.strip()]
        if len(parts) >= 2:
            return parts[-2]
    # Fallback: span containing "Headquarters" → next <p>
    for span in soup.find_all("span"):
        if "Headquarters" in span.get_text():
            p = span.find_next("p")
            if p:
                parts = [x.strip() for x in p.get_text().split(",") if x.strip()]
                if len(parts) >= 2:
                    return parts[-2]
    return ""


def _extract_program_names(soup: BeautifulSoup) -> list[str]:
    """Program names from accordionHeading <h3> tags inside <div id='programs'>."""
    programs_div = soup.find("div", id="programs")
    if programs_div:
        return [
            h3.get_text(strip=True)
            for li in programs_div.find_all("li", class_="accordion_elem")
            for h3 in li.find_all("h3", class_="accordionHeading")
            if h3.get_text(strip=True)
        ]
    # Fallback: accordionHeading anywhere on page
    return [h3.get_text(strip=True) for h3 in soup.find_all("h3", class_="accordionHeading") if h3.get_text(strip=True)]


def _extract_cause_areas(soup: BeautifulSoup) -> list[str]:
    """Primary cause areas via badge-link anchors pointing to /discover/sector/."""
    areas = []
    for a in soup.find_all("a", class_="badge-link"):
        if "/discover/sector/" in a.get("href", ""):
            badge = a.find("span", class_="badge")
            text = badge.get_text(strip=True) if badge else a.get_text(strip=True)
            if text:
                areas.append(text)
    return list(dict.fromkeys(areas))


def _extract_operational_states(url: str) -> list[str]:
    """
    Render the page with Playwright and extract operational states from the
    Highcharts SVG map.  Operational states have class 'highcharts-point' but
    NOT 'highcharts-null-point'; the state name is encoded in 'highcharts-name-*'.
    """
    from playwright.sync_api import sync_playwright

    states: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_selector("[class*='highcharts-name-']", timeout=15000)
            elements = page.query_selector_all(
                ".highcharts-point:not(.highcharts-null-point)"
            )
            for el in elements:
                class_attr = el.get_attribute("class") or ""
                for cls in class_attr.split():
                    if cls.startswith("highcharts-name-"):
                        suffix = cls[len("highcharts-name-"):]
                        state = _class_to_state(suffix)
                        if state:
                            states.append(state)
                        break
        except Exception as exc:
            print(f"   ⚠  State extraction failed: {exc}")
        finally:
            browser.close()

    return list(dict.fromkeys(states))


def _extract_leadership(soup: BeautifulSoup) -> list[dict]:
    """
    Leaders from <ul class='tab-inner__team tab-row'> — each <li> has:
      <div class='tab-inner__info--name'>Name <a class='tab-inner__info--link'>...</a></div>
      <p>Role</p>
    Returns up to 3 dicts with keys: name, role, linkedin.
    """
    leaders: list[dict] = []
    ul = soup.find("ul", class_=lambda c: c and "tab-inner__team" in c)
    if not ul:
        return leaders
    for li in ul.find_all("li"):
        name_div = li.find("div", class_="tab-inner__info--name")
        if not name_div:
            continue
        linkedin_a = name_div.find("a", class_="tab-inner__info--link")
        linkedin = linkedin_a["href"].strip() if linkedin_a else ""
        if linkedin_a:
            linkedin_a.decompose()
        name = name_div.get_text(strip=True)
        role_p = name_div.find_next_sibling("p")
        role = role_p.get_text(strip=True) if role_p else ""
        if name:
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
        "states":     _extract_operational_states(url),
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
