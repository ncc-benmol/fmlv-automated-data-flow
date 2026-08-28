# Bürstner — site survey and adapter notes

Surveyed and built 19 August 2026. Eleventh adapter.

Bürstner is an **Erwin Hymer Group** brand. Like Etrusco, Carado and Eriba it is
**non-core to the UK market** — only a selection of the full European range is sold here —
so per [`README.md`](README.md) the UK-market source is authoritative and should not be
reconciled against a wider European roster. Contact is Emma Hughes at EHG UK, who also
covers Etrusco, Carado and Eriba.

## What the requester brought to the survey

Two URLs and a warning, all of which turned out to matter:

- `https://www.burstner.co.uk/new-motorhomes/` — the UK dealer-network site.
- `https://www.camperuk.co.uk/burstner` — Camper UK, described as Bürstner's UK
  distributor.
- **The warning:** clicking through from burstner.co.uk for "more details" lands on Camper
  UK, and Camper UK's pages are stock listings for actual vehicles, which may carry extras
  that make the price not a clean base-vehicle figure. The requester's own words: "we don't
  want duplicates of the same model that have got extras."

That warning was accurate and became the reason neither of the two supplied UK URLs is the
final source — see below. Midway through the survey the requester supplied a third,
better URL directly: **`https://www.buerstner.com/gb/models`**, the GB edition of
Bürstner's own parent site, with the instruction to use it for specification and the UK
site for the range. That correction is the single most useful thing in this survey.

## Why burstner.co.uk and Camper UK are not the source

**burstner.co.uk is stale.** It lists 7 vehicle families and 27 layout tiles — Eliseo,
Lyseo TD Harmony Line, Limited T, Lyseo Gallery TD Harmony Line, Argos, Elegance, Lyseo I
Harmony Line — entirely in plain server-rendered HTML (an accordion: `main-title` = range,
`vehicle` = family, `layouts` = individual model tiles). **None of those family names exist
on the current parent site.** This is the model-year-changeover pattern in
[`README.md`](README.md) playing out on the UK dealer microsite specifically, one layer
behind the manufacturer's own site.

**Camper UK is dealer stock, confirming the requester's warning.**
`camperuk.co.uk/new-burstner-motorhomes` (the page every burstner.co.uk layout tile links
to, generically — not per model) lists 20 individual for-sale vehicles that collapse to
around 13–14 distinct model names, because several models appear two or three times
(`SIGNATURE SFT 7.1` three times, `HABITON X HMX 6.0` twice, `LYSEO TD HARMONY LINE 736`
twice). A second page, `camperuk.co.uk/motorhomes-for-sale/?COGManufacturer=Burstner`,
turned out not to be manufacturer-filtered at all — it lists Auto-Trail, Carado, Elddis,
Rimor and others alongside Bürstner, mixing used and new. Camper UK also mixes **current
range names with the discontinued burstner.co.uk names** in the same listing
(`LYSEO TD HARMONY LINE 736` next to `B66 600 C`), which is itself useful confirmation that
the old names are gone from the current range rather than a parsing accident.

Neither site publishes weights or dimensions in a form usable as a spec source — Camper UK
is priced stock, not a catalogue.

## Where the data actually lives: buerstner.com/gb

`https://www.buerstner.com/gb` is the parent site's **GB market edition** — plain HTTP,
`needs_javascript=no`, confirmed by fetching with `Fetcher` alone. The roster comes from
`/gb/models`, which redirects to `/gb/en/model-overview` — a single page whose full card
set (all 6 ranges) is rendered server-side and then filtered client-side by the
`?model=semiIntegrated` / `?model=campervan` query strings, which do **not** change what a
plain HTTP fetch receives.

### The roster: 6 ranges, 20 layouts

