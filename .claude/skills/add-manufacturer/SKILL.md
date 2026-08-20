---
name: add-manufacturer
description: Add a new manufacturer to the FMLV pipeline - survey their website, fill in the config/manufacturers.csv registry row, and write, wire up and test a new adapter in src/adapters/. Use when asked to add or support a manufacturer or brand, write an adapter for one, or get a new manufacturer's products flowing into FMLV.
---

# Adding a manufacturer

Two things have to exist before a manufacturer's products can flow into FMLV: a row in
`config/manufacturers.csv`, and an adapter module in `src/adapters/`. This skill produces
both.

The person invoking this is usually an expert on motorhomes and on this manufacturer, and
is usually not a coder. Talk to them accordingly: ask about vehicles and brands, not about
parsers and JavaScript, and explain your findings in those terms too.

**Do not restate what `docs/adapters/README.md` already says.** That file holds everything
learned from the four adapters written so far, and it is the reference for *how* to make
these judgements. This skill is the running order and the things that must not be skipped.
Read it at the point where the running order tells you to.

**Branch:** always work on the `master` branch for this skill, unless the user explicitly
asks you not to.

Work in three stages, and **stop at the checkpoint between stage 1 and stage 2**. Stage 1
takes minutes and decides everything; stage 2 takes an hour and is expensive to undo.

---

## Stage 0 — Ask what they already know

**Do this first, before fetching anything.** The person asking holds things that are not
discoverable from the website at any price: when the new model year is announced, which
range is actually caravans, which sub-brand sits on a separate site, that last season's
price list was withdrawn and reissued with different weights.

Run the `AskUserQuestion` tool for three questions:

1. **What do you know about this manufacturer?** Anything worth watching out for, any
   ranges that are unusual or that people get wrong, anything that has caught someone out
   before, anything the adapter should pay particular attention to.
2. **Any URLs you already have?** The models page, a price list, a brochure, a UK
   importer's site — paste in whatever you have.
