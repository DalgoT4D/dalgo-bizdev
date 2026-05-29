"""Delete rows from NGO Research sheet by NGO name (case-insensitive).

Usage:
    python3 scripts/delete_research_rows.py "NGO Name A" "NGO Name B"
"""
import json, sys
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

HERE = Path(__file__).parent
names_to_delete = {n.strip().lower() for n in sys.argv[1:] if n.strip()}

if not names_to_delete:
    print("No names provided — nothing deleted")
    sys.exit(0)

cfg = json.load(open(HERE.parent / "workdocs" / "bizdev" / "districts.json"))
sa = str(HERE / cfg["service_account_file"])
creds = Credentials.from_service_account_file(
    sa, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gc = gspread.authorize(creds)
ws = gc.open_by_key(cfg["research_sheet_id"]).worksheet("NGO Research")
all_vals = ws.get_all_values()
rows_to_delete = [
    i + 1
    for i, row in enumerate(all_vals)
    if row and row[0].strip().lower() in names_to_delete
]
for row_idx in sorted(rows_to_delete, reverse=True):
    ws.delete_rows(row_idx)
print(f"Deleted {len(rows_to_delete)} row(s)")
