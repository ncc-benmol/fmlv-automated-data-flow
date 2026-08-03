# TODO

Working task list for the FMLV automated data flow. See [DESIGN.md](DESIGN.md) for the
reasoning behind these.

**Prototype target:** one manufacturer end-to-end producing an uploadable CSV by the middle
of day 2; five or six manufacturers by the end of day 3–4. Scope is **motorhomes and
campervans only**.

Legend: **[P]** = required for the prototype · **[F]** = future / optional, deliberately
deferred.

---

## Phase 0 — Foundations

- [x] **[P]** Obtain a real FMLV export and the NCC field guide
- [x] **[P]** Decide scope: motorhomes only, caravans deferred
- [x] **[P]** Manufacturer registry template (`data/manufacturers.csv` + README)
- [x] **[P]** Project design document
- [x] **[P]** Ben: populate `data/manufacturers.csv` with the pilot manufacturers
- [x] **[P]** Add dependencies: `pydantic`, `openpyxl`, `httpx`, `pypdf`, `playwright`, `pytest` (drop unused `numpy`)
- [x] **[P]** Set up `pytest` (`uv run pytest`; `testpaths` configured in `pyproject.toml`)
- [ ] **[P]** A `just`/`make` task for the common commands (run, sweep, test)
- [ ] **[F]** Ruff + type checking in CI

## Phase 1 — Canonical model and FMLV read/write

The only part of the system that knows about the 68 columns. No network, no API spend,
verifiable against the real Adria export.

