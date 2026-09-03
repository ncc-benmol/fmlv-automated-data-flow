# Bailey — site survey and adapter notes

Surveyed and built 20 August 2026. Twelfth adapter.

Bailey is a British manufacturer (Bailey of Bristol), building motorhomes and campervans
alongside touring caravans on the same site. The requester's instruction: caravans are out
of scope entirely — motorhomes and campervans only.

## What the requester brought to the survey

- **Two example model URLs**, one motorhome and one campervan, both from the same
  observation: "it has lots of good data on the page."
  - `https://www.baileyofbristol.co.uk/motorhomes/adamo/adamo-60-2/`
  - `https://www.baileyofbristol.co.uk/campervan/endeavour/endeavour-b62/` — "the URL
    that has all the weights and measures."
- **"I can't see anything really not straightforward about Bailey."** No gotchas flagged
  up front, beyond excluding caravans.
- **`ncc_supplier_name` is `Bailey of Bristol`**, supplied directly from the requester
  having checked Nova's own export dropdown — confirmed working: `fmlv fetch-export`
  succeeded and returned 24 products.

Both URLs turned out to be exactly right, and the observation about data richness held up
completely — this is the cleanest source surveyed of any manufacturer so far.

## Where the data lives: one URL per vehicle, no PDF needed

Every model has its own page — `/motorhomes/<range>/<slug>/` or
`/campervan/<range>/<slug>/` — plain server-rendered HTML, `needs_javascript=no`. Each
page carries a **"Technical specification"** section with one row per fact and, critically,
**explicit literal `Range` and `Model` text fields** — no splitting a marketing name to
find them, unlike every manufacturer surveyed before this one.

The Adamo 60-2 page's technical specification, in full:

```
Range                                    Adamo
Model                                    60-2
Designated Travelling Seats              2
Berths                                   2
Cab                                      Ford Transit Cab (Magnetic Grey)
Engine                                   165bhp / 1995cc
Chassis                                  Ford Transit skeletal chassis
Roof Profile                             Low Profile
Overall Body Length                      6.096m
Max Width Vehicle with Mirrors Extended  2.740m
Max Width Vehicle with Mirrors Folded    2.393m
Overall Height                           2.863m
Tyre Sizes                               235/65R16C
MTPLM                                    3500kg
MRO                                      2827kg
Total User Payload                       673kg
```

And the price, quoted elsewhere on the same page with its basis stated in full:

> **RECOMMENDED OTR PRICE: £75,999.** Recommend Retail Price as at 1st August 2026
> (prices include VAT @ 20%). This on the road price includes a cost of £1,400 which
> comprises a 12-month road fund licence, first registration fee, a set of number plates
> and delivery to a Retailer in Great Britain.

Campervan pages (Endeavour B62 checked) carry the same shape, with one difference: a
single **`Base Vehicle`** field (`Ford Transit`) in place of the motorhomes' separate
`Cab`/`Chassis` rows, plus a `Roof Profile` given as a van body-height code (`H3`) rather
than a named profile, and a third width figure, `Overall Width`, alongside the two mirror
variants — see the width note below.

**No PDF was needed and none was used.** Bailey do publish brochures and price lists as
PDFs (a modal on every page offers to download them), but nothing in them is needed —
every field FMLV wants is already in the page's own HTML, one vehicle per page, with
nothing to attribute across a column.

## Why this is structurally the safest source surveyed yet

Every other PDF-sourced manufacturer's real risk has been **column attribution** — Morelo,
Swift, Sunlight and Etrusco all print several layouts side by side and have to keep each
number matched to the right one; Auto-Trail avoided it by giving each model a whole page
to itself, which was the best case found until now.

Bailey does better: **one URL is one vehicle**, so there is no column to misalign at all,
in HTML or otherwise. The self-check still holds and was checked directly: **`Total User
Payload` equals `MTPLM - MRO` exactly** on every page checked (Adamo 60-2: `3500 - 2827 =
673`; Endeavour B62: `3500 - 2912 = 588`), which is a genuine arithmetic check even though
there is no column-slip failure mode for it to actually be defending against here.

