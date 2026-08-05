
# Local end-to-end test plan (Phases 1–7)

Written 2026-08-04 after reviewing Phases 1–6 as merged (commit `820eab5`) plus Phase 7
as specified above — Phase 7 was still in progress on a teammate's branch at the time of
writing, so **§T7 and §T8 are written against the Phase 7 spec, not against its code.**
Adjust the function/CLI names in those two stages to whatever actually lands.

The goal is a run that goes registry → fetch → adapt → diff → **SQLite** → review UI →
approved-changes CSV, on this machine, with real writes to a real database file.

## T-pre — what has to exist before an end-to-end run

Gaps in the *harness*, not bugs in Phases 1–6. The first is done; the other two still
need doing before §T3.

- [x] **T-pre-1 — There was no orchestrator.** Every stage existed and was unit-tested,
      but nothing performed the *sequence*. **Resolved by pulling Phase 8's CLI forward**
      — `fmlv run <manufacturer>` (`cli.py`), rather than a throwaway driver script.
      Three things it settles that any driver would have had to:
      - **The baseline is filtered to one manufacturer before `diff_products`.**
        `matching.match_products` requires this and nothing enforces it — an unfiltered
        baseline would let an Adria product match another brand's row. The filter is
        `Motorhome.manufacturer == Manufacturer.fmlv_manufacturer`, and
        `tests/test_cli.py` pins it with a two-brand export.
      - **A run that raises is recorded as `failed` with the message**, not left stuck at
        `status='running'`. Snapshots taken before the failure stay on disk.
      - **Which adapter runs which brand** — `adapters.adapter_for`, keyed on
        `fmlv_manufacturer` rather than the not-yet-confirmed `manufacturer_id`.