- [x] **[P]** Layout enums for the 8 constrained groups (`fmlv/enums.py`)
- [x] **[P]** Column order and field classes — carry-through / required / layout / dealer (`fmlv/schema.py`)
- [x] **[P]** `Motorhome` canonical model (`fmlv/model.py`)
- [x] **[P]** Reader: `.xlsx` and `.csv` export → `list[Motorhome]` (`fmlv/io.py`)
- [x] **[P]** Writer: `list[Motorhome]` → upload CSV in exact column order (`fmlv/io.py`)
- [x] **[P]** Validation rules, reported as data not exceptions (`fmlv/validation.py`):
  - [x] exactly-one per single-select group, flagged if ambiguous rather than raised; many allowed for bed types
  - [x] `fridge` and `fridge_freezer` not both set (enforced by the `Refrigeration` enum's shape — a field can only hold one value)
  - [x] `payload == mtplm - mro` reconciles
  - [x] all required fields present
  - [x] `automatic_*` is all-or-nothing
- [x] **[P]** Round-trip test: read Adria export → write → read, assert models are identical (`tests/fmlv/test_io.py`)
- [x] **[P]** Run validation across the whole Adria export and eyeball the failures — see the data-quality note below
- [ ] **[F]** Same treatment for the touring caravan schema

## Phase 2 — Registry and run store

- [x] **[P]** Load and validate `data/manufacturers.csv`; skip `caravan`-only rows for now
      (`registry/loader.py` — a blank `categories` defaults to *included*, with a warning)
- [x] **[P]** SQLite schema + migrations: `run`, `source_snapshot`, `product`,
      `proposed_change`, `decision`, `verification` (`store/schema.sql`)
- [x] **[P]** Run lifecycle: start / finish / fail, with the manufacturer and trigger recorded
      (`store/runs.py`)
- [ ] **[F]** Retention policy for old snapshots and runs
- [ ] **[F]** Proper migrations once real run history exists — `schema.sql` is currently
      applied idempotently with `CREATE TABLE IF NOT EXISTS` and has no versioning

## Phase 3 — Fetch and snapshot

- [x] **[P]** HTTP fetcher with sane timeouts, retries and a descriptive user-agent
      (`fetch/http.py` — retries 5xx/429 with backoff, honours `Retry-After`, doesn't
      retry a plain 404)
- [x] **[P]** Snapshot every response to `data/snapshots/<manufacturer>/<run>/`
      (`paths.snapshot_dir`; `Fetcher`/`BrowserFetcher` write into whatever directory
      they're given)
- [x] **[P]** Content hashing + skip-if-unchanged — `FetchResult.unchanged` compares
      against a `previous_hash` the caller supplies. **Not yet wired up**: recording
      "verified unchanged" against the `verification` table is product-level and
      belongs with Phase 5's diff logic, once there's a product to attach it to
- [x] **[P]** Rate limiting / politeness between requests (`politeness_delay_seconds`)
- [x] **[P]** Playwright fetcher for JS-rendered sites (`fetch/browser.py`, tested
      against a real headless Chromium — see the one-time setup note below)
- [x] **[P]** PDF download and text extraction (download is just `Fetcher.fetch()`
      with an `application/pdf` response; `fetch/pdf.py` extracts the text)
- [ ] **[F]** `robots.txt` handling and a documented crawl policy
- [ ] **[F]** Re-diff a past run from snapshots without re-fetching
- [ ] **[F]** Conditional GET (`If-None-Match`/`ETag`) to skip re-downloading large
      unchanged PDFs — today every fetch re-downloads; fine at prototype scale

> **One-time local setup:** `BrowserFetcher` needs Chromium installed once per
> machine — run `uv run playwright install chromium` (~115 MB download). Already done
> on this dev machine; the Dockerfile (Phase 8) needs the same step baked in.

## Phase 4 — Exploration spike and the first adapter

Do this **before** committing to an adapter interface — the sites decide the shape.

- [ ] **[P]** Survey 3–5 pilot manufacturer sites: HTML tables? JSON blob? PDF only?
      JS required? Record findings in `data/manufacturers.csv` — **Adria done** (see
      below), Swift/Sunlight/Morelo/Rimor/Auto-Trail still to go
- [x] **[P]** Write up the general pattern, if there is one — first pass in
      `docs/adapters/README.md`, based on Adria alone so far; revisit once a second
      manufacturer's survey either confirms or breaks the "two fetches per product"
      hypothesis it describes
- [x] **[P]** Define the adapter interface: snapshot → `list[Motorhome]` + provenance
      (`adapters/base.py`: `Adapter`, `ExtractedMotorhome`, `Provenance`)
- [x] **[P]** First adapter end-to-end (Adria, since we have its baseline data) —
      `adapters/adria.py`; run live against the Matrix range, two rows matched the
      baseline's MRO/MTPLM/RRP exactly. Full write-up: `docs/adapters/adria.md`
- [x] **[P]** Provenance on every extracted field: source URL + snippet, for the reviewer
      — done for every numeric field the Adria adapter extracts
- [ ] **[P]** Adapters for the remaining pilot manufacturers
- [ ] **[F]** LLM fallback for PDF-only sources (Haiku 4.5 / Sonnet 5, Batch API for sweeps)
- [ ] **[F]** Adapter self-test harness — flag when a site changes shape and a parser silently stops finding products

## Phase 5 — Matching and diff

- [ ] **[P]** Match scraped products to existing `product_id`s (range + model name);
      persist the mapping so a rename doesn't create a duplicate
- [ ] **[P]** Field-level diff against the baseline export
- [ ] **[P]** Classify results: new product / changed field / unchanged-confirmed / disappeared
- [ ] **[P]** Prioritise tracked numerics; treat a layout-flag change on an existing
      product as high-suspicion
- [ ] **[P]** Leave `product_id` blank for genuinely new products
- [ ] **[F]** Model-year rollover handling — blocked on open question 1
- [ ] **[F]** Propose `archived = Yes` for products that vanish from a manufacturer's site
- [ ] **[F]** Materiality thresholds

## Phase 6 — Review app

- [ ] **[P]** FastAPI + HTMX app in the same container
- [ ] **[P]** Run list, then per-manufacturer change queue
- [ ] **[P]** Per-field accept / reject / correct, with a free-text corrected value
- [ ] **[P]** Source snippet and a link to the live manufacturer page beside each change
- [ ] **[P]** Persist every decision with who and when
- [ ] **[P]** Remember rejections so the next run doesn't re-propose them
- [ ] **[F]** Bulk accept for a whole product or a whole field across products
- [ ] **[F]** Authentication — currently a trusted internal network
- [ ] **[F]** Concurrent reviewers

## Phase 7 — Output and NCC integration

- [ ] **[P]** Emit the approved changes as a CSV in exact FMLV column order
- [ ] **[P]** Carry through `product_id`, `year`, `manufacturing_release_date`,
      `latest_model_id`, `images`, `archived` untouched
- [ ] **[P]** Validate the generated CSV before it is offered for upload
- [ ] **[P]** Playwright: log in to the NCC site and download the current export
- [ ] **[P]** Credential handling via environment variables
- [ ] **[F]** Automated upload — deliberately manual for now
- [ ] **[F]** Confirm upload validation rules with whoever runs the site (open question 3)

## Phase 8 — Packaging and operations

- [ ] **[P]** Dockerfile including Playwright browsers (`playwright install chromium`
      needs to run at image-build time — see the note under Phase 3; locally it's a
      ~115 MB one-time download)
- [ ] **[P]** `data/` volume for exports, snapshots, SQLite and generated uploads
- [ ] **[P]** CLI: `run <manufacturer>` and `sweep`
- [ ] **[P]** Cron-scheduled sweep
- [ ] **[P]** README covering how to run it, for whoever inherits it
- [ ] **[F]** Heavier scheduling through August–September peak season
- [ ] **[F]** Failure alerting (email/Slack) when a run or an adapter breaks
- [ ] **[F]** Backup of the SQLite file

---

## For Ben — things found while building Phases 1–3

Nothing here blocked the work (everything degrades to a warning, never a crash), but
each needs a human decision or a data fix.

- [ ] **Confirm what `manufacturer_id` actually is.** `data/manufacturers.csv` now has
      real values (`3` for Adria Mobil, `125` for Sunlight, `46` for Morelo, `26` for
      Swift, `75` for Rimor, `61` for Auto-Trail) instead of the slug the README
      originally described. These look like NCC-side IDs — please confirm the source
      system and whether they're guaranteed stable, then I'll finish updating the
      README's wording (already adjusted provisionally).
- [ ] **Sunlight and Morelo share the same `website_url`**
      (`https://www.morelo-reisemobile.de/en/`) in the registry — the loader catches
      this automatically as a `duplicate_website_url` warning (see
      `tests/registry/test_loader.py`), but it looks like a copy-paste slip between
      the two rows rather than something intentional. Please fix whichever one is wrong.
- [ ] **`categories` is blank for every row** in the current registry. The loader
      defaults a blank row to "included in motorhome runs" (the prototype's only scope
      anyway) so this doesn't block anything, but it'll matter the moment caravans are
      switched on — worth filling in when convenient rather than urgently.
- [ ] **`country` uses "UK"** for the British manufacturers; the README asks for
      ISO 3166-1 alpha-2 (`GB`). Not used for anything yet, so harmless today — flagging
      so it doesn't propagate if the field starts driving logic (e.g. language/currency
      handling) later.
- [ ] **Data quality in the sample export itself**, found by running validation across
      all 41 Adria products (`fmlv.validation.validate_all`): 5 products where the
      published payload doesn't reconcile with `mtplm - mro`, and 2 products with both
      "blown air" and "wet central" heating ticked (only one should be). These are
      pre-existing in the NCC's own current export, not introduced by anything here.
      Worth deciding whether the pipeline should ever propose a correction to the
      *baseline* itself when the manufacturer's own site reconciles cleanly, or leave
      that out of scope — noted as open question **8** below.
- [ ] **Adria's site model-naming won't line up with the baseline export's `model`
      column by exact string match.** The site names a configuration by layout code +
      trim (e.g. `"670 DC"` + `"Supreme Alde RHD"`); the baseline export has
      `"Supreme 670 DC"`. Same product, different word order. Phase 5's matching logic
      will need something looser than an exact match (see `docs/adapters/adria.md`).
      Also spotted while cross-checking: the baseline itself has an inconsistently
      cased `manufacturer_range` for at least one row (`"Matrix Supreme"` vs `"Matrix"`
      for a `Supreme MB` product) — pre-existing in the NCC's export, not introduced here.

## Open questions to chase

Tracked in [DESIGN.md §9](DESIGN.md). The ones that block work:

- [ ] **1** — does the website bump `year` on rollover, or do we write it? *(blocks Phase 5)*
- [ ] **2** — is there an NCC API? *(could replace Phase 7's Playwright work)*
- [ ] **3** — upload validation rules; does one bad row reject the file? *(shapes Phase 7)*
- [ ] **4** — permission to crawl; would any manufacturer supply a feed instead?
- [ ] **5** — European brands: always English and GBP via the UK importer?
- [ ] **6** — PDF vs HTML precedence, per manufacturer *(Phase 4 spike should answer)*
- [ ] **7** — controlled vocabularies beyond the enum groups
- [ ] **8** — should the pipeline ever propose fixing the *baseline* export when it
      disagrees with a manufacturer's own site, or only ever propose changes sourced
      from the manufacturer? *(shapes Phase 5's diff logic; see the data-quality note above)*

---

## Future investigations

Worth exploring once the prototype has proven itself:

- [ ] **[F]** Touring caravans — second schema and adapter set
- [ ] **[F]** Images and floorplans, specifically for determining the ~40 layout flags on
      **new** products where the floorplan may be the only reliable source
- [ ] **[F]** Direct structured feeds from cooperative manufacturers, replacing scraping
- [ ] **[F]** Fully automated upload
- [ ] **[F]** Coverage reporting — which products have not been verified recently
- [ ] **[F]** Trend data: price history per product over time, a by-product of run history
