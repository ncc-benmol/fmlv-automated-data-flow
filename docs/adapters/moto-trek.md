# Moto-Trek — site survey and adapter notes

British, Rotherham. Launched 2012 by Equi-Trek, the UK's largest luxury horsebox maker, and
still part of Trek-Group — which is why a race-car transporter and a braked trailer sit in
the same vehicle list as the motorhomes. Survey date **27 August 2026**; adapter written the
same day, `src/adapters/moto_trek.py`.

## What the requester brought to the survey

- The FMLV name is **`MOTO-TREK LIMITED`**, given as already formatted to match the export.
  It does match, exactly, on all 19 rows.
- The website is <https://moto-trek.co.uk/>.
- **"Slide-Outs" is not a motorhome type.** It is a feature of their standard coachbuilts and
  campervans, and the site's `/slideouts/` page is a marketing grouping. So it is neither a
  `manufacturer_range` nor a `body_type`, and FMLV agrees — it holds no Slide-Outs range.
- **The data on the site is good.** Broadly true: everything in scope is in plain
  server-rendered HTML, and every price the site publishes matches FMLV to the pound. The two
  qualifications are that the site publishes *less* than FMLV holds (no seats anywhere, no
  payload except on one model) and that FMLV holds some figures the site contradicts — see
  "What a first run would propose".

All three held up. The Slide-Outs point mattered most: the nav menu groups X-Cite, Euro-Treka
and Pioneer under "Slide-Outs", and taking that as the range would have proposed a rename on
four products that FMLV already files correctly under `X-Cite`, `Euro-Treka` and `Pioneer`.

## Where the data lives: plain HTML — and there ARE five hidden PDFs

**The first pass of this survey concluded there was no PDF anywhere, and that was wrong.**
Recording the error because the reasoning was the exact one `README.md` warns against:

- No `.pdf` href on `/vehicle/leisure-treka-eb/`, and I generalised from that one page to all
  13. The Ford Custom Campervan page **does** link two PDFs.
- The sitemap has six child sitemaps (post, page, pre-owned-vehicles, vehicle, category,
  users) and none lists a downloads or brochure page — true, but irrelevant, because these
  documents are in **no page and no sitemap at all**.
- Each vehicle page has a `Downloads` button and it is a dead `href="#downloads"` anchor with
  no such element on the page. A Downloads tab that downloads nothing reads as "no documents
  exist"; it actually means the documents were never wired up to the button.

What found them was the WordPress media library, which is the definitive test on a WP site and
should be the first thing tried on any future WP manufacturer:

```
GET /wp-json/wp/v2/media?mime_type=application/pdf&per_page=100     # X-WP-Total: 5
```

| Document | Uploaded | Linked from | Use |
|---|---|---|---|
| `January-2024-Retail-Price-List.pdf` | 2024-01-11 | nothing | **the source of every price FMLV holds** |
| `Moto-Trek-Retail-Price-Guide-October-2024.pdf` | 2025-07-21 | nothing | same prices, on-the-road basis |
| `handbook-LT-ELD.pdf` | 2024-01-11 | nothing | confirms the ELD, and decodes the asterisks |
| `Ford-Custom-Optional-Extra-List.pdf` | 2024-01-11 | Ford Custom page | out of scope |
| `Ford-Transit-Custom-Manual-Rev1-07-11-2022.pdf` | 2024-01-11 | Ford Custom page | out of scope |

All five fetch unauthenticated, 200, `application/pdf`. `robots.txt` blocks only `/wp-admin/`.

**They do not change the source decision.** Both price lists are **2024** — two model years
stale — and the website republishes the same figures for everything it prices. The rule holds:
the website wins, and the PDFs are worth exactly two things, a price *basis* and a
cross-check. Neither is a reason to parse them per run. But see "Price basis" below, because
one of them explains a figure the website no longer publishes.

So this remains an HTML-sourced manufacturer, and **attribution is free**: one URL per model,
one set of numbers on it. Plain `httpx` is enough — `needs_javascript=no`.

WordPress + Elementor, with Dynamic Content for Elementor driving the spec block.

## The roster: `/motorhomes/` is complete, and the sitemap is not

This is the reverse of Etrusco. The sitemap is the **wrong** source here:

| Source | Vehicles | Notes |
|---|---|---|
| `/motorhomes/` | 11 | the complete leisure roster |
| nav menu (on every page) | 13 | adds Tornado under *Motorsport*, Cyclone under *Trailers* |
| `wp-sitemap-posts-vehicle-1.xml` | 13 | same 13, no grouping to tell them apart |

