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

**Specifications and price come from two different documents**, and joining them is the
only join this adapter makes.

- **Specifications** — the per-range **Website Tech Spec** PDFs, linked from each model
  page (not from `/downloads/`, which lists brochures and owner's manuals only).
- **Price** — the **range pages**, which carry a `Price from` figure per model in plain
  server-rendered HTML (`needs_javascript=no`).
- **Model page HTML** carries a "Specifications" block with berths, seatbelts, total
  seats, standard engine, length and width — but no weights. Useful as a cross-check, not
  as the source.
- **The price and options list PDF** (`Motorhome-Price-and-Options-List-1st-June-2026.pdf`)
  is a **rasterised image**. `extract_text` returns the page headings and footnotes only;
  page 2 yields four text runs in total and not one of them is a price. It is unusable as
  a parsing source — but see below, because it is not unusable as a *reference*.

### The price is the on-the-road price, and that was verified rather than assumed

The range page shows `F-Line F60 — Price from £69,005.00`. Rendering the scanned price
list to images and reading it (`pymupdf`, 130 dpi — `extract_text` cannot help here)
shows the same vehicle in a four-column table:

| Model | Ex works (excl. VAT) | VAT (20%) | Ex works (incl. VAT) | **On the road\*** |
|---|---|---|---|---|
| F60 | £56,975.00 | £11,395.00 | £68,370.00 | **£69,005.00** |

The website figure is the **on-the-road** column exactly, on **ten of ten models checked
across two ranges** (all six F-Line, all four Expedition Coachbuilt), and the arithmetic
closes: £68,370 + £635 = £69,005, where the £635 is the price list's own footnote —
"number plates, twelve month's vehicle excise duty, delivery and first registration fee
(as set by HM Government)". On-the-road is the basis FMLV's guide price records, so the
website figure is taken as published, with no adjustment.

An earlier revision of this document concluded that Auto-Trail publishes no
machine-readable price and that `rrp_pounds` is never proposed, as for Swift and Rimor.
That was right about the PDF and wrong about the manufacturer: the price was in the HTML
all along, one level up from the model pages that were surveyed. **The lesson worth
keeping is that "the document that should hold X does not" is not the same finding as
"X is not published."**

### Reading an image-only PDF, and the full audit it made possible

Nothing automated can extract from this document, but the pages can be **rendered and read
visually** — `pymupdf` at 130 dpi (`extract_text` is useless here, and the repo has no
poppler for `pdftoppm`). That turned an unusable document into the best verification the
project has had, because the price list also prints **Gross Vehicle Weight** and **Overall
Length** per model, from a source entirely independent of the tech specs.

All nine price pages were transcribed and cross-checked on 16 August 2026. Two things made
that trustworthy rather than a leap of faith:

1. **The document validates its own transcription.** Four price columns are redundant:
   ex works excl. VAT + VAT = incl. VAT, and incl. VAT + £635 = on the road. A misread
   digit breaks one of them. **34 of 37 rows are exactly self-consistent.**
2. **The result was then compared with the adapter's parse.** 110 values across all 37
   products — price, MTPLM, overall length — with **zero mismatches**.

The three rows that fail the arithmetic are **a misprint in Auto-Trail's price list, not a
transcription error** — confirmed by a second independent read of the document. Imala 730, 736 and 736G each show `£31,461.00` in the ex works
incl. VAT column where £67,884 + £13,577 = **£81,461** — an 8 printed as a 3. The
on-the-road column is unaffected and correct (£81,461 + £635 = £82,096, exactly as
printed), so the figure FMLV records is right and nothing needs changing. Worth passing
back to Auto-Trail.

That audit is also what filled the one gap the parser could not: see the C71 note below.

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

1. **The berth maximum is published twice.** The upper bound of `Sleeps 4-6` and the
   separate `Max. No. of berths` row agree on **all 21 models that state both, with no
   disagreement**, which is how a slipped block boundary is caught. The four campervan
   documents have no `Max. No. of berths` row, so this is available on 21 of 37.

   Note the check compares the two published *maxima* with each other, not either of them
   against `berths`. `berths` records the **lower** bound — the standard build, per the
   base-vehicle rule in [`README.md`](README.md) — so comparing it against
   `Max. No. of berths` would reject every model whose `Sleeps` is a range, which is 17 of
   the 37, while catching nothing. The adapter keeps `sleeps_max` alongside `berths`
   purely so this check retains its full strength.
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

   **The figure does exist, in the price list**, which gives C71 as `3,500/3,650/4,400kg`.
   That document is a rasterised image, so no parser can reach it — but a person can read
   it, and on 16 August 2026 one did. C71's MTPLM is **3500 kg**, and it now comes from
   `_MANUALLY_SOURCED_MTPLM_KG` rather than being left blank.

   Three independent things agree on that figure, which is why it was trusted:

   - The price list prints `3,500/3,650/4,400kg`, and the transcription of the whole
     document was validated against Auto-Trail's own VAT arithmetic on all 37 rows. A
     second, independent read of the same document on 16 August 2026 reproduced all 21
     motorhome rows identically, including this one.
   - **The optional extras pages confirm which of the three figures is the vehicle.**
     `Gross vehicle weight upgrade from 3,500kg to 3,650kg before vehicle registration —
     FOC` and `4,400kg chassis upgrade from 3,500/3,650kg before registration — £1,200`.
     So 3,500 kg is the build, 3,650 an upgrade applied before registration, and 4,400 a
     paid option. This also settles the one place the base-vehicle rule looked strained:
     a *no-cost* uprate is still an uprate, not the vehicle.
   - **The technical specification corroborates it without publishing it.** C71 states
     `Max. gross train weight 4750kg` and `Max. towing weight 1250kg`, and 4750 − 1250 =
     3500. The towing identity closes exactly, from a different document.
   - Its three siblings, C63/C72/C73, are all 3500 kg.

   The entry is deliberately marked as manual: `collect` narrates it on every run and the
   reviewer's provenance snippet says it was read off a page image, on what date, and that
   **it does not refresh itself**. Prefer a visible gap to a stale figure — that table
   holds one entry, not a copy of the price list, and it must be re-verified at each
   model-year changeover.

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

11. **Height can be two figures too**: the Frontier ranges publish `Height 3030/3106mm`.
    The extra 76 mm is the roof-mounted satellite dome in the optional Media+ pack, so
    3030 is the vehicle. This one is easy to get wrong in a way trap 4 is not: a
    dimension pattern anchored on `mm` skips *forward* past the slash and lands on 3106,
    the exact opposite of the leading-figure rule applied to weights. Capture the whole
    slash-separated group, then take the first.

12. **The page and the document name the same vehicle differently, and in a different
    order.** This is what makes the price join non-trivial. The roster says
    `V-Line 610 Sport` where the card says `V-Line Sport 610`, so neither string is a
    prefix of the other and no head-trimming aligns them; and the campervan cards say
    `Expedition Van 54` where the roster says just `54`. Position is no help either —
    the Frontier range page lists Scout, Delaware, Comanche while the document's roster
    says Delaware, Scout, Comanche. The join drops every word belonging to the range
    label, wherever it appears, then matches on suffix. Suffix matching is safe here for
    the same reason it is when slicing blocks: the variants extend the tail, so `68` does
    not take `68 XL`'s price.

## Berths and seats: both take the standard figure

`berths` takes the **lower** figure of `Sleeps 4-6`, and
`mh_passenger_seats_inc_driver` the **lower** figure of `Seatbelts 4-6 (inc. driver)`.
Both follow the base-vehicle rule in [`README.md`](README.md): FMLV has one column per
spec, and it records the vehicle as standard.

Auto-Trail's own copy makes the same distinction — the `Sleeps 4-6` C73 is sold as "truly
a six-berth, and *optional* six-belt motorhome". The sixth berth and the fifth and sixth
belts are both things the buyer adds.

**This reversed an earlier decision, and the reasoning behind that decision was sound**,
so it is worth recording why it did not survive. The adapter previously took the upper
berth figure, on the evidence that Auto-Trail's separate `Max. No. of berths` row agrees
with it on all 21 models that publish one. That evidence is real, and the check built on
it is retained — but it establishes that the *maximum* is genuinely 6, which is a
different question from what the vehicle sleeps as standard. FMLV records the latter
(decision from the NCC side, 16 August 2026: "most of the time the higher figure will be
related to options").

Consequently `berths` records 4 for the C73 while `sleeps_max` and `stated_max_berths`
both hold 6 and are checked against each other. The provenance snippet carries
Auto-Trail's published wording — `Sleeps: 4-6` — so a reviewer seeing `berths = 4` can
tell it was read from a range rather than printed as `4`.

## Product count

37, cross-confirmed four ways: the ten documents' `Applicable to` rosters, the live
range pages, the price list's per-range "Applicable to" footnotes, and the row counts
within the documents themselves (37 `Sleeps` rows, 37 `Chassis type` rows). The
motorhome figure of 21 also matches the price list PDF exactly.

## Runs

**13 August 2026**, all ten ranges: 37 products, 30 fetches, 31 seconds, none dropped.
Two warnings, both expected and both genuine document faults rather than parse failures:
the F74 height typo and the Comanche towing figure.

**16 August 2026**, after adding price, changing berths to the standard figure, and
sourcing C71's weight from the price list image: **37 products, 37 priced, none dropped,
one field blank** (F74's height, the `2880m` typo). Two warnings as before, plus a note
narrating the manually sourced C71 weight.

Products hand-checked against the source documents, chosen to cover every weight trap and
now the price too:

| | Berths | Seats | L×W×H (mm) | MTPLM | MRO | Payload | Price |
|---|---|---|---|---|---|---|---|
| Imala 736G | 4 | 4 | 7258×2353×3065 | 3500 | 3075 | 425 | £82,096 |
| Adventure 65 | 4 | 4 | 6363×2050×2680 | 3500 | 3145 | 355 | £85,860 |
| Grande Frontier GF-80 | 4 | 2 | 8070×2350×3040 | 4500 | 3725 | 775 | £129,784 |
| Frontier Comanche | 4 | 2 | 8799×2350×3030 | 5000 | 4035 | 965 | £125,506 |
| F-Line F60 | 2 | 2 | 5994×2350×2880 | 3500 | 2790 | 710 | £69,005 |

All match. Imala 736G exercises the multi-value `3500/3650/4400kg` row, Adventure 65 the
campervan-only `Max. authorised weight` label, GF-80 the parenthetical trap (its row reads
`Max. gross weight (with 3650kgs no cost option) 4500kg`, and 4500 is correct), and
Comanche the dual height.

The weights and lengths were checked against the **price list's** own Gross Vehicle Weight
and Overall Length columns as well as the tech spec — a genuinely independent document.
Comanche's 5,000 kg / 8.80 m and GF-80's 4,500 kg / 8.07 m both agree, as do all four
prices against the price list's On The Road column.

Runs currently emit `the export has no rows for 'Auto-Trail', so every scraped product was
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
- ~~Whether FMLV wants the awning-inclusive width or the bare width~~ — **settled, 16
  August 2026:** the bare width (`2373mm`), excluding both door mirrors and awning. Now a
  general rule for every manufacturer, in [`README.md`](README.md): "the basic width of
  the vehicle without wing mirrors, as most vehicles are normally quoted." It is also the
  figure the model page HTML shows.
- **Whether the £635 of on-the-road charges belongs in the guide price** was settled the
  same day — it does, FMLV records the on-the-road figure — but the corresponding question
  for the *other* manufacturers is still open. Morelo and Sunlight prices come from their
  price lists on an unstated basis, so Auto-Trail's prices may not currently be on the
  same footing as theirs.
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
