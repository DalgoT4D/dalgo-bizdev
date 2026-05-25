# /bizdev/research/research-ngo

Research one or more NGOs and log findings to the NGO Research Google Sheet.

## Input: $ARGUMENTS

One or more NGO names, exactly as they appear in the **Combined** tab of the scraper sheet.
Wrap multi-word names in quotes when passing more than one.

Examples:
- `/bizdev/research/research-ngo Pallium India`
- `/bizdev/research/research-ngo "Pallium India" "Bosconet" "Goonj"`

## Output

Appends a new row per NGO into the **"NGO Research"** tab of the research Google Sheet
configured in `workdocs/bizdev/districts.json`.

**Rows are never overwritten.** If an NGO already has a row, it is silently skipped.

Columns written (62 total):

| Group | Columns |
|---|---|
| Identity | NGO Name, Profile URL, Org Website, HQ City |
| Description | Overview, Programs (comma-joined) |
| Cause flags | `[Cause] Education` … `[Cause] Disaster Management` — `TRUE` or blank (10 cols) |
| State flags | `[State] Andhra Pradesh` … `[State] West Bengal` — `TRUE` or blank (36 cols) |
| Financials | Budget ₹ (Total Revenue from Combined tab) |
| Leadership | Leader 1–3: Name, Role, LinkedIn (9 cols) |

## Steps

### 1. Verify config

Read `workdocs/bizdev/districts.json` and confirm:
- `research_sheet_id` is set and non-empty
- `service_account_file` path resolves under `secrets/`

If anything is missing, stop and tell the user to run `/bizdev-setup`.

### 2. Ensure Combined tab exists

Run the dedicated check script:

```bash
python3 scripts/check_combined_tab.py
```

If it exits 0, continue. If it exits 1 (Combined tab absent), prompt the user:

```
❌ Combined tab not found in the scraper sheet.

The district scraper needs to run first to populate the Combined tab.
Run it now?  [Y/n]  bash scripts/run_scraper.sh
```

Wait for the user's confirmation before proceeding. If they decline, stop and explain that
the Combined tab is required to look up NGO profile URLs.

### 3. Run the profile scraper

Pass all NGO names as separate positional arguments:

```bash
python3 scripts/give_do_profile_scraper.py "NGO Name 1" "NGO Name 2" ...
```

The script will:
1. Look up each NGO in the **Combined** tab → retrieve Profile URL and Budget ₹
2. For each found NGO, fetch its give.do profile page and extract:
   - **Org website** — first external link on the profile
   - **HQ city** — from the "Headquarters: City, State" field
   - **Overview** — mission/about paragraph
   - **Program names** — list of program titles (comma-joined in sheet)
   - **Cause areas** — matched against the 10 fixed sectors; flagged `TRUE`
   - **Operational states** — matched against all 36 states/UTs; flagged `TRUE`
   - **Leadership** — up to 3 leaders with name, role, and LinkedIn URL
3. Append a row to the "NGO Research" tab (creates the tab with headers if absent).
   Skip any NGO that already has a row.

### 4. Report the result

After the script exits, summarise for the user:

```
Research complete — X added, Y skipped, Z not found

Added:
  ✓ <NGO Name>
      Website:  <url>
      HQ City:  <city>
      Causes:   <matched cause areas>
      States:   <N> state(s)
      Programs: <N> program(s)
      Leaders:  <Name (Role), ...>

Skipped (already in sheet):
  — <NGO Name>

Not found in Combined tab (run scraper first):
  ⚠ <NGO Name>

Sheet: https://docs.google.com/spreadsheets/d/<research_sheet_id>/
```

### Troubleshooting

| Error | Fix |
|---|---|
| `research_sheet_id` not set | Add it to `workdocs/bizdev/districts.json` and share the sheet with the service account (Editor role) |
| `Combined` tab not found | Run `bash scripts/run_scraper.sh` to populate all district tabs and generate the Combined tab |
| NGO not found in Combined tab | The NGO may not be listed on give.do in any registered district. Check the name spelling against the scraper sheet. |
| HTTP 403 / 429 on profile fetch | give.do is rate-limiting. Wait 60 s and retry. |
| Fields showing blank / wrong values | give.do may have changed its HTML. Inspect the profile page and update the relevant `_extract_*` function in `scripts/give_do_profile_scraper.py`. |
| `NGO Research` tab header mismatch | Delete the tab and re-run — the script will recreate it with the correct 62-column header. |
