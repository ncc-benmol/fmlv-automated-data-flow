# Manufacturer registry — field guide

> **Scope:** the prototype covers **motorhomes and campervans only**. Touring caravans are
> a later phase. Keep the `categories` column populated anyway — rows marked `caravan` are
> simply skipped by the runner for now, so caravans can be switched on without a schema change.

`manufacturers.csv` is the seed list that drives every run. One row per manufacturer.
Fill in what you know; leave the rest blank or `unknown` — the exploration spike will
populate the source-shape columns.

Only `manufacturer_key`, `fmlv_manufacturer`, `categories` and `website_url` are needed
to start work on a manufacturer. Everything else can be discovered.

## Columns

| Column | Required | Values | Notes |
|---|---|---|---|
| `manufacturer_key` | yes | lowercase slug, no spaces | Our stable internal ID, e.g. `adria`, `swift`, `bailey`. Never changes, even if the brand renames. Used for folder names and DB keys. |
| `fmlv_manufacturer` | yes | free text | **Must match the `manufacturer` column in the FMLV export exactly** (e.g. `Adria Mobil`). This is how we join scraped data back to existing product IDs. |
| `fmlv_display_name` | | free text | Matches the FMLV `manufacturer_display_name` column (e.g. `Adria`). |
| `categories` | yes | `motorhome`, `caravan`, or both comma-separated | Which FMLV export schema(s) this manufacturer appears in. Motorhome and caravan exports have different columns, so this decides which extraction schema we use. |
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