The 11: The Terrain, Leisure-Treka RL / EB / ELD, X-Cite EB Elite, X-Cite G Elite,
Euro-Treka IB, Pioneer, Ford Custom Campervan, Xplora FDB, Xplora ELD.

**Cyclone 180S is a trailer** — "Galvanised Steel Chassis", "Lockable Coupling", "Six Fully
Braked Wheels", "Independent Suspension", £41,999. It has berths, a garage and a living area,
and it is not a motor vehicle.

**Tornado Transporter is the dangerous one.** It is filed under *Motorsport*, but:

- its spec block is **byte-identical to Leisure-Treka EB and The Terrain** (6.36m / 2.05m /
  2.76m, 2500kg / 3500kg) except that berths reads 3 rather than 2, so it parses perfectly
  and looks completely plausible;
- and **FMLV already holds it as a current product** — `product_id` 5486, range `Tornado`,
  model `Tornado`, year 2026, `campervan_high_top`, £64,995, not archived.

So it cannot simply be dropped as "not a leisure vehicle": dropping it reports a
disappearance on a product the NCC deliberately holds. See "The Tornado decision" below.

The nav menu is the only source that separates the three groups, and it is present on every
page, so the adapter should take the roster **and** the grouping from the nav — not from the
sitemap, and not from `/motorhomes/` alone (which flattens the grouping away).

## The spec block: two sibling containers, and nothing pairs a label to its value

This is the whole risk of the adapter. The "Vehicle Specification" accordion panel contains
exactly two child containers, confirmed by walking the div nesting on
`/vehicle/leisure-treka-eld/`:

```
container 288a948                     <- the accordion panel
  container b284b60                   <- LABELS: 12 text-editor widgets
    widget 00bde5f  "Berths"
    widget ffe2f9f  "Engine Size"
    ...
  container 9b3642f                   <- VALUES: 10 text-editor widgets
    widget a84d19c  "4"
    widget fda4890  "2.0L 140BHP"
    ...
```

There is **no row element and no per-row pairing.** Label *n* means value *n*, and that is the
only thing joining them. Worse, the two columns are different lengths on every single page,
because DCE drops an empty widget rather than rendering it blank:

| Vehicle | Labels | Values | Surplus |
|---|---|---|---|
| Leisure-Treka EB / RL, The Terrain, Tornado | 15 | 13 | the two below |
| Leisure-Treka ELD | 12 | 10 | the two below |
| Xplora FDB | 15 | 13 | the two below |
| Xplora ELD | 12 | 10 | the two below |
| X-Cite EB / G, Euro-Treka IB | 9 | 7 | the two below |
| **Pioneer** | **5** | **5** | **none** |
| Ford Custom Campervan | — | no spec block at all | — |

**The label set itself varies per model**, which is the good news: DCE hides the label and its
value together, so the surviving pairs stay in step. The ELD is the only model publishing
`M.I.R.O` / `M.T.P.L.M` / `Maximum User Payload` / `Waste Water Capacity`; every other model
publishes `Unladen Weight` / `Gross Weight`. Pioneer publishes no widths or heights at all.

**Only two labels are ever empty — but the surplus is a subset of them, not always both.**
`Overall Width (Mirrors Folded)*` and `Overall Height (Inc. Aerial)*` are present on **twelve**
of the thirteen pages and empty on all twelve. The **Pioneer carries neither**, because it
publishes no width or height at all and DCE drops these two along with `Overall Width*` and
`Overall Height*`.

That distinction cost a bug: the adapter first required the surplus to *equal* both labels and
silently dropped the Pioneer — the check's own failure mode, pointed the wrong way. The subset
test is what it should always have been, and it still asserts the thing that matters: **no
data-bearing label runs past the end of the value column.** Two things follow:

- Moto-Trek publishes exactly one figure per measurement, and **the asterisked one is already
  the base-vehicle figure.** The ELD handbook decodes the asterisk, which the site never
  explains: "6.36m in length / 2.26m wide **with the mirrors folded** / 2.64m tall **with the
  TV aerial stowed**". So `Overall Width*` is the folded-mirror width and `Overall Height*` is
  the aerial-stowed height — the narrowest and lowest published figures, which is what FMLV
  wants. The two empty labels would hold the *wider* and *taller* alternatives. Nothing to do.
- **The surplus is the alignment check.** Any labels beyond the value count must be exactly
  that trailing pair. If they are not, the columns have shifted for a reason not yet
  understood, and the product must be dropped rather than guessed at.

### The ELD proves the pairing, and exposes a real error on their site

Positional pairing on `/vehicle/leisure-treka-eld/` gives:

