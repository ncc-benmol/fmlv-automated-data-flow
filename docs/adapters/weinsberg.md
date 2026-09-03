# Weinsberg — site survey and adapter notes

German, Jandelsbrunn. A brand of Knaus Tabbert AG, sibling to [Knaus](knaus.md). Survey
date **3 September 2026**, two days after the Knaus survey, and this document leans on that
one heavily: same parent, same price-list generator, same traps — but a *different website*
and a different primary source, so the conclusions are not transferable wholesale.

## Scope: the WEINSBERG brand only, and caravans are out

Knaus Tabbert AG owns KNAUS, TABBERT, WEINSBERG, T@B, MORELO and RENT AND TRAVEL. This
adapter covers **WEINSBERG-branded motorhomes and campervans only**. Caravans (CaraOne,
CaraCito, CaraTwo …) are excluded, per the requester and per
`config/manufacturers.README.md` — `weinsberg.com` sells all three, so unlike `knaus.com`
the scoping here has to be *done*, not merely assumed.

### Two manufacturer ids, and why 252 is the right one

`resources/manufacturers-full-list.csv` carries **two** rows that could be this brand:

| id | Name | DisplayName |
|---|---|---|
| 112 | `Knaus Tabbert AG Weinsberg` | Weinsberg |
| 252 | `Knaus Tabbert AG` | Weinsberg |

The requester specified **252**, and the export settles it rather than leaving it to
judgement. `fmlv fetch-export` on supplier `Weinsberg` returns 88 rows carrying **both**
manufacturer strings:

| `manufacturer` | rows | years |
|---|---|---|
| `Knaus Tabbert AG` | 34 | all 2026, none archived |
| `Knaus Tabbert AG Weinsberg` | 54 | 2022–2025, 23 archived |

Every current-model-year row is under `Knaus Tabbert AG`, and every `…AG Weinsberg` row is
old enough that `cli._is_current_model_year` drops it anyway. So id 252 gives exactly the
34-row baseline the diff should see, and id 112 would contribute nothing but history.
Nothing is orphaned by the choice — but note that id 112 is a *live* string in FMLV's data,
not a dead one, and if the NCC ever re-issues current-year rows under it this row is wrong.

The NCC supplier name is **`Weinsberg`**, given by the requester, and it worked on the
first `fetch-export` attempt — worth noting against Knaus, where it took three guesses.

## What the requester brought to the survey

All of it held up, and two points were the survey's most valuable steers:

- **The site is <https://weinsberg.com/en-uk/> and caravans are out of scope.** Correct.
- **"A lot of the tech data is in the price list which has to be downloaded."** Correct, and
  stronger than it sounds: the UK site publishes **no per-layout page at all** (see below),
  so the price list is not merely the better source, it is the *only* source for weights,
  berths and seats.
- **"The number of seats with seatbelts is once again slightly confusing as they state a
  maximum, but then show the standard number."** Exactly right, and the same shape as Knaus.
  See the seats section.
- **"The MIRO info appears to be duplicated on at least some models"**, with a screenshot of
  the CaraHome UK price list. Confirmed, and characterised across all 29 products below.

The screenshot also quietly resolved the survey's biggest wrong turn: it reads
**`List price in GBP including 20% VAT`**, and the document linked from the site's own
downloads page reads `List price in EUR including 19% VAT`. Without the screenshot the EUR
list would have looked like the right answer, because the download card *calls* it a UK
price list.

## Where the data lives: six per-range UK price lists, rediscovered per run

Each range page under `/en-uk/{motorhomes,camper-vans}/<slug>/` carries a **Download price
list** button pointing at `konfigurator.knaustabbert.de/rest/1/downloadPriceList/<token>` —
the same host Knaus uses. Those six documents are the source:

| Range page | Price-list range title | Layouts |
|---|---|---|
| `/motorhomes/caracore/` | `CaraCore` | 3 |
| `/motorhomes/carahome/` | `CaraHome` | 3 |
| `/motorhomes/carasuite-edition-spicy/` | `CaraSuite EDITION [SPICY]` | 5 |
| `/motorhomes/edition-pepper/` | `CaraCompact EDITION [PEPPER]` | 3 |
| `/camper-vans/edition-fire/` | `CaraBus EDITION [FIRE]` | 7 |
| `/camper-vans/grey-edition-fire/` | `CaraBus GREY EDITION [FIRE]` | 7 |

Each is 14–19 pages, GBP, `including 20% VAT`, and carries price, chassis, all three
dimensions, MRO with its tolerance band, MTPLM, wheelbase, berths and belted seats. Real
rows, `CaraCore` page 5:

```
Technical Data 650 MF 650 MEG 700 MEG
List price in GBP including 20% VAT 88.995,- 89.985,- 92.485,-
Chassis FIAT FIAT FIAT
Total length (cm) 699 699 741
Mass in running order (basic model without optional equipment but with basic
equipment) (kg) (Hints: H140)
2.930 (2.783
- 3.076)
...
Technically maximum authorised laden mass (kg) 3.500 3.500 3.500
Beds (Hints: H141) 5 4 5
Three-point belts in driving direction 2 2 2
```

**Rediscover the token from the range page every run; never hardcode it.** The token is a
zlib-compressed CBOR map —
`{b: "WEINSBERG", c: "UK", l: "EN", m: 2027, k: "R50-CARACORE-MJ27"}` — with a trailing
signature. That is worth knowing for two reasons: it explains why the URL is stable enough
to be worth reading off the page, and it closes off the temptation to *construct* one. A
hand-built token reproducing the CBOR body byte-for-byte is **rejected** by the server
(it returns JSON, not a PDF), because the signature cannot be forged. There is no route to
a document the site does not link.