| Range | URL | Layouts | Price range (GBP) | Old name (burstner.co.uk / Camper UK) |
|---|---|---|---|---|
| Signature SFT (Fiat) | `/gb/signature` | 7.0, 7.1, 7.4, 7.5 | 94,895 – 99,395 | — |
| Signature SMT (Mercedes) | `/gb/smt` | 7.0, 7.1, 7.4, 7.5 | 109,995 – 114,495 | — |
| B66 Motorhomes (TD) | `/gb/b66/motorhomes` | 594, 644, 684, 690, 744 | 79,995 – 88,795 | Lyseo TD Harmony Line |
| B66 Campervans (C) | `/gb/b66/vans` | 600, 640, 644 | 64,995 – 69,995 | Campeo C |
| Habiton (HM) | `/gb/habiton` | 6.0, 6.1 | 88,995 / 92,395 | Eliseo (probable) |
| Habiton X (HMX) | `/gb/habiton` (same PDF) | 6.0, 6.1 | 96,795 / 102,995 | — |

No A-class or integrated range currently exists on the site — Argos, Elegance and Lyseo I
Harmony Line (the old integrated-range names) appear discontinued for the current model
year. No caravans, so nothing to exclude on that count.

**The overview card for each range confirmed which URL it links to** — this is how the
rebrands above were established: the "Campeo C" card links to `/gb/b66/vans` and its price
(£64,995) matches B66 Campervans' cheapest layout exactly; the "Lyseo TD Harmony Line" card
links to `/gb/b66/motorhomes` and its price (£79,995) matches B66 Motorhomes' cheapest
layout exactly. Both are the *same* range under its old marketing name, not a separate
product.

### The specs and price: five per-range PDFs, three of them unlinked

Each range has a "Prices & Technical Data" PDF, dated **June 2026** for Signature and B66,
**August 2026** for Habiton (one edition ahead — worth re-checking whether Signature/B66
have since been superseded too). All five extract as clean real text, no scanned images.

**Only two are linked in HTML** — `/gb/b66/motorhomes` and `/gb/b66/vans` each carry an
`href` straight to their PDF. `/gb/signature`, `/gb/smt` and `/gb/habiton` carry **zero**
`.pdf` references anywhere on the page (checked by grepping the full fetched HTML), yet all
three PDFs exist at the predictable URL the B66 pages' own links reveal:

```
/buerstner/01-relaunch-2025/technische-daten/26-08-17-uk/buerstner-technical-data-2027-<slug>-gb.pdf
```

`<slug>` is `b66-td`, `b66-c`, `signature-sft`, `signature-smt`, `habiton` — guessed and
confirmed by fetching (`signature-smt` was not linked anywhere, `habiton-x` and `sft`/`smt`
alone both 404, `signature-sft`/`signature-smt`/`habiton` all resolve). **This is a
Rimor-style unlinked-document risk on three of the five documents**: the dated folder
segment (`26-08-17-uk`) is what will change between editions, and the only place it is
observable in HTML is the two B66 links. The plan for an adapter: fetch a B66 page first,
read the date-folder out of its PDF href, then build the other four PDF URLs from the same
folder — never hardcode the date.

A representative table, from `buerstner-technical-data-2027-b66-td-gb.pdf`:

```
                                         594 TD          644 TD          684 TD          690 TD
Price                                    80,795.-        82,495.-        80,995.-        79,995.-
Overall length (approx. cm)              599             699             689             699
Overall width (approx. cm)               230             230             230             230
Overall height (approx. cm)              295             295             295             295
Technically permissible maximum
  laden mass (kg)*                       3500            3650            3650            3500
Mass in running order (kg) (+/-5%)*       3056 (2903      3196 (3036      3211 (3050      3141 (2984
                                          to 3209)*       to 3356)*       to 3372)*       to 3298)*
Permitted number of seats
  (including driver)*                    4               4               4               4
Sleeping berths standard / max.          2 - 4           2 - 4           2 - 4           2 - 5
```

(744 TD prints on its own single-column page a few lines later: £88,795, 736cm long,
MTPLM 4400kg.)

### The self-check: the same printed tolerance band as Etrusco and Sunlight