```
Berths                = 4
Engine Size           = 2.0L 140BHP
Overall Length        = 6.36m / 20’9″
Overall Width*        = 2.26m / 7’4″
Overall Height*       = 2.64m / 8’6″
Garage Length         = 3160kg          <- a weight against a length label
M.I.R.O               = 3160kg
M.T.P.L.M             = 3500kg
Maximum User Payload  = 340kg
Waste Water Capacity  = 70L
```

`Garage Length = 3160kg` is obviously wrong, and the tempting reading is that Garage Length's
value is missing and everything below it has shifted up by one. **The arithmetic says
otherwise:** 3500 − 3160 = 340 holds exactly as printed, and any one-place shift breaks it
(it would make payload 3500 against an MTPLM of 3160). Cross-checked against the widget ids,
which are template-stable per field: `6aa2ced` carries Garage Length's value, and on the
Leisure-Treka EB page the same `6aa2ced` holds `2.59m`.

So positional pairing is correct, and Moto-Trek have typed the M.I.R.O into the Garage Length
field on their own site. **A per-label type check catches it** — a `Length` label whose value
is `kg` is not a length. Drop the field, narrate it, keep the product.

This is the payload self-check earning its keep before a line of adapter code exists, and it
is the negative test the adapter must carry.

## The self-checks

Five, in descending order of strength. Moto-Trek publishes less redundancy than the PDF
manufacturers, so no single one of these is sufficient.

1. **Per-label type agreement.** `Berths` ⇒ integer; `Engine Size` ⇒ contains `BHP`;
   any `Length`/`Width`/`Height` ⇒ metres; any `Weight`/`M.I.R.O`/`M.T.P.L.M`/`Payload` ⇒ `kg`;
   `Waste Water Capacity` ⇒ litres. A mismatch drops **that field** with a warning. This is
   the check that catches the ELD, and it catches any single-place shift that crosses a type
   boundary.
2. **The trailing-surplus check** described above. A surplus that is not exactly
   `Overall Width (Mirrors Folded)*` + `Overall Height (Inc. Aerial)*` drops the **product**.
3. **`M.I.R.O` < `M.T.P.L.M`.** True on all 11. A violation drops the product.
4. **`payload == MTPLM − MRO`** where all three are published. Only the ELD publishes all
   three, so this fires once — but it is the check that resolved the ELD, so it stays.
5. **Metric against imperial.** Where both are published the pair is a free redundancy:
   `6.36m / 20’10”` computes to 20′10.4″. Only the five Boxer van conversions publish
   imperial, and it is sloppily rounded — the ELD's `6.36m / 20’9″` is 1.4″ out and its
   `2.64m / 8’6″` is 1.9″ out. Usable at **±3 inches, as a warning only.** Do not drop on it.

### And a real cross-document check: the index cards carry three in-scope fields

The first pass of this survey said the index cards carried only a price. They carry **berths
and gross weight too** — a filter for short lines had hidden them, because the card renders
each as its own element:

```
Terrain | from £74995.00 | The Terrain encompasses rugged looks… | 2 | 3500kg
Pioneer | from £199995.00 | The Pioneer is the ultimate luxury motorhome…  | 4/6 | 7500kg
```

Eleven cards on `/motorhomes/`, one per leisure vehicle, and **berths, MTPLM and price agree
with the vehicle page on all eleven** — including Pioneer's `4/6` and its 7500kg. That is a
genuine Rimor-style cross-document redundancy on 3 of the 13 in-scope fields, for one extra
fetch that the adapter needs anyway to get the roster. Compare it, and narrate a disagreement
rather than picking a side.

## Parsing traps

- **`POA` is not a price.** Euro-Treka IB, X-Cite EB, X-Cite G, Tornado and the Ford Custom
  publish `POA`; the other six publish `from £72495.00`. A pattern that reaches for digits
  must not read `POA` as zero, and must not read FMLV's held price as confirmation.
- **A typo in the separator.** Living Area Width reads `2.17m ‘ 7’1″` on four pages — a left
  single quote where every other cell has `/`. Split on the *metric* half and treat the
  remainder as the imperial cross-check, rather than splitting on `/`.
- **Curly quotes throughout.** `’` and `″`, not `'` and `"`.
- **Metres, to at most 2 decimal places, and sometimes fewer.** `8.7m`, `3.2m`, `2m`, `0.7m`.
  So dimensions are good to 10mm at best; FMLV's held values (6360, 2050, 2760) are consistent
  with that.
- **Berths can be a range.** Pioneer publishes `4/6`. Take **4**, per the lower-figure rule —
  which is what FMLV already holds.
- **Trim is in the site's name and not in FMLV's.** The site sells "X-Cite EB Elite"; FMLV
  holds range `X-Cite`, model `EB`. Leisure-Treka pages say "Available in ‘Classic’ & ‘Elite’
  Specifications" and mark Elite equipment with `*`; the headline price is the Classic. So the
  base vehicle is the Classic, and `Elite` is not part of the model name.