### The near-miss: the downloads page's "Price list, UK" is the EUR list

`/en-uk/support/catalogues-price-lists/` offers six documents, and its cards are labelled
**"Price list, UK"**. They are not. All three resolve to
`/fileadmin/media/mj2026-2027/global/…/Price_List_Model_Year_2027-1_{RM,CAVA,WW}_DE-EN__05-08_13-30-59_.pdf`
— the `global`, `DE-EN`, **euro** price lists, quoting `List price in EUR including 19% VAT`
throughout. The word `GBP` appears **zero times** in either of them.

This is the README's "does the downloads page list more than the current document?" trap in
a new form: the near-miss is not a superseded model year or a glossy catalogue, it is a
*differently-priced market edition sitting behind a label that names the right market*.
Reading the card would have put euro prices into `rrp_pounds` on all 28 layouts and
reintroduced the exchange-rate problem that is the worst data in `morelo.py` — while the
site publishes sterling two clicks away.

The rule that catches it is not "prefer the per-range document" but **read the currency out
of the document you actually downloaded**. The adapter should require
`List price in GBP including 20% VAT` and reject a document offering EUR — a one-line
assertion that would have failed loudly here.

### The European lists are still useful — as the second source

The same two euro documents are the **European superset**, and they earn their keep twice:

- They are the cross-document check described under "self-check" below.
- They settle the roster questions, because they list ranges the UK does not get:
  `CaraCompact`, `CaraSuite`, `CaraBus` and `CaraBus GREY` all exist in Europe as plain
  (non-`EDITION`) ranges with identical layout rosters to their `EDITION` siblings. The UK
  gets only the `EDITION` variants. That is the README's "a non-core brand's UK site is a
  deliberate subset" rule, and it means **a shorter UK roster is not evidence of a parse
  failure** — the plain ranges are absent by design, not by accident.

## There is no per-layout page on the UK site

Worth stating plainly, because it is the biggest structural difference from Knaus and the
reason the source ranking comes out the other way round.

The German tree has one page per layout — `/wohnmobile/caracore/grundrisse/650-meg/`. The
UK tree has **nothing equivalent**: `/en-uk/motorhomes/caracore/layouts/650-meg/` and
`/en-uk/motorhomes/caracore/grundrisse/650-meg/` both return the site's 404 page. The
`CaraCore layouts` heading on the range page is a JS-driven carousel that renders no model
names into the served HTML.

So where Knaus's website beat its PDFs on attribution and completeness, Weinsberg's website
carries almost no per-layout data at all. The PDF is not a fallback here; it is the source.

**And the 404 page returns HTTP 200.** Any probe of a UK URL has to test the `<title>` for
`404 - Page not Found`, not the status code.

### What the range page *does* give: three free checks per range

The range page is still worth fetching, and not only for the token. It publishes, in the
served HTML:

- **the layout count** (`3 layouts`),
- **the cheapest price** (`from 88.995,00 £ *`),
- **`up to N sleeping places`** and **`up to N belted seats`**.

All four reconcile against the price list on all six ranges — the counts exactly, the price
against the roster's minimum, and the two maxima against `Max. number of beds` and
`Max. belt-secured seats` respectively. That is a completeness check that costs nothing and
does not depend on the sitemap.

Note *which* rows the site's maxima correspond to: `up to 5 sleeping places` on CaraSuite is
the maximum of `Max. number of beds` (5), **not** of `Beds` (3). The website publishes
ceilings; the price list publishes both ends. This is the requester's seat/berth warning
showing up on the berth side as well.

## X-PEDITION: one product, on its own website, priced in the UK but listed nowhere

The single hardest scoping call in the survey, and the FMLV baseline decides it.

X-PEDITION is a Mercedes Sprinter campervan, one layout (`600 MQ`). It is:

- **on the UK campervan index** with a UK price, `102.490,00 £ *`, and four key facts;
- **not linked from it** — the index's cards are `<div class="link__button">`, not anchors,
  so no `href` for X-PEDITION (or for either `EDITION [FIRE]` range) appears in the served
  HTML at all;
- **on its own site**, `weinsberg-xpedition.com`, which has locales for thirteen markets and
  **no `en-uk`** (`/en-uk/` returns "Oops, an error occurred!");
- **absent from every UK price list**, and its only configurator link anywhere on the site
  points at the `/de` market, not `/uk`;
- **present in the European euro price list**, in full, as its own range.

And **FMLV already holds it** — `product_id` 8610, range `X-Pedition`, model `600 MQ`,
Mercedes, `campervan_high_top`. So excluding it would report a product the NCC holds as
disappeared, which settles the question: it is in scope.

Its specs therefore come from the **European euro list** — the only document that carries
them — while its price comes from the **UK campervan index card** in sterling. That is a
deliberate, documented departure from taking one document per product, and it is the honest
one: the alternative is a blank on every weight, or a converted euro price.

Two cautions recorded here because they will not be obvious later:

- **Its own microsite disagrees with the price list**, and the price list wins. The
  microsite says total length 600 cm, exterior height 290 cm and `Berths: up to 3`; the
  price list says 594 cm, 283 cm and `Beds 2` / `Max. number of beds 2`. The UK index card
  agrees with the price list (`594 cm`, `up to 2 sleeping places`), so the microsite is the
  odd one out — two sources against one, and the microsite has no spec table.
- **It is the one product with no `List price in GBP` document**, so the currency assertion
  above cannot be applied to it. Its price is read from the index card, whose footnote gives
  the same basis (`Prices include 20% VAT … manufacturer's recommended retail prices`).

