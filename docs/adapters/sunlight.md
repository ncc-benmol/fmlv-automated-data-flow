# Sunlight — site survey and adapter notes

Surveyed 6 August 2026, against the **model year 2027** UK price lists
(`reisemobile-mj27-uk.pdf`, `camper-vans-mj27-uk.pdf`, both version 08/2026, valid from
01.08.2026).

Fourth manufacturer, third in a row whose data lives in a published PDF rather than on
the website — and the best-behaved source so far. Two price lists linked in plain HTML
off `/en/info-material/`: no JavaScript, no form, no login.

**26 layouts across 9 ranges**, from two page fetches and two PDFs:

| Catalogue | Ranges | Layouts |
|---|---|---|
| Motorhomes | Van Adventure, Low Profile Adventure, Low Profile UNLTD, A Class Adventure, Coachbuilts Root | 16 |
| Camper Vans | CLIFF Adventure, CLIFF X, CLIFF Vanlife, VW IBEX | 10 |

## Two things that make this the easiest source yet

**1. The UK price list is already in sterling.** Sunlight is German, but publishes a
`United Kingdom & Ireland` edition quoting `Price £`. This is the direct answer to
Morelo's worst problem — no exchange rate, no stale constant, nothing baked into a
proposed price change. Worth checking for on every remaining German and Italian
manufacturer before reaching for a conversion.

**2. Every table cell is its own text run.** The `Prices and technical data` pages read
as a clean stream:

```
'Prices and technical data', 'Van Adventure', 'V 60', 'V 66', 'V 67S',
'Price £', '59,090.-', '61,690.-', '62,590.-',
'Permitted seats (including driver)*', '4', '4', '4',
'Berths', '2 - 3 OPT', '2', '2 - 4 OPT', ...
```

Cell boundaries come free. None of the splitting guesswork Morelo and Swift need
applies: no column-order ambiguity, no run-together names, no ragged left-hand columns.
A row is its label followed by one run per model, and that is the whole parser.

This is why the adapter parses **runs, not lines** — and it is not a stylistic choice.
Joined into a line, `CLIFF 540 V` is indistinguishable from `CLIFF 540` followed by a
stray `V`, and Sunlight sells *both* a `CLIFF 540` (in CLIFF Adventure) and a
`CLIFF 540 V` (in CLIFF Vanlife). Reading the second as the first would silently merge
two different products.

`fetch.pdf.extract_positioned_text` was changed from returning runs sorted left-to-right
to returning them in the page's own drawing order, which is the information-preserving
choice — order is the one thing that cannot be reconstructed afterwards, whereas any
caller wanting left-to-right can sort on `x`. The Morelo adapter now does that sort
explicitly at its call site, which also makes its (genuinely subtle) ordering rule
visible where it is relied on rather than hidden in a shared utility.

## What Sunlight publishes

Price, permitted seats, berths, length/width/height, mass in running order, and
technically permissible maximum laden mass — for every layout. Plus the base chassis
(`Fiat Ducato`, `Ford Transit`, `VW`), which fills `base_vehicle_manufacturer`.

Three conversions worth knowing about:

- **Dimensions are centimetres in a single cell** (`596 / 214 / 274`), split and
  multiplied by 10.
- **Payload is derived, not published.** `MTPLM − MRO`, as `adria.py` does it.
  Sunlight's own "manufacturer-specified mass for optional equipment" is deliberately
  *not* used for this — it is a cap on factory-fitted extras, a different quantity that
  happens to sit in the same table and would be an easy mistake to make.
- **Berths and seats can carry an option** (`2 - 3 OPT` = two berths, a third only with
  optional equipment). The standard figure is recorded, and the cell's own wording is
  carried into the provenance snippet, since a single number cannot express the rest.

## The self-check

Morelo and Swift both publish payload alongside MTPLM and MRO, giving a free arithmetic
check on the parse. Sunlight publishes no payload, so there is no equivalent — but it
prints each mass with the ±5% tolerance band type approval allows:

```
Mass in running order* (kg)   2657 (2524 to 2790)*
```

The band is a function of the mass, so the pair must be self-consistent — which makes it
the same kind of free check that the value was read from the right column. A slipped
column pairs one layout's mass with another's band and fails it. All 26 products
reconcile. Three kilograms of slack are allowed, since the band is printed rounded to
whole kilograms.

An independent sanity check, too: the five "from" prices on the motorhomes page
(£59,090 / £64,890 / £71,490 / £81,090 / £60,990) each match the cheapest layout parsed
out of that range exactly.

## Discovery: the URL cannot be hardcoded or cached

The price lists are **Dropbox share links** carrying `rlkey` and a short-lived `st`
token:

```
https://www.dropbox.com/scl/fi/tdu2ilmhzts4ytqc5lgkv/reisemobile-mj27-uk.pdf?rlkey=...&st=...&dl=1
```

Neither the opaque path segment nor the token can be reconstructed, so the URL is
rediscovered every run. Two traps in doing so:

1. **The page lists every model year it has ever published** — 2027 back to 2024. "The
   first link found" is neither the current one nor stable. The `mjNN` in the filename
   is the model year and the highest wins.
2. **The glossy catalogues sit on the same page** under a different naming scheme
   (`Sunlight-Kat-RM-2024-UK-IRL.pdf`) and have no technical tables. Only the
   `*-mjNN-uk.pdf` files are price lists. Same shape of trap as Morelo's
   `kataloge_preislisten` directory, and worth expecting on any manufacturer with a
   downloads page.

The registry's `price_list_url` therefore points at the **info-material page**, not at a
PDF — pointing it at a PDF would record a URL that expires.

## Known gaps

- **Model-year labelling.** The 2027 list is live now, alongside 2026. The adapter takes
  the newest, which is right for "what is currently published" but means a run today
  proposes 2027 data against a baseline that may still be 2026 products. That is really
  the year-rollover question in DESIGN.md §6.9 rather than an adapter bug, but Sunlight
  is the first manufacturer surveyed where two model years are published at once, so it
  will surface there first.
- **A single `Fiat` / `Ford` / `VW` is recorded** as the base vehicle manufacturer, from
  the first word of e.g. `Fiat Ducato`. The full chassis name is available in the same
  cell if FMLV ever wants it.
- Prices include UK VAT and are "recommended retail"; whether that matches FMLV's basis
  is the same open question as for the other manufacturers.
- The website's own model pages were not surveyed beyond confirming the range-level
  "from" prices, since the price list is strictly more complete.

## What this adds to the general pattern

Three of four manufacturers now publish everything in a PDF, and the PDF has been the
better source every time. What Sunlight adds to [`README.md`](README.md)'s guidance:

- **Check for a market-specific edition before converting a currency.** A German
  manufacturer publishing a UK price list in sterling removes the single worst piece of
  data in the Morelo adapter.
- **Parse runs, not lines, when cell boundaries matter.** Lines are a lossy rendering of
  a table. Where a value can contain a space, the run boundaries are the only thing that
  says where one cell ends.
- **A downloads page usually lists more than the current document.** Both Morelo and
  Sunlight had a near-miss sitting next to the file actually wanted; Sunlight also had
  three superseded years of the right file. Match precisely, and prefer the newest.