## Range and model strings: take them from the export, and they are already right

The export settles this and the FMLV *page titles* mislead. Product URLs and titles render as
`MOTO-TREK Leisure-Treka EB Peugeot`, which reads as though the base vehicle is part of the
model. It is not — the export holds `base_vehicle_manufacturer` separately:

| `manufacturer_range` | `model` |
|---|---|
| `Leisure-Treka` | `EB`, `ELD`, `RL` |
| `X-Cite` | `EB`, `G` |
| `Xplora` | `ELD`, `FDB` |
| `Pioneer` | `IB` |
| `Tornado` | `Tornado` |
| `The Terrain` | `The Terrain` |
| `Euro-Treka` | `QB`, `G`, `G SPORT` — all archived |

Emitting range = family and model = bare layout code gives a **1.000** match on all 10 current
products, so no rename is proposed and no identity is at risk. Two notes:

- **`Pioneer IB` is not derivable from the site.** The page is titled just "Pioneer" and names
  no layout. The `IB` must come from the baseline, which is a second reason to read the export
  first rather than build the identity from the page.
- **`The Terrain` and `Tornado` repeat the range in the model.** Odd, but it is what FMLV
  holds, and the slug `moto-trek-the-terrain-the-terrain-peugeot` confirms it is deliberate
  rather than an export artefact. Emit the repeat.

Two ranges are close enough to matter for the matcher: `Euro-Treka IB` against the archived
`Euro-Treka QB` scores `{euro,treka,ib}` vs `{euro,treka,qb}` = **0.500**, exactly at
`DEFAULT_THRESHOLD`. It does not bite, because the QB is archived and out of the baseline — but
if the QB is ever unarchived, the IB will match it and be reported as a revision of it.

## Model year: Moto-Trek publishes none

Nowhere on the site. The only years present anywhere are an award (`2023 Award Winning Design
as voted by the Caravan and Motorhome Club`), a `2024` award on the RL, and the Xplora's `2022`
launch. No "2026 season", no "MY2027", no dated price list — because there is no price list.

FMLV holds `year` 2026 on all 10 current products. So the site is taken as current and the
year carried through untouched. Nothing here to re-check in late September, which is unusual
enough to be worth writing down: the model-year changeover simply does not surface on this
manufacturer's website.

## Body type is out of scope, and the height threshold does not apply to most of these

`config/field_guide_motorhome.csv` marks 13 fields `in_scope`, and the `type_*` columns are not
among them, so `body_type` is neither compared nor proposed.

**The 2300mm threshold only applies once a vehicle is already a campervan.** Rule restated from
the NCC side, 27 August 2026: it separates `campervan_high_top` from `campervan`, and it never
promotes a coachbuilt. So the X-Cite at 2870mm is **simply a low-profile motorhome** — its
height says nothing about its body type, and FMLV's `coach_built_low_profile` is right. Same for
the Xplora at 2890mm and the Pioneer. Every existing adapter already gates it this way
(`chausson.py`, `etrusco.py`, `elddis.py`), so there is nothing to change in the shared code —
but it is the first question to ask, not the second, and comparing *widths* across a campervan
and a coachbuilt (as an earlier draft of this file did) is not the test either.

Applying it in the right order to Moto-Trek:

| Product | Body, from shape | Then height | FMLV holds |
|---|---|---|---|
| Leisure-Treka RL / EB, The Terrain, Tornado | van conversion, 2.05m wide | 2760 > 2300 ⇒ high top | `campervan_high_top` ✓ |
| **Leisure-Treka ELD** | **coachbuilt, 2.26m wide** | n/a — threshold does not apply | `campervan_high_top` ✗ |
| X-Cite EB / G | coachbuilt, slide-out side | n/a | `coach_built_low_profile` ✓ |
| Xplora FDB / ELD | coachbuilt | n/a | `coach_built_low_profile` ✓ |
| Pioneer IB | coachbuilt, over-cab bed | n/a | `coach_built_over_cab_bed` ✓ |

So the only wrong one is the **Leisure-Treka ELD**, and it is wrong on the shape question rather
than the height one. Three things put it on the coachbuilt side of its own siblings:

- **2.26m wide against their 2.05m.** A Peugeot Boxer body is 2050mm, so the RL and EB are the
  van and the ELD is not.
- **2.64m tall against their 2.76m** — *lower* despite being wider, which is the characteristic
  low-profile-coachbuilt profile against a high-top van conversion's.
