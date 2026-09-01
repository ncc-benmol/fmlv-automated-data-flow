# Knaus — site survey and adapter notes

German, Jandelsbrunn. Part of Knaus Tabbert AG. Survey date **1 September 2026**, four days
after the brand's Caravan Salon announcement, which is the whole reason this survey looks
the way it does.

## Scope: the KNAUS brand only

Knaus Tabbert AG owns six brands — KNAUS, TABBERT, WEINSBERG, T@B, MORELO and the rental
brand RENT AND TRAVEL. **This adapter covers KNAUS-branded vehicles only.** Confirmed by
the requester, 1 September 2026: *"Knaus own a number of brands, and for this set up we are
only reviewing Knaus branded models, not Weinsberg or T@B."*

FMLV agrees, and so does the NCC export dropdown — `Knaus`, `Weinsberg` and `Morelo` are
three separate entries. `resources/manufacturers-full-list.csv` has separate rows for
Weinsberg (ids 112 and 252) and T@B (141). None of them are this row's business, and
`knaus.com` conveniently carries nothing else.

One consequence worth stating: the August 2026 press release covers all five brands, so
most of it is out of scope. Only the KNAUS section applies, and of that only the motorhomes
and campervans — the NORDWIND and SPORT announcements are caravans, which the whole
prototype excludes (`config/manufacturers.README.md`).

## What the requester brought to the survey

- The site is <https://www.knaus.com/en-gb>.
- **"Van" is a motorhome range, not a campervan range.** The campervans are BoxTime and
  BoxLife Platinum. This is the single easiest mistake to make here and the requester
  flagged it unprompted — VAN TI, VAN TI PLUS and VAN TI VW VANSATION are all coachbuilts,
  and all three live under `/en-gb/motorhomes/`.
- **The specifications are in the section called "Layouts".** Correct, and it is the
  per-layout pages reached from there rather than the index itself.
- FMLV already carries Knaus as 2027, but it was done a while ago and needs re-checking
  against the 28 August 2026 announcement. It did. See "What changed since FMLV was last
  updated" below — seven baseline rows no longer exist.
- The NCC supplier name went round three times (`Knaus` → `Knaus Tabbert AG` →
  `Knaus Tabbert AG Knaus`). It is **`Knaus`**, read straight out of the site's own
  dropdown rather than settled by discussion; see below.

All of it held up.

### The supplier name, settled from the dropdown

`fmlv fetch-export` failed with Playwright's `did not find some options`, which is what a
wrong `ncc_supplier_name` looks like. Rather than guess a fourth time, the 113 dropdown
labels were read directly off `/nova/resources/products`. Exactly one matches: `Knaus`.

Worth remembering as a technique — the failure mode is unmistakable, and the list is two
minutes' work to dump. It is also the cheapest possible confirmation that the brand-level
scoping is real, because `Weinsberg` and `Morelo` are sitting right there beside it as
their own entries.

## Where the data lives: per-layout pages, in plain static HTML

`https://www.knaus.com/en-gb/motorhomes/layouts` and
`https://www.knaus.com/en-gb/camper-vans/layouts` are the two index pages. Each renders one
card per layout, server-side, with no JavaScript needed — a plain `httpx` fetch has the lot.
Each card carries:

- the range name (`<h3>`) and the model plus model year (`<span class="c-tag">590 MF (2027)</span>`),
- the price (`<p>from 75.895 GBP* incl. Selection equipment</p>`),
- a **Technical data** link to the layout's own page,
- a **Compare layout** link carrying an opaque layout id (`?layout1=FR05393452799`).

The layout page then holds the entire technical specification as 25 `<dt>`/`<dd>` pairs,
split across **two** `<dl>` blocks — the split falls mid-table, between
`Technically maximum authorised laden mass` and `Maximum payload`, so a parser that takes
the first `<dl>` gets thirteen rows and silently loses berths. Real example, `/en-gb/motorhomes/sky-ti-vw/650-meg`:

```
Chassis                                              = VW
Engine power                                         = 120 kW / 163 PS
Gearbox                                              = autom.
Vehicle category                                     = ACTIVE PLUS
Total length (cm)                                    = 699 cm
Width (outside) (cm)                                 = 230 cm
Width (inside) (cm)                                  = 218 cm
Height (outside) (cm)                                = 287 cm
Height (inside) (cm)                                 = 199 cm
Mass in running order (…) (kg)                       = 3.107 kg (2.951 kg - 3.262 kg)
Mass in running order (…) (kg)                       = 3.107 kg (2.951 kg - 3.262 kg)
Effective vehicle mass (…) (kg)                      = 3.302 kg
Technically maximum authorised laden mass (kg)       = 3.500 kg
Maximum payload (kg)                                 = 8 kg
Remaining payload (kg)                               = 8 kg
Towing load (kg)                                     = 2.000 kg
Wheelbase (cm)                                       = 399 cm
Number of persons allowed in driving operation       = 2
Beds                                                 = 2
Max. number of beds                                  = 4
Automatic three-point belts                          = 2
Max. belt-secured seats                              = 4
```

**Attribution is free**: one URL per layout, one `<dd>` per field, nothing to align. That
is the whole reason this source beats the PDF, and it puts Knaus at the Auto-Trail end of
the risk spectrum rather than the Rimor end — the parsing risk here is entirely "which
*label* is this?", never "which column is this?".

Thirty-nine fetches a run: two index pages, 28 layout pages and nine price lists.

### Units and number format

Everything is centimetres, and FMLV wants millimetres — multiply by ten. The masses use
**German thousands separators**: `3.500 kg` is 3500, not 3.5. So does the price:
`75.895 GBP` is £75,895. Strip `.` before parsing, and never treat it as a decimal point.

## The 2027 catalogue PDFs are the near-miss, not the source

`https://www.knaus.com/en-gb/catalogs-downloads` publishes two English MY2027 catalogues:

| Document | Pages | Size |
|---|---|---|
| `KNAUS_Katalog-RM_EN_260715_98269.pdf` (motorhomes) | 35 | 29 MB |
| `KNAUS_Katalog-CAVA_EN_260715_98288.pdf` (camper vans) | 19 | 27 MB |

They *do* carry "LAYOUTS & FACTS" spec pages, and those pages extract cleanly with
`extract_positioned_text` — proper x-separated columns, one per layout, no merged cells.
It would be an entirely parseable source. It is still the wrong one, for two independent
reasons.

**First, the fields are not there.** The catalogue's table is total length, widths,
heights, max. number of beds, bed sizes and refrigerator litres. There are **no weights, no
prices and no seat counts anywhere in either document.** MRO, MTPLM and payload — three of
FMLV's thirteen in-scope fields — simply do not appear, and berths appear only as the
*maximum*, which is the wrong end of the range rule.

**Second, both were printed before the range changed.** The filenames carry `260715` and
page 35 carries `07/26` — July 2026, six weeks before the 28 August announcement. So:

- **VAN TI PLUS is absent entirely** from the motorhome catalogue. It is the announcement's
  world premiere, and it is live on the site.
- **The catalogue says the SKY TI is a Fiat.** Page 32: *"All layouts are built on a Fiat
  chassis."* The site says `Chassis = VW`, the URL is `/motorhomes/sky-ti-vw`, and the press
  release says *"Built on the state-of-the-art VW Crafter chassis"*. The catalogue is a
  model generation behind on the single most load-bearing field a chassis change touches.
- **The catalogue still lists L!VE I 900 LEG**, which has since gone (below).

This is the README's rule doing exactly what it is for: the website overrules the PDF, and
here the reason holds visibly rather than by assumption — the PDF can be *shown* to be
wrong, on a field the manufacturer's own press release contradicts.

The catalogues remain useful as a **cross-check on dimensions and bed counts**, and as the
second source that explains the L!VE I 900 LEG disappearance. They are not the source.

