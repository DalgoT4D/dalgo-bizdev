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

**Rows are not overwritten by default.** If an NGO already has a row, its current data is
shown and you are asked whether to refresh it. Refreshing re-scrapes the give.do profile
and replaces the existing row.

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

### 3. Check for existing rows

Before running the scraper, fetch all rows currently in the "NGO Research" tab:

```bash
python3 scripts/fetch_research_rows.py
```

Parse the JSON output (case-insensitive name match) to find which input NGOs already have
rows. If none of the input NGOs exist in the sheet, skip to Step 4.

**For each NGO that already has a row**, display its current data:

```
Already in sheet:
  — <NGO Name>
      Website:  <Org Website>
      HQ City:  <HQ City>
      Causes:   <[Cause] cols where value == "TRUE", comma-joined>
      States:   <count of [State] cols where value == "TRUE"> state(s)
      Programs: <count of comma-separated values in Programs col> program(s)
      Leaders:  <Leader 1 Name (Leader 1 Role), Leader 2 Name (Leader 2 Role), ...>
```

Then use `AskUserQuestion` with a **multi-select** question:

> These NGOs already have research rows. Select any you want to refresh (re-scrape and overwrite):

- One option per existing NGO (label = NGO name, description = "Re-scrape and overwrite existing data")
- Plus an option: **"Keep all / don't refresh"** (description = "Leave existing rows unchanged")

**Default is to keep** — do not refresh unless the user explicitly selects an NGO name.

**If the user selects NGOs to refresh**, delete their rows before running the scraper:

```bash
python3 scripts/delete_research_rows.py "NGO Name A" "NGO Name B"
```

Track which NGOs are:
- **to_scrape** — new NGOs (no existing row) + confirmed refreshes (row just deleted)
- **kept** — existing-row NGOs the user did not select for refresh

If `to_scrape` is empty, skip Step 4 and go directly to Step 5.

### 4. Run the profile scraper

Pass only the `to_scrape` NGOs as positional arguments:

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

### 5. Report the result

Combine results from Steps 3 and 4 and summarise:

```
Research complete — X added, Y refreshed, Z kept, W not found

Added:
  ✓ <NGO Name>
      Website:  <url>
      HQ City:  <city>
      Causes:   <matched cause areas>
      States:   <N> state(s)
      Programs: <N> program(s)
      Leaders:  <Name (Role), ...>

Refreshed:
  ↺ <NGO Name>
      Website:  <url>
      HQ City:  <city>
      Causes:   <matched cause areas>
      States:   <N> state(s)
      Programs: <N> program(s)
      Leaders:  <Name (Role), ...>

Kept (not refreshed):
  — <NGO Name>
      Website:  <from existing row>
      HQ City:  <from existing row>
      Causes:   <from existing row>
      States:   <N> state(s)
      Programs: <N> program(s)
      Leaders:  <Name (Role), ...>

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
