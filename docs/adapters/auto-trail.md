# Auto-Trail — site survey and adapter notes

Surveyed 13 August 2026, against the **2026 season** website technical specifications.

Auto-Trail is the sixth manufacturer surveyed, and the cleanest source yet. It is the
first where **attribution is free in a PDF**: every range publishes a "Website Tech Spec"
document that devotes a run of whole pages to one model at a time, with the model name
repeated as a running header. There are no side-by-side columns anywhere, so the entire
class of column-misalignment failure that dominates [Morelo](morelo.md),
[Swift](swift.md) and [Sunlight](sunlight.md) — and that defeated
[Rimor](rimor.md)'s catalogue outright — simply does not arise.

**37 layouts across 10 ranges, 10 PDF fetches plus range-page discovery, no browser:**

| | Ranges | Layouts |
|---|---|---|
| Motorhomes | Expedition Coachbuilt, Excel, F-Line, Imala, Frontier, Grande Frontier | 21 |
| Campervans | Adventure, Expedition, V-Line SE, V-Line Sport | 16 |

## What the user brought to the survey

Ben supplied the example model page and the Expedition Coachbuilt tech spec PDF, and
both turned out to be the right documents — the tech spec PDF is the source this adapter
parses. He also flagged, in advance, that **Expedition is used twice**: once as a
coachbuilt motorhome range and once as a campervan range. That is correct and it is the
single most important naming hazard on this site (see below). Nothing he gave was
superseded.

## The two Expeditions

Auto-Trail sells:

- **Expedition Coachbuilt** — 4 motorhomes, C63/C71/C72/C73, on
  `/motorhomes-range/expedition-coachbuilt/`, spec PDF `...Tech-Spec-Expedition-Coach.pdf`.
- **Expedition** — 7 campervans, 54/66/67/67 Flex/68/68 XL/68 XL Flex, on
  `/campervans-range/expedition/`, spec PDF `...Tech-Spec-Expedition-Van.pdf`.

These are different vehicles at different weights on different body styles, and nothing
in a model's own name distinguishes them — `EXPEDITION 68` and
`EXPEDITION COACHBUILT C73` only differ because the coachbuilt models carry the word.
The range label must therefore come from **which document the model was read out of**,
never from the model name. The adapter's range identifiers keep them apart explicitly:
`expedition-coachbuilt` vs `expedition-van`.

The PDF titles do disambiguate — `EXPEDITION COACHBUILT — TECHNICAL SPECIFICATION`
against `EXPEDITION VAN — TECHNICAL SPECIFICATION` — but the campervan range is called
"Expedition" everywhere on the website, so "Expedition Van" is a document-internal name
only. Do not surface it to reviewers as the range name.

## Where the data lives

**Not in the HTML, and not in the price list.** Both were checked:

- **Model page HTML** carries a "Specifications" block with berths, seatbelts, total
  seats, standard engine, length and width — but **no weights and no price**. It is
  server-rendered (`needs_javascript=no`), and is useful as the cross-check, not as the
  source.
- **The price and options list PDF** (`Motorhome-Price-and-Options-List-1st-June-2026.pdf`)
  is a **rasterised image**. `extract_text` returns the page headings and footnotes only;
  page 2 yields four text runs in total and not one of them is a price. There is no
  published, machine-readable price for Auto-Trail. `rrp_pounds` is therefore never
  proposed, as for Swift and Rimor.