## OUTLAW is not a range

`/en-uk/camper-vans/carabus-carabus-grey-outlaw/` looks like a seventh range and is not. Its
own copy says the vehicle is *"The CaraBus/CaraBus GREY EDITION [FIRE] 630 MEG [OUTLAW]"* —
i.e. it is the **630 MEG layout of the two EDITION [FIRE] ranges**, both already collected.
It has no price list of its own, and the page's key facts are visibly broken:
`up to 0 sleeping places`, `0 layouts`, `0 kg`, `Total length 0 cm`, no price.

So it contributes no products. FMLV's own 2025 row `CaraBus / 630 MEG OUTLAW` (5677) is
archived, and the current-year rows are `630 MEG Edition FIRE` /
`630 MEG GREY Edition FIRE`, which agrees. **Do not fetch it as a range** — a zero-product
range page is exactly the shape that looks like a parse failure a year from now.

## The roster: 29 products, and where the number comes from

| | Range | Layouts |
|---|---|---|
| Motorhomes | CaraCore | 3 |
| | CaraHome | 3 |
| | CaraSuite EDITION [SPICY] | 5 |
| | CaraCompact EDITION [PEPPER] | 3 |
| Campervans | CaraBus EDITION [FIRE] | 7 |
| | CaraBus GREY EDITION [FIRE] | 7 |
| | X-PEDITION | 1 |
| **Total** | | **29** |

Reconciled three ways: each range page's own `N layouts` claim, each price list's stated
`Technical Data <roster>` header, and the European euro lists. All three agree.

**Neither index page is a complete roster** — the README's rule, and Weinsberg breaks it
twice over. `/en-uk/camper-vans/` renders cards for X-PEDITION and both `EDITION [FIRE]`
ranges but links none of them, and `/en-uk/motorhomes/` links its four. Both
`EDITION [FIRE]` slugs were found by taking the **German sitemap's** slugs
(`camper-vans-kastenwagen/edition-fire/`, `.../grey-edition-fire/`) and trying them under
`/en-uk/` — the sitemap is German-only (`weinsberg.com/sitemap.xml?sitemap=pages` lists no
`/en-uk/` URL at all), so it gives slugs, not URLs. The two ranges are also linked from
`/en-uk/the-brand/new-products-2027/…`, which is where a customer would find them.

Fifteen fetches a run: 2 index pages, 6 range pages, 6 UK price lists, and the European
campervan list for X-PEDITION.

## Units and number format

Identical to Knaus, and for the same reason — the same document generator.

- **Everything is centimetres.** FMLV wants millimetres; multiply by ten.
- **German thousands separators throughout.** `3.500` is 3500, `2.930` is 2930, and
  `88.995,-` is £88,995. Never treat the `.` as a decimal point. The trailing `,-` on prices
  is a German convention for "and no pence".

## The self-check: two of them, and both hold 28/28

**The ±5% production tolerance band.** Every `Mass in running order` prints its band:

```
2.930 (2.783 - 3.076)
```

and the price list's own Important Notes say why — *"a calculated nominal value subject to
production-related variations of up to ± 5% … separately indicated in the technical data
following the calculated value"* — with hint `H140` reading *"Incl. indication of
production-related tolerances of ±5%"*. **Verified 28 of 28** (the 28 from UK price lists;
X-PEDITION's band holds too, from the euro list), to within a kilogram of rounding. This is
`_reconciles()`.

**The cross-document check.** Every UK per-range list's `Total length`, `Width (outside)`,
`Height (outside)`, `Technically maximum authorised laden mass` and `Mass in running order`
were compared against the same layout in the European euro lists: **28 agree, 0 differ, 0
absent.** The two documents differ *only* on currency and on `Maximum payload` (below),
which makes this a genuine Rimor-style second source rather than a restatement.

A third, weaker check comes free: the range page's `N layouts`, `from` price and two maxima,
described above.

### What is *not* a self-check: "Maximum payload"

Same conclusion as Knaus, reached independently here. `Maximum payload (kg)` is a
homologation figure and reconciles with nothing: CaraCore 700 MEG prints **18 kg** where
`3500 − 2960 = 540`, and CaraSuite 700 MEG prints 33 where the arithmetic gives 542.

It is also **the one field where the UK and European documents disagree** — CaraHome prints
`85 50 200` in euros and `63 22 170` in sterling for the same three layouts — which is by
itself sufficient reason not to record it: a figure that changes with the market it is
priced in is not a property of the vehicle.

