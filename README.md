# Dalgo Bizdev — NGO Prospecting Pipeline

This tool helps you find and research NGOs listed on [give.do](https://give.do). It pulls structured data into two Google Sheets that you own: a **Discovery Sheet** with thousands of NGOs across cities, and a **Research Sheet** with deep profiles of the NGOs you want to evaluate.

> **You'll need:** Claude Code installed, and a Google account to connect your sheets.

---

## First-Time Setup

Setup takes about 5 minutes and only needs to be done once.

1. Open this folder in Claude Code
2. Create two blank Google Sheets in your Google Drive — one for discovery, one for research (you can name them anything)
3. Run `/bizdev-setup` in Claude Code — it will ask for your sheet links and handle everything else
4. Once setup completes, run `/bizdev/scraping/refresh-source` to do your first data pull

Your configuration is stored locally on your machine and is never shared with others.

---

## Day-to-Day Usage

### Step 1 — Build your NGO discovery list

```
/bizdev/scraping/refresh-source
```

Claude will scrape give.do for every city you've configured and populate your Discovery Sheet. This takes 15–20 minutes per run. When it finishes, open your Discovery Sheet and look at the **Combined** tab — it has all NGOs across all your cities, deduplicated.

To add a new city to your list:

```
/bizdev/scraping/add-district <City Name>
```

### Step 2 — Research specific NGOs

Once you've spotted NGOs worth evaluating in the Combined tab, run:

```
/bizdev/research/research-ngo "NGO Name"
```

You can pass multiple names at once:

```
/bizdev/research/research-ngo "Bosconet" "Pallium India" "Goonj"
```

Use the name exactly as it appears in the Combined tab. Claude will fetch each NGO's full give.do profile and add a row to your Research Sheet. If an NGO is already in the sheet, it's skipped — you can safely re-run without duplicating data.

---

## What the Sheets Contain

### Discovery Sheet

| Column | What it is |
|--------|-----------|
| NGO Name | Name as listed on give.do |
| HQ Location | City or region |
| FY Year | Financial year of the revenue figure |
| Total Revenue ₹ | Annual revenue (number, filterable) |
| Profile URL | Direct link to their give.do page |

One tab per city you've added, plus a **Combined** tab that merges and deduplicates everything.

### Research Sheet (NGO Research tab)

| Column group | What it is |
|---|---|
| Name, Profile URL, Website | Identity and links |
| HQ City, Overview | Location and mission statement |
| Programs | All program names, comma-separated |
| Cause area columns | One column per sector (Education, Health, Child & Youth Development, etc.) — ticked `TRUE` if the NGO works in that area |
| State columns | One column per Indian state — ticked `TRUE` if the NGO operates there |
| Budget ₹ | Annual revenue pulled from the discovery data |
| Leader 1–3 | Name, role, and LinkedIn for up to 3 leaders |

The ticked columns make filtering easy — for example, you can instantly filter for NGOs working in **Education** in **Maharashtra**.

---

## What's in This Folder

- **scripts/** — the automation behind both commands. No need to touch these.
- **workdocs/bizdev/** — your personal configuration, created during setup. Not committed to git.
- **secrets/** — your Google connection key, also created during setup. Never share this file.

---

## Cities

You start with no cities configured. Cities are added during `/bizdev-setup` or anytime with `/bizdev/scraping/add-district`.

Some cities that work well with give.do: Bangalore, Delhi, Mumbai, Chennai, Pune, Hyderabad, Kolkata, Ahmedabad, Lucknow, Jaipur, Thiruvananthapuram.