Everything numeric comes from the per-range **Website Tech Spec** PDFs, linked from each
model page (not from `/downloads/`, which lists brochures and owner's manuals only).

A model's block looks like this, verbatim from the Expedition Coachbuilt document:

```
EXPEDITION COACHBUILT C63
Sleeps 4
T otal seats 4
Seatbelts 4 (inc. driver)
Standard engine 140BHP
Length 6338mm
Width (excl. door mirrors) 2373mm
(2408mm with awning)
Height 3060mm
...
Max. gross weight (with 3650kgs no cost option) 3500/3650kg
Max. gross train weight (with 3650kg upgrade MGTW increases to 4900kg) 4750/4900kg
Mass in running order 2960kg
Wheel base 3450mm
Max. towing weight 1250kg
```

## Discovery, per run

The spec PDF URLs carry WordPress upload counters — `Tech-Spec-Excel-4.pdf`,
`Tech-Spec-F-Line-8.pdf`, `Tech-Spec-Imala-6.pdf` — which increment every time Auto-Trail
re-uploads a document. **They must be rediscovered each run and never hardcoded.** The
chain is: range page → any model page → the `Tech-Spec` PDF link on it.

### Do not use the sitemap

`/sitemap.html` lists a complete-looking set of model URLs and is **stale**:
`excel-675b`, `excel-690l`, `f-line-f68` and `grande-frontier-gf88` all 404. The
`/motorhomes-range/<range>/` and `/campervans-range/<range>/` pages are current and
agree exactly with the price list's "Applicable to" lines. Use those.

Model URL slugs are not derivable from model names — the F-Line F67 lives at
`/motorhomes/f67/`, and the campervan Expedition 54 at `/campervans/54-2/`. Read links,
don't construct them.

## The self-check

Each document states its own roster: `Applicable to Expedition Coachbuilt C63, C71, C72,
C73`. That line is the authority on how many models the document contains, and the
adapter asserts the blocks it found against it. This is a completeness check the
manufacturer publishes against itself, and it is what makes a silently-dropped model
detectable.

For the weights and berths, three checks:

1. **Berths are published twice.** The upper bound of `Sleeps 4-6` and the separate
   `Max. No. of berths` row agree on **all 21 models that state both, with no
   disagreement** — which is both why `berths` takes the trailing figure and how a
   slipped block boundary is caught. The four campervan documents have no
   `Max. No. of berths` row, so this is available on 21 of 37.
2. **Ordering and payload plausibility**, available on all 37: `MGTW > MTPLM > MRO`, and
   `payload = MTPLM − MRO` within 100–2000 kg (real values run 355–965 kg). This is the
   drop criterion, and it is what catches the C71 trap below.
3. **`MGTW − MTPLM == max towing weight`**, on the six motorhome ranges. Holds on 17 of
   the 18 rows publishing all three. Used as a warning, not a drop — see below.

Axle loadings are *not* usable as a check: only 4 of the 10 documents print numbers
against them, the rest carry the label with `Included` / `Cost option` and no figure.

### The one product that fails check 1

**Frontier Comanche** publishes MTPLM 5000 kg, MGTW 6000 kg and max towing weight
1500 kg. 6000 − 5000 = 1000, not 1500. This is Auto-Trail's own inconsistency, not a
parse error: Comanche is a 5000 kg tri-axle (`Max. rear axle loading 2x 1600kg`) that has
evidently kept the 1500 kg towing figure belonging to the 4500 kg Delaware and Scout.

The parsed MTPLM, MRO and payload for Comanche are all correct and internally consistent
(5000 − 4035 = 965 kg payload; axles 2100 + 2×1600 = 5300 ≥ 5000). Dropping the product
would discard good data over a bad towing figure in a field FMLV does not carry, so
check 1 is a **narrated warning**, not a drop, and check 2 is the drop criterion.

## Traps

1. **`Max. gross train weight` is not `Max. gross weight`.** MGTW is the towing-combination
   figure and is 1250–2500 kg larger. Any pattern matching `Max. gross` loosely will read
   4750 kg as the MTPLM of a 3500 kg motorhome. Match the labels in full.

2. **Expedition Coachbuilt C71 has no `Max. gross weight` row at all.** The document goes
   straight from axle loadings to gross *train* weight. This is the trap and the reason
   check 1 matters: a loose parser reads C71's MTPLM as 4750 kg, and the result — a
   plausible 7.26 m motorhome with a 1670 kg payload — looks entirely reasonable. MTPLM
   must be optional, and absent rather than guessed.

3. **Campervans use a different label**: `Max. authorised weight 3500kg`, not
   `Max. gross weight`. All 16 campervans publish MTPLM this way. Matching only the
   motorhome label loses every campervan weight while looking like "campervans don't
   publish weights".

4. **MTPLM is often several figures**: `3500/3650kg`, and Imala 736 prints
   `3500/3650/4400kg`. The **first** is the standard build; the rest are upgrade options.
   Take the leading figure.

5. **Never parse the parenthetical.** `Max. gross weight (with 3650kgs no cost option)`
   is boilerplate reproduced even where it contradicts the row — the Frontier document
   carries that exact parenthetical on rows whose value is 4500 kg and 5000 kg. Anchor on
   the figure at the **end** of the row, per the tail-anchoring rule in
   [README.md](README.md).

6. **A kerning artefact inserts spaces after some capitals**: `T otal seats`, `Ty re s`,
   `T ruma`, `Max. T orque`. Normalise `([A-Z]) (?=[a-z])` before matching labels, or
   `Total seats` never matches and seat counts come back empty.

7. **Both hyphen and em-dash appear as separators**, sometimes in the same document
   (`- 3,500kg/3,650kg manual` and `— 3,500kg/3,650kg manual` both occur in the
   Expedition Coachbuilt PDF). Normalise before matching.

8. **All-caps section headings look like model headings.** `POWER`, `SAFETY`,
   `INSULATION & STRENGTH`, `LIVING ROOM FEATURES` are indistinguishable from
   `EXCEL 690T` by case alone. Anchor model blocks on the document's own
   `Applicable to` roster rather than on "is this line all-caps".

9. **The F-Line F74 publishes `Height 2880m`** — a typo for 2880mm. The `mm` unit is
   required rather than optional, so the value stays unread and the adapter narrates the
   gap. Accepting a bare `m` would mean reading a figure whose unit the document got
   wrong; every other F-Line states 2880mm correctly.

10. **The roster repeats the range name on its first entry only**, and does it
    inconsistently: `Excel 620S, 620G, 690T`, but `F-LINE F60, F62, ...` against a
    `F-Line` label, and `V-Line 540 SE, 610 SE, ...` against a `V-Line SE` label. Model
    names are taken by stripping leading words for as long as they keep spelling out the
    range label, compared on alphanumerics only. Frontier's roster (`Delaware, Scout,
    Comanche`) carries no range name at all and is left untouched.

## Berths and seats: different rules, on purpose

`berths` takes the **upper** figure of `Sleeps 4-6`; `mh_passenger_seats_inc_driver`
takes the **lower** figure of `Seatbelts 4-6 (inc. driver)`.

The asymmetry is Auto-Trail's, not an oversight. The berth maximum is confirmed by their
own `Max. No. of berths` row on all 21 models that publish one, and it is how they
market the vehicles — the `Sleeps 4-6` C73 is sold as "truly a six-berth". The upper belt
figure has no such confirming row, and the same sentence calls it "*optional* six-belt",
so the lower figure is what the vehicle has as built.

**Worth a reviewer's confirmation:** the seat-belt choice is the weaker of the two. If
FMLV wants the maximum belted seats rather than the standard, that is a one-line change
(`_leading_int` to `_trailing_int` in `parse_models`).

## Product count

37, cross-confirmed four ways: the ten documents' `Applicable to` rosters, the live
range pages, the price list's per-range "Applicable to" footnotes, and the row counts
within the documents themselves (37 `Sleeps` rows, 37 `Chassis type` rows). The
motorhome figure of 21 also matches the price list PDF exactly.

## First run

13 August 2026, all ten ranges: **37 products, 30 fetches, 31 seconds, none dropped.**
Two warnings, both expected and both genuine document faults rather than parse failures:
the F74 height typo and the Comanche towing figure.

Three products hand-checked against the source document, chosen to cover the three
weight traps:

| | Berths | Seats | L×W×H (mm) | MTPLM | MRO | Payload |
|---|---|---|---|---|---|---|
| Imala 736G | 6 | 4 | 7258×2353×3065 | 3500 | 3075 | 425 |
| Adventure 65 | 4 | 4 | 6363×2050×2680 | 3500 | 3145 | 355 |
| Grande Frontier GF-80 | 4 | 2 | 8070×2350×3040 | 4500 | 3725 | 775 |

All three match. Imala 736G exercises the multi-value `3500/3650/4400kg` row, Adventure
65 the campervan-only `Max. authorised weight` label, and GF-80 the parenthetical trap —
its row reads `Max. gross weight (with 3650kgs no cost option) 4500kg`, and 4500 is
correct.

The run also emits `the export has no rows for 'Auto-Trail', so every scraped product was
classified as new`, which is the unconfirmed join key below doing exactly what it should.

## What is unverified

- **`fmlv_manufacturer = "Auto-Trail"` is inherited from
  `resources/manufacturers-full-list.csv` (ID 61) and has not been confirmed against a
  real FMLV export** — there is no Auto-Trail export under `data/exports/`. If the export
  spells it differently (`Auto-Trail VR Ltd`, the legal name on the price list), the run
  will find an empty baseline and propose all 37 products as new. Confirm before the
  first real run is reviewed.
- `ncc_supplier_name = "Auto-Trail"` is likewise inherited and not confirmed against the
  NCC export dropdown.
- Whether FMLV wants the awning-inclusive width (`2408mm with awning`) or the bare width
  (`2373mm`) is a judgement — the adapter takes the bare width, which is the figure the
  model page HTML also shows.
- **`body_type` is unset for all 16 campervans.** Only the six coachbuilt and A-class
  ranges publish a `BODY STYLES` section. All four campervan ranges are 2680mm high-roof
  Ducato conversions, but Adventure fits an elevating pop-top as standard (`Included`)
  while Expedition offers one as a cost option and the V-Lines not at all — so whether
  they are `campervan_high_top`, `campervan_elevating_roof` or a mix is a domain call
  the documents do not settle. Nothing is guessed.
- The **cross-document check against the model page HTML** — which republishes berths,
  seatbelts, total seats, length and width per model — is documented here but **not
  implemented**. The in-document checks proved sufficient, and using it would cost 37
  extra fetches per run. It is the obvious next defence if a parse ever looks wrong.
