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
(`Fiat Ducato`, `Ford Transit`, `VW`), which fills `base_vehicle_manufacturer` — the make
is the cell's first word, and the whole cell is carried into the provenance snippet, since
`Fiat` alone does not say which of Fiat's vans a layout sits on.

> `base_vehicle_manufacturer` was set on the model but **not registered as provenance**
> until it was fixed alongside the same omission in `burstner.py` and `morelo.py`. The
> provenance dict is the pipeline's only record of what an adapter looked at —
> `diff/compare.py` compares only the fields it names, and `store/changes.py` proposes
> only those fields for a `NEW_PRODUCT` — so the value was silently dropped: correct-
> looking on every product FMLV already held, blank on every genuinely new one, despite
> being a REQUIRED field. See [`burstner.md`](burstner.md) for the full write-up.

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

## MY27: Sunlight renamed the ranges, and matching couldn't follow

The 27 August 2026 run proposed **17 of 26 layouts as new products**. Six were. The
other eleven were vehicles FMLV already held, and the same run raised disappearance
notices against the very rows it was proposing to duplicate — it asked for 6549 to be
deactivated and for a second copy of it to be created, in one report.

Sunlight changed two things at once for model year 2027:

| MY26, as FMLV holds it | MY27 price list |
|---|---|
| `Van Adventure Edition` `V60` | `Van Adventure` `V 60` |
| `Low Profiles Adventure` `T58` | `Low Profile Adventure` `T 58` |
| `Coachbuilts` `A60` | `Coachbuilts Root` `A 60` |
| `A Class Adventure Edition` `I67S` | `A Class Adventure` `I 67S` |

Neither change on its own is fatal, but together they fall through
`diff/matching.py`'s 0.5 threshold: `V 60` tokenises to `{v, 60}` and `V60` to `{v60}`,
which share *nothing*, so the whole score rested on a range name that had also been
edited. The scores landed at 0.20–0.43. The one layout in that family that did match —
`T 66S` at 0.667 — matched only because FMLV's row 8268 happens to store the code with a
space in it, which is the clearest possible demonstration that the spacing, not the
vehicle, was deciding the outcome.

`Coachbuilts Root` is not a parse artefact, incidentally: it is the literal heading run
on page 43 of `reisemobile-mj27-uk.pdf`.

The fix is in the matcher, not here — adjacent model-code fragments are now joined
before scoring, and a layout code that disagrees on both sides blocks a match outright.
Re-run against the same snapshots: **20 matched, 6 new.** See `src/diff/matching.py`.

The six genuinely new: `Low Profile UNLTD` T 7003S / T 7033P / T 7433Q / T 7433S — a new
Ford Transit range with no UNLTD counterpart in FMLV at all — plus `VW IBEX` 604D on the
VW Crafter, and `CLIFF X` 602, the 602 layout extended into the X trim (FMLV held the X
in 600 and 640 only).

### The export is a history, not a line-up

Chasing this turned up a second fault worth knowing about on every manufacturer.
Sunlight's baseline export holds 105 rows for 38 live products: `Coachbuilts A60` is in
there twice, as archived 2022 product 3524 and live 2026 product 6562, identical in
range and model. Both score the same against a scraped `Coachbuilts Root A 60`, so the
winner was whichever the export happened to list first — the archived one, in eight of
the eleven recovered products. The model-year update would have landed on a dead row
while the live one drifted out of date, which is a quieter failure than a duplicate and
would not have shown up in a health check at all. `matching.py` now breaks ties toward
the live row, newest year first.

## The name FMLV renders

FMLV builds a product's display name as manufacturer + range + model, so the price
list's `CLIFF X` / `CLIFF 602` reads back as **"Sunlight CLIFF X CLIFF 602"**. The
adapter now trims a leading model word the range already carries, via
`base.model_without_range_prefix`.

It only ever drops a *leading* word, only when the range genuinely contains it, and only
when what remains still names the layout — so `CLIFF Vanlife`'s `CLIFF 540 V` becomes
`540 V` and stays distinct from `CLIFF Adventure`'s `540`, and a hypothetical model of
just `CLIFF` is left alone rather than emptied.

This produces no churn on the products FMLV already holds: it stores the CLIFF layouts
as `540`, `600`, `640` already, so the trim makes the adapter agree with the baseline
rather than propose a rename. Only genuinely new products were carrying the doubled name,
which is why `CLIFF X 602` surfaced it.

The helper is deliberately **not** wired into every adapter. Bürstner's
`Lyseo TD Harmony Line` holds both `TD 680 G` and `680 G` as separate FMLV rows, so the
same rule there would collapse a distinction FMLV is currently making. Apply it per
manufacturer, once that manufacturer's naming has been checked.

## body_type

Filled from the range name and the layout's series letter — Sunlight's naming carries it
reliably, which not every manufacturer's does:

| Source | Reads as | Evidence |
|---|---|---|
| `T` series | `coach_built_low_profile` | the range is *named* `Low Profile` |
| `I` series | `a_class` | the range is *named* `A Class` |
| `A` series | `coach_built_over_cab_bed` | not stated; all three live FMLV `Coachbuilts` layouts |
| `V` series | `coach_built_low_profile` | not stated; all seven live FMLV `Van` layouts |
| `CLIFF Adventure`, `CLIFF X` | `campervan_high_top` | FMLV precedent across both ranges |
| `CLIFF RT` | `campervan_elevating_roof` | FMLV precedent |
| `CLIFF Vanlife` | `campervan_high_top_elevating_roof` | FMLV precedent |

**The `V` series is the trap.** `Van Adventure` reads like a panel-van conversion, and
guessing that would put a `Yes` in the wrong one of eight mutually exclusive columns. It
is a narrow-bodied (2140mm) low-profile coachbuilt, it sits in the *motorhome* price
list, and FMLV classes every live V layout that way.

Against the real baseline the rule **confirms all 20** products FMLV already holds and
contradicts none — a stronger start than `burstner.py` got, where two of thirteen
disagreed and turned out to be FMLV's own errors.

`VW IBEX 604D` is deliberately **left blank**. It is a VW Crafter camper van with no FMLV
precedent, and the price list does not say whether its roof is a fixed high top or an
elevating one. Its 2720mm height sits between CLIFF's 2610mm high tops and Vanlife's
2810mm pop-top, so height does not settle it either. A blank is an honest gap a reviewer
fills in seconds; a wrong `Yes` is a silent error nothing downstream re-checks.