## Two places where the site's own naming disagrees with FMLV's, and two different calls

Trusting the page's own literal `Range`/`Model` fields felt safe given how explicit they
are — and mostly was, but not entirely. Per [`README.md`](README.md), "let the FMLV export
decide the range and model strings" is the default; both disagreements below were checked
against the real export, and the requester made the call on each rather than the default
being applied automatically.

1. **"Adamo XL" exists as its own range in FMLV; the site nests it under "Adamo".** The
   Adamo range's overview page (`/motorhomes/adamo/`) lists eight models under one URL,
   including three whose own page states `Range: Adamo`, `Model: XL-I` (and `XL-T`,
   `XL-DL`). FMLV's real export currently holds these three under a separate range,
   `Adamo XL`, model `I` / `T` / `DL`. **Requester's decision, 2026-08-20: follow the
   site.** `XL-I` / `XL-T` / `XL-DL` are just model names within the one `Adamo` range,
   not a second range — the adapter reads `Range` and `Model` verbatim, with no `XL-`
   splitting. This will propose merging the 3 existing `Adamo XL` products into `Adamo` on
   the first run; accepted as the intended outcome, not flagged as a problem to fix later.
   One consequence worth remembering: FMLV's range-level distinction between the 3500kg
   standard Adamo and the 4250kg Adamo XL chassis class disappears once the range name is
   shared — the weight class is still visible per model, just not filterable by range.
2. **"Autograph" on the site is "Autograph IV" in FMLV.** Every one of the six Autograph
   models states `Range: Autograph` on its own page; the real export holds `Autograph IV`
   for all six, and this one **is** treated as a naming gap to close rather than a
   deliberate merge — cosmetic only, no vehicles are combined. **Fix:** map `Autograph` →
   `Autograph IV`.

Adamo, Alora, Endeavour and Endurance all matched the export's range name verbatim —
Autograph is the only range-name correction the adapter makes.

## The roster: 5 ranges, 22 current models

| Range (FMLV) | Site range page | Models |
|---|---|---|
| Adamo | `/motorhomes/adamo/` | 60-2, 69-4, 75-4i, 75-4t, 75-4dl, XL-I, XL-T, XL-DL |
| Alora | `/motorhomes/alora/` | 69-4i, 69-4t, 69-4s |
| Autograph IV | `/motorhomes/autograph/` | 72-2, 79-4i, 79-4t, 79-4xt, 79-4f, 81-5 |
| Endeavour | `/campervan/endeavour/` | B62, B65, B68 |
| Endurance | `/campervan/endurance/` | E62, E65 |

The two motorhome-range index pages (`/motorhomes/` lists Adamo, Alora, Autograph;
`/campervan/` lists Endeavour, Endurance) are each a reliable entry point — every model
linked from a range's own overview page (e.g. `/motorhomes/adamo/`) turned out to have a
working, data-complete page.

## Body type: unusually reliable, because Bailey states it directly

Every motorhome page checked states **`Roof Profile: Low Profile`** verbatim — Adamo,
Adamo XL and Alora and Autograph all read the same. No A-class or over-cab range appears
to exist currently, so `Low Profile` → `coach_built_low_profile` can be trusted directly
as the manufacturer's own classification, not an inference from dimensions the way
Bürstner's had to be abandoned.

Campervans state a van body-height code instead (`H3` seen on both Endeavour B62 and
Endurance E62) and also give a literal `Overall Height` in metres, so the existing
height-threshold rule in [`README.md`](README.md) applies directly — 2824mm (B62) is
comfortably clear of the 2300mm line, so `campervan_high_top`.

**No Bailey campervan gets the elevating-roof variant.** The pop-top is explicitly listed
among factory-fit **optional** extras, and only for two specific models: "Pop-top roof to
create additional high level double bed... (B65 & B68 only)". Per the base-vehicle rule,
an option never changes what the vehicle is as standard, so this never flips
`campervan_high_top` to `campervan_high_top_elevating_roof` for any current model.

