# FMLV Automated Data Flow — project design

**Status:** prototype design, agreed 2026-08-03; deployment target revised 2026-08-05 (§8.2)
**Owner:** Ben Molyneaux (NCC)

---

## 1. Context

The NCC runs **Find My Leisure Vehicle (FMLV)**, a public tool that lets consumers browse
technical data and pricing across every UK caravan and motorhome manufacturer in one place.
The value of the tool depends entirely on the data being current and consistent.

Today, keeping it current is manual. Someone downloads a CSV export of the live data from
the NCC website, then works through each manufacturer's own website model by model,
comparing prices, weights and dimensions against the export and noting what has changed.
Manufacturers have been asked to supply their own data in the FMLV CSV format, but in
practice they do it slowly, incompletely, or not at all, and the submissions frequently
contain mistakes. So the NCC ends up doing the work anyway.

The data itself is well suited to automation: it is almost entirely numeric, hard-fact and
structured. What makes it laborious is the fan-out — roughly **100 manufacturers** and
**~2,000 products**, each published in a different place, in a different shape.

## 2. Goal

Automate the find-and-compare work so a human is only asked to do the thing a human is
actually needed for: **confirming that a proposed change is correct.**

Concretely, for one manufacturer at a time:

1. Take the current FMLV data as the baseline.
2. Visit the manufacturer's website and read the current published specification.
3. Detect every difference against the baseline.
4. Put those differences in front of an expert reviewer for accept / reject / correct.
5. Emit a CSV in the exact FMLV upload format containing the approved changes.

### Success criteria for the prototype

| Milestone | Target |
|---|---|
| One manufacturer end-to-end, producing a CSV good enough to actually upload | Middle of day 2 |
| Five or six manufacturers working | End of day 3–4 |

### Non-goals for the prototype

- Touring caravans (see §3).
- Writing to the NCC website automatically (see §6.2).
- Image handling and floorplan interpretation (see §10).
- Multi-user concurrency in the review step — one reviewer at a time is fine.

## 3. Scope

**Motorhomes and campervans only.** It is by far the larger and more important segment.
Touring caravans use a different export schema (62 columns vs 68, different type flags and
dimension sets) and are deferred to a later phase. The manufacturer registry carries a
`categories` column from day one so caravans can be switched on without a schema change.

---

## 4. The FMLV data model

Derived from a real Adria export (`csv-examples/…/motorhome-campervans.xlsx`, 42 products)
and the NCC's own field guide (`csv-examples/field_guide_motorhome.csv`).

### 4.1 Grain and identity

One row = one product = one vehicle at a particular specification, layout and price.
The primary key is **`product_id`, assigned by the NCC website**, not by this application.

- An existing product keeps its `product_id` across model years. A 2027 model is an
  **update to the 2026 row**, not a new row.
- A genuinely new product is submitted with `product_id` **blank**; the website's import
  process mints the ID.

### 4.2 Three classes of field, which behave very differently

| Class | Count | Examples | Changes? | Pipeline treatment |
|---|---|---|---|---|
| **Carry-through** | 6 | `product_id`, `year`, `manufacturing_release_date`, `latest_model_id`, `images`, `archived` | n/a | Guide says "PLEASE Leave as is!". Read from the export, written back untouched. Never extracted, never diffed. |
| **Numeric / identity** | ~14 required | `rrp_pounds`, `mro_kilograms`, `mtplm_kilograms`, `mh_*_mm`, `berths` | **Often — this is the job** | Extracted and diffed on every run. |
| **Layout flags** | ~40 | `island_bed`, `side_shower_toilet`, `rear_garage` | Almost never, for an existing product | Extracted for new products; for existing products, a change here is rare and treated as high-suspicion. |
| **Dealer-only** | 3 | `dealer`, `dealer_specials_range`, `dealer_model_variant` | n/a | "LEAVE BLANK UNLESS DEALER EXCLUSIVE". Not published on manufacturer sites — out of scope. |

This split is the single most important design input. **The recurring job is a handful of
numbers per product**, not 68 fields — which is what makes the running cost and the
reviewer's workload tractable.

### 4.3 The 40 layout flags are really 8 constrained groups

The field guide shows the Yes/No columns are not independent:

| Group | Rule | Columns |
|---|---|---|
| Body type | exactly one | 8 |
| Sleeping area | exactly one | 4 |
| Bed types | **many allowed** | 7 |
| Kitchen location | exactly one | 3 |
| Bathroom layout | exactly one | 7 |
| Lounge location | exactly one | 3 |
| Heating | exactly one | 3 |
| Refrigeration | at most one ("do not put YES in both") | 2 |
| `rear_garage`, `microwave` | plain yes/no | 2 |

**Decision:** model these internally as **enums, not booleans**, expanding to the 40 columns
only when writing the upload CSV. Three payoffs:

- an extractor picks from a closed list instead of emitting 40 independent flags;
- a diff reads as `bathroom_layout: rear → side` rather than two confusing boolean flips;
- the exactly-one rules are enforced by the type rather than by a check that can be forgotten.

Implemented in `src/product_model/enums.py`.

### 4.4 Derived and cross-checkable values

`mh_payload_kilograms == mtplm_kilograms - mro_kilograms` holds exactly for every row in
the sample, automatic-variant figures included. We still **store** the published value for
round-trip fidelity, but the identity is used as a free confidence check on any extraction:
a payload that doesn't reconcile is a signal the parse went wrong.

### 4.5 The automatic-gearbox variant

`automatic_mro_kilograms`, `automatic_mh_payload_kilograms`, `automatic_rrp_pounds`,
`automatic_price_min_range_pounds` are an **all-or-nothing group** describing the automatic
version of the same model, where one is offered. Effectively a second price and weight set
per product, and they must be tracked alongside the manual figures.

### 4.6 Discontinuation

Handled by the `archived` Yes/No column, not by deleting rows.

---

## 5. Architecture

See [docs/architecture-overview.html](docs/architecture-overview.html) for a diagram of
the pipeline: the NCC baseline and the manufacturer's site as two lanes converging on the
diff engine, the human review gate, and the CSV loop back to the NCC site, with SQLite
logging every stage. In outline:

1. Playwright downloads the current export from the NCC site — the baseline.
2. The manufacturer's site is fetched and snapshotted; unchanged pages (by content hash)
   are skipped.
3. A per-manufacturer adapter turns a snapshot into canonical `Motorhome` objects.
4. The diff engine matches products to `product_id` and compares field by field.
5. A reviewer accepts, rejects or corrects each proposed change in the FastAPI + HTMX
   review app.
6. Approved changes are emitted as a CSV in FMLV's exact column order, uploaded to the
   NCC site by hand.

Every run, fetch, proposed change and decision is logged to SQLite throughout.

### 5.1 Component responsibilities

| Component | Responsibility |
|---|---|
| `product_model/` | Canonical model, schema, read/write of FMLV exports, validation rules. The only place that knows about the 68 columns. |
| `registry/` | Manufacturer list (`config/manufacturers.csv`) — who to visit, where, and in what shape. |
| `fetch/` | HTTP + headless browser retrieval, snapshotting, content hashing, politeness/rate limiting. |
| `adapters/` | One module per manufacturer. Turns a snapshot into canonical `Motorhome` objects. The only manufacturer-specific code. |
| `diff/` | Matching scraped products to existing `product_id`s, then field-level comparison. |
| `webapp/` | The FastAPI + HTMX app. |
| `store/` | SQLite: run history, decisions, hashes. |

---

## 6. Key decisions

### 6.1 Deterministic parsers first, LLM as a narrow fallback

**Decision:** each manufacturer gets a hand-written (Claude-assisted, at development time)
deterministic parser. An optional per-source LLM fallback exists but stays unused until a
PDF-only manufacturer forces it.

**Why:** near-zero running cost, fast, reproducible, and diffable. Claude is used at
*development* time via Claude Code to author each adapter, which is where the leverage is.

**Trade-off, recorded honestly:** ~100 parsers is real ongoing maintenance, and each one
breaks when a site is redesigned. The fallback exists so that one awkward PDF-only
manufacturer cannot block the pilot. If parser maintenance becomes the dominant cost, the
balance should be revisited.

### 6.2 NCC site: automated download, manual upload

**Decision:** Playwright logs in and downloads the current export automatically. The
generated upload CSV is written to a folder and uploaded **by hand**.

