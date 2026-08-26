# Wingamm — site survey and adapter notes

Italian, Verona. Fibreglass monocoque bodies, built since 1977, and a range small enough
(eight products) that the whole thing fits in five PDFs. Survey date **26 August 2026**.

## What the requester brought to the survey

- The models index is
  <https://www.wingamm.com/en/camper-compatti-lusso-monoscocca-vetro-resina/> — not the
  `/en/camper-caravan/` archive the sitemap points at.
- **Wingamm sell campervans, motorhomes and caravans. Caravans are out of scope for this
  review.** That excludes Rookie and Rookie L, which the site files in the same
  `camper-caravan` taxonomy as everything else.
- **The ranges are Brownie, City Pro and Oasi.** Straightforward, and worth stating,
  because FMLV's own `manufacturer_range` disagrees for two of the three (below).
- **The Oasi 690 G is labelled "Oasis 690 G" on the website. That is a typo — use `Oasi`.**
  Confirmed 26 August 2026.

All four held up, and the last one turned out to be one of *two* title bugs on the index
page rather than one.

## Where the data lives: five "CATALOG AND PRICE LIST" PDFs

`https://www.wingamm.com/en/download/` is the English download area — nine documents, and
the only roster of them anywhere. Five are in scope:

| Document | WPDM id | Covers | Last updated |
|---|---|---|---|
| 1. OASI 540.1 CATALOG AND PRICE LIST | 90167 | Oasi 540.1 | 2026-08-26 |
| 2. OASI 610 CATALOG AND PRICE LIST | 90170 | Oasi 610 ST, 610 GL, 610 M | 2026-08-26 |
| 3. OASI 690 CATALOG AND PRICE LIST | 131963 | Oasi 690 Twins, 690 G | 2026-08-26 |
| BROWNIE CATALOGUE | 90047 | Brownie | 2023-11-20 |
| CITYPRO CATALOGUE | 90050 | City Pro | 2023-11-20 |

The other four are the two Rookie caravan price lists, the Rookie L catalogue and a logo
kit. That last row has a title and **no readable download link**, so eight of the nine
rows parse; `count_download_rows` exists to say so, because the day a *catalogue* row
changes shape the only symptom would be a quietly missing range.

`/en/` is a language, not a market — the site is a translation mirror that keeps Italian
slugs on every path. It publishes no prices, no downloads and no sterling anywhere, so
`/en/download/` is the only English-specific page that matters, and what English gets
there is a genuine subset: the three Oasi documents are priced, Brownie's and City Pro's
are catalogues only. Their price lists exist in Italian, French and German-for-Austria
alone (see the price section).

**Discover the list per run** rather than hardcoding ids: the page renders one
`<a class='wpdm-download-link' href='…/download/<slug>/?wpdmdl=<id>&refresh=…'>` per
document, the `refresh` parameter is a cache-buster and can be dropped, and the ids move
when a document is replaced (the 690 catalogue is already on its second id, and there is a
stray uncategorised "Oasi 610 Catalog", 135770, that the page does not list).

### The form is a front door, not a lock

Every model page and every download page carries a Brevo lead-capture form — "fill out the
form to access the configurator and receive brochures, price lists". Ignore it. Requesting
`…/download/oasi540-1-catalog/?wpdmdl=90167` returns `application/pdf`, 13.8 MB, no cookie,
no token, no referer check. Same as Rimor: **check whether the gate is guarding anything
before submitting anybody's details.** Nothing was submitted for this survey.

### Attribution is free, which is the whole reason to prefer the PDFs

Each document is one range. Inside it:

- **One floorplan page per layout**, carrying that layout's name and starting price:
  `OASI 610ST  106.300 €`, `OASI 610GL 106.300 €`, `OASI 610M  106.300 €`. This is the only
  place the individual 610 and 690 layouts are named in the document.
- **One `TECHNICAL DETAILS` block per range** (2–3 pages), one `label unit value` per line:

  ```
  External length MM 6.103
  External width MM 2.240
  External height MM 3.030
  Overall maximum weight KG 3.500
  Weight in running order KG 3.047
  Payload KG 453
  ```

  Shared across the range's layouts, which is correct — the 610 ST, GL and M are the same
  monocoque with different furniture, and FMLV already holds identical numbers for all
  three.