## Width: two mirror figures, no mirror-free one — use the folded figure

Every page gives `Max Width Vehicle with Mirrors Extended` and `...Folded`, never a true
body-only width. Per the base-vehicle rule ("exclude mirrors... where both figures are
given, take the narrower"), **`Mirrors Folded` is the one to use** for `mh_width_mm` on
both product types.

Campervan pages add a third field, plain `Overall Width`, which on the one page checked
(Endeavour B62) exactly duplicated the `Mirrors Extended` figure (`2.489m` both) — almost
certainly a template quirk rather than a genuine third measurement. It is not used.

## Open items, resolved by the requester

- **`74-4T` vs `75-4t` is a baseline typo, not a model change.** FMLV's baseline holds an
  Adamo model `74-4T`; the current site has no `74-4T` but does have `75-4t`, sharing the
  same bed-code suffix and the same Ford chassis — the same shape of trap Etrusco's
  `V 6.6 SF` / `V 6.8 SF` was. **Requester's decision, 2026-08-20: the data is identical,
  so this is the same vehicle** — FMLV's `74` was a mistake and should have read `75` all
  along. No special-casing needed: the two names are close enough (differing in one digit
  of four tokens) that the existing matcher should pair them on its own; the run's diff
  will read as a correction to the existing product rather than one new plus one
  disappeared, and a reviewer should accept it as such.
- **Endeavour's roster change is confirmed real, not a parse gap.** Baseline holds `B62`,
  `B63`, `B64`, `B65`; the site currently has `B62`, `B65`, `B68`. **Requester's decision,
  2026-08-20: correct as three models** — the range changed today, and `B68` is a genuine
  new model, not a discovery artefact.
- **A casing-only mismatch.** The site's own `Model` field for some Alora/Adamo layouts
  differs from the baseline only in letter case (`69-4I` vs baseline's `69-4i`). Cosmetic;
  recorded as published rather than force-matched to baseline's casing.
- **Price basis and model year are both explicit here**, unlike most manufacturers
  surveyed — the OTR price states its own VAT/fees breakdown and effective date on the
  page, and the export's `year` column already reads 2026 for every current-range model
  found, so there is no rollover ambiguity to resolve at this point.

## Two traps found while building, neither visible during the survey

1. **The price row this adapter first tried is dead on every campervan page.** The
   "Technical specification" section's own `OTR Price` (and `RRP Price`) rows are
   HTML-commented out for both Endeavour and Endurance — a block copy-pasted from
   Bailey's **caravan** template and disabled rather than adapted; its own tooltip text
   still reads "your new Bailey **caravan**". The fix was to read the price from the
   page's hero banner instead (`<small>OTR</small> £X`), which is present and correct on
   both product types — see `_HERO_PRICE`.
2. **`Chassis` is not always the base vehicle.** Every Ford-based range (Adamo, Adamo XL,
   Alora, Endeavour, Endurance) states the same brand in both `Cab` and `Chassis`, so it
   never mattered which was read — until Autograph IV, where `Cab: Peugeot Cab (Graphite)`
   and `Chassis: AL-KO AMC` disagree. AL-KO AMC is a subframe system bolted onto the
   Peugeot cab, not a vehicle manufacturer. **`Cab` is read first now, `Chassis` only as a
   fallback** — see `parse_model_page`.

Also caught, and handled with a small tolerance rather than a special case: **weights are
usually whole kilograms but not always** — Autograph IV 79-4F publishes MRO as
`3431.5kg`. A digits-only pattern silently matched just the `5` out of `.5kg` and returned
a 5kg motorhome on the first live run; `_kilograms` now captures the decimal point, and
`_reconciles` allows 1kg of slack for the case where two decimal figures each round
independently.

## First run — 20 August 2026

**22 layouts across 5 ranges, none skipped, none dropped.** 12 fetches: 5 range overview
pages plus one per model page they link.

| Range | Models | Prices |
|---|---|---|
| Adamo | 8 (60-2, 69-4, 75-4I, 75-4T, 75-4DL, XL-I, XL-T, XL-DL) | £75,999 – £88,499 |
| Alora | 3 (69-4I, 69-4T, 69-4S) | £75,499 (all three) |
| Autograph IV | 6 (72-2, 79-4I, 79-4T, 79-4XT, 79-4F, 81-5) | £94,499 – £98,699 |
| Endeavour | 3 (B62, B65, B68) | £72,999 – £75,999 |
| Endurance | 2 (E62, E65) | £72,999 – £75,999 |

All 22 prices read directly from `bailey.collect()` against the live site.

**Diff against the real FMLV baseline (run #15): 21 of 22 scraped matched a baseline
product, 1 new, 2 disappeared** — exactly `Endeavour B68` new and `B63`/`B64`
disappeared, both confirmed genuine by the requester before the run. **`Adamo 75-4t`
matched baseline's `74-4T` product** on the existing fuzzy matcher alone, no special-casing
needed, exactly as the requester predicted — the run's diff reads as a correction
(price, width) to that product rather than one new plus one disappeared. **86 proposed
changes, 21 of them year bumps, 199 fields checked and unchanged.**

Three products hand-checked against the source page and the run's own proposed changes:

| | Source | Proposed change |
|---|---|---|
| Adamo XL-I | Range Adamo, Model XL-I, MTPLM 4250kg | `manufacturer_range: Adamo XL → Adamo` (the merge), width 2740→2393mm, price 83,999→87,499 ✅ |
| Autograph IV 72-2 | Cab "Peugeot Cab (Graphite)", Chassis "AL-KO AMC" | `base_vehicle_manufacturer: Peugeot → AL-KO` was the first (wrong) result; fixed to stay `Peugeot`, matching baseline exactly — no change proposed for that field ✅ |
| Endeavour B62 | Hero banner "OTR £72,999"; commented-out `OTR Price` row in the tech-spec section | price read correctly from the hero banner; no reliance on the dead labelled row ✅ |

Confirmed end to end: `Bailey` appears in the review app's trigger dropdown, filtered by
`adapter_for()`.

## What happened to the requester's URLs

Both used directly as the model of what every page looks like — no near-miss document to
reject, unlike every EHG-brand survey so far. The observation that prompted the request
("lots of good data on the page") held up completely.

---

# Bailey — touring caravans

Surveyed and built 3 September 2026, as `src/adapters/bailey_caravan.py`. **The first
caravan adapter**, and the reason Bailey was chosen for it: the motorhome survey above
found this the cleanest source of any manufacturer, so the novelty could stay in the
schema work rather than being tangled up with a difficult site.

Note the correction to the survey above, which opens *"caravans are out of scope
entirely — motorhomes and campervans only."* That was true until 3 September 2026.

## Why a second adapter rather than a flag on the first

FMLV keeps motorhomes and touring caravans as **separate exports with separate schemas**
— 68 columns against 62, different body types, renamed dimensions, no base vehicle. One
NCC "Export Products by Supplier" action returns both sheets. So `bailey_caravan.py`
produces `Caravan` objects, declares `VEHICLE_CLASS = VehicleClass.CARAVAN`, and registers
under `("Bailey", caravan)` alongside `bailey.py`'s `("Bailey", motorhome)`.

Every *parsing* helper is imported from `bailey.py` unchanged — the `col-6` markup is
identical across both halves of the site.

## Where the data lives

`/touring-caravans/<range>/<slug>/`, one URL per vehicle, server-rendered, no JavaScript.
`/current-caravan-models/` links all 23 current models across the five ranges, so a full
sweep is one index fetch plus 23 pages.

**Two traps in the site's shape**, both of which cost time during the survey:

* **`/caravans/` returns an `image/png` with a 200 status.** Not a 404, not a redirect —
  the URL a person would guess serves a picture. `/touring-caravans/` is the real section
  root, and `/current-caravan-models/` is the index worth crawling.
* **A model page carries two blocks of `col-6` label/value pairs.** `Axle` and
  `RRP Price` sit in an early one, roughly 96KB in; `Range`, `Model` and every dimension
  sit under the "Technical specification" heading 240KB further down. A fixture trimmed to
  the section a reader would call "the spec table" silently loses the axle and the price,
  which is exactly what happened on the first attempt. The fixtures are whole pages.

Unlike the motorhome template, `RRP Price` is the live row here and `OTR Price` is the
empty one — the reverse of `bailey.py`, which has to read its price from the hero banner.

## What is collected, and what is deliberately not

Twelve fields off the page, plus two asserted: `body_type` (always rigid) and `twin_axle`
(from the `Axle` row). `Total User Payload == MTPLM - MRO` reconciles on all 23 models.

Three deliberate omissions:

* **`exterior_body_length_mm`.** Bailey publish internal and shipping length and nothing
  between them — the field is absent from all 23 pages. The requester's reading
  (3 September 2026) is that this is *an industry trend rather than one brand's
  omission*: "This may be a trend in the caravan industry to exclude that length, in
  which case more and more manufacturers will be leaving it out." So it was taken out of
  automated scope in `config/field_guide_caravan.csv` **globally**, not special-cased
  here, and dropped from `caravan_schema.REQUIRED` — FMLV itself holds it blank on 5 of
  Bailey's 27 live products, so requiring it would raise an error against FMLV's own data
  on every run. Whatever FMLV holds is left untouched.
* **Every layout flag.** The pages describe layouts in marketing prose — "parallel seat
  front lounge and rear island king size bed" — and a bed-sizes block naming Front
  Double, Front N/S Single and Rear Fixed Double. Enough to guess from, not enough to be
  right. `bailey.py` takes the same line.
* **`optional_equipment_payload_kilograms`.** Out of scope, and blank on all 92 real
  caravan products FMLV holds.

## Range names: the spec table abbreviates

| Spec table says | FMLV holds | Action |
|---|---|---|
| `Pegasus Black` | `Pegasus Black Edition` | corrected |
| `Phoenix Black` | `Phoenix Black Edition` | corrected |
| `Unicorn Deluxe`, `Alicanto Grande Deluxe`, `Discovery` | same | left alone |

The requester confirmed the longer form is the real name: the brochure and the URL slug
both carry "Edition", and only the specification template drops it. **The page's own
`<h1>` and `<title>` abbreviate it too** ("Pegasus Black Messina"), so there is no better
in-page source to read instead — hence a correction table, the same resolution used for
`Autograph` -> `Autograph IV` on the motorhome side.

`Unicorn Deluxe` is a **distinct range from `Unicorn`**, not a rename of it — the
requester was explicit. `Unicorn` (15 products) and `Phoenix +` (12) are entirely archived
in FMLV; do not collapse them into their Deluxe/Black Edition successors.

## What the first run should find

Checked against FMLV's own export (81 products, 27 live) on 3 September 2026:

* **Unicorn Deluxe Cabrera matches FMLV on all twelve collected fields.** A complete
  confirmation, and the strongest evidence the extraction is right — a parsing error
  would not land on twelve correct values.
* Real changes elsewhere, mostly 2026 price rises and weight revisions: Messina
  £32,499 -> £34,499 with MTPLM 1708 -> 1712kg; Phoenix 420 £23,599 -> £24,999;
  Discovery D4-2 £19,999 -> £21,499.
* **Four `Alicanto Grande` products will report as disappeared.** FMLV holds them live;
  the site now lists only `Alicanto Grande Deluxe`. Expected, not a fault — they need a
  human decision about deactivating them on the NCC site.
* Three Discovery models publish no awning size, and FMLV holds it blank for them too.
