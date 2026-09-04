# Murvi — site survey and adapter notes

**ADAPTER WRITTEN 2026-09-02.** `src/adapters/murvi.py`, ten products from one price list
PDF. Runs #1 and #2 are recorded in [First runs](#first-runs--2-september-2026-runs-1-and-2).

**Read [The identity problem](#the-identity-problem-range--model-is-not-unique) before
touching this adapter.** `manufacturer_range` + `model` does not uniquely identify a Murvi
product, and the consequence is not cosmetic: a run covering both base vehicles at once
writes one chassis's weights and price onto the other chassis's `product_id`. The adapter
is therefore built to be run **one chassis at a time**, and the registry row is `paused` so
a scheduled sweep cannot do the unsafe thing on its own.

Murvi Motorcaravans Limited, 4 East Way, Lee Mill Industrial Estate, Ivybridge, Devon
PL21 9GE. A small independent British converter, trading since 1980, building panel-van
conversions on Fiat Ducato and Ford Transit. `manufacturer_id` 181, `NCCApproved` blank in
`resources/manufacturers-full-list.csv`.

Surveyed 2 September 2026.

## What the requester brought to the survey

Four things, all of which proved correct and two of which saved real time:

- **`https://www.murvi.co.uk/` is the site.** There is no separate UK site — Murvi are a UK
  manufacturer selling in the UK, so `uk_site_url` stays blank.
- **"Don't include pre-owned Murvi."** Acted on, and it matters more than it sounds: 20 of
  the site's 47 pages are individual used, ex-demonstrator, "Fast Track" and sold vehicles,
  which is **more pages than the new range has**. A crawler taking every page mentioning
  "Murvi Morello" would collect a used 2019 Mercedes conversion as a current product. The
  roster is taken from the navigation, not from a page sweep. See
  [The roster](#the-roster-ten-products-and-twenty-pages-of-noise).
- **"They have a price list listed for Feb 2026."** Correct, current, and it is the source.
- **"They also have a brochure for the new murvi range … I think a lot of the brochures are
  out of date so it's worth checking this in file names and titles."** This was the single
  most valuable thing brought to the survey, and it was right. The brochure is **four years
  out of date**, and the trap is exactly where it was predicted to be — in the titles. See
  [The brochure is the near-miss](#the-brochure-is-the-near-miss-and-the-page-titles-lie).
- **"The single bed and disabled versions are actually options not separate model types like
  the pimento, morello etc."** Correct, and Murvi's own words confirm it — see
  [Single beds and disabled adaptions](#single-beds-and-disabled-adaptions-are-options-not-products).

The NCC supplier dropdown label is **`Murvi`**, read off the dropdown by the requester and
since confirmed by a successful `fmlv fetch-export "Murvi"`.

## Where the data lives: one price list PDF, one model per page

`https://www.murvi.co.uk/?page_id=1968` ("PRICE LIST") links exactly one PDF:

```
https://www.murvi.co.uk/wp-content/uploads/2026/02/Murvi-price-list-February-2026.pdf
```

20 pages, 414 KB, text extracts cleanly (`is_empty()` false, ~5–6.6 K chars per page). It
carries **every one of the 13 in-scope fields** except MRO, which is derivable. Verified by
fetching it, not inferred.

**Attribution is free**, which is what the question at the top of `README.md` is really
asking. Each of the ten products gets a **pair of whole pages** — a specification page and
an options page — with the model named in a running header (` Ford Murvi Pimento`). There
are no columns and no side-by-side models anywhere in the document, so Rimor's
unattributable-spans problem cannot arise and none of the column-alignment defences are
needed. This is Auto-Trail's best case, and the parsing risk moves entirely to *which label
is this?*

A real spec block, page 1, quoted verbatim:

```
 Ford Murvi Pimento
Dimensions
Overall length  5.531M (18'1")
Overall height  2.580M (8' 6")
Overall width 2.059M (6' 9") Mir folded 2.094M (6'10")
Payload  600 K gs
PIMENTO  including 20% VAT £77,290.00
as above  excluding VAT £64,475.00
MURVI Pimento motorcaravan based on the NEW Ford Transit
35 Leader (3,500kg GVW) MWB L2H2 High Roof van in White
```

Note `600 K gs` and `Mir f olded` — pypdf splits words mid-token on this document, so
patterns must tolerate internal whitespace (`K\s*gs`, `f\s*olded`). This is cosmetic, not a
column problem.

### One fetch per run, and rediscover the link

Two fetches: the price-list page, then the PDF it links. **Rediscover the PDF from
`?page_id=1968` every run and never hardcode the February 2026 URL** — the media library
holds **18 superseded price lists** going back to 2021, all still live, all named to the
same pattern:

```
Murvi-price-list-February-2026.pdf   <- current
Murvi-price-list-October-2025.pdf
Murvi-price-list-August-2025.pdf
Murvi-price-list-June-2025.pdf
Murvi-price-list-March-2025.pdf      <- and "March 2025 (1)" and "March + 2025"
...back to Murvi-price-list-June-2021.pdf
```

This is Swift's lesson with the archive already in place: a pattern loose enough to match
`Murvi-price-list-.*\.pdf` matches all nineteen, and the newest by *filename month* is not
reliably the newest either — "Murvi price list June 2025" was uploaded on 2025-07-06, and
three separate March 2025 lists exist. Take the single link off the price-list page, which
is what a customer clicks, and treat the filename as a label rather than as a version.

The page-linked document and the newest upload agree today (both February 2026), so there is
no Etrusco-style year conflict to resolve — but the check is cheap and the archive is
unusually deep, so make it.

## The brochure is the near-miss, and the page titles lie

The requester's instinct to check titles was exactly right, and it is worth recording
precisely how the trap is laid, because it runs the Etrusco rule in reverse.

| Page title | PDF it links | Actual vintage |
|---|---|---|
| **"Murvi Brochure"** (`?page_id=2070`) | `JAN_22_MURVI_BROCHURE.pdf` | **January 2022** |
| **"NEW MURVI"** (`?page_id=1144`) | `Murvi-2018-Brochure-1.pdf` | **2018** |

So the page titled **NEW** links the **eight-year-old** brochure, and the page presented as
*the* Murvi brochure is four years stale. Etrusco's lesson was "establish a document's year
from the page that links it, not from its filename". **Here the filename is the honest half
and the page title is the misleading one** — which does not overturn the Etrusco rule so
much as show what it is really for: the two sources of a document's date must be
*reconciled*, and whichever one you trust by default, you have to look at both. A survey
that trusted the "NEW MURVI" title would have built on a 2018 document.

Neither brochure is a usable source in any case, and this is verified rather than assumed.
The 2022 brochure is 8 pages, 3.8 MB, and glossy only — across the whole document:

| Pattern | Hits |
|---|---|
| `Payload` | **0** |
| `Overall length` / `Overall width` / `Overall height` | **0** |
| `GVW` | **0** |
| `Price` / `including 20% VAT` | **0** |

Zero weights, zero dimensions, zero prices. It is not even a cross-check. `brochure_url` is
populated with it because it is the only brochure Murvi publish and the registry should
record what exists, but nothing should ever read it.

**There is no current brochure.** Checked three ways rather than concluded from one: the WP
media library holds 35 PDFs and the newest brochure among them is the Jan 2022 file;
`/wp/v2/search` for `brochure` returns 3 hits and for `catalogue` returns **0**; and
`/wp/v2/types` shows no custom post type that could hold an unlinked one. There is no
sitemap and no `robots.txt` on this site, so the sitemap-orphan check that saved the Elddis
survey is unavailable — the REST API is the substitute, and on WordPress it is the better
tool anyway (Moto-Trek's lesson: try `/wp/v2/media?mime_type=application/pdf` first).

Murvi's permalinks are plain `?page_id=N`, so **page IDs are the stable identifiers** on
this site. There are no slugs to read meaning from, and the slugs that exist are unreliable
— `Morello XL` lives at slug `morello` while `Morello` lives at `morello-2`, and `Piccolo`
is at the misspelled `picollo`. Key on page ID.

## The website has no numbers at all, so the usual rule does not apply

All seven model pages are marketing prose with a photo gallery shortcode. Not one publishes
a weight, a dimension, a price, a berth count or a seat count. Bed sizes appear in **inches**
(`75” x 54”`), which is the only measurement on any of them.

Every model page ends with the same sentence, and it settles the source question in Murvi's
own words:

> For further information please click on "Price List" as this includes a fully detailed
> breakdown of the specification, technical information and the options available for each
> Murvi model.

So "the website overrules the PDF" has nothing to overrule here — the website *points at*
the PDF, for exactly the data we want. This is not the Elddis exception (where the site was
provably wrong and the PDF right); it is the simpler case where only one source carries the
numbers.

It is worth knowing that the model pages are **also stale**, so they cannot serve as a
tiebreak even where they say something relevant. Six of the seven were last modified in
2021, and the Morello page still advertises a chassis Murvi no longer sell:

> The Morello is based on the Fiat Ducato LWB, Ford Transit L3 and **Mercedes Sprinter MWB**.

There is no Mercedes anywhere in the February 2026 price list, nor in the October 2025 one.
Do not read base vehicles off the model pages.

Where the pages *do* agree with the price list they agree exactly, which is worth one
sentence as a sanity check: the Morello XL page says "the Fiat Ducato XLB (**6.363M**) and
the Ford Transit L4 (**6.7m** long)", against the price list's 6.363M and 6.704M. Morocco's
"currently only based on the Fiat Ducato LWB" matches the price list offering no Ford
Morocco. Useful corroboration, too thin and too stale to be a self-check.

## The self-check

MRO is **not published anywhere**, so the usual `payload == MTPLM − MRO` is unavailable — MRO
has to be *derived* as `MTPLM − payload`, which makes that arithmetic true by construction
and worthless as a check. Two genuine redundancies replace it, and between them every one of
the ten products is covered.

### 1. Every price is printed twice, and it catches a real error

Each model's price appears on both of its two pages — once on the specification page and
once on the options page — inclusive and exclusive of VAT each time. Four printed figures
per model, which must agree pairwise.

They agree on nine products and **disagree on Fiat Murvi Morello XL**:

```
page 19 (spec)     MORELLO XL  including 20% VAT £79,956.00 / as above excluding VAT £66,699.00
page 20 (options)  MORELLO XL  including 20% VAT £78,596.00 / as above excluding VAT £66,699.00
```

The ex-VAT figure is identical on both pages; the VAT-inclusive figure differs by £1,360.
**£79,956 is the correct one**, on four independent grounds:

- Fiat Morocco XL prints **£79,956** on *both* of its pages, and shares Morello XL's ex-VAT
  £66,699 exactly.
- The two are the same base van (Fiat Ducato Maxi XLWB 35, L4H2), the same dimensions
  (6.363/2.565/2.050) and the same payload (400 kg) — they are priced identically by design.
- FMLV already holds both at the same `rrp_pounds` (£77,574 each).
- Three of the four printings say £79,956.

**This error is not new.** The October 2025 price list contains the identical pair of figures
(£79,956 on the spec page, £78,596 on the options page), so it is a long-standing typo in
Murvi's document rather than a fresh slip, and it will not fix itself.

**Decision, requester, 2 September 2026: take £79,956 and narrate it every run.**
`_KNOWN_PRICE_TYPO` implements it, and two properties of that implementation matter:

- It **warns rather than dropping the product**, which departs from the usual "a product
  failing the self-check is dropped" rule and does so deliberately. The failure is one bad
  cell on a page whose weights and dimensions are sound and match FMLV exactly; dropping the
  vehicle would lose ten good figures to save one, and the missing-data rule's whole point is
  that a visible gap beats stale data — not that a good figure should be discarded beside a
  bad one.
- It is **keyed on the exact pair of figures**, not on the model. The day Murvi correct
  either page, or a different pair starts disagreeing, the override stops applying and the
  run raises a `WARNING: … this is a NEW disagreement` instead of silently reusing a decision
  made about a different discrepancy. `test_a_new_price_disagreement_is_warned_about_not_silently_resolved`
  is the guard.

Note the VAT arithmetic itself is **not** a usable check. `exc × 1.2` misses `inc` by a
consistent £80–£84 on all ten products (Ford Pimento: 64,475 × 1.2 = 77,370 against a printed
77,290), and the discrepancy is not a constant, so it cannot be a single non-VATable line
item. Do not reconcile on it and do not derive one price from the other; read both as printed.

### 2. Length and height are determined by the base van's body code

The document names the donor van's body code in prose for all ten products, and that code
fixes the exterior dimensions. Group the products by `(make, body code)` and length and
height must be **byte-identical within each group**:

| Make | Body code | Models | Length | Height |
|---|---|---|---|---|
| Ford | L2H2 (MWB) | Pimento | 5531 | 2580 |
| Ford | L3H2 (LWB) | Morello, **Pimento XL** | 5981 | 2580 |
| Ford | L4H3 (LWB) | Morello XL | 6704 | 2846 |
| Fiat | L2H2 (MWB) | Pimento | 5413 | 2540 |
| Fiat | L3H2 (LWB) | Morello, Pimento XL, **Morocco** | 5998 | 2540 |
| Fiat | L4H2 (Maxi XLWB) | Morocco XL, **Morello XL** | 6363 | 2565 |

Three of the six groups have more than one member and **all three agree**, so 7 of 10
products are cross-checked against a sibling on the same donor van. Any page mis-attribution
breaks a group immediately.

**The two makes write the code differently**, which is the Elddis label trap in miniature —
one pattern will not match both:

```
Ford:  35 Leader (3,500kg GVW) MWB L2H2 High Roof van in White      <- code before "High Roof"
Fiat:  Ducato 35 (3,500kg GVW) MWB High Roof van (L2H2) with        <- code parenthesised after
```

`MTPLM` comes from the same sentence (`(3,500kg GVW)`, or `(4,000kg GVW)` for the Ford
Morello XL alone), so a product whose GVW cannot be read is a product whose whole spec block
failed to parse.

### 3. And the whole parse is confirmed against FMLV, 10/10

Not a parse check — the baseline is what we propose changes *to* — but worth recording as
evidence that the reading above is right. **All ten length/width/height triples read off the
February 2026 price list match FMLV's stored values exactly**, on all three dimensions, for
all ten products.

That includes the width rule: FMLV holds **2059** for every Ford, which is the body width,
not the 2094 "Mir folded" figure printed beside it. `README.md`'s "exclude wing/door mirrors"
rule is therefore confirmed by the customer's own data — and note this document is the first
where the mirrors-folded figure is the *larger* of the two, so "take the narrower" and
"exclude the mirrors" happen to agree, but only the second is the reason.

## The identity problem: range + model is not unique

**This is the blocking issue, and it needs a human decision before any adapter is written.**

FMLV splits Murvi's products **by base vehicle**, and stores the chassis in
`base_vehicle_manufacturer` while leaving `manufacturer_range` and `model` identical between
a layout's Ford and Fiat versions. The full export, 11 rows:

| product_id | range | model | chassis | year | archived | rrp |
|---|---|---|---|---|---|---|
| 7126 | Pimento | Pimento | Ford | 2026 | **Yes** | 77290 |
| 7127 | Morello | Morello | Ford | 2026 | **Yes** | 78598 |
| 7128 | Pimento | XL | **Ford** | 2026 | No | 78598 |
| 7129 | Morello | XL | **Ford** | 2026 | No | 83963 |
| 7130 | Pimento | XL | **Fiat** | 2026 | No | 75068 |
| 7131 | Morocco | Morocco | Fiat | 2026 | No | 75068 |
| 7132 | Morello | Morello | Fiat | 2026 | No | 75608 |
| 7133 | Pimento | Pimento | Fiat | 2026 | No | 73103 |
| 7134 | Morocco | XL | Fiat | 2026 | No | 77574 |
| 7135 | Morello | XL | **Fiat** | 2026 | No | 77574 |
| 7136 | Piccolo | Piccolo | Fiat | **2024** | No | 69540 |

So the identity split is **range = family** (Pimento / Morello / Morocco / Piccolo) and
**model = `XL` or the family name repeated**. Note `model` is bare `XL`, not `Pimento XL`.

`(Pimento, XL)` names **two** live 2026 products, 7128 on a Ford and 7130 on a Fiat. So does
`(Morello, XL)` — 7129 Ford and 7135 Fiat. And `cli._dedupe_baseline` collapses rows sharing
`(manufacturer_range, model)` to the newest year. Both twins are 2026, so the tie breaks on
export order and **the Fiat is silently discarded**. Verified by running the repo's own
filters over the real export:

```
all rows                                  -> 11
after archived + model-year filter        ->  8
after _dedupe_baseline (what diff sees)   ->  6   <- 7130 and 7135 are gone
```

Two live, non-archived, current-model-year products vanish from the baseline before the diff
begins. Everything downstream then goes wrong in the way that is hardest to see:

- Ten collected products meet six baseline rows, so **four are reported new** — including
  duplicates of 7130 and 7135, which FMLV already holds. An upload would create them twice.
- `diff/matching.py` scores on the range-plus-model word bag only, so a collected Ford
  Pimento XL and a collected Fiat Pimento XL **both score 1.000** against the one surviving
  `(Pimento, XL)` row. The chassis is invisible to the matcher, so nothing prefers the right
  one, and a Fiat's weights and price can be written onto a Ford row.
- `MATCH_THRESHOLD` cannot help. This is not two vehicles scoring too close — it is two
  vehicles with **identical** identities. No threshold separates 1.000 from 1.000.

This is a genuinely new shape. Every previous brand's problems were *renames* (Wingamm,
Bailey, Etrusco) or *near-misses* (Knaus, Etrusco); Murvi is the first where FMLV holds two
distinct current products under one identity on purpose, because for a van converter the
donor chassis *is* the product distinction — different length, height, payload and price.

### How it was resolved: chassis in the model, and one chassis per run

Two decisions from the requester on 2 September 2026, and they are **Murvi-specific by
explicit instruction** — "please include both models as separate entities, but add the
chassis name into the model name … Again don't make this a general rule for going forward"
and "if something like this comes up again please raise it with us again."

So the adapter emits the chassis as part of `model`, leaving `manufacturer_range` untouched:

| Family | Chassis | range | model | renders as |
|---|---|---|---|---|
| Pimento | Ford | `Pimento` | `Ford` | Murvi Pimento Ford |
| Pimento XL | Fiat | `Pimento` | `XL Fiat` | Murvi Pimento XL Fiat |
| Morocco XL | Fiat | `Morocco` | `XL Fiat` | Murvi Morocco XL Fiat |

A layout whose name *is* its range carries the chassis alone rather than repeating itself,
which also drops FMLV's existing `Pimento` + `Pimento` doubling. The requester will amend
these names before uploading, and future runs will still see chassis-free names in FMLV —
which is fine, and the next section says why.

**But renaming on the adapter's side does not fix the matching, and this is the part worth
understanding.** Measured with the real `match_products` against the real export:

| What the adapter emits | Correct | Landed on the **wrong** row | Wrongly "new" |
|---|---|---|---|
| FMLV's current names (no chassis) | 4 | **2** | 4 |
| `Pimento XL Ford` etc. | 4 | **2** | 4 |

Identical, because **the baseline rows contain neither "Ford" nor "Fiat"** — the chassis
lives in a column the matcher never reads, so adding it to the scraped side lowers every
score uniformly (1.000 → 0.667) and distinguishes nothing. The four failures are caused
upstream, by rows that are already gone: 7130 and 7135 deduped away, 7126 and 7127 archived.

**What does fix it is scoping the run to one chassis**, which is why `DEFAULT_RANGES` names
base vehicles rather than FMLV ranges and why `baseline_in_scope` filters on
`base_vehicle_manufacturer`. Within a single chassis no two Murvi baseline rows share a
range and model, so `_dedupe_baseline` collapses nothing and the greedy matcher has exactly
one candidate per product:

| Run | Correct | Wrong row | New |
|---|---|---|---|
| `--range Fiat` | **6 / 6** | 0 | 0 |
| `--range Ford` | **2 / 2** | 0 | 2 — the two archived rows, which is honest |
| both at once | 4 | **2** | 4 |

This is the same mechanism Adria and Wingamm use, for the same reason: a `--range` selector
that is not an FMLV range needs the hook, or the default scopes the run to zero rows.

**A combined run remains unsafe and always will be**, so two guards stand against it:
`collect` emits a prominent warning naming 7130 and 7135 when more than one chassis is
requested, and the registry row is **`status=paused`** so scheduled sweeps skip it while it
stays manually runnable. Run `--range Fiat` and `--range Ford` separately, every time.

For the record, the alternative that needs no pipeline change *and* no per-chassis
discipline is to put the chassis into FMLV's own `model` by hand — simulated, and it gives
**10/10 at 1.000, nothing new, nothing disappeared**. It was not chosen because the
requester prefers to amend names at upload time, and per-chassis runs achieve the same
safety without twelve manual edits.

### One real data error already visible in the baseline

Independent of the identity question, `mtplm − mro == payload` holds on **10 of the 11**
baseline rows. The exception is 7133, Fiat Pimento:

```
7133  Pimento Pimento Fiat : mtplm 3500 - mro 3000 = 500  !=  payload 600
```

The February 2026 price list gives Fiat Pimento a 3,500 kg GVW and a 600 kg payload, so its
MRO is **2900** and FMLV's 3000 is wrong. A run will propose `mro_kilograms 3000 → 2900`.
That is the adapter working, and it is the same arithmetic FMLV's other ten rows satisfy.

## Price basis: including 20% VAT, confirmed on 4/4 Ford rows

The document prints both figures explicitly (`including 20% VAT` / `as above excluding VAT`),
so unusually the basis needs no inference. **FMLV holds the VAT-inclusive figure**, confirmed
exactly on all four Ford products:

| Product | Price list inc VAT | FMLV `rrp_pounds` |
|---|---|---|
| Ford Pimento | £77,290 | 77290 ✓ |
| Ford Morello | £78,598 | 78598 ✓ |
| Ford Pimento XL | £78,598 | 78598 ✓ |
| Ford Morello XL | £83,963 | 83963 ✓ |

The six **Fiat** rows are all stale, by £1,832 to £2,567:

| Product | Price list inc VAT | FMLV holds | Change a run would propose |
|---|---|---|---|
| Fiat Pimento | £75,670 | 73103 | +2,567 |
| Fiat Morello | £77,440 | 75608 | +1,832 |
| Fiat Pimento XL | £77,440 | 75068 | +2,372 |
| Fiat Morocco | £77,440 | 75068 | +2,372 |
| Fiat Morocco XL | £79,956 | 77574 | +2,382 |
| Fiat Morello XL | £79,956 | 77574 | +2,382 |

These are **genuine price rises, not a basis change** — the basis is proven correct by the
four Ford rows matching to the pound. Note the October 2025 price list carries prices
*identical* to February 2026 on all ten products, so the Fiat figures FMLV holds predate
October 2025, and Murvi have not moved a price in at least four months.

No on-the-road/ex-works question arises: Murvi print no delivery or registration fee anywhere
in the document, so the VAT-inclusive figure is the headline a buyer sees.

## Body type: `campervan_high_top`, all ten

FMLV holds `type_campervan_high_top = Yes` on **all 11** rows and every other `type_*` as
`No`, with no disagreement anywhere in the export.

That is also what the shared rule derives. These are panel-van conversions on unmodified
factory high-roof vans — the document says "High Roof van" for all ten — at published
heights of 2540–2846 mm, comfortably above the shared `HIGH_TOP_ABOVE_MM = 2300`. And
**no elevating roof is offered on any model**: the word "pop-top" appears nowhere in the
price list, and the only roof option is a *taller fixed* one ("See H3 higher roof option -
minimum 2M headroom" on the Ford Pimento). Per the 21 August 2026 rule, silence means the
elevating roof is not part of the standard specification, so none of the four elevating
variants applies.

Body type therefore agrees with the baseline on all ten and nothing is proposed. Record it
with provenance anyway — an unregistered field is blank on a genuinely new product.

## Berths and seats: 2 and 2, and read them as standard

The price list publishes no berths row and no seats row. Both have to come from prose, and
both are corroborated by FMLV holding **2 and 2 on all 11 rows without exception**.

**Berths = 2.** Every model converts its lounge into either one double or two singles, never
more:

> The Pimento has an extremely comfortable, high back lengthways settee that easily converts
> into a full size double bed (75" x 54")

> the same beds will also form a generous size double bed 76" x 60" *(Morocco XL, which makes
> two singles or one double)*

**Seats = 2**, being the two cab seats. Rear travel seats are explicitly an **option**, which
is the base-vehicle rule doing the work:

> This forward facing position also gives **the option of up to two rear travel seats**, one
> three-point, inertia reel seat belt and one lap restraint.

So the standard fitment is 2 and the ceiling is 4. This is the Bürstner distinction exactly —
a *permitted* or *available* figure is not `mh_passenger_seats_inc_driver`, which records the
belted seats fitted as standard — and here the lower figure is safe to take because Murvi
label the upper one as an option rather than as a homologation permission, and because FMLV's
own 11 rows agree with it 11 times. Carry the manufacturer's wording into the provenance so a
reviewer sees "up to two rear travel seats" beside the recorded `2`.

Note the **Piccolo is the exception** and is out of scope for it: its page says "forward
facing seats for four" with "two integral 3-point inertia reel seat belts" as *standard*, so
it would be 4 seats, not 2 — and FMLV holds 2, which looks wrong. It is a 2024 row for a
discontinued model, so nothing will propose against it, but do not generalise the seats rule
from the Piccolo page.

## The roster: ten products, and twenty pages of noise

There is **no sitemap and no `robots.txt`**, so the roster comes from the site navigation,
cross-checked against the price list. Those two agree, which is the reconciliation
`README.md` asks for.

The navigation lists seven model pages. The February 2026 price list prices **ten
chassis/layout combinations**:

| Family | Ford | Fiat |
|---|---|---|
| Pimento | ✓ | ✓ |
| Pimento XL | ✓ | ✓ |
| Morello | ✓ | ✓ |
| Morello XL | ✓ | ✓ |
| Morocco | — | ✓ |
| Morocco XL | — | ✓ |
| Piccolo | — | **not priced** |

**Expected product count: 10.** That is the number the tests should assert and the number a
first run must be compared against. It is the price list's own roster — ten spec pages, ten
options pages, twenty pages exactly — and it reconciles with the eight non-archived
current-year FMLV rows plus the two Ford rows FMLV has archived (see below).

Two absences, both explained rather than assumed:

- **No Ford Morocco or Ford Morocco XL.** The Morocco page says "currently only based on the
  Fiat Ducato LWB", so this is a fact about the range, agreed by two sources.
- **Piccolo is discontinued.** It is absent from the February 2026 price list *and* from the
  October 2025 one, its page was last modified in June 2021, and its FMLV row carries year
  **2024** — so `_is_current_model_year` already drops it and it cannot be reported as
  disappeared. The page is still live and still in the navigation, which is why the roster
  has to come from the price list as well as the nav.

**And the two archived Ford rows are a live question.** FMLV has 7126 (Ford Pimento) and 7127
(Ford Morello) as `archived = Yes`, yet the February 2026 price list sells both, and their
stored prices and dimensions match it *exactly* (£77,290 / 5531×2059×2580 and £78,598 /
5981×2059×2580). They were almost certainly archived by mistake, or archived as part of
whatever data entry produced the identical-identity pairs. An archived row is excluded from
the baseline, so a run will propose both as **new products** — which is right in the sense
that FMLV has nothing live for them, but a human should un-archive rather than duplicate.
Flag it, do not work around it.

## Single beds and disabled adaptions are options, not products

Confirmed by the requester and by Murvi's own words. Two pages sit in the navigation
alongside the model pages and read as though they might be models; neither is.

`Single Bed Options` (`?page_id=2010`) opens:

> **Single beds are now an option on all Ford models.**

and closes the question of whether the variant is a distinct product with its own belted
seats:

> Rear seat belts are not available with the single bed option.

The price list treats it the same way, as a line inside the Ford Pimento's standard
specification rather than as a priced model:

```
Pimento SB - Single bed option (no rear lap restraints)
```

`Disabled adaptions` (`?page_id=860`) is likewise a services page, not a layout.

So neither generates a product, and this is the Le Voyageur 45-years case rather than Adria's
60Y. The `SB` suffix *does* appear in the wild on individual ex-demonstrator pages ("Ford
Murvi Pimento XL SB"), which is another reason the used-vehicle pages must not feed the
roster — they would introduce `Pimento XL SB` as a phantom eleventh product.

## Model year

Murvi publish **no model year anywhere** — not on the model pages, not in the price list,
which is dated by *effect* ("Price List with effect from February 2026") rather than by
season. FMLV holds 2026 on all ten current rows and 2024 on the Piccolo.

Murvi issue price lists on their own schedule — February 2026, October 2025, August 2025,
June 2025, March 2025 (×3), February 2025 — roughly three to five a year, with no
relationship to the Düsseldorf or NEC calendar. The requester confirmed on 2 September 2026
that the February 2026 list is the current one, so there is no rollover pending.

Because no year is published, leave the seasonal 2026 → 2027 bump proposals **UNDECIDED,
never rejected** — `was_previously_rejected` matches on `(product, field, new_value)` with no
run scoping, so a rejected bump is suppressed forever and closes the `--bump-year` route too.

## First runs — 2 September 2026, runs #1 and #2

Two runs, one per chassis, both `succeeded`. Two fetches each (the price-list page and the
PDF), ~2.4s of website sweep, snapshots in `data/snapshots/181/`.

**Run #1, `--range Fiat`** — 6 scraped against 6 baseline: **6 changed, 0 unchanged, 0 new,
0 disappeared**, 19 changes proposed of which 6 are year bumps, and 77 fields checked and
confirmed unchanged. Exactly what the survey predicted, and the 13 real changes are the
three groups it predicted:

- **6 model renames**, adding the chassis (`Morello` → `Fiat`, `XL` → `XL Fiat`, …). No
  `manufacturer_range` change on any product, which is the point — the range was already
  right, so only one half of the identity moves and the other stays correct.
- **6 price rises**, £1,832 to £2,567, matching the table above to the pound.
- **1 MRO correction**, product 7133 Fiat Pimento `3000 → 2900` — the FMLV data error the
  survey found, now proposed by the arithmetic FMLV's own other ten rows satisfy.

Nothing was proposed for any dimension, on any of the six products. That is the strongest
result in the run: all eighteen length/width/height figures were read out of the PDF and
found to agree with what FMLV already held.

**Run #2, `--range Ford`** — 4 scraped against 2 baseline: **2 changed, 2 new, 0
disappeared**, 34 changes proposed of which 2 are year bumps. The two matched products
(7128 Pimento XL, 7129 Morello XL) got a model rename and a year bump and **nothing else** —
no price, no weight, no dimension — confirming that FMLV's Ford rows already hold the
February 2026 figures exactly.

The two "new" products are Ford Pimento and Ford Morello, at 15 fields each. **They are not
really new** — FMLV holds them as 7126 and 7127 with `archived=Yes` — so the right action is
to **un-archive those two rows, not to accept the new products**, which would duplicate them.
See the roster section above.

Hand-checked against the source document, three products:

| Product | Page | The document says | The run proposed |
|---|---|---|---|
| Ford Pimento (new) | 1 | `5.531M`/`2.580M`/`2.059M`, `Payload 600 K gs`, `(3,500kg GVW)`, `£77,290.00` | 5531/2580/2059, 600, 3500, MRO 2900, £77,290 |
| Fiat Pimento (7133) | 9 | `5.413M`, `Payload 600 Kgs`, `(3,500kg GVW)`, `£75,670.00` | MRO 3000→2900, £73,103→£75,670 |
| Fiat Morello XL (7135) | 19 | `6.363M`/`2.565M`/`2.050M`, `Payload 400Kgs`, `£79,956.00` | dimensions confirmed, £77,574→£79,956 |

**Leave the 8 year bumps UNDECIDED, never rejected.** Murvi publish no model year anywhere,
and `was_previously_rejected` matches on `(product, field, new_value)` with no run scoping —
a rejected 2026 → 2027 stays suppressed forever and closes the deliberate `--bump-year`
route too.

Confirmed end to end: `adapter_for("Murvi")` resolves, and Murvi appears in the review app's
trigger dropdown as the sixteenth manufacturer despite `status=paused` — that list is
filtered on `adapter_for()` alone, so pausing keeps it manually runnable exactly as intended.
Full suite 1122 passed, 2 skipped.

## What is unverified

- **`fmlv_manufacturer` is confirmed** as `Murvi` from the export's own `manufacturer`
  column, and `ncc_supplier_name` as `Murvi` from a successful download. Neither is a guess.
- **A combined-chassis run is still possible and still unsafe.** It is guarded by a warning
  and by `status=paused`, not prevented. The durable fix is to make
  `base_vehicle_manufacturer` part of `cli._dedupe_baseline`'s key and of the matcher's
  score, which would let a full run work and would remove the per-chassis discipline
  entirely — deliberately not done, because it is shared pipeline code and the requester
  asked that Murvi's handling not become a general rule. Revisit if a second brand does
  this; that is the trigger the requester asked for.
- **A price divergence between the Ford Morello and the Ford Pimento XL would raise a
  spurious warning.** Murvi's Ford Pimento XL options page carries a stray
  `Ford Murvi Morello` header — their layout error — so the Morello's price cross-check
  reads a page that is not its own. Both are £78,598 today so it agrees silently. It can
  never produce a wrong *value* (the specification page's figure is always the one returned)
  and the header pattern is deliberately left loose, because the same looseness is what
  survives pypdf corrupting five headers' first letter.
- **The `automatic_*` columns are out of scope** in `config/field_guide_motorhome.csv`, so
  nothing reads or writes them — but note FMLV *does* hold four of them for every Murvi row
  (`automatic_mro_kilograms` = MRO + 30, `automatic_mh_payload_kilograms` = payload − 30,
  plus an automatic RRP), and the price list prices an "8 - speed Automatic" at £2,100
  ex-VAT on the Fiat models. The stored automatic RRPs do not follow from the base price and
  that option cost by any arithmetic tried (Fiat Morello: 75,608 + 2,520 = 78,128 against a
  stored 77,588), so their basis is unknown. Out of scope, so left alone — recorded here
  because it is the obvious next thing someone will ask for.
- **`.env` had a typo in the NCC login email** (`oliver.m@thrncc.org.uk` for
  `oliver.m@thencc.org.uk`), which made `fetch-export` fail with a 30-second navigation
  timeout rather than an authentication error. Worked around with an environment override
  for this survey; the file itself is untouched and still wrong. Not a Murvi issue, but it
  will block the next person too.
- **Berths and seats are read from prose, not from a row**, because Murvi publish neither.
  Both are corroborated by FMLV holding 2/2 on all 11 rows, which is strong, but neither is
  a figure Murvi state as a number anywhere. If Murvi ever publish a berth or seat count,
  read it and keep the prose as the cross-check.
- **Contact details** (Rex, `rex@murvi.co.uk`, 01752 892200) come from
  `resources/manufacturers-full-list.csv` and the price list footer; not verified by contact.
- **Nothing has been uploaded.** Runs #1 and #2 are proposals sitting in the review queue;
  no `generate-upload` has been run and no FMLV row has been written.