No columns anywhere, so none of `README.md`'s column-alignment defences are needed. The
risk here is entirely **which label is this**, the Auto-Trail failure mode.

## The self-check: MTPLM − MRO = payload, and one range that cannot use it

| Range | MTPLM | MRO | Payload | Checks out |
|---|---|---|---|---|
| Oasi 540.1 | 3500 | **not published** | 655 | no — see below |
| Oasi 610 | 3500 | 3047 | 453 | 3500 − 3047 = 453 ✓ |
| Oasi 690 | 3500 | 3150 | 350 | 3500 − 3150 = 350 ✓ |
| Brownie | 3500 | 2747 | 753 | 3500 − 2747 = 753 ✓ |
| City Pro | 3500 | 2888 | 612 | 3500 − 2888 = 612 ✓ |

**The 540.1 catalogue omits MRO entirely.** Its technical block jumps from
`Overall maximum weight KG 3.500` to `Payload KG 655`. FMLV holds 2845, which is exactly
3500 − 655, so whoever entered it derived it the same way — but a figure derived from the
other two cannot then be used to check them. For the 540.1 the check degrades to the
**cross-document** form: the models index card and the model page both republish length,
seats and total mass, so those are compared against the PDF instead. Say so in the
provenance rather than presenting a derived MRO as a published one.

Two payload decoys to avoid, both inside the same block: `Garage payload KG 200`,
`External rear motorbike rack payload (OPT) KG 150` and `Towbar payload (OPT) KG 2.000`.
And the 610 catalogue prints `PAYLOAD 350KG` as marketing copy on a feature page — which is
the *690's* payload, not the 610's. Anchor on the exact label plus its unit token.

## Label variance: every document names the weights differently

Five documents, five vocabularies. This is the single thing most likely to break the parser
on a range it was not tested against:

| Field | Labels seen |
|---|---|
| MTPLM | `Overall maximum weight` (540, 610, Brownie), `Maximum authorized mass` (690), `Maximum permissible weight` (City Pro) |
| MRO | `Weight in running order` (610, Brownie), `Mass in running order` (690, City Pro), absent (540) |
| Payload | `Payload`, `Payload*` (City Pro) |
| Seats | `3 points seatbelts` + `Approved number of places` (540, 610, Brownie), `Approved seats` (690), `Three-point seatbelts` (City Pro) |
| Berths | `Number of beds` (540, 610, Brownie, City Pro), `Sleeping capacity` (690) |
| Interior height | `Interior height CM` / `Internal height CM` / `Internal height MM` (City Pro) |

Numbers are as inconsistent as the labels: `3.500` and `3500`, `2.240` and `2240`, in the
same corpus and sometimes the same document. Strip `.` as a thousands separator, but only
between digits — `540.1` is a model name and `13,9` a turning radius.

### The two 2023 catalogues split labels from values

Brownie's and City Pro's technical pages are the older template. Page 1 of 2 is
`label unit value` per line as above, but **page 2 of 2 emits every label first and then
every value**, in two blocks:

```
Travel seats
Number of beds
Longitudinal drop-down bed size
…
N. 4
N. 2
CM –
```

Pairing those by position is exactly the silent misalignment `README.md` warns about, and
the counts do not even match (22 labels, 21 values). Everything the pipeline needs is on
page 1 *except* berths, so read berths for these two from the site instead — the index card
gives `Berths: 4` / `Berths: 2` and the model pages `Sleeps: 4` / `Sleeps: 2`, agreeing.

## Berths: `3+1` on the 540.1

`Number of beds N. 3+1` — a drop-down double, a dinette single, and an optional fourth from
the dinette conversion (`Optional bed created from the dinette`, priced at
`NIGHT DOUBLE (4° Letto) € 980`). Lower figure, so **3**, which is what FMLV holds. Carry
the raw `3+1` into the provenance snippet.