- **MRO 3160kg against their 2500kg**, confirmed by the ELD's own handbook. A 660kg difference
  is a different vehicle, not a different way of measuring one.

The site's `/campervans/` page lists all three Leisure-Trekas, which is presumably what the
current classification rests on — but that page also lists the Ford Custom, so it is a
navigation grouping, not a declaration.

Out of scope, so **not for this adapter to change**. Flagged for a human.

### The width and height labels mean different things on the van and the coachbuilt

Worth writing down, because it looks like an inconsistency and is not. The ELD handbook says
"2.26m wide **with the mirrors folded**", while the RL and EB publish 2.05m under the same
`Overall Width*` label — which is a body width, mirrors excluded.

Both are the base-vehicle figure, because of the geometry: on a 2.26m coachbuilt the folded
mirrors sit *inside* the body width, so the two measurements coincide. On a 2.05m van they do
not, which is exactly why the van pages put the narrower body figure under `Overall Width*` and
leave `Overall Width (Mirrors Folded)` empty rather than the other way round.

The consequence for the adapter is nil — take `Overall Width*` as published in both cases — but
it is the reading that nearly overturned the EB/RL correction below, and the weights are what
settle it.

## The Ford Custom Campervan is a different supplier, and the site holds nothing for it

`Three-Peaks Campers` is its own entry in the NCC export dropdown, alongside `Moto-Trek`.
Its single product:

```
product_id 5488 | manufacturer MOTO-TREK LIMITED | display_name Three Peaks
range Ford Camper | model Ford Camper | base vehicle Ford | berths 4 | seats 4
£63,995 | MRO 2560 | MTPLM 3200 | 4972 x 2032 x 2100 | campervan_elevating_roof
```

So `manufacturer` is the *same string* as Moto-Trek's — `MOTO-TREK LIMITED` — while
`manufacturer_display_name`, `ncc_supplier_name` and `manufacturer_id` (210 against 76) all
differ. Since `fmlv_manufacturer` is both the registry key and the `ADAPTERS` key, a second
row would collide with this one and dispatch to the same adapter.

**It is out of scope, and there is nothing to collect anyway.** The vehicle page has *no spec
block* — labels and values alike. Its specification is a prose bullet list, and not one of
FMLV's numbers appears on it: no length, no width, no height, no MRO, no MTPLM, and `POA`
where the price would be. The only in-scope facts recoverable are berths (from body copy,
"comfortable sleeping for 4") and seats (from "Two Rear Seat Belts" plus twin captains), and
FMLV already holds both correctly at 4 and 4.

FMLV's `campervan_elevating_roof` is right, incidentally, and for the documented reason: the
standard conversion list includes "Pop up Roof (Low Profile)" — *included*, not a cost option —
and a low-profile pop-top on a SWB Transit Custom is not a high top.

Note the page copy is branded: "The **Three Peaks** Ford Custom campervan", "the Three Peaks
camper". The vehicle's *name* on the site is just "Ford Custom Campervan".

## Payload has to be derived, and FMLV already derives it

The site publishes payload on the ELD only. FMLV holds it on all 10, and it is arithmetic:
Tornado and The Terrain hold 1000 = 3500 − 2500, the ELD holds 340 = 3500 − 3160.

If the adapter emits MRO and MTPLM but no payload, the old payload stays — and for the
Leisure-Treka EB and RL that leaves 340kg sitting beside a 1000kg gap. An inherited figure
that is now arithmetically impossible is worse than either updating or blanking it.

**So derive `payload = MTPLM − MRO`**, say so in the provenance snippet, and where the
manufacturer publishes the figure use theirs and check it against the subtraction. This
matches what FMLV already does and invents nothing.

Two fields have no source in the current site and must stay unproposed:

- **Seats.** There is no seats or seatbelts row anywhere on the site, and the ELD handbook
  declines to give a number too: "All available travelling seats are fitted with 3 point
  seatbelts. Depending on the specification of your motorhome this may include additional
  travelling seats in the rear." Travel seats appear only as an option ("Additional Travel
  Seat – Leisure-Treka only"). Genuinely unpublished — FMLV's values cannot be checked at all.
- **Price where the site says `POA`** — X-Cite EB and G, Euro-Treka IB, Tornado.

## Price basis: known at last, and it is *not* on-the-road

The two hidden price lists settle a question the website cannot, and correct a claim the first
pass of this survey got wrong. FMLV's X-Cite price is **not** unsourced:

| | January 2024 list | October 2024 guide |
|---|---|---|
| Basis | net + VAT, labelled "2024 Retail Price" | **on-the-road**: net + VAT + £55 registration + £345 RFL |
| Leisure-Treka EB Classic | £72,495 | £72,895 |
| X-Cite EB Elite | **£97,995** | £98,395 |
| Pioneer IB | £199,995 | £200,215 |