`Mass in running order (kg) (+/-5%)` prints the band alongside the figure, e.g.
`3056 (2903 to 3209)*`. 3056 × 0.95 = 2903.2, × 1.05 = 3208.8 — the band is a function of
the mass, so a slipped column fails the check. Payload would be derived as
`MTPLM − MRO`, as for Etrusco and Sunlight. **The same trap both of those adapters
document also appears here**: `Manufacturer-specified mass for optional equipment` sits
directly between the two masses and is not payload — it is a cap on factory-fitted extras
(as low as 8 kg on 690 TD, which would be a startling payload if misread).

Berths print as a `standard / max` pair per layout column — Signature SFT's row is
`2 - 3   4 - 5   2 - 3   4 - 5` across its four columns (SFT 7.0, 7.1, 7.4, 7.5
respectively). Per [`README.md`](README.md) the standard/lower figure is what gets
recorded, with the raw string kept in provenance.

## A price discrepancy found, and how it was resolved

**B66's cross-checks are clean**: the page-level floorplan price list on
`/gb/b66/motorhomes` (`B66 690 TD Floorplan | £79,995`) matches both the PDF and the
model-overview "from" card exactly, for every B66 layout checked.

**Signature and Habiton's overview cards do not match their own PDFs.** The
model-overview cards show Signature SFT from £76,495 and Habiton HM from £71,295 and
Habiton HMX 6.0 from £83,995 — but the PDFs' cheapest layouts in each range are £94,895,
£88,995 and £96,795 respectively.

This turned out not to be a same-model conflict at all. **Signature and Habiton's family
pages carry no per-layout price anywhere in HTML** — no floorplan list like B66's, no
per-model figure of any kind. The only website price for these two ranges is the single
range-level "from £X" teaser card on the model-overview page, which is not a price for any
specific layout — it is a range-level minimum, and per the requester's decision (2026-08-19)
**a figure that only points at the range's cheapest point is not what a per-model price
needs to be.** Both PDFs are also dated by their own cover page — "June 2026 Edition" /
"August 2026 Edition" — never "2027", so the requester's general rule ("use the website
unless the PDF states 2027 prices") does not hand the win to the PDF on model-year grounds
either; the PDF wins here simply because **it is the only source that prices the specific
layout at all.**

**Decision: use the PDF's per-layout price for every range, including Signature and
Habiton.** The overview's range-level "from" figure is not used as a price for any
layout — it is noted in provenance as a known, unexplained mismatch on two of the six
ranges, in case EHG can explain it later.

### The same jump shows up against the real FMLV baseline, and is not a parsing error

`ncc_supplier_name` is **confirmed as `Bürstner`** (the same string as `fmlv_manufacturer`)
— `fmlv fetch-export` succeeded and returned 26 active products. Comparing the baseline to
the PDF prices, by model:

| Range | Baseline price | PDF price | Change |
|---|---|---|---|
| B66 (7 models, TD + C) | £61,695 – £84,565 | £64,995 – £88,795 | **+5%**, consistent across all 7 |
| Signature SFT (4 models) | £73,095 – £75,795 | £94,895 – £99,395 | **+29–31%** |
| Habiton HM / HMX (2 models) | £68,495 / £80,795 | £88,995 / £96,795 | **+30% / +20%** |

B66's rise looks like an ordinary annual increase. Signature and Habiton's does not, and
neither PDF says "2027" anywhere in its visible text — only "June 2026 Edition" / "August
2026 Edition". The one hint either way is an internal asset path on the Signature page,
`2-pdp-signature-fiat-mj27` ("mj27" reads as *Modelljahr 27*), suggesting that page's
content is already built for the 2027 season even though its cover date says otherwise —
inference, not something the document states.

**Requester's decision (2026-08-19): treat `buerstner.com` (the parent site and its PDFs)
as the authoritative source for the model ranges, and treat the FMLV baseline as the
out-of-date side of the comparison.** The size of the jump is not treated as evidence
against the PDF — a stale baseline is exactly what this adapter exists to correct, not a
reason to doubt the new figures.

### FMLV's own range/model naming, read from the real export

The export also settles the range/model split, the same way it did for Etrusco:

| Site range | FMLV `manufacturer_range` | FMLV `model` pattern | In baseline now |
|---|---|---|---|
| B66 Motorhomes | `B66` | `TD 594`, `TD 644`, `TD 684`, `TD 690`, `TD 744` | 594, 644, 684, 690, 744 (all 5) |
| B66 Campervans | `B66` | `C 600`, `C 640`, `C 644` | 600, 644 only — **`C 640` is new** |
| Signature | `Signature` | `SFT 7.0`, `SFT 7.1`, `SFT 7.4`, `SFT 7.5` | all 4 (SFT only — **no SMT row exists yet**, so all 4 SMT layouts are new) |
| Habiton | `Habiton` | `HM 6.0`, `HMX 6.0` | 6.0 of each only — **`HM 6.1` and `HMX 6.1` are new** |

Two things worth carrying into the build:

- **FMLV treats B66 Motorhomes and B66 Campervans as one range, `B66`**, distinguished only
  by the model prefix (`TD` vs `C`) — matching the site's own single `B66` branding rather
  than the two separate URLs (`/gb/b66/motorhomes`, `/gb/b66/vans`) it lives at. Likewise
  `Habiton` and `Habiton X` collapse to one range, `Habiton`, distinguished by `HM` vs `HMX`.
  **`Signature` almost certainly works the same way** for `SFT` vs `SMT`, by the same
  pattern, though no SMT row exists yet to confirm it directly.
- **The model's letter-code and number are in the opposite order from the B66 PDF table.**
  The B66 tables print `594 TD`, `600 C` (number first); FMLV holds `TD 594`, `C 600`
  (letter first). The Signature and Habiton PDF tables already print letter-first
  (`SFT 7.0`, `HM 6.0`), matching FMLV directly — **only B66 needs its two tokens
  reversed.**

### Resolved: reading order is trustworthy here, and the berths split is the documented rule, not a bug

`extract_positioned_text` on B66's spec page shows almost every value run reports `(0, 0)`
— pypdf could not place them — but the handful it does place (the header names, and the
mass-in-running-order band where it wraps) confirm reading order already matches
left-to-right column order. So the adapter reads columns in plain reading order and
defends itself the way `morelo.py` and `auto_trail.py` do instead: **a row whose column
count disagrees with the header's is dropped for the whole table**, never guessed at.