## The per-range price lists: the second source, and how they are found

Every layout page links **its own range's UK price list** on
`konfigurator.knaustabbert.de`, behind an opaque token. That is the discovery route the
adapter uses, and it matters more than it looks:

| Document | Language | Covers |
|---|---|---|
| per-range list, linked from each layout page | EN / UK | that one range |
| two category-wide lists, on `/en-gb/catalogs-downloads` | EN / UK | all 7 motorhome ranges; both campervan ranges |
| `Preisliste Modelljahr 2027-1 VAN TI` | **DE** | linked only from `de-de` pages |

Reading the link off the **English layout page** structurally avoids both near-misses —
the German list and the combined lists — without any filename matching. All eleven are
dated `28.08.2026`, the day of the Caravan Salon announcement.

Two things come out of them that the website cannot give:

1. **`Three-point belts in driving direction`** — see the seats section.
2. **The base MTPLM** — see below.

And they republish length, width, height, MRO and price, which agree with the website on
**28 of 28 layouts**. That is a cross-document check in the Rimor sense.

### One fallback, for a range too new to have a price list

**VAN TI PLUS links none** — it is the 28 August world premiere and its own document is
not published yet. It *is* in the category-wide motorhome list, so `collect` falls back to
`/en-gb/catalogs-downloads` once per category when a layout is covered by no per-range
list. Without that, the newest vehicles would be precisely the ones missing a seat count.

This is why `PriceList.rows` is keyed on **`(range, model)` and not on `model`**: the
category-wide list covers seven ranges in one document and `650 MEG` exists in six of
them. Keying on the model alone would leave one range's figures standing for all six.

### The columns cannot be recovered from coordinates

`extract_positioned_text` reports `(0, 0)` for very nearly every run in these PDFs, so the
Rimor-style defence of reading x-positions is unavailable. Reading order does preserve the
columns — `Total length (cm) 699 759 777` — and the parse is made safe by pinning every
row to the page's **own stated roster** (`Technical Data 650 MEG 700 DEG 700 DX`): a row
that does not yield exactly that many values is rejected outright rather than sliced.

Only rows whose cells are bare integers are read. `Rim size` and `Bed size, rear` contain
spaces and would make the count meaningless, so they are not read at all.

### MTPLM: the website publishes the uprated figure on two layouts

The two sources agree on 26 of 28. On **L!VE WAVE PLATINUM SELECTION 700 MEG** and
**L!VE I 700 MEG** the website says 3650 kg and the price list says 3500 kg — and the
price list also carries, on those very ranges' options pages:

```
201781-01  Load increase from 3.500 kg*** to 3.650 kg***   329,-   o o o o o
```

`o` on every layout of both ranges. So 3650 is a £329 option and 3500 is the base vehicle;
the base-vehicle rule takes 3500, and the adapter prefers the price list's figure.

This is a deliberate, documented departure from "the website overrules the PDF", and it
meets that rule's own test: the website figure can be **shown** to be the optioned one
rather than merely suspected of being stale. FMLV's baseline holds 3650 on both, so the
run proposes `3650 -> 3500` twice, with the option line quoted in the provenance.

## The self-check: the ±5% production tolerance band

Every `Mass in running order` value is printed with its tolerance band:

```
3.107 kg (2.951 kg - 3.262 kg)
```

and the row's tooltip says why — `Incl. indication of production-related tolerances of ±5%`.
The band is redundant with the central figure, which makes it a free parse check of exactly
the kind Sunlight, Etrusco and Bürstner provide. **Verified 28/28**, every layout, to within
one kilogram of rounding.

That is the `_reconciles()` check. A product whose band does not bracket its own MRO at ±5%
has been misparsed and gets dropped with an `on_progress` warning.

It is worth being honest about what it does and does not buy here. With one URL per layout
there are no columns to swap, so the classic misalignment this defends against is nearly
impossible in the first place. What it *does* catch is the realistic failure: a thousands
separator mishandled, or a `<dd>` read from the wrong row after a template change. Both
would break the band arithmetic immediately.