The **net** prices are byte-identical between the two documents (X-Cite £81,662.50 in both).
Nothing changed between January and October 2024 except the presentation: the October guide
adds a flat **£400** of registration fee and road fund licence and calls it `GRAND TOTAL`.

And the January column is exactly what the website publishes and exactly what FMLV holds — on
all seven priced products, and on the X-Cite's £97,995 that the website has since replaced
with `POA`. So:

- **FMLV's basis is net + VAT, and so is the website's.** Recorded here and in the registry
  `notes`, per the rule, because it is now actually known rather than merely absent.
- **Take the website's headline figure, and note this is the rule rather than an exception to
  it.** The standing preference for an on-the-road price is really a preference for *the
  headline price a buyer sees* — which for Auto-Trail happens to be the on-the-road column.
  Here it is not: Moto-Trek's headline is the ex-works-plus-VAT figure, so that is what FMLV
  records. Rule stated by the requester, 27 August 2026: **the two prices have to be
  consistent, because someone who sees a vehicle on FMLV then goes and looks at
  moto-trek.co.uk.** A mismatch does not read as a difference in basis; it reads as FMLV being
  wrong.
- Adopting the October guide's `GRAND TOTAL` would have proposed **+£400 on every priced
  product** — seven changes that are not price changes — *and* left FMLV disagreeing with the
  manufacturer's own page on all seven. Both reasons point the same way.
- **The X-Cite mystery is solved and needs no action.** FMLV's £97,995 came from this site's
  own January 2024 list. The site no longer publishes it, so the adapter proposes nothing and
  the correct figure stays put by inaction.

### Euro-Treka IB is the archived G SPORT under a new name

Both price lists call it **`IB (G-Sport)`** — one vehicle, two names. FMLV holds an archived
`Euro-Treka` / `G SPORT` (2024, £139,995) and an archived `QB`. So the "new" Euro-Treka IB is
not a new vehicle so much as a renamed one.

Nothing breaks: `{euro,treka,ib}` against `{euro,treka,g,sport}` scores **0.400**, below
`DEFAULT_THRESHOLD`, and the G SPORT row is archived and therefore out of the baseline anyway.
It will be proposed as new, which is the right outcome. Worth knowing so that "new product" is
not read as "vehicle Moto-Trek has just launched".

Its price is `POA` on the site and £152,995 / £153,215 in the 2024 lists. **The adapter leaves
it blank** — confirmed by the requester, 27 August 2026 — because a two-year-old figure on a
product being created fresh is worse than a gap a reviewer can fill, and unlike the X-Cite
there is no held value to preserve by inaction.

**But it will not stay blank, and that is the reviewer's job rather than the adapter's.**
Francis expects to enter roughly **£150,000** by hand when he uploads it, because *FMLV needs
some price indication to classify a vehicle when people sort and filter* — a blank price does
not merely read poorly, it drops the product out of sorted results. His figure lands within
2% of Moto-Trek's own withdrawn numbers, which is the useful part: a well-judged round guide
price is close enough, and it is offered as a guide price rather than asserted as collected.

So do **not** be helpful here and fill the POA from the 2024 list to save the keystroke. That
would present a superseded figure as though the run had found it. Narrate the gap instead —
which is the same division of labour the `POA` X-Cite and Tornado rely on.

## What a first run would propose

Against the 10 current, non-archived baseline rows. This is the number to compare the real run
against, and the reason to hand-check the Leisure-Trekas first.

| Product | Proposed changes |
|---|---|
| **Leisure-Treka EB** | width 2260→**2050**, height 2640→**2760**, MRO 3160→**2500**, payload 340→**1000** |
| **Leisure-Treka RL** | the same four |
| Leisure-Treka ELD | none — exact match on all 8 published fields |
| **X-Cite EB** | MRO 3000→**3050**, payload 481→**450** |
| **X-Cite G** | MRO 3000→**3050**, payload 481→**450**, height 2870→**2890** |
| Xplora FDB | none |
| Xplora ELD | none |
| **Pioneer IB** | length 8700→**8350**, MRO 4500→**5000**, MTPLM 7000→**7500** |
| **Tornado** | berths 2→**3** |
| The Terrain | none |
| **Euro-Treka IB** | **new product** — 6 berths, 8700 × 2250 × 3200, MRO 4300, MTPLM 5000, no price |

### Pioneer's gross weight has four different values

The one proposal resting on a single source, so worth stating plainly:

| Source | MTPLM |
|---|---|
| Vehicle page spec table (current) | **7500kg** |
| `/motorhomes/` and `/slideouts/` cards (current) | **7500kg** |
| October 2024 price guide | 7200kg |
| January 2024 price list | 7000kg |
| FMLV holds | 7000kg |

The site says 7500 in two independent places and is current, so it wins — but note the
trajectory 7000 → 7200 → 7500 looks like a chassis genuinely being uprated across model years
rather than a typo, which supports taking the newest. Its engine disagrees the same way: the
site says `2.3L 156BHP`, both price lists say `180BHP`. Engine is not an in-scope field.

### FMLV has given the EB and RL the ELD's figures

The four changes on each of the Leisure-Treka EB and RL are one error, not eight. FMLV holds
all three Leisure-Trekas at 3160 / 3500 / 340 and 6360 × 2260 × 2640 — which is the **ELD's**
specification, byte for byte. The site distinguishes them plainly: the RL and EB are 2.05m
wide and 2.76m high, the ELD is 2.26m wide and 2.64m high. Those are two different bodies.

This is the Elddis pattern in reverse — there, one range's figures had been copied onto its
siblings on the *website*; here it has happened in *FMLV*. Three things say the site is right:

- **The 660kg gap in MRO settles it.** 3160kg against 2500kg cannot be a measurement
  convention, so the ELD is genuinely a different, heavier vehicle from the RL and EB — which
  is what rules out the alternative reading that FMLV has deliberately normalised the range
  onto one set of mirrors-folded figures. See the label note in the body-type section: the
  width and height *could* be read either way, and only the weights break the tie.
- The site's figures are internally consistent — 3500 − 2500 = 1000 — as are the ELD's.
- The Tornado and The Terrain, which are the same 2.05m Boxer shell, are held by FMLV at
  exactly the site's 2500 / 3500 / 1000 and 6360 × 2050 × 2760. So FMLV holds the correct
  figures for that body already, on two other products.

So proposing these is the adapter working. Hand-check them first anyway.

### The ELD is confirmed three times over

Its handbook independently restates the whole specification, and it matches the spec table and
FMLV exactly:

```
Your motorhome is: 6.36m in length / 2.26m wide with the mirrors folded
                   2.64m tall with the TV aerial stowed
Maximum technically permissible laden mass and registration mass – 3500Kg
Mass of vehicle in running order – 3160Kg
Mass of user payload – 340kg
```

So the ELD's figures are the best-evidenced on the manufacturer — three sources agreeing — and
they are the same figures FMLV has wrongly copied onto the EB and RL.

### X-Cite payload 481 does not reconcile in FMLV either

FMLV holds MRO 3000, MTPLM 3500, payload **481**. 3500 − 3000 = 500. The site gives MRO 3050,
which makes the gap 450. Whichever is right, the held row does not add up — worth mentioning
because it is the kind of thing the adapter's own self-check would have refused to emit.

### The Tornado decision

Not the adapter's to make silently. The case for **including** it: FMLV holds it as a current
2026 product, its page carries a full spec block, and excluding it reports a disappearance on
a vehicle the NCC chose to list. The case against: Moto-Trek file it under *Motorsport*, it is
named "Transporter", and its published specification is a copy of Leisure-Treka EB's — which
means the one figure that differs, berths 3 against FMLV's 2, may be the placeholder rather
than the correction.

Recommendation: **collect it, and narrate that its figures are indistinguishable from
Leisure-Treka EB's.** A reviewer can reject the berths change in one click; a silent
disappearance is harder to notice. Cyclone 180S stays excluded — it is a trailer.

## First run — 27 August 2026, run #38

Eleven products collected against a ten-product baseline, and the classification came out
exactly as the survey predicted: **6 changed, 4 unchanged, 1 new, 0 disappeared.** 13 fetches
(one index, then one per collected vehicle), 14.5s.

The real proposals, hand-checked against the site on three products:

| Product | Proposed | Checked |
|---|---|---|
| Leisure-Treka EB, RL | width 2260→2050, height 2640→2760, MRO 3160→2500, payload 340→1000 | ✅ site says 2.05m / 2.76m / 2500kg |
| X-Cite EB | MRO 3000→3050, payload 481→450 | ✅ |
| X-Cite G | + height 2870→2890 | ✅ site says 2.89m, EB says 2.87m |
| Pioneer IB | length 8700→8350, MRO 4500→5000, MTPLM 7000→7500 | ✅ site says 8.35m / 5000 / 7500 |
| Tornado | berths 2→3 | as expected — and see the Tornado decision |
| Euro-Treka IB | new: 6 berths, 8700×2250×3200, 4300/5000/700, Peugeot, no price, no seats | ✅ |
| ELD, Xplora FDB / ELD, The Terrain | nothing | ✅ exact match |