The berths split against baseline (`594 TD` and `644 TD` recorded as `4`, `684 TD` and
`690 TD` as `2`, where every column's own printed figure is `2 - 4` or `2 - 5`) is real,
and is the [`README.md`](README.md) rule working as intended, not a misread: the standard
(lower) figure is what FMLV records, and the baseline predates this adapter. The first
live run confirmed it — see below.

Similarly, the `/gb/signature` and `/gb/habiton` family pages each carry one generic
"Further key data" fact table — a single representative spec, not one row per layout —
and its figures disagree in small ways with the PDF (717×**230**×284cm and MTPLM **3500**
kg on the page, versus 717×**235**×284cm and MTPLM **3650** kg for every Signature SFT
layout in the PDF). **Use the per-layout PDF, never this page-level table** — the first
run's diff against baseline shows this was the right call: FMLV's own baseline held the
page-level 230mm/3500kg figures, and the adapter correctly proposes the PDF's 235mm/3650kg
as a genuine spec change, not a parse error.

Similarly, the `/gb/signature` and `/gb/habiton` family pages each carry one generic
"Further key data" fact table — a single representative spec, not one row per layout —
and its figures disagree in small ways with the PDF (717×**230**×284cm and MTPLM **3500**
kg on the page, versus 717×**235**×284cm and MTPLM **3650** kg for every Signature SFT
layout in the PDF). **Use the per-layout PDF, never this page-level table.**

## `ncc_supplier_name` and `fmlv_manufacturer` are confirmed

`ncc_supplier_name` is **`Bürstner`** — the same string as `fmlv_manufacturer`, umlaut and
all — confirmed 19 August 2026 by running `fmlv fetch-export` successfully, which returned
26 products (13 of them the current 2026 model year, the rest a 2022-dated prior
generation the diff run does not compare against).

## Deliberately not attempted: `body_type`

FMLV's own baseline shows two splits that do not line up with anything this document
publishes:

- **B66 TD 744 is `a_class`**; every other B66 TD and every Signature SFT layout is
  `coach_built_low_profile`. TD 744 *is* the outlier of its range in the document — it sits
  in its own single-column table on a heavier chassis (4400kg against its siblings' 3500 /
  3650) and is 2990mm tall against their 2950mm — but none of that says "A-class", and the
  one signal that would, **width, does not separate it at all**: every B66 TD is 2300mm,
  where an A-class body is normally wider than the semi-integrated it shares a range with.
  Checked 27 August 2026. (An earlier version of this note recorded TD 744 as 2910mm and
  *shorter* than its siblings; that was wrong — it is the tallest.)
- **B66 C 644 has an elevating roof as standard** (`campervan_high_top_elevating_roof`);
  its sibling C 600 does not (`campervan_high_top`) — but the PDF's `Sleeping roof` row,
  the only candidate signal, prints values for the *first two* columns (600 C, 640 C) and
  is blank for the third (644 C), the opposite of what baseline says.

Guessing a uniform rule from height or from the `Sleeping roof` row would risk proposing a
wrong "correction" to an existing, correct classification. `body_type` is left unset for
every Bürstner product — new and existing alike — so an existing classification is never
touched, and a new layout (`C 640`, `HM 6.1`, `HMX 6.1`, all four `SMT`) surfaces as an
honest gap for a reviewer to classify by eye rather than a guess. `mh_height_mm` is still
collected for every layout, which is what that classification needs.

## `base_vehicle_manufacturer`: read from the document, cross-checked against the range

Each of the five documents names its base vehicle **once**, in the engine/`Chassis
Equipment` list rather than in the layout table — `Fiat Ducato Multijet 3 - 2.2l - 140 hp
- Euro 6E` on the B66 and Signature SFT documents, `Mercedes Benz Sprinter 4,5 t - 417
CDI` on Signature SMT, `Mercedes Benz Sprinter 317 CDI` on Habiton. So this is a
document-level fact shared by every layout in it, unlike everything the layout tables
carry, and it is read once per document by `published_chassis`.

Two things that shape matters for:

- **The make is anchored to the base vehicle's own model name, not just the make.** The
  Habiton document carries `Mercedes Comfort Seats` and `Mercedes emergency call system`
  in its equipment lists, the first of them only 34 lines from the real chassis line, so
  a pattern matching `Mercedes` alone reads a seat trim option as the base vehicle.
- **`DOCUMENTS` still records a per-range make, but as a cross-check rather than the
  value.** The document is the live source and wins where the two disagree, per
  [`README.md`](README.md); the displaced make is written into the provenance snippet so
  a reviewer is told the adapter expected otherwise — because the competing reading of a
  disagreement is that the document changed shape and the line was misread. All five
  agreed as surveyed, so nothing changed value when this was introduced. Bürstner writes
  `Mercedes Benz` unhyphenated, and **FMLV holds neither that nor `Mercedes-Benz` — it
  holds `Mercedes`**, in all 35 of its Mercedes rows across four manufacturers. That is
  what is recorded. The requester confirmed it 27 August 2026: "we say Mercedes not
  Mercedes Benz in FMLV, meaning the same thing but shorter". The adapter shipped the
  long form initially and nobody saw it, because the field was not registered as
  provenance and so was never proposed; the same slip was in `coachman.py` (four
  undecided proposals in the queue) and `morelo.py`.

**Why this needed fixing at all.** The value was set on the model from the first run but
never registered in the provenance dict, and that dict is the pipeline's only record of
what an adapter looked at: `diff/compare.py` compares only the fields it names, and
`store/changes.py` proposes only those fields for a `NEW_PRODUCT`. An unregistered value
is therefore silently dropped — which is why the 13 layouts FMLV already held looked
correct (their baseline value carried through untouched, never actually confirmed) while
all seven new ones (`B66 C 640`, `Habiton HM 6.1`, `HMX 6.1`, all four `SMT`) reached the
upload CSV with `base_vehicle_manufacturer` blank, a REQUIRED field. Setting a field is
not enough; it has to be registered. The same omission was found and fixed in
`morelo.py` and `sunlight.py` at the same time.

## What is still unconfirmed

- Whether the Signature and B66 PDFs (June 2026 edition) have since been superseded by an
  edition matching Habiton's August 2026 date.
- The price basis (on-the-road vs ex-works) is not stated anywhere found; recorded as
  published per the guide-price rule in [`README.md`](README.md).
- Whether the large Signature/Habiton price and MTPLM increases reflect a genuine chassis
  upgrade for the 2027 season (the coherent reading — higher MTPLM alongside a higher
  price) or something else. The requester's decision stands regardless: `buerstner.com`
  is the authoritative source and the FMLV baseline is the out-of-date side.
- **`Mass in running order (kg) (+/-5%)` for Habiton X prints one band for two
  columns** (`HMX 6.0` and `HMX 6.1` share one printed figure where every other table
  gives one per column) — both layouts are missing `mro_kilograms` and the derived
  `mh_payload_kilograms` as a result. Left blank per the missing-data rule rather than
  guessed; re-check if Bürstner reissue this document.

## First run — 19 August 2026

**20 layouts across 6 ranges, none skipped, none dropped.** 7 fetches: 2 to discover the
dated document folder from the B66 pages' own links, 5 for the technical-data PDFs
themselves.

| Range | Layouts | Prices | Chassis |
|---|---|---|---|
| Signature SFT | 4 (7.0, 7.1, 7.4, 7.5) | £94,895 – £99,395 | Fiat |
| Signature SMT | 4 (7.0, 7.1, 7.4, 7.5) | £109,995 – £114,495 | Mercedes |
| B66 (TD) | 5 (594, 644, 684, 690, 744) | £79,995 – £88,795 | Fiat |
| B66 (C) | 3 (600, 640, 644) | £64,995 – £69,995 | Fiat |
| Habiton (HM) | 2 (6.0, 6.1) | £88,995 / £92,395 | Mercedes |
| Habiton X (HMX) | 2 (6.0, 6.1) | £96,795 / £102,995 | Mercedes |

**Diff against the real FMLV baseline (run #11): 13 scraped matched 13 baseline products
byte-identically on range and model — no fuzzy-match ambiguity anywhere, unlike Etrusco's
first run.** 7 new (`B66 C 640`, `Habiton HM 6.1`, `Habiton X HMX 6.1`, all four Signature
SMT layouts), 0 disappeared, 145 proposed changes of which 13 are year bumps, 44 fields
checked and found unchanged.

Three products hand-checked against the source document and the run's own proposed
changes:

| | Source | Proposed change |
|---|---|---|
| B66 TD 690 | £79,995, MRO 3141 (2984–3298), MTPLM 3500 | price 76,295→79,995, MRO 2990→3141, payload 510→359 ✅ |
| Signature SFT 7.0 | £94,895, 717×235×284cm, MTPLM 3650, MRO 3163 | price 73,095→94,895, width 2300→2350mm, height 1980→2840mm, MTPLM 3500→3650, MRO 2880→3163, payload 620→487 ✅ |
| Habiton X HMX 6.0 | £96,795, height 285/299cm (base 285), MTPLM 4100, seats 4 | price 80,795→96,795, height 1900→2850mm, MTPLM 3880→4100, seats 2→4 ✅ (no MRO/payload proposed — the known gap above) |

**Zero `type_*` (`body_type`) changes proposed anywhere** — confirms the deliberate
omission above is working as intended. **One berths correction proposed** (`B66 TD 594`,
`4→2`), exactly the divergence flagged during the survey and resolved per the standard
(lower-figure) rule rather than suppressed.

Confirmed end to end: `Bürstner` appears in the review app's trigger dropdown, filtered by
`adapter_for()`.

## What happened to the requester's URLs

`burstner.co.uk` and `camperuk.co.uk` were both verified and both rejected — the first for
being a stale roster of discontinued model names, the second for being dealer stock with
duplicate/mixed-condition listings, exactly as the requester warned. The specification
source is the URL supplied midway through the survey, `buerstner.com/gb/models`.