## The website disagrees with the PDFs on Oasi width and height, and the website is wrong

Three sources, three answers, for vehicles that all share one monocoque cross-section:

| Source | Oasi width × height |
|---|---|
| Index cards (all six Oasi) | 2248 × 3020 |
| Model pages, 540.1 and 610 ST | 2248 × 2961 |
| Model pages, 610 GL and 610 M | 2240 × 3030 |
| Model pages, both 690s | absent — no width or height at all |
| **All three catalogues** | **2240 × 3030** |

`README.md`'s default is that the site overrules the PDF, and the test for diverging is not
"which is newer" but **"can I show one of them is wrong?"** Here I can, twice over. The
site contradicts *itself* — the 610 ST and 610 GL are the same shell and it gives them
different figures — and FMLV's own baseline already holds 2240 × 3030 on all six Oasi, plus
Brownie and City Pro figures that match their catalogues to the millimetre. The catalogue
is where this data came from; the index cards are marketing copy.

Brownie and City Pro agree exactly between index card and PDF (5890 × 2190 × 2750 and
5990 × 2050 × 2770), which is what makes the Oasi disagreement legible as a site defect
rather than a document being stale.

## Price: published in euro, ex works, VAT excluded — and FMLV's pounds are better

Every Oasi catalogue prices each layout, and the footer says what the figure is:
`Prices ex-works and VAT excluded. This pricelist may be updated without notice.`

| Layout | Published price | Basis | FMLV `rrp_pounds` |
|---|---|---|---|
| Oasi 540.1 | € 99.800 | ex works, VAT **excluded** | £92,410 |
| Oasi 610 ST / GL / M | € 106.300 (all three) | ex works, VAT excluded | £95,960 / £97,540 / £96,220 |
| Oasi 690 Twins / G | € 114.900 (both) | ex works, VAT excluded | £110,130 / £110,130 |
| Brownie | € 115.168 | ex works, Italian VAT 22% **included** | £93,500 |
| City Pro | € 104.432 | ex works, Italian VAT included | £84,430 |

Brownie's and City Pro's figures come from `LISTINO AGOSTO 2025`, their Italian price
lists (`/it/download/brownie-listino-prezzi-3/?wpdmdl=90156` and
`.../citypro-listino-prezzi-4/?wpdmdl=90157`), which are the only priced documents those
two have in any language. So the five documents **do not share a basis**: taking them at
face value would put a VAT-excluded figure on the six Oasi and a VAT-included one on the
other two, a 22% step between ranges of the same brand. Normalising the two to ex-VAT
gives € 94,400 and € 85,600.

**The adapter emits no `rrp_pounds`.** FMLV's figures are not derivable from the euro ones
at any single rate — against the ex-VAT euro figures the ratio runs 0.918 to 0.987 — and
FMLV prices the three 610 layouts differently where every Wingamm document prices them
identically. Its data comes from a UK importer price list that is not on the website, at a
granularity nothing published matches. Proposing a euro ex-works figure would replace eight
good UK prices with something well short of what a buyer pays, on a brand where RHD is
itself a `€ 3.000` option. Swift, Rimor and Chausson already set the precedent for
collecting no price; this is the stronger version of it, because here there *is* a
published price and it is still the wrong number.

The euro figure is narrated through `on_progress` rather than attached to the record, so it
reaches the run log and a reader of this file without ever being able to reach a
`Motorhome`. Requested from Wingamm UK on 26 August 2026; if a sterling list arrives, this
decision is the thing to revisit first.

