# Adria Mobil (adria.co.uk) — Phase 4 survey and first adapter

Manufacturer ID 3, priority 1 pilot. Code: `adapters/adria.py`. Tests:
`tests/adapters/test_adria.py` (against real captured fixtures, no network).

## Site shape

`adria.co.uk` (the UK importer site — used over the group site `adria-mobil.com`
because it has GBP pricing, which is what the FMLV export needs) is built on
**Laravel + Livewire + Alpine.js**. A model-range page like `/motorhomes/matrix`
renders almost empty: no price, no specs, just marketing copy and trim names.

The real data loads in two separate steps, discovered by watching the network panel
while actually interacting with the rendered page — neither was visible from a plain
HTTP fetch or from a browser fetch that only waited for `networkidle`:

### 1. Layout/trim/price — a scroll-triggered Livewire AJAX call

The page's layout-selector component only mounts when it scrolls into the viewport
(`x-intersect` — an Alpine.js intersection observer), firing `POST /livewire/update`.
Nothing requests this on page load; a headless fetch that doesn't scroll never sees it.
This is why `fetch/browser.py` gained `BrowserFetcher.fetch_with_capture(scroll=True)` —
a generic capability (see [`README.md`](README.md)), not Adria-specific.

The response body is a JSON envelope; the useful part is
`components[0].snapshot` (itself a JSON string) `.data.apiData`, which is wrapped in
**Livewire v3's wire-format**: every array/collection is serialised as a 2-element
`[data, meta]` pair rather than a plain list. `adria.unwrap_livewire()` undoes this
recursively. Once unwrapped, `apiData` is a list of layouts (e.g. "670 DC"), each with
a `products` list of sellable trim configurations (e.g. "Supreme Alde RHD"), each
carrying an `id`, a `priceString`/`price.retail_price_with_tax` (already whole GBP,
matches the displayed price exactly), `berths`, `seats`, and a `configuratorURL`.

Weights and dimensions are **not** in this payload — checked byte-for-byte during the
survey. Some sibling nodes under the same layout carry raw chassis `length`/`width`
figures with `id: null` (a "base vehicle" entry, not a sellable configuration) — the
adapter skips these; the PDF's dimensions are used instead, since they're per-
configuration rather than per-chassis.

### 2. Weights/dimensions — a per-configuration PDF, plain HTTP

The page has a "download technical data" button (`showDownloadTechnicalDataLink`).
Following it leads to `configure.adria-mobil.com` — a second Livewire app, an
interactive step-by-step configurator — but the PDF it ultimately serves turned out to
sit at a **predictable, unauthenticated URL**:

```
https://configure.adria-mobil.com/<market>/<period>/<product id>/pdf
```

`<market>`/`<period>` (`gb`/`25-26`) and `<product id>` all come straight out of the
JSON's `configuratorURL` and `id` fields, so `adria.technical_data_pdf_url()` builds it
without ever driving the configurator itself. This is a plain `Fetcher.fetch()` — no
browser, no session/cookies needed; confirmed with a fresh `httpx` client with no prior
state.

