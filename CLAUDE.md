# Dalgo Bizdev — Claude Code Guide

Dalgo is an open-source data platform for NGOs. It replaces manual Excel/Google Sheets workflows with automated data ingestion (Airbyte), transformation (dbt), orchestration (Prefect), and visualization (Superset + custom dashboards).

## Repositories

## Skills (evaluation lenses)

## Key Constraints

- Users are non-technical NGO staff (program managers, data coordinators, field staff)
- ~20 partner NGOs, ~₹2L/year budgets, small engineering team
- Users on slow internet and old devices — performance and simplicity matter
- Open source (AGPL-3.0)

## Bizdev — NGO Prospecting Pipeline

Scripts and commands for scraping give.do district listings and researching NGO prospects.

### Folder layout

| Path | Purpose |
|------|---------|
| `scripts/give_do_scraper.py` | Scrapes NGO name, location, FY revenue from give.do district pages → scraper sheet |
| `scripts/give_do_profile_scraper.py` | Fetches an NGO's give.do profile page; extracts cause areas, program count, impact metrics, leadership → research sheet |
| `scripts/run_scraper.sh` | One-click runner — checks deps, then runs the district scraper |
| `scripts/give_do_requirements.txt` | Python dependencies for both scraper scripts |
| `workdocs/bizdev/districts.json` | Registered districts, scraper sheet ID, research sheet ID, and service account path |
| `secrets/<key>.json` | Google service account key (gitignored) |

### Bizdev Commands

```
/bizdev/scraping/refresh-source
```
Re-scrapes all districts in `workdocs/bizdev/districts.json` and updates the scraper Google Sheet.

```
/bizdev/scraping/add-district <DistrictName>
```
Validates a new give.do district URL and registers it in `workdocs/bizdev/districts.json`.

```
/bizdev/research/research-ngo <NGO Name>
```
Looks up the NGO's give.do profile URL from the scraper sheet, scrapes cause areas / program count / impact metrics / leadership, and upserts a row into the "NGO Research" tab of the research Google Sheet.

### Key Config

All sensitive config lives in `workdocs/bizdev/districts.json` (gitignored). Do not hardcode these values in CLAUDE.md or any committed file.

- **Districts config**: `workdocs/bizdev/districts.json` (gitignored — read this file for sheet IDs and service account path)
- `sheet_id` — scraper sheet (district tabs)
- `research_sheet_id` — research sheet ("NGO Research" tab); must be shared with the service account

### Running the scraper manually

```bash
# All registered districts
bash scripts/run_scraper.sh

# One specific district
bash scripts/run_scraper.sh --district Kochi

# One-off URL (not in config)
bash scripts/run_scraper.sh --url "https://give.do/discover/project-district/Kochi/" --tab "Kochi"
```