A second, weaker check comes free: **MRO ≤ effective vehicle mass ≤ MTPLM**, which holds
28/28 and would catch a wholesale row-offset.

### What is *not* a self-check: "Maximum payload"

The page publishes `Maximum payload (kg)` and `Remaining payload (kg)`, and neither is
FMLV's payload, nor do they reconcile against anything. `SKY TI VW 650 MEG` prints
`Maximum payload = 8 kg`. Every candidate identity was tested across all 28 layouts and all
28 fail:

| Candidate | Holds |
|---|---|
| `maxpay == MTPLM − effective mass` | 0/28 |
| `maxpay == MTPLM − effective mass − 75 × persons` | 0/28 |
| `maxpay == MTPLM − MRO` | 0/28 |
| `maxpay == MTPLM − MRO − 75 × persons` | 0/28 |

The residual is close to but not a clean multiple of 75, which is the signature of an EU
1230/2012 homologation figure with a personal-effects allowance folded in. **Do not try to
derive it and do not record it.** See the payload section below for what FMLV actually
holds.

## The trap: `Mass in running order` is printed twice

**18 of the 28 layouts print the `Mass in running order` row twice, with two different
figures**, in the same `<dl>`, with byte-identical labels, byte-identical `data-hints`
tooltips, and nothing whatsoever to tell them apart:

```html
<dt …>Mass in running order (basic model without optional equipment but with basic equipment) (kg)
  <span class="c-hint js-hint …" data-hints="[&quot;Incl. indication of production-related tolerances of ±5%&quot;]" …>
</dt>
<dd class="text-right font-bold">2.690 kg (2.555 kg - 2.824 kg)</dd>
…
<dt …>Mass in running order (basic model without optional equipment but with basic equipment) (kg)
  <span class="c-hint js-hint …" data-hints="[&quot;Incl. indication of production-related tolerances of ±5%&quot;]" …>
</dt>
<dd class="text-right font-bold">2.700 kg (2.565 kg - 2.835 kg)</dd>
```

The German page (`/de-de/reisemobile/van-ti-vansation/550-mf`) shows the same duplication
with the same two figures, so it is genuine in Knaus's own data rather than a translation
artefact. The gap is small — 10 to 17 kg — but it flips sign by range: the L!VE TI and VAN
TI layouts have the second figure *higher* by 10, the BOXLIFE and the two 700-series L!VE
WAVEs have it *lower* by 12 to 17. That pattern is consistent with two chassis or drivetrain
variants, but the page names only one chassis, one engine and one gearbox, so this is
inference, not evidence.

**Decision: take the first figure, and carry both into the provenance snippet.** The
reasoning:

1. It sits immediately below the `Chassis` / `Engine power` / `Gearbox` rows in the same
   "Basic equipment" block, so document order pairs it with the base vehicle those rows
   describe — and the base vehicle is what FMLV records.
2. FMLV's own baseline holds `2690` for `Van TI 550 MF`, which is the first figure.
3. Both values sit inside each other's ±5% band, so the exposure is a rounding-scale error
   rather than a wrong vehicle.

Point 2 is weak evidence on its own — two other baseline rows (`L!VE WAVE 700 MEG` at 3033,
`700 DX` at 3053) match the *second* figure, and the rest match neither, being from an older
snapshot. **This is the one genuinely unresolved question in the survey.** The requester's
2027 price list, offered during the survey but not yet supplied, may settle it; so would
asking Knaus. Until then the reviewer sees both numbers in the provenance and can overrule.

## Payload: derived, because FMLV derives it

FMLV holds **`payload = MTPLM − MRO`** — verified across the 2027 baseline: **29 of 33 rows
hold exactly**, and the four that break it are all `Boxlife` rows carrying figures that
match nothing on the site either (`540 MQ` holds 419 where `3500 − 2708 = 792`). Those four
are pre-existing FMLV noise, not a rival convention.