The PDF (~5 MB, 8 pages) is a real technical spec sheet. Pages 2–3 ("B. Dimensions and
weights") give clean `Label (unit) value` lines that `parse_technical_data_pdf()`
regexes out: `Body length (mm)`, `Total width (mm)`, `Total height (mm)`, `Mass in
running order (MIRO-min, kg)` → `mro_kilograms`, `Max authorised weight (kg)` →
`mtplm_kilograms`. Page 8 ("O. Collection") gives `Nr. of berths` / `Nr. of seats`
cleanly too. `mh_payload_kilograms` is computed as `mtplm - mro` rather than parsed —
the PDF's closest line ("max loading weight... with All Inclusive Pack weight
deducted") measures something subtly different and isn't a reliable match.

Everything past those two sections is ~50 lines of optional equipment, ticked or
crossed out per configuration (✕ = not fitted) — this is where the ~40 layout flags
would come from, but parsing it reliably is a harder problem than the numeric fields
and, per DESIGN.md §4.3, lower priority for an *existing* product. **Not attempted in
this first adapter** — a known, deliberate gap, not an oversight.

### 3. The 60Y anniversary editions — same shape, three unlisted pages

Added 2026-08-20. Adria's 60th-anniversary editions sit at `/60y/matrix`, `/60y/coral`
and `/60y/twin`, one layout each, and are built exactly like an ordinary range page —
same Livewire component, same `configuratorURL`, same technical-data PDF.

Two things about them are worth carrying forward:

- **They are in no index.** `/motorhomes` and `/campervans` list nine ranges between
  them and none of these three. This is `docs/adapters/README.md`'s "no single menu is a
  complete roster" again, and it is why the follow-up below — reading the range list off
  the index pages instead of hardcoding it — would have *lost* these three rather than
  found them. Whatever replaces `RANGES` has to reconcile against a second source.
- **Neither is their data duplicated.** `/motorhomes/matrix` returns seven
  configurations and none is the 60Y (checked 2026-08-20), so sweeping these pages adds
  products rather than double-counting existing ones.

**FMLV files them under the ordinary range, marked in the model** — product 8195 is
range `Matrix`, model `670 SL 60Y`, per `docs/adapters/README.md`'s rule that the export
decides these strings. That forced `RangeConfig` to separate two things this adapter had
previously treated as one string:

| | Ordinary range | 60Y edition |
|---|---|---|
| `label` — what `--range` and `schedule.csv` name | `Matrix` | `Matrix 60Y` |
| `fmlv_range` — what lands in `manufacturer_range` | `Matrix` | `Matrix` |
| Model | layout + trim (`670 DC Supreme Alde RHD`) | layout + `60Y` (`670 SL 60Y`) |

The trim is dropped for a 60Y product because it carries nothing: it is a different
shape on each of the three pages (`60 years RHD`, `Coral 60Y 670 DL`, `Twin 60Y 640
SGX`) and on two of them merely repeats the layout code. Each PDF titles itself exactly
as FMLV names the product (`MATRIX 670 SL 60Y`), which is a useful independent
confirmation that this naming is Adria's own and not an invention of this adapter.

**A consequence worth knowing about, because it reaches outside the adapter.** A
`--range`-narrowed run filters the baseline export so it only diffs against rows in the
swept ranges. That filter used to be a match on `manufacturer_range`, which cannot work
once label and range differ — and it fails destructively in *both* directions: too
narrow and the 60Y products find no baseline, are classified `NEW_PRODUCT`, and would be
uploaded as duplicates of products the NCC already holds; too wide and `--range Matrix`
pulls in the 60Y row it never sweeps and reports a live product as disappeared. So
`cli.baseline_scope` now delegates to an optional `baseline_in_scope(motorhome, labels)`
the adapter may declare — the same `getattr` opt-in as `DEFAULT_RANGES`, leaving every
other adapter untouched. Adria's implementation reads the `60Y` suffix on `model`,
because that is the only place FMLV records the distinction at all.

### The scroll bug these pages exposed

All three returned **zero** configurations at first, and the reason was not in this
adapter: `BrowserFetcher._scroll_to_bottom` scrolled in 2000px steps against a 720px
viewport. That tiles a page with gaps, and the element carrying Adria's `x-intersect` is
**20px tall** — on these three pages it landed in a gap, was never on screen while the
page was still, and its intersection observer never fired. On `/motorhomes/matrix` the
same element happens to land inside a rest position, which is the only reason the
adapter ever worked.

The fix is generic and lives in `fetch/browser.py`: no step may exceed half a viewport,
so consecutive positions overlap and nothing can be skipped. Regression test:
`tests/fetch/test_browser.py::test_fetch_with_capture_finds_a_trigger_that_falls_between_scroll_steps`.

**The general lesson is about the failure mode, not the arithmetic.** A page yielding no
captures is indistinguishable from a page that has no lazy-loaded data, so this bug
presents as "those pages must be built differently" and can silently cost a whole range
on any future JS-driven site. `collect` now narrates a range page that made no
`livewire/update` call at all, so the next occurrence says so out loud.

## Self-checks

Added 2026-08-20, and this adapter needs them more than any other: it reaches its
weights and dimensions by **constructing** a URL from an id rather than following a
link, so the failure to defend against is a spec sheet that belongs to a different
vehicle — plausible, internally consistent, and invisible to everything downstream.

Adria publishes no payload to reconcile against its two masses (see above), so the
redundancy `docs/adapters/README.md` asks for is found in two other places:

| Check | What it catches | On failure |
|---|---|---|
| The PDF's own running title names the layout it was fetched for | A constructed URL resolving to another vehicle's sheet | **Drop** |
| Mass in running order is below max authorised weight | A mis-parse; a non-positive payload, which would otherwise satisfy `validation.py`'s `payload == mtplm - mro` check by construction | **Drop** |
| The range page's JSON and the PDF agree on berths and seats | A definitional difference between two independently maintained sources | **Warn, keep, show both** |

The third only warns *because* the first exists. Once the title has confirmed the
document is the right vehicle's, a berths disagreement is a question about definitions —
Adria's seats row varies by chassis rating — and dropping the product would discard a
correct price and correct dimensions over something a reviewer is better placed to
settle. Both figures go into the provenance snippet instead.

The title is read from the running footer (`<title>\nCreated date:`), which every page
repeats, rather than from the first line of the extracted text — it is then the document
*stating* what it describes rather than an assumption about layout.

## Fields added 2026-08-20

- **`base_vehicle_manufacturer`**, from the spec sheet's own chassis section heading
  (`CA. Fiat Chassis`, `CB. Mercedes Chassis`). Adria's spelling is already FMLV's:
  `Fiat`, `Mercedes`, `MAN`, `Renault` are the four in the real baseline, and `Mercedes`
  rather than `Mercedes-Benz` matches on both sides. Deliberately *not* read from the
  `Chassis type ...` line, which gives the variant (`special`, `panel van`, `AL - KO`)
  and not the manufacturer. A document whose headings disagree leaves the field unset
  rather than taking the first hit. Validated on the live Matrix run: it agreed with the
  baseline on all six existing rows and proposed a value only where the baseline was
  blank.
- **`mh_payload_kilograms` now carries provenance**, so it is actually diffed. It was
  computed before but had no `Provenance` entry, and `diff/compare.py` only compares
  fields the provenance dict covers — so a payload change was silently never proposed.
  The snippet shows the subtraction, as `burstner.py` does.
- **Provenance snippets now keep the qualifier the recorded figure drops.** Adria writes
  `Nr. of seats 3 AT 3,500KG (4 AT 3,650KG)` and `Nr. of berths 2 (OPTIONAL 3RD BERTH)`;
  the base figure is what FMLV records per `docs/adapters/README.md`, but the snippet
  stopped at the digit and threw the rest away. On a seats row that differs by chassis
  rating, the discarded half was the whole story.

## Validation against the real baseline export

Ran the adapter live against the Matrix range (7 configurations) and compared to the
41-row Adria baseline (`csv-examples/…/motorhome-campervans.xlsx`):

- **`MB 670 SL` and `MB 670 DL`**: MRO, MTPLM *and* RRP all matched the baseline
  exactly. Strong evidence the parse is genuinely correct, not coincidentally
  plausible.
- Several other rows (`670 DC`, `670 SC`, `670 SL`) matched dimensions and RRP but
  showed a higher MTPLM (3650kg vs baseline's 3500kg) on the same body code — page 4 of
  the PDF mentions an "extended homologation" option (35L → 36.5L Fiat chassis rating).
  Read as a genuine current-vs-baseline delta worth a reviewer's attention, exactly the
  behaviour DESIGN.md §6.4 asks for (surface everything, no threshold) — not treated as
  a bug and not silently reconciled.

## Known gaps / follow-ups

- **Range list is hardcoded** (`RANGES` in `adria.py`), read off the site nav by hand
  during the survey — 6 motorhome ranges + 3 campervan ranges, re-confirmed unchanged
  2026-08-20, plus the 3 60Y pages. A new range won't be picked up until the constant is
  updated. Reading it dynamically from the `/motorhomes` and `/campervans` index pages
  is the obvious fix but is **not sufficient on its own**: neither index lists any of
  the three 60Y pages, so an index-driven roster would have to be reconciled against a
  second source or it would quietly drop them.
- **Model naming won't match the baseline's naming 1:1.** The site names a
  configuration by layout code + trim (`"670 DC" + "Supreme Alde RHD"`); the baseline
  export uses `"Supreme 670 DC"`. Same product, different word order/casing — Phase 5's
  matching logic will need to handle this, not exact-string-match on `model`.
  `manufacturer_range` in the baseline is also inconsistently cased/punctuated for at
  least one row (`"Matrix Supreme"` vs `"Matrix"` for a `Supreme MB` product) — a
  pre-existing baseline quirk, not something this adapter introduced.
- **Layout flags (body type, bed types, bathroom layout, heating, …) are not
  extracted.** Deliberately deferred — see above. One caution for whoever picks this up:
  the `✕` semantics recorded above (`✕` = not fitted) does **not** survive contact with
  the sheets. `Driver airbag ✕`, `ABS + EBD ✕` and `Right hand drive ✕` all appear on a
  RHD vehicle, while the *unmarked* lines are things like `Roof-mounted air conditioning`
  and `Solar panel 1x (set)` — which reads as the opposite convention. Settle this
  against a known product before writing any of it: getting it backwards would flip
  ~40 columns on every product at once.
- **Cost/politeness at full scale**: each PDF is ~5 MB; a full run across all 9 ranges
  with several configurations each means dozens of multi-megabyte fetches. Fine at
  prototype scale per DESIGN.md §8.1, but worth keeping an eye on once content-hash
  gating (Phase 3, already built) is wired up against a previous run's hashes — most of
  these won't need re-fetching once a manufacturer has been run once.
