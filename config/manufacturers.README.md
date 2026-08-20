# Manufacturer registry — field guide

> **Scope:** the prototype covers **motorhomes and campervans only**. Touring caravans are
> a later phase. Keep the `categories` column populated anyway — rows marked `caravan` are
> simply skipped by the runner for now, so caravans can be switched on without a schema change.

`manufacturers.csv` is the seed list that drives every run. One row per manufacturer.
Fill in what you know; leave the rest blank or `unknown` — the exploration spike will
populate the source-shape columns.

Only `manufacturer_id`, `fmlv_manufacturer` and `website_url` are needed to start work
on a manufacturer. Everything else can be discovered. `categories` is technically
optional too — a blank value is treated as "include in motorhome runs" by default
(see below) — but fill it in when known, since a blank value also emits a loader
warning every time.

## Columns

| Column | Required | Values | Notes |
|---|---|---|---|
| `manufacturer_id` | yes | integer | The manufacturer's identifier. Used as the stable key for folder names, DB rows and matching runs across time — never changes, even if the brand renames. **Open question:** confirm what system this ID actually comes from and whether it's guaranteed stable (see TODO.md) — it's currently populated with NCC-side numeric IDs (e.g. `3` for Adria Mobil) rather than a slug we invented. |
| `fmlv_manufacturer` | yes | free text | **Must match the `manufacturer` column in the FMLV export exactly** (e.g. `Adria Mobil`). This is how we join scraped data back to existing product IDs. |
| `fmlv_display_name` | | free text | Matches the FMLV `manufacturer_display_name` column (e.g. `Adria`). |
| `ncc_supplier_name` | for `fmlv fetch-export` | free text | The exact label this manufacturer has in the NCC site's own "Export Products by Supplier" dropdown (`/nova/resources/products` → `...` → Export Products by Supplier). Not always the same string as `fmlv_manufacturer` (e.g. `Adria Mobil` vs `Adria Caravans & Motorhomes`) — confirm by opening the dropdown, don't guess. |
| `categories` | | `motorhome`, `caravan`, or both comma-separated | Which FMLV export schema(s) this manufacturer appears in. Blank is treated as "motorhome" by default (the prototype's only scope right now) — the loader raises a `categories_unset` warning so the gap gets noticed rather than silently assumed forever. |
| `status` | | `active` / `paused` / `retired` | `paused` = skip in scheduled sweeps but still runnable manually. `retired` = brand no longer trading. |
| `pilot_priority` | | integer, 1 = first | Ordering for the prototype. Leave blank for anything not in the pilot set. |
| `country` | | ISO 2-letter | `GB`, `DE`, `SI`, `IT`… Flags where we may hit non-English pages or EUR pricing. |
| `website_url` | yes | URL | The manufacturer's primary/group site. |
| `uk_site_url` | | URL | UK importer or UK-market site, where it differs from the group site. For European brands this is usually the authoritative source for GBP pricing and UK-spec weights. |
| `models_index_url` | | URL | The page that lists all current models/ranges. This is the crawl entry point — the single most valuable field to fill in. |
| `price_list_url` | | URL | Current retail price list, usually a PDF. Likely the authoritative price source. |
| `brochure_url` | | URL | Full brochure PDF, often carries the technical specification tables. |
| `specs_format` | | `html_table` / `json` / `pdf` / `mixed` / `unknown` | Filled in during the exploration spike. Decides whether we write a deterministic parser or send it to Claude. |
| `needs_javascript` | | `yes` / `no` / `unknown` | Whether the spec data is server-rendered or requires a headless browser. Cost/latency driver. |
| `login_required` | | `yes` / `no` | Dealer-portal gated data. |
| `ncc_member` | | `yes` / `no` | Context for the permission conversation. |
| `contact_name` | | free text | Named contact at the manufacturer. |
| `contact_email` | | email | |
| `contact_phone` | | phone | |
| `last_verified` | | `YYYY-MM-DD` | When a human last confirmed the URLs in this row still resolve. |
| `notes` | | free text | Anything odd: separate sites per sub-brand, model-year timing, known data-quality problems. |

## Conventions

- Save as UTF-8. Quote any field containing a comma.
- One row per **FMLV manufacturer name**, not per brand family. If two brands share a
  parent but appear under different `manufacturer` values in the export, they get two rows.
- If a manufacturer publishes motorhomes and caravans on separate sites, put the primary
  in `models_index_url` and note the second URL in `notes` — we'll split the row if it
  turns out to be a recurring pattern.

## Loading and validation

`src.registry.load(path)` reads this file and never raises on a
single bad row — problems come back as a list of `Issue`s alongside whatever did parse
successfully. It also checks two things across rows that are easy to get wrong by hand:

- **Duplicate `manufacturer_id`** — flagged as an error; both rows are still loaded.
- **Duplicate `website_url`** — flagged as a warning. This is usually a copy-paste
  mistake between adjacent rows (two different brands pointing at the same site) —
  see the open to-do about Sunlight/Morelo in TODO.md.

The five blank rows at the bottom of the template (with only `status=active` filled
in) are placeholders for the next manufacturer and are silently skipped, not reported
as broken.