Narration behaved: the Ford Custom and the Cyclone were each skipped with their reason, the
ELD's `Garage Length = 3160kg` was reported and that one field blanked while the rest of the
product was kept, all four `POA` prices were reported as proposing nothing, and the Tornado was
flagged as having no index card to cross-check against (it is not on `/motorhomes/`).

A `--range "Xplora"` run (#39) scoped to 2 products against 2 baseline rows, 0 changed, 0
disappeared — so the default `cli.baseline_scope` match on `manufacturer_range` is right and no
`baseline_in_scope` hook is needed.

### The bug the Pioneer caught, and the two probes that lied

Worth recording because both were caught by *running the adapter's own functions* over the
saved pages rather than by a convenience reimplementation:

- The surplus check required equality with `_ALWAYS_EMPTY_LABELS` and **silently dropped the
  Pioneer**, the one page carrying neither. A checker whose failure mode is discarding a good
  product is worse than no checker, and it presented as "10 products collected", a plausible
  number. Now a subset test, with the Pioneer as a fixture.
- A `.{70}…` regex over the ELD handbook's text returned nothing for seats, weights *and*
  payload, because `.` does not cross newlines without `DOTALL` — it read exactly like a
  handbook that discusses none of them. A keyword tally showed 48 hits for `seat`.
- A div-nesting walker reported one label per column with every value dumped into a surplus
  list. Building from its output would have collected one field per product.

### The review burden, which is real and is not this adapter's doing

Of the 48 proposed changes, **15 are in-scope fields the run did not find** and which the
pipeline therefore surfaces for a human to confirm — most of them `mh_passenger_seats_inc_driver`
on all 11 products, plus the four `POA` prices and the Pioneer's unpublished width and height.
Six more are `year` bumps, 2026→2027, which ride along on the products that had another change.

That leaves **21 genuine field changes**. The seats prompts will recur on every single run,
forever, because Moto-Trek publish no seat count anywhere — which is exactly the friction
`docs/adapters/README.md` describes as the reason `price_min_range_pounds` was moved out of
scope and mirrored at output instead. Worth a decision if it grates: either seats come out of
`config/field_guide_motorhome.csv`'s in-scope set for everyone, or the "attempted and not
found" work lands and distinguishes it from "never attempted".

## What is unverified

- **Base vehicle for Euro-Treka IB and Pioneer.** FMLV has Pioneer on `IVECO`; the site's
  Pioneer page shows `2.3L 156BHP` and no cab text. Euro-Treka IB's cab line says "Peugeot
  Boxer 2.0Litre ... AL-KO Chassis" at a 5000kg MTPLM. `base_vehicle_manufacturer` is out of
  scope so nothing turns on it, but the Euro-Treka pairing is odd.
- **Whether the always-empty mirrors/aerial labels ever populate.** Empty on all 13 pages on
  27 August 2026. If Moto-Trek ever fills them, the trailing-surplus check will start dropping
  products rather than silently misaligning them — which is the intended failure direction, but
  it will need the check relaxing.
- **Whether `/motorhomes/` stays the complete roster.** It excludes Tornado and Cyclone today
  purely because they are filed under Motorsport and Trailers. A third such vehicle would
  appear in the nav and the sitemap, and the adapter should narrate anything in the nav it
  chose not to collect.
- **Seats.** Genuinely unpublished, so FMLV's values cannot be checked from this site at all —
  confirmed against the vehicle pages, the index cards and the ELD handbook.
- **Whether the hidden PDFs are ever refreshed.** Both price lists are 2024 and the newer one
  was re-uploaded in July 2025. If a 2026 or 2027 list ever appears in the media library it
  becomes the better price source, including for the four models the site now marks `POA`. The
  media-library query is one cheap fetch, so it is worth re-running at each model-year check
  even though the adapter does not depend on it.

## Two probe bugs worth recording

Both were mine, both produced confident wrong answers, and `README.md` warns about exactly
this ("Does your verification probe fail where the adapter fails?"):

1. **A `.{70}…` regex over PDF text found nothing** in the ELD handbook — for seats, weights
   and payload alike — because `.` does not cross newlines without `DOTALL`, and the extracted
   text is line-broken. A keyword tally showed 48 hits for `seat` and 26 for `kg`. The
   *absence* of matches read exactly like "the handbook says nothing about weights". Collapse
   whitespace before matching PDF text.
2. **A div-nesting walker mis-scoped the spec block** and reported one label per column with
   every value dumped into a "surplus" list. Had the adapter been written from that output it
   would have collected one field per product. The nesting trace was the direct evidence; the
   convenience wrapper over it was the thing that lied.