So the adapter derives payload from the two masses it reads, and ignores the site's own
`Maximum payload` and `Remaining payload` entirely.

## Berths and seats: three ceilings and one fitment figure

The sources publish five person-related counts, and only one is right for each field.

| Row | Where | SKY TI VW 650 MEG | Meaning |
|---|---|---|---|
| `Beds` | both | 2 | berths as standard |
| `Max. number of beds` | both | 4 | berths with options |
| `Number of persons allowed in driving operation` | both | 4 | **type-approval ceiling** |
| `Automatic three-point belts` | both | 2 | the cab's inertia-reel belts |
| `Max. belt-secured seats` | both | 4 | fitment ceiling |
| `Three-point belts in driving direction` | **price list only** | 4 | **belted seats as standard** |

**Berths -> `Beds`.** The lower-figure rule, and here the document labels the two ends
explicitly rather than printing a range, so there is nothing to interpret.

**Seats -> `Three-point belts in driving direction`.** This took two passes and the second
reversed the first, which is worth recording.

The website publishes only the first five rows, so on the website alone the choice looked
like `Automatic three-point belts` (2 on all 28) against `Number of persons allowed in
driving operation`. The price list settles it twice over:

- **`Number of persons allowed in driving operation` is disqualified by Knaus's own
  words.** The price list's legal section defines it as *"the permissible number of
  occupants in running order, as determined by the manufacturer during the type-approval
  process"*, and uses it to compute a 75 kg-per-passenger mass. That is precisely the row
  [`burstner.md`](burstner.md) established is **not** `mh_passenger_seats_inc_driver`.
  Reading it would also have matched FMLV's baseline of 4 on 32 of 33 rows, which is
  exactly the kind of agreement that makes a wrong field look right.
- **`Three-point belts in driving direction` is the fitment figure**, and it is only in
  the price list. It reads 2 on 26 layouts and **4** on SKY TI VW 650 MEG and VAN TI PLUS
  650 MEG — the two whose standard L-shaped seating group carries two belted seats.

The options table corroborates those two 4s rather than leaving them asserted: article
552686-01, *"Two folding seats with 3-point seat belts, facing the direction of travel"*,
is `-` (not possible) on the 650 MEG, whose `L-shaped seating group` is `s`, and `o`
(optional, £2,534) on the 700 DEG and 700 DX. So 4 is standard on the 650 MEG and 2 is the
base vehicle everywhere the folding seats are an extra — the base-vehicle rule, applied
with the manufacturer's own s/o markings as evidence.

**Decision from the requester, 1 September 2026:** record the belted-seat figure. This
proposes `4 -> 2` on 26 products and leaves the two 4s confirmed. Note the shape of that
against [`burstner.md`](burstner.md)'s warning — 26 products disagreeing the same way is
the pattern that survey says to distrust — so the reason it is being accepted here is not
the count but the documented definition: Knaus tell us in writing which row is the
type-approval ceiling, and it is not this one.

## Price: GBP on the index card, and the basis is stated

Prices are sterling, on the layouts index card, **not on the layout page**. The footnote
gives the basis:

> **The price shown here is the RRP for the corresponding base model, including individual
> options.

So it is an RRP for the base model, published by the manufacturer, in the market's own
currency — no exchange-rate problem of the kind `morelo.py` carries. Range from £69,984
(BOXLIFE PLATINUM SELECTION 540 MQ) to £111,485 (SKY TI VW 700 DX).

Two things to carry through:

- **German thousands separator.** `from 75.895 GBP*` is £75,895.
- **The Selection and Vansation ranges append `incl. Selection equipment` /
  `incl. Vansation equipment`.** That is part of the price basis, not decoration — put the
  raw string in the provenance snippet so a reviewer sees which basis a figure is on.

Recording the basis is the point of the README's price rule: if Knaus ever drops the
"incl. Selection equipment" packaging, every one of those 22 layouts shows a price change
that is not a price change, and this note is what makes it diagnosable in seconds.

