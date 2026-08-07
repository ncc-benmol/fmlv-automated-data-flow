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
      they're given). **Bug found and fixed during local testing (§T6)**: the snapshot
      filename was derived from the URL alone, so a URL fetched more than once with
      different content (e.g. one POST route shared by every page, like Adria's
      Livewire endpoint) silently overwrote its own earlier snapshot. Filenames now
      fold in the content hash too — same content still dedups to one file, different
      content no longer collides.
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
> on this dev machine; the Windows Server VM (Phase 8) needs the same step run once
> during provisioning.

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

- [x] **[P]** Match scraped products to existing `product_id`s (range + model name);
      persist the mapping so a rename doesn't create a duplicate — token-based
      matching (`diff/matching.py:match_products`), since exact string matching
      doesn't work (see the Adria word-order note below); one-to-one greedy
      assignment by score. Persistence is `store/products.py:upsert_seen`, matching
      first on `fmlv_product_id` (stable NCC identity) and falling back to exact
      `manufacturer_range`/`model` for products with no id yet, updating the existing
      row in place on a rename rather than inserting a duplicate
- [x] **[P]** Field-level diff against the baseline export (`diff/compare.py:compare_fields`)
      — only diffs fields the adapter's `provenance` dict actually covers, so a field
      an adapter never attempts (e.g. Adria's layout flags) is never proposed as
      "changed"
- [x] **[P]** Classify results: new product / changed field / unchanged-confirmed / disappeared
      (`diff/classify.py:diff_products` — every scraped and every baseline product
      gets exactly one outcome, per DESIGN.md §6.5)
- [x] **[P]** Prioritise tracked numerics; treat a layout-flag change on an existing
      product as high-suspicion (`diff/compare.py:sort_changes` orders tracked
      numerics first, layout flags last; `FieldChange.high_suspicion`)
- [x] **[P]** Leave `product_id` blank for genuinely new products (`ProductDiff.fmlv_product_id`
      is `None` for `ChangeKind.NEW_PRODUCT`)
- [x] **[P]** Model-year rollover handling — open question 1 resolved (see DESIGN.md
      §6.9): the pipeline never bumps `year` itself. `diff/year_rollover.py` gives
      both future routes a shared primitive (`bump_year`) and a seasonal plausibility
      check (`in_rollover_window`, June-September); `ProductDiff.year_rollover_eligible`
      is set for a `CHANGED_FIELD` product seen in that window. Two things still to
      build on top of this:
      - [x] **[P]** Phase 8 CLI: a run-trigger parameter to bump `year` for every
            product of a manufacturer (scenario 1 — user-supplied, not automatic) —
            `fmlv run <manufacturer> --bump-year`, which widens the same
            `store/changes.py:persist_diff` branch route 2 uses (`bump_year_all`)
            rather than adding a second mechanism. Still only ever a *proposal*: it
            is reviewed and accepted per product like any other field
      - [x] **[P]** Phase 6 review UI: a per-product checkbox, shown only when
            `year_rollover_eligible` is true, that calls `bump_year` on accept
            (scenario 2) — done as **another `proposed_change` row** (`field="year"`),
            not a separate mechanism: `store/changes.py:persist_diff` proposes it with
            `source_url=None` and an explanatory snippet, so accepting it goes through
            the exact same accept/reject/correct plumbing as every other field. Shown
            with a "possible rollover" badge (`review/templates/partials/change_row.html`)
- [ ] **[F]** Propose `archived = Yes` for products that vanish from a manufacturer's site
- [ ] **[F]** Materiality thresholds
- [x] **[P]** Wire `diff_products` results into `proposed_change`/`verification` rows
      — done in Phase 6: `store/changes.py:persist_diff`. `DISAPPEARED` products are
      still not persisted (no actionable proposal exists for them yet — see the
      `archived = Yes` item above).
- [ ] **[P]** Caching function - aim to not re-download exactly the same PDF assets I've we've already got a copy in data/snapshots. The except here would be if the existing pdf is more than 1 month old, in which case we should re-download anyway.

## Phase 6 — Review app

- [x] **[P]** FastAPI + HTMX app in the same container — `review/app.py:create_app`;
      the container itself is Phase 8, not built yet, but the app has no other
      runtime dependency beyond the SQLite file it's pointed at
- [x] **[P]** Run list, then per-manufacturer change queue — `GET /`, `GET /runs/{id}`
      (`review/templates/runs.html`, `run_detail.html`), grouped by product via
      `store.list_change_queue`
- [x] **[P]** Per-field accept / reject / correct, with a free-text corrected value —
      `POST /runs/{id}/changes/{id}/decide`; a blank value on "correct" is rejected
      with an inline error rather than recorded (`review/app.py:decide`)
- [x] **[P]** Source snippet and a link to the live manufacturer page beside each
      change — `proposed_change.source_url`/`source_snippet`, carried straight from
      the adapter's `Provenance` through `persist_diff`, rendered in
      `partials/change_row.html`
- [x] **[P]** Persist every decision with who and when — `decision.decided_by`/
      `decided_at` (`store/decisions.py:record_decision`); a decision is never
      edited in place, a later one just supersedes it (`latest_decision`), so the
      full history survives (DESIGN.md §6.7)
- [x] **[P]** Remember rejections so the next run doesn't re-propose them —
      `store/changes.py:was_previously_rejected`, matched on the exact
      (product, field, new_value) triple; a *different* corrected figure from the
      manufacturer is still proposed (DESIGN.md §6.8)      
- [x] **[F]** Bulk accept for a whole product or a whole field across products
- [ ] **[F]** Authentication — currently a trusted internal network
- [ ] **[F]** Concurrent reviewers

## Phase 7 — Output and NCC integration

- [x] **[P]** Emit the approved changes as a CSV in exact FMLV column order —
      `output/build.py:build_upload_motorhomes` applies every `accept`/`correct`
      decision (per DESIGN.md §6.3) on top of the baseline `Motorhome`, one field at a
      time (`apply_field`); `write_upload_csv` hands the result to `product_model.io.write_csv`,
      which already writes `schema.COLUMNS` order. A product with no `accept`/`correct`
      decision at all contributes nothing — there's nothing approved to upload for it.
- [x] **[P]** Carry through `product_id`, `year`, `manufacturing_release_date`,
      `latest_model_id`, `images`, `archived` untouched — true by construction: an
      existing product starts from a deep copy of its baseline row, and no field is
      touched unless a decision says so. `year` is the one exception that *can* be
      touched, via the same year-rollover proposal Phase 5/6 already route through
      `proposed_change` (DESIGN.md §6.9) — `apply_field` treats it like any other field.
- [x] **[P]** Validate the generated CSV before it is offered for upload —
      `output/build.py:write_upload_csv` runs `product_model.validation.validate_all` over the
      built rows before writing. Consistent with DESIGN.md's "report as data, not
      exceptions" (§1 Phase 1's validation): a validation problem doesn't block the
      write, it's returned as `UploadResult.issues` for a reviewer to see next to the
      CSV, with `UploadResult.has_errors` as the "was this actually clean" check the
      Phase 8 CLI can act on. (Open question 3 — what the NCC upload path itself
      enforces — is still unanswered; this is our own pre-flight check, not theirs.)
- [x] **[P]** Playwright: log in to the NCC site and download the current export —
      `fetch/ncc.py:download_export`. **Surveyed against the real site 2026-08-06**
      (Ben walked through it live): the login page is a plain form at
      `/nova/login`, but there is no single "download everything" button — exports
      come from the admin panel's ("Nova") "Export Products by Supplier" resource
      action, **one manufacturer at a time**, as a zip containing
      `motorhome-campervans.xlsx` + `touring-caravans.xlsx`. `NccSiteConfig`'s
      URLs/selectors are now the real ones, not placeholders.
      `tests/fetch/test_ncc.py` covers the full flow against local fixtures.
- [x] **[P]** Credential handling via environment variables — `fetch/ncc.py`:
      `NccCredentials.from_env()` reads `NCC_LOGIN_EMAIL`/`NCC_LOGIN_PASSWORD`, raising
      `NccCredentialsError` rather than proceeding with a blank credential. Never
      hardcoded, never committed, matching DESIGN.md §8's secrets row. `.env` is set
      up on the dev machine (gitignored, per `.env.example`).
- [x] **[P]** Wire `download_export` into the CLI — previously written but never
      called from anywhere except tests. `fmlv fetch-export <manufacturer>`
      (`cli.py:_fetch_export_command`) is the new command; it resolves the
      manufacturer from the registry, requires `ncc_supplier_name` to be set (a clear
      `CommandError` if not), and writes to
      `data/exports/<manufacturer_id>_<manufacturer>/<date>_<manufacturer>_motorhome-campervans.xlsx`,
      and prints progress ("logging in...", "triggering the export download...") so a
      terminal isn't silent for the several seconds a real browser login takes.
- [x] **[P]** Registry: `ncc_supplier_name` column (`data/manufacturers.csv`,
      `registry/models.py`, `registry/loader.py`) — the exact label a manufacturer has
      in the NCC's supplier dropdown, which doesn't always match `fmlv_manufacturer`
      (e.g. `"Adria Mobil"` vs `"Adria Caravans & Motorhomes"`). Filled in for all six
      pilot manufacturers.
- [x] **[P]** Scope `data/exports/` per manufacturer — since the NCC only offers
      exports one manufacturer at a time, `paths.manufacturer_exports_dir` and
      `cli.latest_export(manufacturer_id=...)` fix a real bug the old single shared
      `data/exports/` directory had: downloading manufacturer A's export and then
      running manufacturer B would have silently used A's stale file as B's baseline.
- [x] **[P]** CLI and review-app entry points to generate the upload CSV, kept
      deliberately separate from `run`/the run-trigger so a CSV is never produced
      before a reviewer has actually decided anything — `fmlv generate-upload <run_id>`
      (`cli.py:_generate_upload_command`) and a "Generate upload CSV" button on the run
      detail page (`webapp/app.py:generate_upload_route`, `GET /runs/{id}/upload.csv`
      to download it), both wrapping the existing `output.generate_upload`. Warns
      (doesn't block) if changes on the run are still pending a decision.
- [ ] **[F]** Automated upload — deliberately manual for now
- [ ] **[F]** Confirm upload validation rules with whoever runs the site (open question 3)

## Phase 8 — Packaging and operations

**Deployment target changed 2026-08-05:** the client's IT has provisioned a **Windows
Server VM**, not the Linux/Docker host originally assumed. See DESIGN.md §8.2. Docker is
off the table; the application runs as a Windows service. Everything below is rewritten
accordingly — no application code is affected, only packaging and scheduling.

### 8a — Prove the host (deployment smoke test, DESIGN.md §8.3)

Deliberately ahead of the real deployment: prove the VM can run and serve *anything*
before debugging FMLV logic on it at the same time.

- [x] **[P]** Trivial FastAPI service returning the current date/time
      (`deploy/smoketest/smoke_service.py` — one file, PEP 723 inline dependencies so
      `uv run` fetches its own deps and the whole toolchain gets exercised)
- [x] **[P]** Provisioning script: install `uv`, verify Python 3.14
      (`deploy/windows/01-bootstrap.ps1`)
- [x] **[P]** Service install script: NSSM wrap + auto-start + firewall rule
      (`deploy/windows/02-install-smoketest.ps1`), with a matching uninstall
      (`03-uninstall-smoketest.ps1`)
- [x] **[P]** Reachability check runnable from the dev machine
      (`deploy/windows/check-from-local.ps1`)
- [x] **[P]** Runbook for the whole sequence (`deploy/windows/README.md`)
- [x] **[P]** Ben: run the sequence on the VM — **done 2026-08-05, it works.** uv
      installed, the service registered and auto-started, and the dev machine reached
      it. No IT firewall change was needed beyond the local Windows Firewall rule
      `02-install-smoketest.ps1` adds.
- [x] **[P]** Record the outcome: **the VM is dual-homed**, and only one of its two
      addresses is reachable from a dev machine.

      | Address | Reachable from dev machine? |
      |---|---|
      | `192.168.16.43` | **yes** — this is the one to use |
      | `10.47.17.232` | no |

      Port **8099** (the smoke test default). The 10.47/16 address is presumably a
      separate management or client network that isn't routed to the office LAN — not a
      problem, but it has two consequences worth carrying into 8b:

      - the review app should be reached on **192.168.16.43**, and that's the address to
        quote when asking IT to open the real application's port;
      - the service binds `0.0.0.0`, so it currently listens on *both* interfaces.
        Decide in 8b whether to keep that or bind the reachable address only —
        binding one interface is the tighter default for an app with no authentication
        (Phase 6's `[F]` item), given we don't know what else is on 10.47/16.
- [x] **[P]** Outbound internet from the VM — all four `01-bootstrap.ps1` checks passed
      (PyPI, astral.sh, GitHub, thencc.org.uk), no proxy set. Open question 9 resolved;
      Phase 3 needs no proxy handling. The real workload still isn't proven — see the
      caveat under question 9
- [x] **[P]** Service **survives a reboot** with nobody logged in — confirmed
      2026-08-05. After a restart the service was answering 128 seconds after it
      started, with no interactive login. **Phase 8a is complete: all four things the
      smoke test exists to prove are proven.**
- [x] **[P]** Host facts, from the smoke test's own reply: hostname **`NCC-AI1`**,
      Windows Server 2025, Python 3.14.6, checkout at
      **`C:\apps\fmlv-automated-data-flow`**, service running as `NCC-AI1$` — i.e. the
      machine account, so it is on **`LocalSystem`** (see 8b)
- [x] **[P]** **Set the VM's timezone to UK time** 
- [ ] **[F]** Render stored timestamps in UK local time in the review app — the
      templates currently print the raw UTC ISO string (`run_detail.html`, `runs.html`,
      `partials/change_row.html`). Unambiguous, but an hour off wall-clock during BST
      and ugly to read. Cosmetic, and independent of the timezone item above
- [ ] **[P]** Ask IT for the VM's proper hostname/FQDN — an IP is fine for a smoke test,
      but the review app's users shouldn't be given a bare address that can change
- [ ] **[P]** Tear the smoke test down once 8b is deployed
      (`03-uninstall-smoketest.ps1`) — it has no business outliving the question it
      answered

### 8b — Deploy the real application

- [ ] **[P]** Provisioning script for the app proper: checkout, `uv sync`,
      `uv run playwright install chromium`, create `data\` and `logs\`
- [ ] **[P]** NSSM service definition for the review app (`uvicorn`), auto-start,
      stdout/stderr redirected to rotating files under `logs\`
- [ ] **[P]** `data\` directory on the VM for exports, snapshots, SQLite and generated
      uploads — decide the drive/path with IT, and confirm it's inside the VM backup
- [ ] **[P]** `.env` on the VM for `NCC_LOGIN_EMAIL`/`NCC_LOGIN_PASSWORD` and the
      Anthropic key, ACL'd to the service account only
- [ ] **[P]** Decide the service account — the smoke test ran as `LocalSystem` (it
      reported `NCC-AI1$`, the machine account), which is the install script's default.
      Simplest, but more privilege than this needs, and a machine account is an
      awkward thing to ACL a credentials file to. A dedicated local account is the
      tidier answer now that there'll be a `.env` holding NCC login details
- [ ] **[F]** Update procedure: how a new version gets onto the VM (git pull + `uv sync`
      + service restart, scripted) without a container image to swap

### 8c — CLI, scheduling and handover

- [x] **[P]** CLI: `run <manufacturer>` (`cli.py`) — the first code to perform the whole
      sequence: registry → `run` record → adapter → diff → `proposed_change`/
      `verification`. `execute_run` takes injectable fetcher factories so the pipeline
      is testable without a network or a browser (`tests/test_cli.py`). Options:
      `--export`, `--data-dir`, `--registry`, `--trigger`, `--range` (repeatable, for a
      one-range smoke run), `--bump-year`. Exit codes: 0 ok, 1 run failed, 2 bad request.
      Prints live progress during a run — `execute_run(on_progress=...)`, threaded
      through to `adria.collect()`, which narrates each range/product boundary and every
      silent-skip case to the terminal (added during §T6's full-sweep test, where a
      multi-minute silent run was the original complaint)
- [ ] **[P]** CLI: `sweep` — every runnable manufacturer with an adapter, in
      `pilot_priority` order (`registry.active_motorhome_manufacturers` already returns
      exactly that list; `adapters.adapter_for` returns `None` for the ones to skip)
- [ ] **[P]** Scheduled sweep via **Windows Task Scheduler** (was: cron) — a task running
      `uv run fmlv sweep` as the service account, checked in as a `schtasks` /
      `Register-ScheduledTask` script under `deploy\windows\` so it isn't a click-path
      no one can reproduce
- [ ] **[P]** README covering how to run it, for whoever inherits it — must cover the
      Windows service: start/stop, where the logs are, what to do after a reboot
- [ ] **[F]** Heavier scheduling through August–September peak season
- [ ] **[F]** Failure alerting (email/Slack) when a run or an adapter breaks — a failed
      Scheduled Task is silent by default, so this matters more here than it would
      under a supervised container
- [ ] **[F]** Backup of the SQLite file — confirm whether the VM-level backup covers it,
      or whether a scheduled `VACUUM INTO` copy is needed


## For Ben — things found while building Phases 1–3

Nothing here blocked the work (everything degrades to a warning, never a crash), but
each needs a human decision or a data fix.

- [ ] **Confirm what `manufacturer_id` actually is.** `data/manufacturers.csv` now has
      real values (`3` for Adria Mobil, `125` for Sunlight, `46` for Morelo, `26` for
      Swift, `75` for Rimor, `61` for Auto-Trail) instead of the slug the README
      originally described. These look like NCC-side IDs — please confirm the source
      system and whether they're guaranteed stable, then I'll finish updating the
      README's wording (already adjusted provisionally).
- [x] **Sunlight and Morelo share the same `website_url`**
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
      all 41 Adria products (`product_model.validation.validate_all`): 5 products where the
      published payload doesn't reconcile with `mtplm - mro`, and 2 products with both
      "blown air" and "wet central" heating ticked (only one should be). These are
      pre-existing in the NCC's own current export, not introduced by anything here.
      Worth deciding whether the pipeline should ever propose a correction to the
      *baseline* itself when the manufacturer's own site reconciles cleanly, or leave
      that out of scope — noted as open question **8** below.
- [x] **Adria's site model-naming won't line up with the baseline export's `model`
      column by exact string match.** Resolved in Phase 5: `diff/matching.py` scores
      candidates by token overlap (range+model word bags) instead of requiring an
      exact match. `tests/diff/test_real_adria_integration.py` confirms it against the
      real fixtures — the scraped `"670 DC Supreme Alde RHD"` correctly lands on the
      baseline's `"Supreme 670 DC"` (product_id 4147) at a 0.667 score. The 0.5
      threshold (`matching.DEFAULT_THRESHOLD`) is chosen against this one case —
      **worth re-checking once a second manufacturer's naming is in hand**, per the
      docstring's own note. Also spotted while cross-checking: the baseline itself has
      an inconsistently cased `manufacturer_range` for at least one row
      (`"Matrix Supreme"` vs `"Matrix"` for a `Supreme MB` product) — pre-existing in
      the NCC's export, not introduced here; token matching tolerates it fine since
      "Matrix" is still a shared token either way.
- [x] **NCC login/export page structure — resolved 2026-08-06.** Surveyed live with
      Ben logged in: `NccSiteConfig` now holds the real URLs and selectors, and
      `fetch/ncc.py`'s module docstring records the flow. Turned out to be more than a
      config change — the site exports one manufacturer at a time, not "everything",
      so `download_export` gained a `supplier_name` parameter and the registry gained
      `ncc_supplier_name`. No export/import API exists (open question 2, resolved) —
      this resource-action flow is the only route.

## Open questions to chase

Tracked in [DESIGN.md §9](DESIGN.md). The ones that block work:

- [x] **1** — does the website bump `year` on rollover, or do we write it? *(blocks Phase 5)*
      **Resolved** — we write it, only on explicit human instruction, never automatically.
      See DESIGN.md §6.9 and the Phase 5 entry above.
- [x] **2** — is there an NCC API? **Resolved 2026-08-06** — no; the admin panel's
      per-supplier export resource action is the only route. See DESIGN.md §6.2.
- [ ] **3** — upload validation rules; does one bad row reject the file? *(shapes Phase 7)*
- [ ] **4** — permission to crawl; would any manufacturer supply a feed instead?
- [ ] **5** — European brands: always English and GBP via the UK importer?
- [ ] **6** — PDF vs HTML precedence, per manufacturer *(Phase 4 spike should answer)*
- [ ] **7** — controlled vocabularies beyond the enum groups
- [ ] **8** — should the pipeline ever propose fixing the *baseline* export when it
      disagrees with a manufacturer's own site, or only ever propose changes sourced
      from the manufacturer? *(shapes Phase 5's diff logic; see the data-quality note above)*
- [x] **9** — Windows VM networking. **Resolved 2026-08-05**, both halves, by the
      Phase 8a smoke test.
      *Inbound:* reachable from the dev machine on `192.168.16.43:8099` with no IT
      firewall change needed; the VM's other address, `10.47.17.232`, is not reachable.
      *Outbound:* all four checks passed (PyPI, astral.sh, GitHub, thencc.org.uk) and
      no proxy variables were set — so Phase 3's fetching needs no proxy configuration
      and no `HTTP_PROXY` plumbing into the service. **Caveat:** those four are a
      representative sample, not the real workload; the ~100 manufacturer sites and the
      Anthropic API were not individually tested, so a *category*-based block (e.g. a
      web filter on unclassified or foreign domains) would still show up later. The
      first real sweep on the VM is what actually proves it


## Future investigations

Worth exploring once the prototype has proven itself:

- [ ] **[F]** Touring caravans — second schema and adapter set
- [ ] **[F]** Images and floorplans, specifically for determining the ~40 layout flags on
      **new** products where the floorplan may be the only reliable source
- [ ] **[F]** Direct structured feeds from cooperative manufacturers, replacing scraping
- [ ] **[F]** Fully automated upload
- [ ] **[F]** Coverage reporting — which products have not been verified recently
- [ ] **[F]** Trend data: price history per product over time, a by-product of run history
