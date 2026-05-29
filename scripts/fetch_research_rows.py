"""Print all rows from the NGO Research sheet as JSON (stdout)."""
import json
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

HERE = Path(__file__).parent
cfg = json.load(open(HERE.parent / "workdocs" / "bizdev" / "districts.json"))
sa = str(HERE / cfg["service_account_file"])
creds = Credentials.from_service_account_file(
    sa, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
gc = gspread.authorize(creds)
ws = gc.open_by_key(cfg["research_sheet_id"]).worksheet("NGO Research")
print(json.dumps(ws.get_all_records()))