## Body type: derivable, and the baseline agrees 33/33

The site declares the family in the URL path, and the catalogue declares the motorhome
subdivision in its section headings — *"Welcome to our fully-integrated motorhomes"* (L!VE I,
page 7) against *"Welcome to our semi-integrated motorhomes"* (VAN TI, L!VE TI, SKY TI,
L!VE WAVE, VAN TI VW, page 14). That yields a three-line rule:

| Condition | `body_type` |
|---|---|
| URL under `/camper-vans/` | `campervan_high_top` |
| `/motorhomes/` and range is L!VE I | `a_class` |
| `/motorhomes/`, anything else | `coach_built_low_profile` |

**Validated against the FMLV baseline before adoption, per the standing rule: 33 of 33 rows
agree**, with no exceptions in either direction. The nine campervan rows are all
`campervan_high_top`; L!VE I and Sun I are `a_class`; every other motorhome is
`coach_built_low_profile`.

The high-top half also checks out independently. Every campervan is 2580 mm or 2780 mm tall,
comfortably over the shared `HIGH_TOP_ABOVE_MM = 2300`, and **the word "pop-top" and every
synonym for it appears zero times on all ten campervan pages** — so the silence-means-option
rule leaves them as plain high tops rather than the elevating-roof variants. That matches
the baseline exactly.

`body_type` is out of scope in `config/field_guide_motorhome.csv`, so it is never proposed
against an existing product — but a new product's row is seeded blank, and this run has new
products. Set it and register it.

## What changed since FMLV was last updated

This is the question the requester actually asked, and the answer is that the 28 August
announcement moved a lot. The site's 28 layouts were matched against the 33 current-year
baseline rows using the repo's own `diff.matching.match_products`, not by hand:

**26 matched, 2 new, 7 disappeared.**

### Discontinued, and confirmed by a second source

The German sitemap (`sitemaps-1-section-motorhomesKnaus`, last modified 1 September 2026)
lists exactly the same 18 motorhome layouts as the UK site, and the campervan sitemap the
same 10. Because the European roster is the superset, an absence from *both* is a real
discontinuation rather than a UK-market subset — which is the reconciliation the roster rule
asks for, and it is what makes these safe to report:

| Baseline row | Evidence |
|---|---|
| `Sun I 700 LEG`, `900 LEG`, `900 LX` | Absent from the German sitemap, absent from the 2027 catalogue, `/en-gb/motorhomes/sun-i` returns **404**. The Sun I is gone. |
| `L!ve I 900 LEG` | **In** the July catalogue (page 13, beside 650 MEG and 700 MEG), but absent from the September sitemap and **404** on the site. Dropped between catalogue and launch. |
| `Van TI Plus 700 LF` | Replaced. The press release says the VAN TI PLUS comes in *"the 650 MEG and 700 DEG floor plan variants"*; 700 LF is not among them. |

### Two duplicate baseline rows, correctly reported as gone

FMLV holds `Van TI 550 MF` **and** `Van Ti Vansation 550 MF`, and `Van TI 650 MEG` **and**
`Van Ti Vansation 650 MEG` — at byte-identical prices (£73,985 and £75,745 respectively).
They are the same two vehicles entered twice. The matcher gives the `Van Ti Vansation` rows
1.000 against the site and leaves the `Van TI` rows unclaimed, so they report as
disappeared. **That is the right outcome** — but it is a duplicate being cleaned up, not a
model being withdrawn, and the run's "7 disappeared" should be read as five withdrawals plus
two de-duplications.

### Genuinely new

- **`SKY TI VW 700 DX`** — no baseline row.
- **`BOXTIME 600 ME`** — no baseline row.
- **`VAN TI PLUS 700 DEG`** is announced but *not yet published* — neither the UK site nor
  the German sitemap has it. Expect it at the September re-check.

### The SKY TI is a different vehicle now, and the matcher partly hides it

The press release calls the SKY TI a *"new edition"* of *"an established, successful
model"*, and it is a bigger change than that phrasing suggests:

| | FMLV baseline `Sky TI 650 MEG` | Site `SKY TI VW 650 MEG` |
|---|---|---|
| Chassis | Fiat | **VW** |
| Price | £84,790 | **£107,985** |
| MRO | 2870 kg | **3107 kg** |
| Height | 2790 mm | **2870 mm** |

A base vehicle changing make is what the README calls the surest tell of a replacement
reported as a revision. Two of the three SKY TI matches need a decision:

- `SKY TI VW 650 MEG` → `Sky TI 650 MEG` scores **0.800**. Same nameplate, same layout code,
  and Knaus present it as an evolution — defensible as a revision, and recommended as one.
- `SKY TI VW 700 DEG` → `Sky TI 700 MEG` scores **0.500**, exactly at `DEFAULT_THRESHOLD`.
  **This one is wrong.** Different layout code, different chassis, different vehicle. It
  should be a new product with `Sky TI 700 MEG` reported as disappeared. Left alone, the run
  will offer a reviewer a "revision" that rewrites a Fiat coachbuilt into a VW one.

This is Etrusco's failure repeating: a differing bed code is one token of four, so a
replacement scores just high enough to look like a revision.

**Resolved by a per-manufacturer threshold**, which is the shape
[`README.md`](README.md) names for exactly this. `knaus.MATCH_THRESHOLD = 0.55`, read by
the new `cli.match_threshold` hook — the same `getattr` opt-in as `DEFAULT_RANGES` and
`baseline_in_scope`, so no other manufacturer is touched. It works here because KNAUS's
matches are separable in a way Etrusco's were not: the lowest **legitimate** score in the
run is 0.600, the five `Boxlife` renames, and the only 0.500 is the bad pair. Nothing sits
between them.

Requester's decision, 1 September 2026, on the direct question: treat the 700 DEG as a new
model. The 650 MEG stays a revision at 0.800 — same nameplate, same layout code, and KNAUS
present it as an evolution of the same vehicle.

## Range and model strings: FMLV needs renaming, and every rename is deliverable

FMLV's range names are a model generation behind the site's, and inconsistently cased. Every
one of the eight renames scores above threshold, so — unlike Wingamm — **all of them can
actually be delivered** rather than orphaning a product ID:

| FMLV range | Site range | Score |
|---|---|---|
| `Sky TI` | `SKY TI VW` | 0.800 |
| `L!ve TI` | `L!VE TI PLATINUM SELECTION` | 0.714 |
| `L!VE WAVE` | `L!VE WAVE PLATINUM SELECTION` | 0.714 |
| `Van TI` | `VAN TI VW VANSATION` | 0.667 |
| `Boxlife` | `BOXLIFE PLATINUM SELECTION` | 0.600 |
| `Van Ti Vansation` | `VAN TI VANSATION` | 1.000 (casing only) |
| `L!ve I` | `L!VE I` | 1.000 (casing only) |
| `Van TI Plus` | `VAN TI PLUS` | 1.000 (casing only) |

The model half needs no change anywhere — FMLV and the site agree on `650 MEG`, `540 MQ` and
the rest — so the "propose both halves together" rule costs nothing here, but the provenance
snippets should still say the two belong together.

**The casing question is a judgement call for the requester.** FMLV is internally
inconsistent (`BOXTIME` capitalised, `Boxlife` not; `L!VE WAVE` capitalised, `L!ve TI` not),
and adopting the site's form would make it consistent at the cost of about twenty
cosmetic-looking proposals in the first review. Recommended, but say so before running it.

## Model year

Every card carries an explicit `(2027)` tag, and the asset paths say `Modelljahr-2027`, so
the model year is read rather than inferred. The catalogues are `07/26` and the German
sitemap sections were last modified **1 September 2026** — the day of this survey — which is
the announcement landing.

Per the standing rule, **re-check at the end of September**: the VAN TI PLUS 700 DEG is
announced and unpublished, and the SKY TI's arrival on the Crafter is recent enough that
prices and weights may still be revised.

