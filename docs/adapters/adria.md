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

- **Range list is hardcoded** (`DEFAULT_RANGES` in `adria.py`), read off the site nav
  by hand during the survey — 6 motorhome ranges + 3 campervan ranges. A new range
  won't be picked up until the constant is updated; reading it dynamically from the
  `/motorhomes` and `/campervans` index pages would remove that.
- **Model naming won't match the baseline's naming 1:1.** The site names a
  configuration by layout code + trim (`"670 DC" + "Supreme Alde RHD"`); the baseline
  export uses `"Supreme 670 DC"`. Same product, different word order/casing — Phase 5's
  matching logic will need to handle this, not exact-string-match on `model`.
  `manufacturer_range` in the baseline is also inconsistently cased/punctuated for at
  least one row (`"Matrix Supreme"` vs `"Matrix"` for a `Supreme MB` product) — a
  pre-existing baseline quirk, not something this adapter introduced.
- **Layout flags (body type, bed types, bathroom layout, heating, …) are not
  extracted.** Deliberately deferred — see above.
- **Cost/politeness at full scale**: each PDF is ~5 MB; a full run across all 9 ranges
  with several configurations each means dozens of multi-megabyte fetches. Fine at
  prototype scale per DESIGN.md §8.1, but worth keeping an eye on once content-hash
  gating (Phase 3, already built) is wired up against a previous run's hashes — most of
  these won't need re-fetching once a manufacturer has been run once.