**Why:** removes the recurring chore without ever letting the system write to the live
public site. Keeps a human gate on the only irreversible step. Whether the site offers a
proper API is still unknown (§9) — if it does, this is the piece that gets replaced first.

Implemented in `fetch/ncc.py` (Phase 7): `download_export` logs in and saves one
manufacturer's current export, `NccCredentials.from_env` reads the login from
`FMLV_NOVA_LOGIN_EMAIL`/`FMLV_NOVA_LOGIN_PASSWORD` (§8's secrets row). Surveyed against the real
site 2026-08-06 (TODO.md's "For Ben" note is resolved): the login page is a plain
form, but there is **no single "download everything" button** — the NCC's admin panel
(Laravel Nova, at `/nova/...`) only offers exports **one manufacturer at a time**, via
a resource action ("Export Products by Supplier") that returns a zip containing
`motorhome-campervans.xlsx` and `touring-caravans.xlsx`. This is a bigger shape
difference than a config tweak: `download_export` takes a `supplier_name` argument,
and `data/exports/` is scoped per manufacturer (`paths.manufacturer_exports_dir`) so
`cli.latest_export` can never pick up a different manufacturer's stale file as the
baseline. The supplier dropdown's labels don't always match `fmlv_manufacturer`
(`"Adria Mobil"` vs `"Adria Caravans & Motorhomes"`), so the registry carries a
separate `ncc_supplier_name` column. `fmlv fetch-export <manufacturer>` (Phase 8's
`cli.py`) is the command that actually triggers a download — previously
`download_export` existed but nothing called it. Open question 2 (is there a proper
export API?) is now answered: no, this resource-action flow is the only route. The
generated-CSV half of this section — `output/build.py` turning approved decisions
into an upload-ready CSV in `schema.COLUMNS` order, validated before it's offered — is
also Phase 7.

### 6.3 Review via a small web app

**Decision:** FastAPI + HTMX, served by the same Windows service that hosts the pipeline.

**Why:** others will run and maintain this, not just the author, and reviewer time is the
real bottleneck. The app puts the source snippet and a link to the live manufacturer page
directly beside each proposed change, which is where a reviewer's time actually goes.
Accept / reject / correct is **per field**, and the reviewer can type a corrected value.

Implemented in `webapp/app.py` (Phase 6): `create_app(db_path)` builds the app against
one SQLite file, so tests point it at a throwaway one rather than needing a running
server. `store/changes.py` is where a run's diff (Phase 5's `diff_products`) becomes the
`proposed_change`/`verification` rows the app reads and writes — including the §6.9
year-rollover suggestion, which is deliberately just another field proposal rather than a
separate UI mechanism. Not yet built: the service wrapper itself (Phase 8, §8.2),
authentication, and concurrent reviewers — all already scoped as non-goals/[F] in TODO.md.

### 6.4 Change detection: everything, no thresholds

Any difference from the baseline is surfaced — no materiality threshold, no tolerance.
A £5 price move and a 1 kg MTPLM change are both reported. Thresholds can be added later
if reviewers find the volume unmanageable.

### 6.5 Confirming unchanged data is a first-class output

If a product's published data matches the baseline exactly, that is recorded as a positive
**"verified unchanged on <date>"** result, not silence. Knowing a figure was checked and
confirmed last Tuesday is nearly as valuable to the NCC as knowing it changed.

### 6.6 Snapshot everything

Every fetched page and PDF is written to disk before parsing.

**Why:** it makes runs reproducible and debuggable without re-fetching; it lets a parser bug
be fixed and the run re-diffed offline; it provides the evidence trail behind any change a
reviewer approved; and it is the basis of the content hash that keeps costs near zero.
Storage is trivial at this scale.

### 6.7 Everything is logged

Every run, every fetch, every proposed change and every reviewer decision is recorded in
SQLite. There is no formal audit requirement yet, but the cost of logging now is far lower
than the cost of reconstructing history later.

### 6.8 Rejections are remembered

If a reviewer rejects a proposed change, the next run must not re-propose the same change.
Exact semantics to be worked through when the review step is built.

### 6.9 Model-year rollover is always a human decision (resolves open question 1)

**Decision:** the pipeline never bumps `year` on its own — it stays a carry-through field
exactly as the guide says ("PLEASE Leave as is!"). A 2027 model updating the 2026 row's
`year` happens only when a human triggers it, one of two ways:

1. **Globally**, for every product of a manufacturer, as a parameter given when a run is
   triggered (Phase 8's CLI).
2. **Per product, at review time** (Phase 6's UI), via a checkbox offered only when a
   change was actually detected *and* the run fell within the window manufacturers
   typically publish next year's models, **June–September**. This is a plausibility
   signal, not a determination — ticking it is still the reviewer's call.

**Why:** `year` drives which model-year row a change lands on, so getting it wrong is
worse than leaving it for a human — consistent with §6.3's per-field accept/reject/correct
and with never letting the pipeline silently reinterpret a carry-through field.

Implemented in `diff/year_rollover.py`: `bump_year` is the shared primitive both routes
call; `in_rollover_window` is the seasonal check, computed as part of Phase 5's diff logic
and exposed as `ProductDiff.year_rollover_eligible` for the review app to render. Both
routes are now built, and both converge on the same branch in `store/changes.py:persist_diff`
— route 1 as the CLI's `fmlv run <manufacturer> --bump-year` (`bump_year_all`), route 2 as
the seasonal suggestion needing no flag. Either way the result is an ordinary
`proposed_change` row a reviewer still has to accept: nothing writes `year` on its own.

---

## 7. Storage

**SQLite**, a single file under the application's `data\` directory on the server.
Right-sized for one server, one reviewer, ~2,000 products, and it keeps deployment to a
single process with no database server to install or administer.

Tables, in outline:

| Table | Purpose |
|---|---|
| `run` | One row per execution: manufacturer, trigger (manual/scheduled), started/finished, status. |
| `source_snapshot` | URL, fetch time, content hash, path on disk, run reference. |
| `product` | Local mirror of known products keyed by `product_id`, plus the manufacturer's own identifier for matching. |
| `proposed_change` | Run, product, field, old value, new value, source URL + snippet, confidence. |
| `decision` | Reviewer action on a proposed change: accept / reject / correct, corrected value, who, when. |
| `verification` | Product + field + run, recording "checked, unchanged". |

---

## 8. Operations

| Concern | Decision |
|---|---|
| Runtime | Python 3.14 via `uv`, running directly on a **Windows Server VM** provided by the client's IT (see §8.2). No container. |
| Triggers | Manual "run manufacturer X" from the UI/CLI, **and** an automated schedule read from `config/schedule.csv` and run by an in-process scheduler inside the review app itself (§8.4) — not an OS-level job. |
| Cadence | Per schedule.csv entry, one manufacturer (and optionally one or more ranges) at a time. Weekly or monthly in quiet months; **August–September is peak season** for model-year changes and warrants tighter frequencies, set per entry rather than globally. |
| Headless browser | Playwright available for JS-rendered sites. `playwright install chromium` is run once on the VM as part of provisioning (~115 MB) rather than baked into an image. |
| Persistence | A `data\` directory on the VM: exports, snapshots, SQLite file, generated uploads. Backed up by whatever backs up the VM. |
| Secrets | Anthropic API key and NCC credentials from a `.env` file on the VM, readable only by the service account. Never committed. |

### 8.1 Cost control

Target is **under £5/month, £20 ceiling**. Three mechanisms, in order of impact:

1. **Deterministic parsers** — the chosen primary path costs nothing per run.
2. **Content-hash gating** — a page whose hash is unchanged since the last run is never
   re-parsed and never sent to a model. In a steady month most pages are unchanged.
3. **Model tiering, if the fallback is ever used** — Claude Haiku 4.5 ($1/$5 per MTok) for
   clean structured content, Claude Sonnet 5 ($3/$15; introductory $2/$10 until
   2026-08-31) for PDFs and messy pages, and the Batch API (−50%) for scheduled runs
   where latency does not matter.

### 8.2 Deployment target: Windows Server VM

**Decision (2026-08-05, revising the original plan):** the application is deployed as a
**Windows service on a Windows Server VM**, not as a Docker container on a Linux host.

**Why:** the client's IT team has provisioned a Windows Server VM, and that is what is
actually available. Nothing in the design depended on Linux or on containers — the
application is a Python process, a directory of files and a SQLite file, all of which are
platform-neutral. The cost of this change is confined to packaging and scheduling.

What it changes, concretely:

| Was | Is now |
|---|---|
| Dockerfile, `docker run`, image registry | `uv sync` from a checkout on the VM |
| Container restart policy | **NSSM** wrapping `uvicorn` as a Windows service, set to auto-start |
| Docker volume for `data/` | A directory on the VM's data disk |
| `cron` for the scheduled sweep | Nothing OS-level at all — an in-process APScheduler inside the review app (§8.4), reading `config/schedule.csv` |
| Container logs / `docker logs` | NSSM's stdout/stderr redirection to rotating files under `logs\` |
| Environment variables passed by the container runtime | `.env` file on disk, plus NSSM's `AppEnvironmentExtra` |

What it does **not** change: the CLI, the review app, the storage model, or any of §4–§7.
Code must stay path-safe (`pathlib`, no hardcoded `/`) and must not assume a POSIX shell —
a constraint the codebase already meets, since it has been developed on Windows throughout.

**Trade-off, recorded honestly:** we lose the reproducible-image guarantee, so "it works on
my machine" risk moves onto the provisioning scripts. Mitigated by keeping provisioning as
checked-in PowerShell under `deploy\windows\` rather than as undocumented manual steps, and
by the §8.3 smoke test proving the host can actually run and serve a service before the
real application is deployed to it.

### 8.3 Deployment smoke test

Before the real application goes anywhere near the VM, a deliberately trivial service is
deployed to it — one FastAPI endpoint returning the current date and time — to prove four
things independently of any FMLV logic: Python and `uv` install and run on the host; a
process can be registered as an auto-starting Windows service; the service survives a
reboot; and the port is reachable from a developer machine. Kept in `deploy\smoketest\`
so it can be redeployed any time the host configuration is in doubt.

**Result, 2026-08-05:** it works. uv installed, the service registered and auto-started,
and a developer machine reached it with no firewall change beyond the local Windows
Firewall rule. **Outbound access is unrestricted and unproxied** (PyPI, astral.sh, GitHub
and thencc.org.uk all reachable, no proxy variables set), which resolves open question 9
and means §5's fetching needs no proxy configuration — though four sample domains are not
the same as the ~100 manufacturer sites, so a category-based web filter would still only
surface on the first real sweep.

The service also came back on its own after a reboot with nobody logged in, answering
about two minutes after the machine started. The host is `NCC-AI1`, Windows Server 2025,
Python 3.14.6.

One finding needs fixing before the real deployment: **the VM's clock is set to Pacific
time**, not UK time. Everything this application *stores* is UTC-aware, so no data would
be wrong, but `§6.9`'s June–September rollover window is computed from the **local** date
and would open and close a day late for part of each day, and scheduled runs would fire
eight hours off `schedule.csv`'s `first_run` times. Fixed on the host
(`tzutil /s "GMT Standard Time"`), not in code.

A second finding carries into the real deployment: **the VM is dual-homed**
— `192.168.16.43` is reachable from the office LAN, `10.47.17.232` is not. The application
should therefore be reached on `192.168.16.43`, and since the service binds `0.0.0.0` it
currently listens on both interfaces; §6.3's review app has no authentication yet, so
binding the reachable interface only is the safer default until it does.

### 8.4 Automated scheduling

**Decision (2026-08-13, revising §8.2's original plan):** recurring runs are driven by
an in-process scheduler inside the review app itself, not a separate Windows Task
Scheduler job calling an `fmlv sweep` CLI. The web app is already expected to run
continuously on the server (it's a Windows service, §8.2), so adding one more
in-process scheduled job keeps everything in a single deployable unit rather than
running two services that both need to be kept alive and both need access to the same
`data\` directory.

**The master file is `config\schedule.csv`**, not a database table — a plain CSV a
non-developer can open in Excel to add, remove or pause an automated run, with a field
guide in `config\schedule.README.md`. One row per manufacturer (optionally narrowed to
one or more named ranges); blank ranges means the whole manufacturer. Each row states
a `first_run` time and a repeat frequency (`frequency_value` + `frequency_unit`:
hours/days/weeks) — no cron syntax to get wrong by hand.

**"Is this due yet" is computed fresh every time**, from two things that already
exist rather than a third piece of state to keep in sync: `schedule.csv` itself, and
the most recent matching row in the existing `run` table (§7) with `trigger =
'scheduled'`. A schedule with no prior run yet is due at `first_run`; otherwise it's
due at *(that run's start time)* + *(the entry's frequency)* — regardless of whether
that run succeeded or failed, so a failure is not retried early; the next attempt
waits for the normal interval, same as any other manufacturer's next scheduled slot.
Implemented in `src\scheduling\` (`loader.py` mirrors `registry\loader.py`'s
per-row-`Issue` pattern; `engine.py` does the due-check).

**The scheduler itself** is an APScheduler `BackgroundScheduler`, started on FastAPI's
`lifespan` when the review app boots (`webapp\app.py`'s `create_app`), polling every
five minutes by default. Each tick (`check_schedule`) re-reads `schedule.csv` and the
manufacturer registry from disk — so an edit takes effect on the next tick, no restart
needed — and, for every due entry, calls the same `execute_run(trigger="scheduled")`
pipeline the CLI and the manual "Trigger a run" page both use, resolving any named
ranges through the same `cli.resolve_ranges` the due-check itself used to look up
"when did this last run" — the two can't drift apart because they're the same code
path. A manufacturer with a run already in progress (any trigger) is skipped for that
tick rather than starting a second concurrent run.

**`/schedules`** is a read-only page (§6.3) listing every entry, its resolved scope,
whether it's enabled/paused/erroring, and when it last ran / is next due — the
schedule's counterpart to the existing "Review runs" page. It exists so a schedule
change is visible somewhere other than by reading the CSV, but the CSV remains the
only place a schedule is actually created or changed at this stage.

---

## 9. Open questions

| # | Question | Blocks |
|---|---|---|
| ~~1~~ | ~~The field guide marks `year` "PLEASE Leave as is!", but a 2027 model is said to update the 2026 row with year fields changing. Does the website bump `year` itself, or do we write the new year?~~ **Resolved — see §6.9**: we write it, and only ever on explicit human instruction. | Model-year rollover handling |
| ~~2~~ | ~~Does the NCC site expose an export/import API, or is headless browser automation the only route?~~ **Resolved 2026-08-06 — see §6.2.** No API: the admin panel's "Export Products by Supplier" resource action (one manufacturer at a time, a zip download) is the only route. | Confirmed §6.2's approach |
| 3 | What validation does the upload run, and does one bad row reject the whole file? | Upload CSV strategy |
| 4 | Do we have standing to crawl manufacturer sites, and could any manufacturer supply a feed directly instead? | Politeness policy; could remove work entirely for cooperative brands |
| 5 | For European brands, is UK-market data always published in English and GBP by the UK importer? | Language/currency handling |
| 6 | Where HTML and PDF disagree, PDF is assumed authoritative — to be confirmed per manufacturer during the exploration spike. | Source precedence |
| 7 | Are there controlled vocabularies we must map manufacturer terminology onto beyond the enum groups in §4.3? | Extraction mapping |
| 8 | Should the pipeline ever propose fixing the *baseline* export itself when it disagrees with a manufacturer's own site, or only ever propose changes sourced from the manufacturer? Raised by running validation against the real Adria export, which surfaced 5 pre-existing payload mismatches and 2 rows with two heating options both ticked (see TODO.md). | Phase 5 diff logic |
| ~~9~~ | ~~On the Windows VM (§8.2): is there unrestricted **outbound** internet, and can a chosen port be reached **inbound** from a developer machine?~~ **Resolved 2026-08-05 — see §8.3.** Outbound is unrestricted and unproxied; inbound works on one of the VM's two addresses. | Nothing — Phase 3 needs no proxy handling |

---

## 10. Deferred / future

Not in the prototype, but designed around so they can be added without rework:

- **Touring caravans** — second schema, second set of adapters.
- **Images and floorplans** — the `images` column is carried through untouched today.
  Worth revisiting for *new* products, where the ~40 layout flags must be determined and
  the floorplan image may be the only reliable source.
- **Direct manufacturer feeds** — for any manufacturer willing to publish structured data,
  an adapter that reads it beats scraping outright.
- **Automated upload** — once the pipeline has earned trust.
- **Materiality thresholds** — if reviewers find the change volume unmanageable.
- **Multi-reviewer / concurrent review** — currently single-reviewer by design.