- [x] **T-pre-2 — `.gitignore` did not cover `data/`.** A real run writes
      `data/run_store.sqlite3`, `data/snapshots/**`, `data/exports/**` and
      `data/uploads/**` into a tracked tree; the live Adria sweep alone is 34 PDFs.
      `/data/snapshots` was added early (before §T6's live runs); `/data/exports`,
      `/data/uploads` and `/data/run_store.sqlite3` finished off here, before committing
      — `data/manufacturers.csv` and its README are unaffected and stay tracked.
- [x] **T-pre-3 — The review app had no server entry point.** `review.app.create_app` is
      a factory taking a `db_path`, so `uvicorn review.app:app` doesn't work. **Resolved**:
      `review/serve.py` builds a module-level `app` against `paths.db_path()` (or
      `FMLV_DB_PATH`, to point at a different file), so `uvicorn
      fmlv_automated_data_flow.review.serve:app` serves the real store.

## Known gaps — expected, do not chase these as failures

Found while reviewing; all are already-scoped `[F]`/later-phase items, but each will look
like a bug during a first end-to-end run if you are not expecting it.

- **`source_snapshot` is never written.** Both fetchers snapshot to disk, but no code
  inserts the row. The table will be empty after a successful run, and — the real
  consequence — **skip-if-unchanged cannot work across runs**: `FetchResult.unchanged`
  needs a `previous_hash` the caller supplies, and there is nowhere to get one from. Two
  identical consecutive runs will both re-fetch and re-parse everything. Phase 3 flags
  the wiring as outstanding; this is where it bites.
- **`DISAPPEARED` products are not persisted** (`store/changes.py`), so a product missing
  from the site produces no row anywhere. Deliberate — see the `archived = Yes` `[F]`.
- **Every changed product will also propose a `year` bump.** Today (2026-08-04) is inside
  the June–September rollover window, so `year_rollover_eligible` is true for every
  `CHANGED_FIELD` product. Expect roughly double the proposals you would see in
  February, each with a "possible rollover" badge and no source URL. Correct behaviour,
  surprising volume.
- **`test.py` in the repo root** is a leftover scrap (`print(f"{ii} hello")`). Not picked
  up by pytest (`testpaths = ["tests"]`), but delete it while you are in here.

## T0 — Environment and unit baseline

- [x] `uv run pytest -q` → **129 passed** is the current state on `master`; anything less
      means fix that before going further. (`uv run` warns that `VIRTUAL_ENV` does not
      match `.venv` — harmless, it uses `.venv`.)
- [x] `uv run playwright install chromium` — one-time, ~115 MB. Already done on this
      machine; needed on any other. `tests/fetch/test_browser.py` passing confirms it.
- [x] Confirm the sample export is readable and put a copy where a run will look for it:
      copy `csv-examples/1785753111-…/motorhome-campervans.xlsx` to
      `data/exports/2026-08-04/motorhome-campervans.xlsx`. Until §T8 works, this stands in
      for the Playwright download.

## T1 — Store smoke: does it actually write to a real DB file?

The first stage that writes to disk. Everything below runs against `data/run_store.sqlite3`.

- [x] `store.connect(paths.db_path())` on a path that does not exist yet → file created,
      schema applied. Then `sqlite3 data/run_store.sqlite3 ".tables"` → all six tables.
- [x] `start_run` → `finish_run` → `list_runs` round-trip against that file.
- [x] Re-connect to the **same** file and confirm the schema re-applies without error and
      the earlier run survives — this is the `CREATE TABLE IF NOT EXISTS` idempotency
      claim, and it has only ever been exercised against fresh tmp files in tests.
- [x] Confirm `PRAGMA foreign_keys` is enforced: insert a `proposed_change` with a
      nonsense `product_id` and expect an `IntegrityError`.

## T2 — Baseline read and validation, against the real export

- [x] `io.read_export()` the copy from §T0 → 41 motorhomes, `result.issues` reviewed —
      2 `ambiguous_layout_group` (Supreme 670 SL and 670 DC, both heating options ticked).
- [x] `validation.validate_all()` across all of them → **5 `payload_mismatch`, 2
      `automatic_payload_mismatch`, 1 `layout_group_unset`**. These are pre-existing in
      the NCC's own export (see the data-quality note below) — a *different* count means
      something regressed.
- [x] Round-trip: `write_csv` the parsed rows to `data/uploads/roundtrip.csv`, read it
      back, assert equality — confirmed `True` against the real file, 41 rows both ways.

## T3 — Offline pipeline: fixtures → diff → SQLite

Do this **before** touching the live site: call `cli.execute_run` directly with an
adapter that replays the captured fixtures in `tests/adapters/fixtures/` (the way
`tests/diff/test_real_adria_integration.py` builds its products) and
`_fetcher_factory`/`_browser_factory` set to something inert. This isolates
*persistence* bugs from *scraping* bugs — if §T6 then fails, you already know which
half. `tests/test_cli.py` already does exactly this with synthetic products; the value
of doing it by hand is doing it against the **real 41-row export** and a real
`data/run_store.sqlite3` you can then open and poke at.

- [x] Run it → `run` row reaches `status='succeeded'`, `finished_at` set (run #2).
- [x] `product` rows created, one per matched/new product — matched to `fmlv_product_id`
      4147, the real Matrix 670 DC, not created as new.
- [x] `proposed_change` rows: the known Matrix 670 DC case lands as
      `mtplm_kilograms 3500 → 3650` and `mro_kilograms 3184 → 3228`, with `source_url`
      pointing at the PDF and a non-empty `source_snippet`. Also proposed: berths/seats
      3→4, `rrp_pounds` 93950→93920, and a `year` 2026→2027 rollover suggestion
      (`source_url=None`) — expected, we're inside the June–September window.
- [x] `verification` rows exist for the confirmed dimensions (`mh_length_mm`,
      `mh_width_mm`, `mh_height_mm`) — the §6.5 "checked and unchanged" claim, now
      landing in a real table for the first time.
- [x] `PersistResult` counts match what is actually in the tables (proposed=6,
      verified=3, year_rollover_proposed=1).
- [x] **Re-ran on the same DB (run #3).** `SELECT COUNT(*) FROM product` stayed at 1;
      `first_seen_run_id` stayed 2, `last_seen_run_id` moved to 3 — updated in place,
      not duplicated.

## T4 — Review app against T3's database

Serve the same file §T3 just wrote:

```powershell
uv run uvicorn fmlv_automated_data_flow.review.serve:app --port 8000
```

- [x] `GET /` lists the §T3 runs with the right status badges.
- [x] `GET /runs/{id}` groups proposals by product; tracked numerics sort above layout
      flags; the "possible rollover" badge appears on the `year` rows.
- [x] Each row shows the source snippet and a working link — **caught and fixed a bug
      in the T3 driver script** (not the app): it hardcoded a placeholder PDF URL
      instead of calling `adria.technical_data_pdf_url()` like the real adapter does,
      so run #2/#3's PDF-sourced fields linked to a fake address. Re-ran as run #4 with
      the fix; links now resolve correctly.
- [x] **Accept** one change → row swaps in via HTMX, `decision` row written with
      `decided_by` and `decided_at`.
- [x] **Correct** one with a typed value → stored in `decision.corrected_value`.
- [x] **Correct with an empty value** → inline error, and confirmed **no** `decision` row
      was written.
- [x] **Reject** one (`berths`, run #2) — carried into §T5.
- [x] Decide the same change twice → two `decision` rows, the later one superseding;
      history preserved, nothing edited in place.
- [x] `GET /runs/999999` → confirmed a genuine `404` (JSON body via FastAPI's default
      `HTTPException` handling, not a styled page — fine, the check only asked for
      "404, not a 500").

## T5 — Rejection memory across runs

The §6.8 promise, which needs two real runs against one database to test at all.

- [x] Re-run the driver (**run #4**, done a step early while fixing the T4 PDF-link
      bug). The `berths` change rejected in §T4's run #2 did **not** reappear;
      `PersistResult.suppressed_rejections == 1`, confirmed against the actual
      `proposed_change` rows.
- [x] Patched the PDF text in memory (`"Nr. of berths 4"` → `"...5"` — editing the JSON
      product had no effect, since `_build_extracted_motorhome` prefers the PDF-derived
      spec over the JSON figure) and re-ran (**run #6**): `berths: 3 → 5` **is** proposed,
      `suppressed_rejections == 0`. Confirms only the literal rejected value (`4`) is
      remembered, not the field.

## T6 — Live run against adria.co.uk

First stage that touches the network. Be polite: `Fetcher` defaults to a 1s delay, and
the full `DEFAULT_RANGES` sweep is 9 browser page loads plus **one PDF fetch per
configuration** (~50 requests).

- [x] **Start with one range**, which is what `--range` exists for:
      ```powershell
      uv run fmlv run Adria --range Matrix
      ```
      (`--export` isn't needed — `latest_export()` picks the newest file under
      `data/exports/` automatically.) **Run #7**: 7 products scraped, matching the
      Phase 4 write-up's "Matrix range (7 configurations)". The 670 DC figures matched
      §T3's fixture exactly (`mro 3184→3228`, `mtplm 3500→3650`, `rrp 93950→93920`),
      confirming the fixture data used in T3–T5 genuinely reflects the live site.
- [x] Check `data/snapshots/3/7/` — 1 `.html` (range page), 1 `.json` (captured
      Livewire response), 7 `.pdf` (one per product), all correctly suffixed and
      real-sized (PDFs 2–6 MB, matching the documented "~5 MB" spec sheet).
- [x] Compare the live result against §T3's fixture result. Four of the five changed
      products showed the same `mtplm 3500→3650` "extended homologation" bump the
      Phase 4 write-up described. One (`MB 670 DC`, product 7212) behaved differently
      — `mtplm` *decreased* and `mro` jumped further — plausibly a different base
      chassis ("MB" = Mercedes-Benz, vs. the others' Fiat base), confirmed by hand below
      rather than assumed.
      - [x] Rejection memory (§T5) held up on live data too: `berths` was correctly
            suppressed only for product 4147 (the one it was rejected against in run
            #2), and proposed normally for the other four Matrix products.
      - [x] Counted for silent skips, per the checklist below — none, for this one range:
            all 7 configurations the JSON offered had a resolvable PDF URL, and all 7
            fetched PDFs yielded all 7 spec fields via regex.
- [x] Sanity-check a handful of extracted figures by opening the PDF by hand — opened
      the `MB 670 DC` PDF (`.../cxensr5200w031-14/pdf`, the odd one out above) and
      confirmed MRO 3381 kg / MTPLM 3880 kg / width 2290 mm match what was extracted.
- [x] Then the full sweep — `uv run fmlv run Adria`. **Found and fixed a real bug along
      the way**: `adria.collect()` had no progress output, so a multi-minute sweep gave
      no feedback — added an `on_progress` callback (called at each range/product
      boundary and on every skip/empty-extraction case), wired to `print` in the real
      CLI (`tests/test_cli.py` pins that `execute_run` threads it through). Turning that
      on immediately surfaced a second, more serious bug it was meant to help watch
      for: **`fetch/http.py`'s `snapshot_filename()` hashed only the URL, not the
      content**, and Adria's Livewire endpoint is one fixed POST route shared by every
      range page — so each range's captured JSON silently overwrote the previous one on
      disk. Run #8 (before the fix) kept only 1 of 9 JSON snapshots; `collect()`'s own
      results were unaffected (it reads each file immediately after writing, before the
      next range's overwrite), but the on-disk evidence trail DESIGN.md §6.6 promises
      was broken for 8 of 9 ranges. Fixed by folding the content hash into the filename
      (`fetch/http.py`, `fetch/browser.py`); `tests/fetch/test_http.py` pins both that a
      repeated identical fetch still dedups to one file and that two different
      responses from the same URL no longer collide. Re-ran as **run #9**: all 9 ranges'
      JSON snapshots now survive distinctly, confirmed against the live site. Final
      count, 34/34 products, matches `scraped` exactly with zero silent skips.
- [~] Force a failure — kill the network mid-run — **deliberately skipped**, by choice,
      rather than left undone. `execute_run`'s `try`/`except` → `fail_run` path is
      already exercised by `tests/test_cli.py::test_a_failing_adapter_marks_the_run_failed_and_re_raises`,
      so the mechanism is covered; only the "does a real mid-network-call interruption
      hit that same path" question is left genuinely untested against the live site.
- [x] Ran with `--bump-year` against a scratch `--data-dir`, scoped to `--range "Twin
      Sports"` (3 products) to see route 1 of §6.9 in the queue. Confirmed the point of
      the flag directly: `600 SPB Sports RHD` had **no other proposed change at all**
      and still got a `year: 2026 → 2027` proposal — the bump is independent of whatever
      the diff found, not conditional on it. All 3 products' `year` proposals accepted
      via the review app, `decision` rows recorded correctly.

## T7 — Approved changes → upload CSV *(against the Phase 7 spec — adapt to the code)*

- [ ] Apply the §T4 decisions onto the baseline and emit the CSV. The join to test is
      `proposed_change` + its *latest* `decision`: **accept** takes `new_value`,
      **correct** takes `corrected_value`, **reject** takes neither, and a proposal with
      no decision must not be applied.
- [ ] **Carry-through fields survive untouched** — `product_id`, `year`,
      `manufacturing_release_date`, `latest_model_id`, `images`, `archived`. Diff the
      output against the baseline and confirm the only differences are the accepted
      changes. `year` is the exception and only when a rollover proposal was accepted.
- [ ] **Type round-trip out of TEXT storage.** Every `proposed_change` column is TEXT and
      `_serialize` flattens on the way in, so writing back has to reverse it:
      - an enum was stored as its **FMLV column name** (`BathroomLayout.REAR` →
        `"bathroom_layout_rear"`), so applying it means reverse-mapping column name →
        enum member, not `Enum(value)` on a label;
      - `bed_types` was stored comma-joined and has to split back into a list;
      - numerics are strings and need parsing — a corrected value typed as `"3,650"` or
        `"3650 kg"` by a reviewer must not silently become `0` or crash the writer.
        Test that path explicitly; the review form does no numeric validation.
- [ ] A **new product** (no `fmlv_product_id`) emits with `product_id` blank.
- [ ] `validation.validate_all()` over the generated rows before it is offered for upload.
      Specifically: accepting a change to `mro_kilograms` while rejecting the matching
      `mtplm_kilograms` leaves `mh_payload_kilograms` inconsistent — construct that case
      deliberately and confirm validation catches it rather than shipping a bad row.
- [ ] Read the generated CSV back with `io.read_csv` → 68 columns, exact order, values
      as expected.
- [ ] Open it in Excel once, to check nothing mangles (leading zeros, the `|` image
      separator, UTF-8).

## T8 — NCC site download *(against the Phase 7 spec — adapt to the code)*

- [ ] Credentials from environment variables only; confirm nothing is logged, echoed on
      failure, or written into a snapshot.
- [ ] Log in and download the current export to `data/exports/<date>/`.
- [ ] Feed that real download through §T2 and confirm it parses identically to the sample.
- [ ] Wrong-password path fails with a clear message rather than a Playwright timeout.
- [ ] **Do not upload anything generated by §T7 to the live site during testing.** Upload
      is manual by design (§6.2) and open question 3 — what the site's validation rejects
      — is still unanswered.

## T9 — Reset and repeat

- [ ] Write down the teardown so a run can be repeated from clean:
      delete `data/run_store.sqlite3`, `data/snapshots/`, `data/uploads/`; keep
      `data/exports/` and `data/manufacturers.csv`.
- [ ] `tests/test_cli.py` already covers the wiring *between* phases against a
      `tmp_path` database — the gap every other test left. Once §T3–§T7 pass by hand,
      extend it with the real Adria fixtures and the real export, so the numbers §T3
      checks by hand are pinned rather than re-eyeballed.

---