3. **What is the NCC supplier name?** Ask the user to go to
[Export Products by Supplier](https://findmyleisurevehicle.co.uk/nova/resources/products),
open the supplier drop-down there, and give you the exact value as it appears in that list.

Do not proceed past stage 0 without the NCC supplier name — write it into the `ncc_supplier_name` field of the registry row in step 1.6.

Do not ask them about `specs_format`, JavaScript, or PDF structure. Those are yours to work
out in stage 1.


Three rules for what comes back:

- **Pasted URLs are strong leads, not gospel.** Verify each one by fetching it in stage 1,
  the same as any candidate you find yourself. Every manufacturer surveyed so far has had a
  near-miss document sitting beside the right one — a superseded model year, a glossy
  catalogue without the spec tables. If a pasted URL turns out to be wrong or out of date,
  say so plainly at the checkpoint rather than quietly using something else.
- **What they say about vehicles outranks what you assume.** If they tell you a range is
  caravans, or that prices only firm up in October, that is fact — design around it.
- **Skip the ask if it has already been answered.** If the request already carried the
  context ("add Rimor, their UK price list lands in September and the Katamarano range is
  caravans"), acknowledge what they gave you and go straight to stage 1.

Everything they tell you gets **written down**, not just used: into the `notes` column of
the registry row and into `docs/adapters/<name>.md`. This is the only step in the whole
process that captures knowledge existing nowhere else in the repo, and it should outlive
the conversation.

---

## Stage 1 — Survey

No adapter code is written in this stage. The output is a registry row, a survey document,
and a decision about which document to parse.

### 1.1 Identify the manufacturer

Look up the `manufacturer_id` and canonical name in `resources/manufacturers-full-list.csv`
(`ID,Name,DisplayName,ContactEmail,ContactName,NCCApproved`). **Never ask the user to type
an ID and never invent one** — it is an NCC-side key, and a wrong one silently detaches
every run from its history.

Check `config/manufacturers.csv` first in case a row already exists — several
manufacturers have rows but no adapter yet, in which case stage 1 is mostly done and you
are filling gaps rather than starting fresh.

If the name is ambiguous (several plausible matches) or absent from the full list, stop and
ask. Do not guess between two similar brand names.

### 1.2 Find the data

Read `docs/adapters/README.md` now, in full. Work its questions **in the order it gives
them** — that ordering is the single most valuable thing in the file, and the reason it
opens with "is there a brochure or price list PDF?" is that this was the last thing tried
for the first adapter and the first thing that worked for the three since.

Start from any URLs the user gave you, then fall back to discovery.

Also answer the two follow-on questions that file raises:

- Is there a **market-specific edition**? A UK or Ireland price list in sterling removes
  the exchange-rate problem that is the worst data in the Morelo adapter. Check before
  planning any currency conversion.
- Does the downloads page list **more than the current document** — superseded model years,
  a differently-named glossy catalogue? Plan to rediscover the right one per run rather
  than hardcoding a URL.

### 1.3 Verify by fetching, not by reasoning

**This is not optional.** Actually pull the candidate document and confirm with your own
eyes that the numbers are in it — weights, dimensions, berths, price. "There is probably a
price list PDF" is precisely the assumption that produces a broken adapter.

Use the repo's own fetching code from a throwaway script in your scratchpad directory:

- `src/fetch/http.py` — `Fetcher(snapshot_dir)`, a polite retrying client. `fetch(url)`
  returns a `FetchResult` with `.file_path`; adapters read the file, never a response body.
- `src/fetch/pdf.py` — `extract_text(path)` for whole-document text, and
  `extract_positioned_text(path, page_number)` for `(x, y, text)` runs.
- `src/fetch/browser.py` — `BrowserFetcher`, only if the plain HTTP path has genuinely
  failed. Reaching for this first is the mistake `docs/adapters/README.md` warns about.

Record what you actually saw. Quote a real spec row into the survey document.

### 1.4 Find the self-check

Identify the arithmetic or redundancy **this manufacturer publishes against itself** —
payload against MTPLM minus MRO, a printed tolerance band, anything that lets a parse be
checked without a second source. `docs/adapters/README.md` explains why this matters: a
misaligned column produces plausible, internally consistent motorhomes carrying each
other's weights, nothing downstream flags it, and a reviewer accepts the change.

Every manufacturer surveyed so far has had one. If you genuinely cannot find one, **say so
explicitly at the checkpoint** — it changes the risk profile of the whole adapter and the
user needs to know before agreeing to build it.

### 1.5 Estimate the product count

Find what the manufacturer publicly claims — "20 layouts across four ranges" or similar,
usually on the models index page. This becomes the number the tests assert and the number
you compare the first real run against. Without it you have no way of knowing whether the
parser silently dropped half the range.

### 1.6 Write the registry row

Fill in one of the blank placeholder rows at the bottom of `config/manufacturers.csv`,
following `config/manufacturers.README.md` column by column.

- `fmlv_manufacturer` **must match the FMLV export's `manufacturer` value exactly.** This
  is the join key back to existing product IDs, and it is also the key the adapter is
  registered under. Getting it subtly wrong (a trailing space, `Ltd` vs `Ltd.`) means the
  run finds an empty baseline and proposes every product as new.
- `ncc_supplier_name` is a *different* string — the label in the NCC site's own export
  dropdown, given to you by the user in stage 0. It can be different from
  `fmlv_manufacturer`, and do not guess it yourself.
- Fill `specs_format`, `needs_javascript`, `models_index_url`, `price_list_url` and
  `brochure_url` from what you actually found in 1.2 and 1.3.
- Put the user's stage 0 context in `notes`, and today's date in `last_verified`.

### 1.7 Write the survey document

`docs/adapters/<name>.md`, following the shape of the existing four (`adria.md`,
`morelo.md`, `swift.md`, `sunlight.md`). Cover the site's shape, where the data actually
lives, what the self-check is, anything odd, and what you know is missing or unverified.
Record the user's stage 0 context here too.

---

## Checkpoint — stop and report

**Write no adapter code until the user has said yes.**

Report, briefly and in plain language:

- The document you intend to parse, and why that one rather than the alternatives.
- The evidence it holds the numbers — quote a real row from it.
- How many products you expect, and where that number comes from.
- The self-check you will use, or that there isn't one.
- The drafted registry row.
- **What happened to everything the user gave you in stage 0** — which URLs you used, which
  turned out to be superseded or wrong, and how their context changed your approach.

A domain expert can spot a wrong source choice in seconds. That is the entire point of
stopping here.

---

## Stage 2 — Build

### 2.1 Write the adapter

`src/adapters/<name>.py`. Start from whichever existing adapter is closest in shape:

| Source shape | Copy from |
|---|---|
| One price list or brochure PDF, columnar spec pages | `morelo.py` |
| PDF with two tables that must be joined | `swift.py` |
| PDF where cell boundaries matter (parse runs, not lines) | `sunlight.py` |
| JS-rendered catalogue plus a per-product PDF | `adria.py` |

Required module-level constants:

```python
BASE_URL = "https://www.example.com"
MANUFACTURER = "Example Ltd"          # byte-for-byte equal to the CSV's fmlv_manufacturer
MANUFACTURER_DISPLAY_NAME = "Example"
DEFAULT_RANGES: tuple[tuple[str, str], ...] = (...)   # only if the manufacturer has ranges
```

Required `collect` signature — see `src/adapters/base.py` for the full contract:

```python
def collect(
    http: Fetcher,
    browser: BrowserFetcher,      # or `browser: object,  # noqa: ARG001` if unused
    snapshot_dir: Path,
    *,
    ranges: tuple[tuple[str, str], ...] = DEFAULT_RANGES,
    on_progress: Callable[[str], None] = lambda message: None,
) -> list[ExtractedMotorhome]:
```

Three things that are not negotiable:

- **A `_reconciles()` self-check**, using whatever redundancy stage 1.4 found. Products
  that fail it are **dropped with an `on_progress` warning, never proposed.** Likewise a
  row whose cell count doesn't match the model count — drop the page rather than guess at
  the alignment.
- **Narrate skips.** Anything dropped goes through `on_progress`. A silent drop is
  indistinguishable from a manufacturer discontinuing a model.
- **Error policy matching the existing four:** a failure on one product or one page is
  narrated and skipped; only a wholly unreachable or unparseable document raises.

### 2.2 Wire it in — three edits, all of which fail silently

In `src/adapters/__init__.py`:

1. Add the module to the `from . import ...` line.
2. Add the `ADAPTERS` dict entry, keyed on `<module>.MANUFACTURER`.
3. Add the module name to `__all__`.

Miss any of these and nothing raises. `adapter_for()` returns `None`, which the app treats
as the perfectly normal "nobody has written an adapter for this brand yet" state — the
manufacturer just never appears in the trigger dropdown and scheduled sweeps skip it.
`tests/adapters/test_registry_wiring.py` exists to catch exactly this, so run it.

### 2.3 Fixtures and tests

Capture real artefacts into `tests/adapters/fixtures/` — extracted text as `.txt`,
positioned runs as `.json`. **Never commit the source PDF.** Prefer pages that broke your
parser while you were building; that is how the existing fixtures were chosen.

Write `tests/adapters/test_<name>.py` testing **pure parsing functions only** — no network,
no PDF parsing (`tests/fetch/test_pdf.py` covers that). Follow the existing files: import
the private helpers directly, assert the exact expected product count against the
manufacturer's public claim, and add a negative test for every parsing trap you actually
hit. There is no `conftest.py` in this repo; don't add one.

### 2.4 Verify

```bash
uv run pytest -q
uv run fmlv run "<fmlv_manufacturer>" --range "<one range>"
```

Check stderr for registry issues, compare the product count against the manufacturer's
public claim, and **hand-check three products' weights and prices against the source
document.** Snapshots land in `data/snapshots/<manufacturer_id>/<run_id>/`.

Then confirm end to end — start the review app and check the new manufacturer appears in
the trigger dropdown, which is filtered by `adapter_for()`:

```bash
uv run uvicorn src.webapp.serve:app --port 8000
```

Report the real numbers you got, including anything that was dropped and why. If the count
doesn't match the manufacturer's claim, say so — do not round the discrepancy away.