## First run — 1 September 2026, runs #55–#58

Built and run the same day as the survey. Against the 33 current-year baseline rows:

```
scraped     28 products
classified  25 changed, 0 unchanged, 3 new, 8 disappeared
proposed    186 changes for review
verified    178 fields checked and unchanged
```

Nothing was dropped by the self-check: all 28 layouts' tolerance bands reconciled. Three
products were hand-checked field by field against the price list PDF; SKY TI VW 700 DEG
matched on all thirteen (`759 cm -> 7590`, `3.207 -> 3207`, `3.850 -> 3850`, payload 643,
Beds 3, belts 2, VW, £110,995).

Two `NOTE`s narrated, both the MTPLM uprate case, and one fallback to the category-wide
price list for VAN TI PLUS. `--range "SKY TI VW"` scopes to 2 baseline rows and gives
1 changed, 2 new, 1 disappeared.

**The proposals a reviewer will see**, by field: `rrp_pounds` 28, `mro_kilograms` 27,
`mh_payload_kilograms` 27, `mh_passenger_seats_inc_driver` 26, `manufacturer_range` 24,
`berths` 14, `mh_height_mm` 11, `mh_width_mm` 8, `mtplm_kilograms` 6, `mh_length_mm` 4,
`base_vehicle_manufacturer` 4, `model` 3, `body_type` 2.

Three of those counts are large by design and each has its own justification above: the
seats change (26), the range renames (24), and the price moves (28, a full model-year
repricing on a range that has just been re-announced).

### A first-run scoping bug worth remembering

`baseline_in_scope` initially matched on the **model code alone**, on the reasoning that
too wide a scope is the safe direction. It is — but `650 MEG` exists in six KNAUS ranges,
so `--range "SKY TI VW"` pulled in twelve baseline rows for three products and reported
**eleven** as disappeared. Safe, and useless: a check that fires on a correct run trains a
reviewer to ignore it. The fix is `_BASELINE_RANGE_NAMES`, an explicit map from each site
range to the FMLV row(s) it corresponds to.

## What is unverified

- **Which of the two `Mass in running order` figures is the base vehicle's.** Still the one
  real open question. The price list turned out to print the *same* duplication, so it
  confirms the row is duplicated in Knaus's data model but does not say which figure is
  which — for the SKY TI VW both copies are identical. Worth asking Knaus directly.
- **Whether the `Sun I` withdrawal is UK-only or global.** Three sources agree it is gone
  (404, German sitemap, catalogue), which is enough to report it, but nobody at Knaus has
  confirmed it.
- **`VAN TI PLUS 700 DEG`** is announced and unpublished. Expect it at the September
  re-check, along with the range's own price list.
- **The casing of the range names.** The adapter emits the site's own capitalisation, which
  makes FMLV internally consistent (it currently holds `BOXTIME` but `Boxlife`, `L!VE WAVE`
  but `L!ve TI`) at the cost of some cosmetic-looking proposals. Raised with the requester;
  not yet explicitly confirmed.
- **The layout-comparison endpoint** (`/en-gb/layout-comparison?layout1=FR…`) was found but
  not parsed. The per-layout pages carry everything, so it was not needed; it may be a
  cheaper bulk source if the site changes shape.

## Floorplans

Every layout page carries day and night floorplan renders, identified by `alt` text rather
than by URL — `R13 650 MEG GR T` and `R13 650 MEG GR N` (`GR` = Grundriss, `T`/`N` = Tag /
Nacht). They are clean top-down PNGs at 40 KB and are **legible enough to read kitchen,
lounge, bathroom and bed arrangement off directly.**

None of those fields are in scope for automated collection — kitchen position, bathroom
type, bed type and lounge position are all out-of-scope layout flags in
`config/field_guide_motorhome.csv`, and the adapter attempts none of them. But the images
are a genuine reference for a human filling those columns in by hand, and worth knowing
about.