The website publishes the same number as `Payload ex works` (`up to 77 kg` on CaraCore,
matching the price list's `77 53 18`), so **the website is no escape from it either.**

`mh_payload_kilograms` is therefore **derived as `MTPLM − MRO`**, which is what FMLV holds —
and here the baseline cannot corroborate that, because its own payload figures are
placeholder data (see below). The convention is inherited from [`knaus.md`](knaus.md), where
29 of 33 baseline rows confirmed it.

## The trap the requester flagged: `Mass in running order` printed twice

**All 29 products print the `Mass in running order` row twice.** The requester's screenshot
shows the CaraHome case, where the two figures are identical; the survey found they are
*not always* identical, and the pattern is worth recording in full:

| Range | Label on row 1 | Label on row 2 | row 2 − row 1 |
|---|---|---|---|
| CaraHome | `… (kg) (Hints: H140)` | same | **0** on all 3 |
| CaraSuite EDITION [SPICY] | `… (kg) (Hints: H140)` | same | **0** on 4, **−5** on 700 DX |
| CaraCore | `… (kg) (Hints: H140)` | same | **−12** on all 3 |
| CaraCompact EDITION [PEPPER] | `… (kg)` — **no hint** | `… (kg) (Hints: H140)` | **+22** on all 3 |
| CaraBus EDITION [FIRE] | `… (kg)` — **no hint** | `… (kg) (Hints: H140)` | **−3** on all 7 |
| CaraBus GREY EDITION [FIRE] | `… (kg)` — **no hint** | `… (kg) (Hints: H140)` | **−3** on all 7 |
| X-PEDITION | `… (kg)` — **no hint** | `… (kg) (Hints: H140, H165)` | **0** |

Three things follow.

**The hint reference does not discriminate them.** `H140` is only the ±5% tolerance
footnote, so its presence on one row and not the other is a data-entry inconsistency, not a
second meaning. It was the obvious candidate and it is a dead end.

**The difference is never material.** It ranges from 0 to 22 kg, it changes sign by range,
and **both figures always sit inside each other's ±5% band** — so whichever is taken, the
exposure is rounding-scale, not a wrong vehicle. It is *not* the Knaus reading of two chassis
or drivetrain variants: nothing else on the page varies, and one chassis, one engine and one
gearbox are named.

**Decision: take the first figure, and carry both into the provenance snippet.** Three
reasons, in order of weight:

1. Document order pairs it with the `Chassis` / `Engine power` / `Gearbox` rows immediately
   above it in the same `BASIC EQUIPMENT` block, and the base vehicle those rows describe is
   what FMLV records.
2. It is the same decision [`knaus.md`](knaus.md) reached on the same company's price lists,
   and diverging between two sibling brands for no reason would be worse than either choice.
3. On the ranges where the labels differ, the *unhinted* row comes first — the row that reads
   as the plain figure precedes the one annotated with a tolerance note.

Point 3 is weak and point 2 is consistency rather than evidence, so **this remains unresolved
in the same way it is unresolved for Knaus.** The reviewer sees both numbers in the
provenance and can overrule. Unlike Knaus, FMLV's baseline offers no tie-break at all here,
because its MRO figures are placeholders.

## Berths and seats: four ceilings and one fitment figure

The documents publish six person-related counts. Only one is right for each field, and the
requester's warning is the key to both.

| Row | CaraHome 600 DKG | Meaning |
|---|---|---|
| `Beds (Hints: H141)` | 6 | **berths as standard** |
| `Max. number of beds (Hints: H142)` | 6 | berths with options |
| `Number of persons allowed in driving operation` | 6 | type-approval ceiling |
| `Automatic three-point belts, height-adjustable` | 2 | the cab's inertia-reel belts |
| `Max. belt-secured seats` | 6 | fitment ceiling |
| `Three-point belts in driving direction` | 2 | **belted seats as standard** |

**Berths → `Beds`.** The lower-figure rule, and the document labels the two ends explicitly
(`H142`: *"For some models, additional equipment must be selected in order to achieve the
maximum possible beds"*) rather than printing a range. The two differ on 12 of 29 products,
so the choice is load-bearing: CaraBus 540 MQ is `Beds 2` / `Max. number of beds 4`.

The pop-up roof corroborates it — see body type below. `Beds 2` on the 540 MQ is exactly the
vehicle without the £5,516 roof whose bed is `135 x 200`.

**Seats → `Three-point belts in driving direction`.** This is the requester's point, and the
evidence is the same article number Knaus's survey turned up. In the CaraSuite list:

```
552686-01 Two folding seats with 3-point seat belts, facing the direction of travel  50  2.534,-  - - - - o
```

`–` (not possible) on 650 MF, 650 MG, 650 MEG and 700 MEG, `o` (optional, £2,534) on 700 DX.
So Weinsberg price extra forward-facing belted seats as an option, and the 2 printed in
`Three-point belts in driving direction` is the standard fitment — the base-vehicle rule,
with the manufacturer's own `s`/`o`/`–` markings as evidence.

`Number of persons allowed in driving operation` is disqualified for the reason
[`burstner.md`](burstner.md) established and Knaus's price list states in writing: it is the
type-approval ceiling, used to compute a 75 kg-per-passenger mass. Weinsberg's own document
shows why trusting it would be wrong in *both* directions — it reads **6** on two CaraHome
layouts and **2** on X-PEDITION, where `Max. belt-secured seats` is 4.

### Two honest caveats, both weaker than the Knaus case

**`Three-point belts in driving direction` reads 2 on all 29 products.** It has no variance
whatever, which makes it indistinguishable from `Automatic three-point belts,
height-adjustable` (also 2 on all 29) on the numbers alone. Knaus's equivalent row read **4**
on two layouts and was corroborated per-layout by the options table; here the options table
corroborates the *rule* but the figure itself is a constant. That is a real reduction in
evidence.

**CaraHome publishes a lap-belt row, and Knaus did not.** `Lap seat belts against driving
direction` appears on CaraHome only, reading `2 2` — and the roster is **three** models, so
the row is short and there is no way to tell which two it belongs to (coordinates are
unrecoverable; see below). If lap-belted travel seats count as passenger seats, CaraHome
600 DKG and 650 DG hold **4**, not 2. The adapter cannot resolve it, so it does not read the
row, and both figures reach the reviewer in the provenance instead.

The consequence to expect: recording 2 proposes **4 → 2 on all 28 matched products**. That is
precisely the systematic-disagreement shape [`burstner.md`](burstner.md) says to distrust, so
it is being accepted on the documented definition rather than on the count — and the CaraHome
pair is genuinely open. Flag it to the requester rather than letting it pass as settled.

## Price: sterling, and the basis is published

`List price in GBP including 20% VAT`, from the per-range UK price list, with the basis on
the site's own footnote:

> Prices include 20% VAT. The prices stated are the manufacturer's recommended retail
> prices. … the listed prices do not include the costs for registration papers, delivery
> and transport

So it is a manufacturer's RRP including VAT and excluding delivery — not an on-the-road
price. Range £63,494 (CaraBus 540 MQ Edition FIRE) to £102,490 (X-PEDITION 600 MQ).

Record the basis, per the README's price rule: if Weinsberg ever move to an on-the-road or
ex-VAT figure, every one of the 29 products shows a price change that is not a price change.

**The `,-` suffix and the `.` separator are both live traps.** `88.995,-` is £88,995 —
strip the separator, drop the `,-`.

## Body type: derived, and the baseline agrees 34/34

The site declares the motorhome subdivision itself, in three category pages that name the
range they contain:

| Condition | `body_type` | Weinsberg's own words |
|---|---|---|
| `/camper-vans/` | `campervan_high_top` | — |
| `/motorhomes/integrated-motorhomes/` → CaraCore | `a_class` | *"the CaraCore, the fully integrated motorhome from WEINSBERG"* |
| `/motorhomes/motorhomes-with-alcove/` → CaraHome | `coach_built_over_cab_bed` | *"the CaraHome, our bestseller among alcove motorhomes"* |
| `/motorhomes/semi-integrated-motorhomes/` → CaraCompact, CaraSuite | `coach_built_low_profile` | *"The semi-integrated models from WEINSBERG"* |

**Validated against the FMLV baseline before adoption, per the standing rule: 34 of 34
current rows agree**, with no exceptions in either direction — 16 CaraBus and 1 X-Pedition as
`campervan_high_top`, 3 CaraCore as `a_class`, 4 CaraHome as `coach_built_over_cab_bed`, and
all 10 CaraCompact/CaraSuite rows as `coach_built_low_profile`.

Note this is the first adapter to use `coach_built_over_cab_bed`, and it is the alcove
category — derived from the manufacturer's own category page, not from a heuristic.

### The elevating roof: optional on four layouts, standard on none

The campervans are the interesting half, and the answer is cleaner than Knaus's because
Weinsberg **price the roof in the same document**:

```
103594-01 WEINSBERG pop-up roof KOMFORT, white    163  5.516,-  o o o - - o -
104117-01 WEINSBERG pop-up roof komfort Lava Grey 163  5.928,-  o o o - - o -
```

against the roster `540 MQ | 600 MQ | 600 ME | 600 DQ | 600 MQH | 630 ME | 630 MEG` — so it
is `o` (optional, £5,516) on four layouts and `–` (not possible) on three. **Standard on
none.** Hint `H145` adds *"If this option is selected, the vehicle height increases by
approx. 11 cm"*.

So by the base-vehicle rule every campervan is `campervan_high_top`, never the
`…_elevating_roof` variant — and this is *evidence*, not the silence-means-option default the
README falls back on. It also means the recorded height is the closed height, correctly: the
published `Height (outside)` figures are 258, 282 and 312 cm, all comfortably over the shared
`HIGH_TOP_ABOVE_MM = 2300`, and the pop-up's extra 11 cm is an option's height, not the
vehicle's.

The berth count agrees: `Bed dimensions pop-up roof (cm) 135 x 200` appears on exactly the
layouts where the roof is orderable, and those layouts' `Beds` figure excludes it.

## Parsing: reading order, a stated roster, and labels that wrap

**Coordinates are unrecoverable.** `extract_positioned_text` on the CaraHome technical-data
page returns 124 runs of which **79 report `(0, 0)`**, and every row label sits at `x = 0.0`
with the same `y` as every other label. The Rimor-style defence of reading x-positions is
unavailable, exactly as in the Knaus PDFs.

Reading order *does* preserve the columns, so the parse is made safe the same way Knaus's is:
**pin every row to the page's own stated roster** (`Technical Data 650 MF 650 MEG 700 MEG`)
and reject any row that does not yield exactly that many values, rather than slicing it.

Three concrete traps, all found while verifying:

- **Row labels wrap, and how they wrap depends on the column count.** With three columns
  `Technically maximum authorised laden mass (kg) 3.500 3.500 3.500` is one line; with
  CaraSuite's five it becomes `Technically maximum authorised laden` /
  `mass (kg) 3.500 …`. A parser anchored on a single line silently loses MTPLM on the
  five-column range only — which is what a first verification pass did. Join the label across
  lines before matching it.
- **The MRO cells wrap too**, one model's `2.930 (2.783` / `- 3.076)` split across two lines,
  so the row needs its own parser reconstructing `N.NNN (N.NNN - N.NNN)` triples. This is a
  feature as much as a hazard: three numbers per model make the roster-count check strong.
- **Short rows exist and must be dropped, not padded.** CaraHome's
  `Lap seat belts against driving direction 2 2` genuinely carries two values for three
  models. Taking a fixed count here would swallow the next row's label — the README's trap,
  live in this document.

Rows whose cells contain spaces (`Tyre size`, `Rim size`, `Bed size, rear`, `Body door`) are
**not read at all**: their cell count is meaningless, so they would defeat the very check
that protects the rest.

**Range titles wrap as well, and differ between documents.** `CaraBus EDITION [FIRE]` +
`(2027)` on two lines in one document, `CaraBus GREY EDITION` + `[FIRE] (2027)` in the other.
Join lines up to the `(2027)` marker and strip it.

## Identity: FMLV puts the edition in the model, and the range name loses it

The single most valuable thing `fmlv fetch-export` answered, per the README's rule. The
price lists' range titles are **not** what FMLV calls these vehicles:

| Price-list range | Layout | FMLV `manufacturer_range` | FMLV `model` |
|---|---|---|---|
| `CaraCore` | 650 MF | `CaraCore` | `650 MF` |
| `CaraHome` | 600 DKG | `CaraHome` | `600 DKG` |
| `CaraSuite EDITION [SPICY]` | 650 MF | `CaraSuite` | `650 MF` |
| `CaraCompact EDITION [PEPPER]` | 600 MF | `CaraCompact` | `600 MF Edition PEPPER` |
| `CaraBus EDITION [FIRE]` | 540 MQ | `CaraBus` | `540 MQ Edition FIRE` |
| `CaraBus GREY EDITION [FIRE]` | 540 MQ | `CaraBus` | `540 MQ GREY Edition FIRE` |
| `X-PEDITION` | 600 MQ | `X-Pedition` | `600 MQ` |

Two things to notice, and neither is guessable from the site:

- **The edition name moves from the range to the model**, and the bracket-and-caps styling is
  dropped: `EDITION [PEPPER]` becomes `Edition PEPPER`. The `GREY` sits *before* `Edition`.
- **FMLV is inconsistent about it**, and the adapter must be inconsistent in the same way.
  PEPPER and FIRE are suffixed onto the model; **SPICY is not** — FMLV's five CaraSuite rows
  are bare `650 MF`, `650 MG`, `650 MEG`, `700 MEG`, `700 DX`, matching the SPICY roster
  exactly. Emitting `650 MF Edition SPICY` for consistency's sake would propose a rename on
  all five.

Emitting FMLV's own strings gives **28 matches at exactly 1.000** and **no fuzzy match at
all**, so `MATCH_THRESHOLD` is not needed and must not be declared — there is no bad pair to
separate, and the score distribution has nothing to tune.

Both halves of the identity get provenance, per the README's rule that a proposed rename must
move both columns together. Nothing is being renamed on this first run, but the rule holds
regardless: `model` is compared only where it has provenance, so an unregistered `model` is
silently invisible.

## What changed since FMLV was last updated

The 34 current-year baseline rows were matched against the 29 collected products using the
repo's own `diff.matching.match_products`, not by hand: **28 matched, 1 new, 6 disappeared.**

### New

- **`CaraCompact` `580 MEG Edition PEPPER`** — a third PEPPER layout, £69,695, in both the UK
  and European MY2027 lists. It scores 0.571 against `640 MEG MB Edition PEPPER` and 0.667
  against `600 MEG Edition PEPPER`, both above `DEFAULT_THRESHOLD` — but greedy best-first
  assignment claims every 1.000 pair before either is reached, so it correctly falls through
  as new. Worth knowing that the margin exists.

### Disappeared, and all six confirmed by a second source

The European euro lists are the superset, so an absence from *both* the UK and the European
document is a real discontinuation rather than a UK-market subset. That is the reconciliation
the roster rule asks for:

| Baseline row | Verdict |
|---|---|
| 8617 `CaraHome / 550 MG` | **Genuinely discontinued.** `550 MG` appears **zero times** in the European motorhome price list. |
| 5678 `CaraCompact / 640 MEG MB Edition PEPPER` | **Genuinely discontinued.** |
| 8611 `CaraCompact MB / 640 MEG Edition PEPPER` | **Genuinely discontinued** — and a duplicate of 5678 under a second range spelling. |
| 8612 `CaraCompact Suite MB / 640 MEG Edition PEPPER` | **Genuinely discontinued** — a third spelling of the same vehicle. |
| 5674 `CaraBus / 540 MQ` | **UK-range change, not a discontinuation.** |
| 5676 `CaraBus / 600 DQ` | **UK-range change, not a discontinuation.** |

**The whole Mercedes CaraCompact is gone for MY2027.** `640 MEG`, `MERCEDES` and `Mercedes`
each appear **zero times** in the European motorhome price list, and
`/en-uk/motorhomes/edition-pepper-mb/` 404s. The German sitemap still lists
`wohnmobile/edition-pepper-mb/grundrisse/640-meg-mb/` — stale pages the sitemap has not
dropped, which is why the price list rather than the sitemap is the authority on what is
*current*. Note FMLV holds this one vehicle three times over, under three different range
spellings; all three should go, but that is a judgement for the requester, not the adapter.

**The two plain CaraBus rows are a softer case and should be reported as such.** Plain
`CaraBus` and `CaraBus GREY` both still exist in Europe with the full seven-layout roster;
the UK simply no longer lists them, selling only the `EDITION [FIRE]` versions. FMLV itself
distinguishes the two — it holds `540 MQ` and `540 MQ Edition FIRE` as separate 2026 rows —
so reporting the plain pair as gone from the UK range is right. It is a range withdrawal from
this market, not a vehicle leaving production.

## The baseline is placeholder data, and this run will propose almost every figure

Flagged prominently because it inverts [`burstner.md`](burstner.md)'s warning, and a reviewer
seeing 28 products all change at once needs to know which situation they are in.

FMLV's 34 current rows are **demonstrably self-inconsistent**. Fourteen of the sixteen
CaraBus rows carry byte-identical figures — `mro 2651`, `mtplm 3300`, `payload 649`,
`length 5410`, `width 2050`, `height 2580`, `£58,751` — which are the 540 MQ's numbers copied
onto every layout including the 636 cm 630 ME and the 312 cm-tall 600 MQH. All four CaraHome
rows carry `2935 / 3500 / 565 / 6750 / 2200 / 2800`, which are **CaraCompact's** figures, not
CaraHome's; so does X-Pedition, a Mercedes van. All five CaraSuite rows are identical to each
other.

So the usual rule — *several products disagreeing the same way is a signal about the parse* —
does not apply here, because the disagreement is **provable from the baseline alone**: a
6.36 m vehicle and a 5.41 m vehicle cannot both be 5410 mm long. The bulk change is the
adapter working.

The exception is **seats**, where the baseline's `4` is uniform and *plausible*, and the
proposed `2` rests on the documented definition rather than on the baseline being wrong. Keep
those two cases apart when reviewing.

## Model year

MY2027 throughout, on both the UK and European documents. The price lists are dated in their
filenames (`05-08` — 5 August 2026) and every price-list range title carries `(2027)`. The
Caravan Salon in Düsseldorf opened at the end of August 2026, so per the README's model-year
rule **re-check at the end of September**, when revisions often arrive — and specifically
re-check whether the UK picks up the plain `CaraBus` / `CaraCompact` / `CaraSuite` ranges
Europe already has.

## Open questions

1. **Which `Mass in running order` is the base vehicle's?** Unresolved, as for Knaus. The
   adapter takes the first and shows both. Nothing in either document, and nothing in FMLV's
   own (placeholder) baseline, breaks the tie.
2. **Does CaraHome hold 2 or 4 belted travel seats on 600 DKG and 650 DG?** The lap-belt row
   says `2 2` for three models and cannot be attributed. Needs the requester or Weinsberg.
3. **Should FMLV's three duplicate Mercedes CaraCompact rows all be retired?** They are one
   vehicle held three times; the adapter reports three disappearances because that is what
   the baseline contains.
4. **X-PEDITION's specs come from the European euro list**, the only document carrying them.
   If Weinsberg publish a UK X-PEDITION price list, switch to it — and note the microsite
   disagrees with both on length and height.

## The habitation pack — floorplans, and the fields the adapter never collects

Built 3 September 2026, after the adapter, as the same post-build step Knaus and Dethleffs
got. Four outputs, all under `data/` and none tracked — they are large and regenerable:

| File | What it is |
|---|---|
| `weinsberg-2027-habitation-layouts.csv` | the data, 29 rows × 21 columns — **the only hand-maintained one** |
| `weinsberg-2027-floorplans.html` | the reference page, published as an Artifact |
| `weinsberg-2027-floorplans.pdf` | that page printed to A4, 59 pages |
| `weinsberg-2027-floorplans.docx` | a Word version, for annotating |

**Everything downstream is generated from the CSV**, so the four cannot drift: edit the CSV
and rebuild. The numeric columns are taken from `weinsberg.collect()` rather than retyped,
so the pack and the review queue cannot disagree about a weight or a price. The HTML carries
a print stylesheet, so `Ctrl+P` from the published Artifact gives the same document as the
generated PDF — on paper the card goes single column so the drawing gets the full text width.

The Word build needs `python-docx`, which is **not** a project dependency and should not
become one — run it isolated, `uv run --with python-docx --no-project python <script>`. Two
things it needs that the HTML build does not: the drawings re-encoded as plain JPEG, because
python-docx raises `UnrecognizedImageError` on Weinsberg's own PNGs, and `Arial Narrow`
rather than a webfont.

These cover the fields flagged out of scope in `config/field_guide_motorhome.csv` — bed
types, sleeping area, bathroom layout, kitchen location, lounge, rear garage, fridge and
microwave. `collect()` has no business with any of it; this is human data-entry support.

### Finding the floorplans: `layout-plans`, and the drawing comes *before* its caption

**The UK layouts page is `/layout-plans/`, not `/layouts/`.** The survey had already
concluded there was no per-layout page after `/layouts/` and `/grundrisse/` both 404'd; the
real slug was sitting in a link on the range page all along, which is the README's "follow
the link a customer sees" rule catching a wrong conclusion. Each of the four motorhome
ranges has one, carrying a card per layout with the drawing, the price, the length, and a
**Bed variants** line.

The two campervan ranges have no `layout-plans` page. Their current MY2027 drawings are on
`/en-uk/the-brand/new-products-2027/carabus-{grey-,}edition-fire/`, and X-PEDITION's are on
its own microsite. Three different conventions for one brand.

Three traps, all of which put a drawing on the wrong vehicle while looking perfectly fine:

- **The image precedes its heading.** Verified by dumping byte offsets:
  `…grundriss-650mf-overview.png` at 24331, then `CaraCore 650 MF` at 24736. A window
  running *forwards* from each heading therefore collects the **next** layout's plan, which
  is an off-by-one across the whole range with no visible symptom.
- **A layout code can be a prefix of another.** `600 MQ` is a prefix of `600 MQH`, so a
  substring filename test hands the 258 cm 600 MQ the 312 cm high-roof MQH's drawing — and
  passes its own check. The match has to be delimited (`[-_]600mq[-_.]`).
- **A teaser card sits above the real ones** on both campervan pages, so the first heading
  on the page is not a layout card at all.

The pairing that works reads the **filename first** where a drawing is filed under the
layout's own code, and falls back to position otherwise. Exactly one layout needs the
fallback: **CaraSuite 700 MEG**, whose drawing is still filed under last season's `700me`.

### Weinsberg serve one layout the wrong drawing, and only the small one is right

`edition-pepper/layout/600meg/` serves the **580 MEG's** plan as both its `-tag` and its
`-nacht` full-size asset. Only the 600 MEG's 600×220 `-overview` is its own. Since the
motorhome `-overview` drawings are too small to read a washroom from, the build upgrades
each one to its `-tag` — and taking the bigger file on faith puts a 638 cm vehicle's plan
on a 675 cm one.

So the upgrade is **verified, not trusted**: it compares the *aspect ratio of the drawn
content* before and after, and rejects a replacement more than 2% out. Aspect tracks length
here — 2.151 for the 638 cm 580 MEG against 2.285 for the 675 cm 600 MEG, a 6.2% gap
matching 675/638 — so the swap fails immediately and the correct small drawing is kept, with
the reason carried into that row's notes as a flag. Every honest upgrade measured under 0.2%
out. **Any manufacturer whose drawings come in more than one size needs the same check**; a
mis-filed asset is invisible to a filename test and to the eye.

### Reading a drawing: what was safe to state

**Never nearside/offside.** Weinsberg's renders are left-hand drive and UK vehicles are not.
Side, rear and corner are safe; left and right flip. The page says so in its own header.

**The layout code is a third, independent source, and it is reliable.** Weinsberg's codes
are descriptive German abbreviations — `E` Einzelbetten (single beds), `F` französisches
Bett (French bed), `Q` Querbett (transverse), `D` Doppelbett (double), `K` Kinder
(children's bunks), `G` Garage, `H` Hochdach (high roof). On all 29 layouts the code, the
`Bed size, rear` dimensions and the drawing agree with each other.

**Which is what exposed a real error in Weinsberg's price list.** The `Single bed` and
`Transverse bed` marker rows are **swapped between CaraHome 650 DG and 650 MEG**: the
document marks the 650 DG "Single bed" where its `210 x 141/135` dimension, its drawing and
its `D` code all say transverse double, and marks the 650 MEG "Transverse bed" where its
`190 x 87; 201 x 87`, its drawing and its `E` code all say twin singles. Three sources
against one. Recorded from the drawing, and flagged on both rows.

**`***` on a drawing is the freezer star rating.** It appears on the fridge cabinet of every
one of the 29 plans, which is a second source for `fridge_freezer` independent of the
`Refrigerator (ltr.)` row.

**Weinsberg publish no "island bed" marker row.** CaraSuite 700 DX is marked
`Queen-size bed`, and its drawing shows a 196 x 162 double set clear of the rear wall with
walk-round space at the foot and a wardrobe in each rear corner. That is `island_bed`.

**A published bed size is not a standard bed.** Every CaraSuite layout prints a
`Bed size, lifting bed` figure, but `Beds` excludes it (3 against a `Max. number of beds`
of 5), so the lifting bed is an option and is left out of the bed types per the
base-vehicle rule. On CaraCore and on the CaraBus 600 DQ/600 MQH/630 ME the same bed *is*
counted in `Beds`, so there it is standard. Read the two rows together, not the size.

### The rear garage, and the one row to check

**All 14 motorhomes: `yes`.** Every motorhome price list makes
`Garage door <W> x <H> cm, left/right` standard with published opening dimensions, which is
precisely the external-hatch test the requester set for Dethleffs on 2 September 2026.
Standard load capacity 150 kg, 250 kg a £1,165 option.

**Twelve of the fifteen campervans: `no`.** Their only rear-storage row is
`552964-10 Large variable storage space in the rear`, standard on all seven layouts of each
range with hint `H181 Garage height 135 cm`. No `Garage door` row exists for the campervans
at all — no external hatch, no published opening. Under-bed space loaded through the rear
doors, which is the requester's Dethleffs `no`.

**The two 630 MEGs are recorded `yes` and flagged.** The 630 MEG is the `[OUTLAW]`:
Weinsberg's page calls it a *"separate rear garage"* with *"room for two motorcycles or one
quad bike"* and a *"gas-tight door"* from the living area, the drawing has a motorcycle in
it, and the price list adds two options unique to this layout —
`102785 Checker plate for garage floor` and `103460 Low garage height` — plus airline rails
and lashing eyes. It is still loaded through the rear doors rather than a side hatch, so the
**letter** of the Dethleffs test says no while its **reason** — *is this just the space
under the bed?* — says yes. Recorded `yes` on the reason, and put to the requester.

### Microwave: a `no`, but a weaker one than Dethleffs'

The word appears **zero times** in every Weinsberg document read: all six UK price lists
and both MY2027 catalogues. But **no oven is listed either** — the only `oven`/`grill` hits
in any of them are radiator grilles — so unlike Dethleffs, whose PDFs price three different
ovens and no microwave, these documents may simply not enumerate cooking appliances beyond
the hob. Recorded `no`, with that caveat on every row rather than hidden here.

Heating is a `TRUMA Combi 4` or `Combi 6` on every layout, so blown air throughout. Not a
column in the CSV, but stated in the notes.

### Two things the layout data revealed that the adapter's own diff would not

**Every CaraBus GREY layout shares its drawing with the plain FIRE equivalent** — 7 pairs,
byte-identical. That is legitimate: GREY is a colour and trim edition on the same seven
habitation layouts, which is also why the two price lists carry identical rosters and
identical prices and differ only by a few kilograms of MRO. 22 distinct drawings cover 29
layouts.

**Every kitchen in the range is a side kitchen** and every lounge is a front lounge, so
`fmlv_kitchen_location` and `fmlv_lounge_location` do not discriminate for Weinsberg any
more than they do for Dethleffs. The washroom does: `separate_shower_toilet` on CaraCore,
CaraHome and CaraSuite, `side_shower_toilet` on CaraCompact, the CaraBus and X-PEDITION.
