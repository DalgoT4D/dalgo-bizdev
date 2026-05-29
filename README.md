# Dalgo Bizdev — NGO Prospecting Pipeline

This repo contains the tools we use to discover and research NGO prospects from [give.do](https://give.do).

The pipeline has two steps:

1. **Scrape** — pull a list of NGOs from give.do city pages into a Google Sheet
2. **Research** — deep-dive individual NGOs and log structured profiles into a second sheet

Both steps are run as simple commands inside Claude Code. No coding required.

---

## What You Get

### Scraper Sheet (step 1)
One tab per registered city, plus a **Combined** tab that deduplicates NGOs across all cities.

Each row has:
- NGO Name
- HQ Location
- Financial Year
- Total Revenue (₹, as a number — filterable)
- Profile URL on give.do

### NGO Research Sheet (step 2)
A single **NGO Research** tab. Each row is one deeply researched NGO.

Each row has:
- Name, give.do profile URL, organisation website, HQ city
- Overview (mission statement)
- Programs (all program names, comma-separated)
- **10 cause area columns** — `TRUE` if the NGO works in that area (Education, Health, Child & Youth Development, Livelihoods, Skill Development, Gender, Energy & Environment, Food & Nutrition, Human Rights, Disaster Management)
- **36 state columns** — `TRUE` for each state where the NGO operates
- Budget ₹ (Total Revenue from the scraper sheet)
- Leader 1, Leader 2, Leader 3 — Name, Role, LinkedIn for up to 3 leaders

The cause area and state columns make it easy to filter in Google Sheets — e.g. "show me all NGOs working in Education in Maharashtra."

---

## How to Use

All commands are run inside Claude Code. Type the command and Claude handles the rest.

### Step 1 — Refresh the NGO list

```
/bizdev/scraping/refresh-source
```

Scrapes all registered cities from give.do and updates the scraper sheet. Also writes the Combined tab (deduplicated). Run this whenever you want fresh data — it replaces the existing city tabs.

---

### Step 2 — Research specific NGOs

```
/bizdev/research/research-ngo "NGO Name"
/bizdev/research/research-ngo "NGO A" "NGO B" "NGO C"
```

Looks up each NGO in the Combined tab, fetches its give.do profile, and adds a row to the NGO Research sheet. Use the name exactly as it appears in the scraper sheet.

If an NGO already has a row in the research sheet, it is skipped — existing data is never overwritten.

**Example:**
```
/bizdev/research/research-ngo "Bosconet" "Pallium India" "Goonj"
```

---

### Add a new city

```
/bizdev/scraping/add-district <CityName>
```

Validates the city on give.do and registers it so future `/refresh-source` runs include it.

---

## File Structure

```
scripts/
  give_do_scraper.py          District listing scraper (step 1)
  give_do_profile_scraper.py  NGO profile researcher (step 2)
  run_scraper.sh              Shell wrapper for the listing scraper
  give_do_requirements.txt    Python dependencies

workdocs/bizdev/
  districts.json              Registered cities + sheet IDs (not committed to git)

secrets/
  <key>.json                  Google service account key (not committed to git)

.claude/commands/bizdev/
  scraping/refresh-source.md  Command definition for step 1
  scraping/add-district.md    Command definition for adding a city
  research/research-ngo.md    Command definition for step 2
```

---

## Setup (one-time)

1. Make sure `workdocs/bizdev/districts.json` exists with:
   - `sheet_id` — the scraper Google Sheet ID
   - `research_sheet_id` — the NGO Research Google Sheet ID
   - `service_account_file` — path to the service account key under `secrets/`

2. Both Google Sheets must be shared with the service account email (Editor access).

3. Run `/bizdev-setup` inside Claude Code if starting from scratch — it walks through the full setup.

---

## Registered Cities

Currently scraping: **Bangalore, Delhi, Mumbai, Chennai, Pune, Hyderabad, Kolkata, Ahmedabad, Lucknow, Jaipur, Thiruvananthapuram** (11 cities, ~3,100 unique NGOs in Combined tab).