**One known cost.** `rrp_pounds` is in scope in `config/field_guide_motorhome.csv`, so a
field no adapter populates raises a confirm-this-value row on every matched product — eight
per full run, old value equal to new. That is the pipeline's existing behaviour for a
no-price brand rather than anything specific here (Chausson's runs do the same), and it is
the reason `price_min_range_pounds` was taken out of scope and mirrored at output instead.
Worth knowing before reading a run summary: eight of the proposals are noise.

## Range and model strings: two of the three ranges are wrong in FMLV

The baseline (`fmlv fetch-export "Wingamm"`, 26 August 2026 — nine rows, eight current):

| `manufacturer_range` | `model` | product_id |
|---|---|---|
| Oasi | 540 | 5856 |
| Oasi | 610GL / 610M / 610ST | 5857 / 8417 / 8418 |
| Oasi | 690 TWINS / 690G | 8419 / 8420 |
| **Campervan** | City Pro | 5854 |
| **Coach Built low profile** | Brownie | 5855 |

The Oasi half is clean and the adapter should emit those exact strings — `610GL` unspaced,
`690 TWINS` spaced and capitalised, `690G` unspaced. `540` against the vehicle's actual
name `540.1` is the one soft spot: Jaccard on `{540}` vs `{540, 1}` scores 0.500, which
`diff/matching.py` accepts, but only just.

City Pro and Brownie have a **body type sitting in the range column**. The requester's
"the ranges are Brownie, City Pro and Oasi" settles what they should say. Per `README.md`,
propose *both* halves together or neither.

### One of those two renames can be delivered and the other cannot

`diff/matching.py` scores identity as a Jaccard similarity on the range-plus-model word
bag, and the two corrections land on opposite sides of its 0.5 threshold:

| Baseline identity | Corrected to | Score | Outcome |
|---|---|---|---|
| `Campervan` + `City Pro` | `City Pro` + `City Pro` | 2/3 = **0.667** | proposed normally |
| `Coach Built low profile` + `Brownie` | `Brownie` + `Brownie` | 1/5 = **0.200** | orphans the product |

Run #30 is the evidence: the scraped Brownie was classified **new** and the real one,
`product_id` 5855, was reported **disappeared**. A rename that orphans the product it
renames is worse than the wrong name — an upload would create a duplicate, and a reviewer
would read a discontinuation that has not happened.

So Brownie **emits FMLV's own wrong range**, with no provenance on either half of the
identity, and nothing is proposed: it matches at 1.000 and its weights and dimensions
update normally. The correction is a one-line manual edit on the FMLV site, narrated on
every run until someone makes it — then `intended_range` comes out of `_DOCUMENTS`. The
asymmetry with City Pro is the matcher's, not Wingamm's.

This is a different failure from Bailey's, which was about accepting *one* half of a
proposed rename. Here the rename cannot be proposed at all, because the product it belongs
to stops being recognisable as itself. `README.md` notes that raising
`DEFAULT_THRESHOLD` cannot be the answer to Etrusco's problem; this is the case that shows
lowering it is not the answer either, since 0.200 is far below any threshold that would
still separate real vehicles.

### `--range` selectors are documents, so baseline scope needs the hook

The three Oasi documents are one FMLV range, and `cli.resolve_ranges` keys `--range` on the
label — so the labels have to be `Oasi 540.1`, `Oasi 610`, `Oasi 690` (unique) while
`fmlv_range` stays `Oasi`. That breaks `cli.baseline_scope`'s default, which matches the
selector against `manufacturer_range`: run #32 scoped `--range "Oasi 690"` to **zero**
baseline rows and proposed both products as new. `wingamm.baseline_in_scope` scopes on
`model` instead, which also survives the renames — matching on the range column would have
missed City Pro's row, still filed under `Campervan`, and proposed a duplicate.

## Body type: five Oasi rows are wrong, and City Pro is the campervan

Wingamm state their position on the index page: *"we immediately chose the semi-integrated
camper formula, excluding the solutions with attic, which by sailing, reduce the vehicle's
stability on the road"*. Semi-integrated is low profile, and the bed over the dinette is a
**drop-down** (`W – Longitudinal double drop-down-bed | 350 Kg Patented`), not an over-cab
bed. There is no over-cab bed anywhere in the range.

FMLV holds `type_coach_built_over_cab_bed` on 610GL, 610M, 610ST, 690 TWINS and 690G, and
`type_coach_built_low_profile` on the 540 and Brownie. The five are wrong and the adapter
should propose the correction.

### City Pro is a campervan, and its monocoque body does not change that

Settled by the requester on 26 August 2026, and worth writing down because the evidence
points both ways depending on which part of the page you read. Wingamm's own copy:

> City Pro of the Fiat Ducato van has only the engine and the external measures; the
> bodywork is not the sheet metal of the van, but a fiberglass monocoque with all the
> thermal and acoustic comfort guaranteed by Wingamm standards.

Read literally, that is a coachbuilt — the box is moulded, exactly like every Oasi. But the
heading above it is **"A CAMPER LIVE IN, A VAN TO DRIVE"**, the copy says "the van"
throughout, and the photograph is unmistakably a van with a raised roof. It is 2050 mm wide
against the coachbuilts' 2240, on van external measures. The requester's call, from the
photograph: **`campervan_high_top`** — which is what FMLV already held.

The general rule this produced now sits in `README.md`: **construction is not the test.**
`WingammProduct.body_type` splits accordingly —

- **campervan or coachbuilt** is *declared* per document (`is_campervan`), because shape and
  proportions are a judgement no parser makes;
- **high top** is *derived* from the published height against the shared
  `HIGH_TOP_ABOVE_MM = 2300`; City Pro's 2770 mm clears it comfortably;
- **elevating roof**: none. `README.md`'s rule is that an unmentioned pop-top is an absent
  one, and every Wingamm roof is a fixed load-bearing moulding
  (`W - Load bearing walkable roof | 100% hailproof`);
- **no height, no body type** — the missing-data rule, rather than a guessed classification.

So the adapter proposes no change here, but it now *confirms* the value instead of leaving
it to depend on nobody having touched it: run #37 verifies `body_type` as unchanged rather
than never attempted.

## The roster: eight products, and the index is not to be read for names

Six Oasi layouts + Brownie + City Pro. The index page carries a card per layout, and every
card links to its own `/en/camper-caravan/<slug>/` page:

```
oasi-540  oasi-610-gl  oasi-610-st  oasi-610m  oasi-690-twins  oasi-690-garage
brownie   city-pro
rookie  rookie-l          <- caravans, out of scope
```

`/en/` also links an **`oasi-540-preview`** page that appears in no index. It carries the
540.1's figures verbatim — a leftover preview, not a ninth vehicle — and is listed in
`_IGNORED_SLUGS` so the roster check reports only genuinely new layouts.

Three traps in the index, one of which the requester had already flagged:

- **The Oasi 690 G card is titled "Oasis 690 G".** Use `Oasi`.
- **The Oasi 610 M card is titled "Oasi 610 GL".** So the page renders what looks like the
  610 GL twice and the 610 M not at all. The `href` is the only thing that identifies it.
  Take identity from the catalogue and the slug, never from a card title.
- **The index's own prose says "The Oasi range consists of 3 models in 5 variants".** It is
  six. Three model families is right; the variant count is stale. `README.md` wants a
  published count to check the parse against — this one cannot be used, and the roster
  reconciles instead against the eight FMLV baseline rows and the five catalogues.

`sitemap_index.xml` is Rank Math and lists **only `/it/` URLs**, so it is no use for the
English roster; `sitemap.xml` and `robots.txt` both return the site's catch-all HTML page
rather than 404, which will fool a "does this exist" check.

## Model year

**Wingamm publish no model year at all** — not on the pages, not in the catalogues, not in
the filenames. FMLV holds 2026 on all eight current rows. The three Oasi catalogues were
republished 26 August 2026, the day of this survey, and Wingamm exhibit at Caravan Salon
Düsseldorf, so this is squarely inside `README.md`'s rollover window — but there is nothing
published to justify a bump, so 2026 stands. Re-check late September. If the pipeline
proposes 2026 → 2027 seasonally, leave it **undecided**, never rejected (Elddis, and the
`was_previously_rejected` gate that has no run scoping).

## The model pages have their own vocabulary, and it is not the catalogues'

Found while building, not while surveying, and each one silently cost every product it
touched until it was handled:

| What | Six Oasi pages | Brownie | City Pro |
|---|---|---|---|
| Chassis row | `Drive:` | `Tractor:` | `Tractor:` |
| Mass row | `Total mass:` | `Total mass:` | **`Mass in running order:`** |
| Markup | `<li>…Label: value</li>` | same | value sits *outside* the label's span |

- **`Tractor` is `motrice` translated a second way.** Reading only `Drive` left the base
  vehicle blank on exactly the two products whose catalogues never spell out `FIAT DUCATO`
  either — City Pro's only mention of the marque is `Body-coloured FIAT front bumper`,
  which is why the catalogue fallback requires `DUCATO` and not `FIAT`.
- **City Pro publishes the running order where the others publish the laden weight**, so
  reading only `Total mass` left it with no cross-document check at all — on the one figure
  worth checking twice.
- **The value can sit outside the span holding its own label:**
  `<span><span>Mass in running order:&nbsp;</span></span>2.888 kg`. The pattern therefore
  skips closing tags and whitespace between the colon and the value, but **only** closing
  tags — reaching the next row would mean crossing an opening `<li>`, so an empty row reads
  as empty instead of borrowing its neighbour's number.
- **The index card and the model pages render the same list differently** (`<strong>Label:
  </strong> value` against `<li>Label: value</li>`), which is why one pattern handles both.

The first attempt at this adapter collected **zero products** for the first of these
reasons, and knew it: the check that no seats *and* no berths means a page it cannot read
turned a silent nothing into eight named skips. `README.md`'s "does your verification probe
fail where the adapter fails?" is why it was found in a minute — the probe was
`wingamm.collect` itself, not a script with a fallback the adapter lacked.

## First run — 26 August 2026, run #31

Eight products from 15 fetches: the download area, the models index, five catalogues and
eight model pages. 53 seconds, no browser.

| | |
|---|---|
| scraped | 8 |
| baseline | 8 (9 export rows, one archived 2024 `690 GC`) |
| classified | 7 changed, 1 unchanged, **0 new, 0 disappeared** |
| proposed | 23 |
| dropped | none — all eight reconcile |

The 23 proposals are five real corrections, one rename, two lengths, seven year bumps and
eight price no-ops:

- **`body_type` on 610GL, 610M, 610ST, 690 TWINS and 690G** — `type_coach_built_over_cab_bed`
  to `type_coach_built_low_profile`. The correction this adapter most obviously earns.
- **`manufacturer_range` on City Pro** — `Campervan` to `City Pro`.
- **`mh_length_mm`: Oasi 540 5400 → 5420, City Pro 5999 → 5990.** Both are FMLV
  transcription slips against documents that say 5.420 and 5.990.
- **`year` 2026 → 2027 on seven products.** Wingamm publish no model year at all, so
  **leave these undecided, never rejected** — `was_previously_rejected` has no run scoping,
  so a rejection suppresses the bump permanently and closes `--bump-year` too (Elddis).
- **`rrp_pounds` on all eight, old value equal to new** — the no-price cost described above.

Everything else verified unchanged: 85 fields across the eight products, including every
width, height, MTPLM, MRO and payload. That agreement is the strongest evidence in this
survey that the catalogues are where FMLV's own data came from.

## What is unverified

- **No GBP source found.** FMLV's prices came from somewhere off-site. **The requester was
  contacting Wingamm UK (01292 262233, an Ayrshire number) for the UK price list as of
  26 August 2026.** If one arrives as a document, price becomes collectable and this
  survey's price decision is the first thing to revisit.
- **Brownie's range still needs a manual edit on the FMLV site** — the rename the pipeline
  cannot deliver. Once `manufacturer_range` reads `Brownie` on `product_id` 5855, drop
  `intended_range` from that document in `_DOCUMENTS` and the narration goes with it.
- **Brownie and City Pro catalogues are from November 2023** and are the only English
  documents for those two vehicles. Their figures still match FMLV exactly, so nothing is
  known to be stale — but a 2026 revision would not show up as a new document, only as a
  changed one, which is why the download area must be re-read per run.
- **Interior/layout flags are not attempted**, per the Adria precedent. Note the 540's
  baseline row carries `no_toilet` and `no_shower`, which is wrong — it has a rear bathroom
  with a shower column — but that is out of scope here, not something the adapter should
  quietly start writing.
