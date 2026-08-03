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
- [ ] **[P]** Ben: populate `data/manufacturers.csv` with the pilot manufacturers
- [ ] **[P]** Add dependencies: `pydantic`, `openpyxl`, `httpx`, `pytest` (drop unused `numpy`)
- [ ] **[P]** Set up `pytest` and a `just`/`make` task for the common commands
- [ ] **[F]** Ruff + type checking in CI

## Phase 1 — Canonical model and FMLV read/write

The only part of the system that knows about the 68 columns. No network, no API spend,
verifiable against the real Adria export.

- [x] **[P]** Layout enums for the 8 constrained groups (`fmlv/enums.py`)
- [x] **[P]** Column order and field classes — carry-through / required / layout / dealer (`fmlv/schema.py`)
- [x] **[P]** `Motorhome` canonical model (`fmlv/model.py`)
- [ ] **[P]** Reader: `.xlsx` and `.csv` export → `list[Motorhome]`
- [ ] **[P]** Writer: `list[Motorhome]` → upload CSV in exact column order
- [ ] **[P]** Validation rules, reported as data not exceptions:
  - [ ] exactly-one per single-select group; many allowed for bed types
  - [ ] `fridge` and `fridge_freezer` not both set
  - [ ] `payload == mtplm - mro` reconciles
  - [ ] all required fields present
  - [ ] `automatic_*` is all-or-nothing
- [ ] **[P]** Round-trip test: read Adria export → write → read, assert models are identical
- [ ] **[P]** Run validation across the whole Adria export and eyeball the failures
- [ ] **[F]** Same treatment for the touring caravan schema

## Phase 2 — Registry and run store

- [ ] **[P]** Load and validate `data/manufacturers.csv`; skip `caravan`-only rows for now
- [ ] **[P]** SQLite schema + migrations: `run`, `source_snapshot`, `product`,
      `proposed_change`, `decision`, `verification`
- [ ] **[P]** Run lifecycle: start / finish / fail, with the manufacturer and trigger recorded
- [ ] **[F]** Retention policy for old snapshots and runs

## Phase 3 — Fetch and snapshot

- [ ] **[P]** HTTP fetcher with sane timeouts, retries and a descriptive user-agent
- [ ] **[P]** Snapshot every response to `data/snapshots/<manufacturer>/<run>/`
- [ ] **[P]** Content hashing + skip-if-unchanged, recording "verified unchanged"
- [ ] **[P]** Rate limiting / politeness between requests
- [ ] **[P]** Playwright fetcher for JS-rendered sites
- [ ] **[P]** PDF download and text extraction
- [ ] **[F]** `robots.txt` handling and a documented crawl policy
- [ ] **[F]** Re-diff a past run from snapshots without re-fetching

## Phase 4 — Exploration spike and the first adapter

Do this **before** committing to an adapter interface — the sites decide the shape.

- [ ] **[P]** Survey 3–5 pilot manufacturer sites: HTML tables? JSON blob? PDF only?
      JS required? Record findings in `data/manufacturers.csv`
- [ ] **[P]** Write up the general pattern, if there is one
- [ ] **[P]** Define the adapter interface: snapshot → `list[Motorhome]` + provenance
- [ ] **[P]** First adapter end-to-end (Adria, since we have its baseline data)
- [ ] **[P]** Provenance on every extracted field: source URL + snippet, for the reviewer
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

- [ ] **[P]** Dockerfile including Playwright browsers
- [ ] **[P]** `data/` volume for exports, snapshots, SQLite and generated uploads
- [ ] **[P]** CLI: `run <manufacturer>` and `sweep`
- [ ] **[P]** Cron-scheduled sweep
- [ ] **[P]** README covering how to run it, for whoever inherits it
- [ ] **[F]** Heavier scheduling through August–September peak season
- [ ] **[F]** Failure alerting (email/Slack) when a run or an adapter breaks
- [ ] **[F]** Backup of the SQLite file

---

## Open questions to chase

Tracked in [DESIGN.md §9](DESIGN.md). The ones that block work:

- [ ] **1** — does the website bump `year` on rollover, or do we write it? *(blocks Phase 5)*
- [ ] **2** — is there an NCC API? *(could replace Phase 7's Playwright work)*
- [ ] **3** — upload validation rules; does one bad row reject the file? *(shapes Phase 7)*
- [ ] **4** — permission to crawl; would any manufacturer supply a feed instead?
- [ ] **5** — European brands: always English and GBP via the UK importer?
- [ ] **6** — PDF vs HTML precedence, per manufacturer *(Phase 4 spike should answer)*
- [ ] **7** — controlled vocabularies beyond the enum groups

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
