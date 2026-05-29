#!/usr/bin/env python3
"""
Check whether the Combined tab exists in the scraper Google Sheet.

Exits 0 if found, 1 if not found.

Usage:
  python3 scripts/check_combined_tab.py
"""

import json
import sys
from pathlib import Path

from google.oauth2.service_account import Credentials
import gspread

HERE = Path(__file__).parent
CONFIG_FILE = HERE.parent / "workdocs" / "bizdev" / "districts.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main() -> None:
    if not CONFIG_FILE.exists():
        print(f"❌  Config not found: {CONFIG_FILE}")
        sys.exit(1)

    config = json.loads(CONFIG_FILE.read_text())
    sheet_id = config.get("sheet_id")
    sa_file = str(HERE / config["service_account_file"])

    if not sheet_id:
        print("❌  'sheet_id' not set in workdocs/bizdev/districts.json")
        sys.exit(1)

    creds = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    tabs = [ws.title for ws in sh.worksheets()]
    match = next((t for t in tabs if t.lower() == "combined"), None)

    if match:
        print(f"✓  Combined tab found: '{match}'")
        sys.exit(0)
    else:
        print("❌  Combined tab not found")
        print(f"   Existing tabs: {', '.join(tabs)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
