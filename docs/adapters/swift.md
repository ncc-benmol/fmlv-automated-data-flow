# Swift Group — site survey and adapter notes

Surveyed 6 August 2026 against the **2026** brochures. **Re-surveyed and the adapter
rewritten 28 August 2026 against the 2027 range**, because the source it was built on no
longer exists.

Swift was the third manufacturer surveyed and the easiest. It is now the first to have
had its source taken away mid-life, and the lesson is in the shape of that failure rather
than in the parsing.

## What happened

The 2026 adapter read the "Specification at a glance" table out of Swift's annual
brochure PDFs. On 28 August 2026 it collected **zero products**:

```
[Motorhomes] SKIPPED: no brochure link found on https://www.swiftgroup.co.uk/motorhomes/
[Campervans] SKIPPED: no brochure link found
0 product(s) collected
```

For 2027 there is **no full brochure**. Motorhomes, campervans and caravans all got a
two-page *quick guide* instead — all three stamped "Issued September 2026" — and the
detailed per-layout data moved onto the website. The adapter's link pattern required
`_brochure.pdf`; the file is now `2027-swift-motorhome-quick-guide.pdf`.

Two things about that are worth carrying to every other adapter:

**It failed silently.** Two narrated skips, no crash, no raised error, run status
succeeded. The pipeline treats "no brochure link on the page" as a skip because on any
given run that is usually a transient site change, and it is the right default — but it
means a dead source looks exactly like a quiet week.

**The trigger dropdown kept showing Swift throughout**, because that list is filtered by
`adapter_for()`, which only checks a module is registered under the manufacturer name.
Presence there says the plumbing is connected. It says nothing about whether the source
still exists.

## The trap: the old brochure is still live

The obvious fix — loosen the pattern to accept hyphens and "quick guide" — is the wrong
one. `/brochures/` still lists 70 PDFs including both 2026 brochures, and the old URL
still resolves:

```
/media/noeb4jei/2026_swift_motorhome_brochure.pdf   OK, 20,248,570 bytes
```

A pattern loose enough to match the 2027 guide matches the 2026 brochure too, and would
propose last season's range as current: 30 plausible, internally consistent, wholly stale
products. That is worse than collecting nothing, and nothing downstream would catch it.

So the adapter reads the site, anchors its guide pattern on `quick-guide` rather than on
`.pdf`, and never looks at `/brochures/` at all. `test_swift.py` has an explicit negative
test feeding it both 2026 brochure links and asserting it finds neither.

## Where the data lives now

One page per **range**, at `/{motorhomes,campervans}/product/<id>/<slug>/`, each carrying
a `<script type="application/json" data-product-layouts-data>` block with one object per
layout — plain server-rendered HTML, so still no JavaScript:

```json
{"id":75041,"title":"Kon-Tiki 774","code":"kon-tiki-774","badge":"New for 2027",
 "priceLabel":"From £114,395 OTR","berths":"6 berths",
 "travellingSeats":"5 travelling seats","licenceCategory":"C1","length":"8.22m",
 "width":"2.39m","weightMtplm":"4500kg","weightMro":"3638kg"}
```

**39 products, 13 fetches, no browser.** All nine of those fields are populated on all 39.

| Category | Ranges | Products |
|---|---|---|
| Motorhomes | Kon-Tiki 7, Voyager 6, Escape 5, Trekker 500 4 | 22 |
| Campervans | Merlin 9, Carrera 6, Trekker 2 | 17 |

Up from 30 in 2026. **Monza is gone**; **Merlin is new** — "Swift's new entry-level
campervan". Three vehicles are badged *New for 2027*: Kon-Tiki 740, Kon-Tiki 774,
Trekker 505.

Better than the brochure in two ways, worse in one:

- **Price, on every layout.** The 2026 survey recorded that Swift published none
  anywhere. All 39 now carry `From £x OTR`, which is the basis
  [README](README.md) says FMLV records.
- **Range attribution is free**, which matters more here than anywhere else — see below.
- **No height**, on any Swift document for 2027.

## Trekker is two different ranges

Swift sells a `Trekker` **coachbuilt** range and a `Trekker` **campervan** range. Same
collision as Auto-Trail's Expedition, and the requester flagged it independently.

FMLV already models it, which the real export confirms: the coachbuilts are range
`Trekker 500` (models 540, 584, 594) and the vans are range `Trekker` (S, X, XF, XL). So
`RANGE_NAME_CORRECTIONS` renames the motorhome range, and a layout's range always comes
from **which index page led to its page**, never from its name.

It is worse than a name clash. The layout *numbers* collide too, with **identical length
and MTPLM**:

| | Length | MTPLM | MRO |
|---|---|---|---|
| Voyager 505 | 6.19m | 3500kg | 2837kg |
| Trekker 505 | 6.19m | 3500kg | **2885kg** |

540, 584 and 594 are shared as well. **Only MRO separates them.** Nothing may key a
layout on its number alone — and this is not hypothetical:

**FMLV was holding the wrong weight.** Baseline `Trekker 500 540` carried MRO 3012, which
is the *Voyager* 540's figure, and `Trekker 500 594` carried 3102, the Voyager 594's. The
site says 3074 and 3156. The first run proposes both corrections.

## The bug the first live run found

**Swift's nav block is global**, so the motorhomes index links every campervan range page
too. An href pattern accepting either category read all nine ranges from *each* index —
emitting all 39 products twice, and applying the `Trekker` → `Trekker 500` correction to
the **campervan** Trekker on the first pass.

The category is now interpolated into the pattern per index. Same trap as
[chausson.md](chausson.md)'s global nav, and `test_range_paths_are_scoped_to_their_own_category`
asserts the nav really is global before checking the scoping holds.

## The self-check is cross-document

The JSON publishes MRO but no payload. The quick guide publishes payload but no MRO. So
`payload == MTPLM - MRO` is a genuine check across two independent documents rather than
an arithmetic tautology within one.

On 28 August 2026 it was an **exact bijection**: 39 payload figures across the two
guides, 39 products on the site, all reconciling, none left over.

The guide prints them two ways and both must be read:

```
740                     ← full block, one per floorplan
Length
6.99m / 22'11"
Max Payload
1220kg
MTPLM
4500kg
```

```
244 Max Payload         ← compact line, for a variant sharing its sibling's floorplan
470kg
```

Nine of the seventeen campervans are only reachable the compact way, so reading full
blocks alone would leave a third of the range unchecked.

The Escape prints **dual figures** — `270kg | 400kg` against `3500kg | 3700kg` — paired
*positionally*. That is how the guide encodes what the site sells as separate 2-berth and
4-berth products.

**A contradicted payload drops the layout; a floorplan the guide doesn't cover only
warns.** That asymmetry is deliberate. The brochure version dropped hard because its two
tables were joined on `(range, layout)` and a misjoin was the risk being defended
against. There is no join now — one JSON object is one vehicle — so column misalignment
is structurally impossible, and the remaining risk is Swift mis-stating a figure. Losing
a real vehicle over a gap in a marketing leaflet's coverage would be the worse error.

## The base vehicle comes free, and cross-checks perfectly

Every range page names its chassis once, in the "Exterior & Construction" feature list.
It is a range-level fact — every layout in the range is built on it:

| Range | Stated as | FMLV |
|---|---|---|
| Voyager | Ford Transit Skeletal chassis cab | `Ford` |
| Trekker 500 | Ford Transit Skeletal chassis cab | `Ford` |
| Escape | Fiat chassis cab | `Fiat` |
| Kon-Tiki | Fiat chassis cab | `Fiat` |
| Carrera | Fiat Ducato panel van | `Fiat` |
| Trekker | Ford Transit panel van | `Ford` |
| Merlin | Fiat Ducato panel van | `Fiat` |

Reading it this way reproduces FMLV's own split **exactly** across all 31 baseline
products — Ford 17 (Voyager 9, Trekker 500 3, Trekker 4, Monza 1) and Fiat 14 (Escape 4,
Kon-Tiki 4, Carrera 6). That agreement is what makes it safe to emit, and it is why the
field was added on 28 August 2026 rather than left to hand-filling.

**The make and the body phrase must be matched together.** The Carrera page titles itself
"Award-winning Swift Carrera panel van, refreshed for 2026", so anchoring on `panel van`
alone finds a heading with no make in it. Up to two words are allowed between the two, so
`Transit`, `Ducato` and `Transit Skeletal` all pass.

## Height: nothing is published, and it is handled two different ways

**No 2027 Swift document publishes an overall height.** Not the layout JSON, not the
quick guides — their only "height" mentions are prose ("full height GRP rear panel",
"height adjustable electric drop-down bed"), never a spec row beside Length and Width.
`test_no_swift_document_publishes_a_height_for_2027` asserts that premise, and is the
test to watch: if it ever fails, Swift have started publishing heights again and the
constant below should be retired.

The right answer differs by whether the product already exists in FMLV.

### For the 30 products with a baseline — emit nothing

The requester asked (28 August 2026) to carry the 2026 heights over where 2027 omits
them. **That is implemented by emitting nothing**, because it is what the pipeline
already does: an in-scope field the adapter cannot fill arrives at review as a flagged
no-op change (`old == new`, snippet *"not found on the manufacturer's site this run.
Confirm the existing figure is still correct, or enter a replacement"*). The reviewer sees
it; the stored value is preserved untouched. All 24 matched products behaved that way.

Proposing the 2026 brochure's figure *instead* was considered and rejected. FMLV already
holds heights that disagree with that brochure on the Kon-Tikis — FMLV 2890 against the
brochure's 2880 — so proposing it would rewrite good data with older data on no 2027
evidence at all.

For reference, had a constant been used, this is how far it would have stretched —
measured by whether 2027's length *and* width still match 2026 exactly:

| | Count | |
|---|---|---|
| Length + width identical | 21 | same bodyshell, safe to carry |
| Kon-Tiki, dimensions moved | 5 | width 2380 → 2390, MRO up 18–30kg; the 2027 spec cites an AL-KO conversion "with wide rear track" |
| No 2026 equivalent | 13 | Merlin 9, Kon-Tiki 740 + 774, Trekker 500 505, Trekker XF |

Reassuringly, "the all new Carrera" turns out to be all-new in *equipment* only —
induction hob, lithium, no gas — with every dimension identical to 2026.

### For the Merlin — a hand-sourced constant, because there is no baseline

The flagged-no-op route has nothing to preserve for a brand-new product, so all nine
Merlins would have stayed blank on every run. `_MANUALLY_SOURCED_HEIGHT_MM` holds the
figures from a **pre-launch specification sheet Swift sent the requester in late July
2026**, passed on 28 August. That sheet carries range, base vehicle and height and *no
prices or weights*, so it is useful for this one field and nothing else — everything else
still comes from the site, which by now has both.

| Height | Models |
|---|---|
| 2720 mm | 144, 164, 174 |
| 2790 mm | 244, 264, 274 |

**The 70mm is the elevating roof**, and two independent things say so. The Merlin page
lists "Elevating roof in Black with Mini-Heki skylight" as standard equipment on
`212, 244, 264 & 274` only — exactly the `2xx` models. And the Carrera corroborates it
from a different range: same Fiat Ducato panel van, same 2260mm width, **2720mm on its
five plain models and 2790mm on the 244**, which is the one model its own page gives an
elevating roof ("244 only").

**112, 122 and 212 are deliberately absent.** They were not on the extract supplied, and
the pattern predicts 2720 / 2720 / 2790 — but a predicted height is not a published one,
so they are left blank and narrated rather than guessed.

Same pattern and the same caveat as `auto_trail._MANUALLY_SOURCED_MTPLM_KG`: it **cannot
refresh itself**, it is narrated on every run, and it must be re-verified at each
model-year changeover.

## An FMLV body type that looks wrong: Carrera 244

Not fixed here, because `body_type` is not emitted (below) — but recorded, because the
evidence is unambiguous and it is the same shape of error the
[README](README.md) documents for Autoquest CV60, inverted.

The Carrera page lists an elevating roof as **standard** on the 244: it appears twice,
once in the range highlights ("Elevating roof system with pop-top double bed (244)") and
once in Exterior & Construction ("Elevating roof in Black with Mini-Heki skylight (244
only)"). It appears in **no** `optionalExtras` list on any of the 39 products, so it is
not a cost option. Its 2790mm against the other Carreras' 2720mm is the roof hardware.

FMLV holds Carrera 244 as `campervan_high_top`, not
`campervan_high_top_elevating_roof`. By the README's rule — the word after the feature
decides it, and here it is standard fitment restricted to one model — that looks wrong.

FMLV gets the equivalent Trekker case right, which is what makes the Carrera one stand
out: `Trekker X` (roof stated on the page) is held as
`campervan_high_top_elevating_roof`, and `Trekker XF` (not stated) as
`campervan_high_top`.

## Counting: floorplans versus products

The guides' range cards count **floorplans**; the site sells **variants**.

- Escape's "3 Layouts" are 5 products: 684 and 694 each come 2-berth at 3500kg and
  4-berth at 3700kg, which is exactly what the dual guide columns encode.
- Merlin's "5 Layouts" are 9 products: the leading digit is the variant (112 is 2-berth,
  212 is 4-berth) and the trailing pair is the floorplan.

The two documents agree — they are counting different things.

**Do not trust the range cards for berths.** The Voyager card says "4 / 6 Berth" while
the Voyager 505 is a 2-berth. The per-layout data is right and the card is marketing
rounding.

## Other things that bit, each covered by a test

1. **A model name isn't always a number.** The campervan Trekker's layouts are
   `Trekker X` and `Trekker XF`, which share the prefix `Trekker X` — so a model cannot
   be found by taking the common prefix of the titles on a page, which would make the
   second model `F`. The page slug supplies the boundary instead. The *range* half is
   taken from the title, not the slug, so Swift's own hyphenation survives (`Kon-Tiki`,
   not `Kon Tiki`).
2. **Three dead CMS nodes.** `/campervans/` links five range pages, but
   `74769/merlin` and `79540/merlin` return HTTP 500 (they served empty bodies earlier
   the same day). Only `75043/merlin` carries layouts. Narrated and skipped.
3. **Footnote marks on weights**, `3500kg**` and `663kg*`, on MTPLM as well as payload.

## First run

Run #45, 28 August 2026 — and the first Swift run ever; there was no
`data/snapshots/26/` before it.

```
baseline    31 products
scraped     39 products
classified  23 changed, 1 unchanged, 15 new, 7 disappeared
proposed    222 changes for review, of which 21 are year bumps
verified    135 fields checked and unchanged
```

Run #46, the same day, after adding the base vehicle and the Merlin heights: same
classification, 243 proposed and 159 verified. The 21 extra proposals are the base vehicle
on the 15 new products plus the 6 Merlin heights; the 24 extra verifications are
`base_vehicle_manufacturer` **agreeing with FMLV on every single matched product**, which
is the strongest corroboration in either run.

**7 disappeared, all genuine roster changes and none a parse gap:** Escape 674, Monza S,
Trekker S, Trekker XL, Voyager 475, 485, 494.

**15 new:** Merlin ×9, Kon-Tiki 740, Kon-Tiki 774, Kon-Tiki 894 (with drop down bed),
Escape 684 (2 berth), Escape 694 (2 berth), Trekker 500 505.

Hand-checked against the source: Kon-Tiki 740 (6.99m / 1220kg payload / 4500kg MTPLM,
matching the guide block exactly), Voyager 505 (2 berths, £75,995), Escape 640 (2 berth)
(MTPLM 3700 → 3500, payload 500 → 370, £91,490 → £89,495).

## Are the 15 "new" products really new? — audit, 28 August 2026

The requester asked, because this project has twice found a "new" product that was a
renamed old one (Bailey's `74-4T` vs `75-4t`, Etrusco's `6.6 SF` vs `6.8 SF`) and once
found a kept name behind a changed vehicle (Chausson's 777 vs 797).

Method: fingerprint every product on **length + width + MTPLM + MRO** — the four figures
a rename cannot change — and compare the 15 new against the 7 disappeared. MRO is the
discriminating one, because Swift publish it to the kilogram.

**No renames. Not one of the 15 matches any of the 7.** The three closest approaches, and
why each is a different vehicle:

| New | Closest departing | Verdict |
|---|---|---|
| Kon-Tiki 774 | Escape 674 — same 8.22m, same 4500kg | 148kg heavier, £17,845 dearer, different range. Shares the Fiat AL-KO platform, which is expected across ranges. The Escape's only 4500kg slot moved up into the Kon-Tiki range; the vehicle is not the same one. |
| Trekker 500 505 | Trekker XL — MRO within 5kg | **2070mm wide van against a 2370mm coachbuilt.** Different vehicle class; the name is the only thing they share. |
| Merlin 144 | Trekker XL — MRO within 10kg | 20mm apart in length but again a different body: Ford Transit van vs Fiat Ducato. |

**Variant pairing is correct where Swift now sell two builds of one layout.** This was the
subtler risk — the matcher picking the wrong twin:

| Baseline | Matched to | |
|---|---|---|
| Escape 684 — 4 berth, 3700kg, MRO 3300, £93,150 | `684 (4 berth)` | **identical on all four** |
| Escape 694 — 4 berth, 3700kg, MRO 3350, £93,990 | `694 (4 berth)` | **identical on all four** |
| Kon-Tiki 894 — 4 berth, MRO 3935 | `894` (4 berth, MRO 3965) | right twin; the 6-berth drop-down-bed 894 is genuinely a second product |

So the new Escape 2-berths and the drop-down-bed 894 are real additional products, not
duplicates of rows FMLV already holds.

**Merlin and Carrera are fingerprint twins, and that is expected.** Merlin 244 sits 5kg
from Carrera 144, and Merlin 274 within 15kg of Carrera 184 and 194 — same Ducato shell,
same lengths, different fit-out. Neither can be a rename of the other because **both are
on the 2027 site simultaneously**, and the prices differ by £8,000 (Merlin is the
entry-level range). Worth knowing that FMLV will now hold near-identical weights and
dimensions for two ranges.

### The one genuine anomaly: Voyager 505

| | Berths | Seats | MTPLM | MRO | Price |
|---|---|---|---|---|---|
| 2026 brochure | 4 | 2 | 3500 | 2837 | — |
| FMLV baseline | 4 | 2 | 3500 | 2837 | £73,490 |
| 2027 site | **2** | 2 | 3500 | **2837** | £75,995 |

Two berths have gone and the **MRO is identical to the kilogram**, with the price up
£2,505. Those do not sit together: removing a bed should change the weight. Either Swift
have restated the berth count without changing the vehicle, or the layout changed and the
old MRO was carried forward without re-weighing.

It matters beyond berths. FMLV holds the 505 as `coach_built_over_cab_bed`, and **every
other over-cab Voyager was discontinued for 2027** (475, 485, 494 — all three among the 7
disappeared). If the 505 has lost its over-cab bed, its body type is now wrong too — and
since this adapter does not propose `body_type`, nothing would ever correct it.

**This is the one to put to Swift.** By contrast the other berth changes hang together:
Escape 640 went 4 berths to 2 *with* MTPLM 3700→3500, MRO 3200→3130 and £1,995 off, and
Carrera 144 and 194 went 3 berths to 2 with 10kg off — small, self-consistent changes.

## Body type — added 28 August 2026, after the first review found it blank

Both earlier versions of this adapter left `body_type` unset, on the grounds that the
campervan rule needs a height and Swift publish none. **That reasoning only held for
products FMLV already has.** For a new product there is no stored value to protect, so
"leave it alone" means "leave it blank forever", and the first review of the 15 new
products found exactly that. The requester asked why; this is the fix.

It is settled two different ways, because the two halves of the roster ask different
questions.

### Motorhomes need no height at all

Low profile against over-cab against A-class is about shape, not millimetres, and every
2027 Swift coachbuilt range states its shape in the construction list — `GRP front low
line pod` on the Voyager and Trekker 500, `AL-KO low line chassis conversion` on the
Escape and Kon-Tiki. All 22 are `coach_built_low_profile`.

**The trap, and it is a good one: `over-cab` on a Swift page does not mean an over-cab
bed.** Both ranges that use the phrase mean *storage* — "Moulded over-cab storage
compartments with Skyview opening sunroof" (Kon-Tiki), "Zip pocket storage on the overcab
side lockers" (Trekker 500). Those are lockers in the low-profile pod. Swift's extra
berths come from a **drop-down bed over the front lounge** ("Height adjustable electric
drop-down bed over front lounge (505, 540 & 574)"), which is a low-profile feature. A
keyword search for "over cab" classifies two low-profile ranges as Luton, so
`_OVER_CAB_BED` requires the word *bed*, *double* or *island* after it, and there is a
test for both directions.

A range stating no profile comes back unset and narrated, rather than defaulting to low
profile — which is what should happen the day Swift add an A-class.

### Campervans need both halves of the 2×2

Roof class from the height, elevating roof from the page. The Merlin has heights (above),
so all nine classify:

| | Models | |
|---|---|---|
| `campervan_high_top` | 112, 122, 144, 164, 174 | 2720mm, no elevating roof |
| `campervan_high_top_elevating_roof` | 212, 244, 264, 274 | 2790mm, roof standard |

Both figures clear the ~2680mm the [README](README.md) calls characteristic of an extended
high top.

**112, 122 and 212 have no height of their own and are still classified**, because a
campervan range is one bodyshell — the shortest published height in the range decides the
roof class for all of it. Their `mh_height_mm` still stays empty: this settles the body
type, not the figure.

**The Carrera and Trekker campervans get nothing**, and that is the rule working rather
than failing. Swift publish no height for them, so the roof class is unanswerable, so
FMLV's existing values are left untouched — including the Carrera 244 flag discussed
above, which the requester is correcting by hand.

### What it changed on the first run

Fifteen new products got a body type, fifteen existing motorhomes had theirs confirmed
unchanged, and **one real correction was proposed: Voyager 505,
`coach_built_over_cab_bed` → `coach_built_low_profile`.** That is the change the rename
audit predicted — every other over-cab Voyager was discontinued for 2027, and the 505's
own range page states a low-line pod and a drop-down bed over the front lounge.

## Not emitted, and why
- **`year`** — a carry-through field only a human bumps
  (`src/diff/year_rollover.py`). Today falls inside the June–September window, so the
  review app offered 21 bumps. The site does say 2027.
- **`base_vehicle_manufacturer`** — the range pages name the chassis in feature prose
  ("Fiat chassis cab in Black Metallic"), which is range-level marketing copy, not a
  per-layout field. Not worth the risk of attributing it per product.

## Registry and naming

`fmlv_manufacturer` **`Swift Group Ltd` is confirmed** against a real export — 96 of 97
rows — and `fetch-export` against `ncc_supplier_name` `Swift` succeeded.

**A data error on the NCC side, worth reporting to them:** the 97th row in Swift's own
export is a *Sunlight* product.

## Bessacarr and Ace Motorhomes

`resources/manufacturers-full-list.csv` gives Swift Group Ltd three ids: **26** (Swift),
**228** (Bessacarr), **264** (Ace Motorhomes). Only 26 is registered, deliberately.

Both brands have **zero presence anywhere on swiftgroup.co.uk** — no page, no PDF, no nav
entry, no sitemap entry. There is nothing to scrape and no adapter can refresh them;
archiving them is a decision for the NCC side, not an adapter one.

The requester noted (28 August 2026) that their Nova supplier names would be `Bessacarr`
and `Ace Motorhomes`, and asked whether that breaks anything. **That part is harmless** —
`ncc_supplier_name` is a separate column for exactly this reason, as
[`src/fetch/ncc.py`](../../src/fetch/ncc.py) says.

**What would break is giving them the same `fmlv_manufacturer`.** `ADAPTERS` is keyed on
that string and `collect()` receives no brand identity, so all three rows would resolve
to this adapter, scrape all 39 Swift vehicles, and diff them against their own baseline:
every Swift product proposed as new for Bessacarr, every Bessacarr product reported
disappeared. `cli.find_manufacturer` does refuse a name matching more than one row and
asks for the `manufacturer_id`, but that only stops you typing the wrong thing — it does
not stop the bad diff.

If they are ever wanted, each needs its own `fmlv_manufacturer` matching what FMLV
literally holds, plus an adapter scoped to that brand's ranges.

## Two pipeline bugs the payload work surfaced

Both were found on 4 September 2026 while wiring the derived payload, and neither is
Swift-specific.

**Every caravan gap was described with the wrong wording.** `store.changes`'s
`_missing_field_snippet` chose between "marked in-scope for automated collection, but was
not found on the manufacturer's site this run" and "the adapter could not determine this
field" by testing `missing.field in schema.IN_SCOPE` — the **motorhome** set. Caravans name
their fields differently (`height_mm`, not `mh_height_mm`), so *every* in-scope caravan gap
fell through to the out-of-scope wording and told the reviewer the adapter could not
determine a field it was in fact required to find. 72 rows on Swift's first caravan run, and
Bailey's before it. `MissingField` now carries an `in_scope` flag, set where the right
`FieldProfile` is already in hand, and nothing downstream re-derives it.

**A new product was asked about empty out-of-scope fields.** `persist_diff` proposes every
field an adapter records provenance for, which on a new product includes the ones recorded
with no value — so the optional-payload row above appeared on the two genuinely new
caravans as `None -> None`, a decision for no reason. Now skipped when the field is out of
scope. An empty *in-scope* field is still proposed, which is the point of the exception:
that is how `swift._body_type_basis` offers the reviewer a choice the adapter could not
make, on a product with no baseline to preserve.

## Re-verify after the NEC show

Swift are mid-launch: the guides are stamped "Issued September 2026", three vehicles
carry *New for 2027* badges, and prices are already up. Specs may still move.

# Swift — touring caravans

Surveyed and built 3 September 2026, second of its kind after Bailey's. `swift_caravan.py`
produces `Caravan`s and registers under `("Swift Group Ltd", caravan)` alongside
`swift.py`'s `("Swift Group Ltd", motorhome)`.

## Built on the motorhome sibling, not on Bailey's caravan adapter

Bailey's caravans are one page per vehicle with a literal `Range`/`Model` spec table.
Swift's are the same shape as Swift's *motorhomes* — one page per range, carrying a
`<script type="application/json" data-product-layouts-data>` block with one object per
layout — so every parsing helper is imported from `swift.py` unchanged, `range_and_model`
included. `bailey_caravan.py` contributed the field mapping and the domain rules;
`swift.py` contributed the fetching. That split is the general lesson: which sibling to
copy depends on the *site's* shape, not on the product area.

Seven range pages, 26 layouts:

| Range | Page | Layouts |
|---|---|---|
| Sprite | `/caravans/product/1303/swift-sprite/` | 4 |
| Sprite Grande | `/caravans/product/1304/swift-sprite-grande/` | 1 |
| Challenger | `/caravans/product/1305/swift-challenger/` | 6 |
| Challenger Grande | `/caravans/product/1306/swift-challenger-grande/` | 4 |
| Conqueror | `/caravans/product/72924/swift-conqueror/` | 3 |
| Conqueror Grande | `/caravans/product/72943/swift-conqueror-grande/` | 4 |
| Elegance Grande | `/caravans/product/1309/swift-elegance-grande/` | 4 |

Three base ranges each have a Grande sibling; Elegance exists only as a Grande. Conqueror's
node id is six digits where the other six are four — its pages were rebuilt — which is why
paths are always rediscovered from `/caravans/` rather than constructed.

Unlike Bailey, whose `/caravans/` serves an `image/png` with a 200 status, Swift's
guessable URL is the right one.

## `length` is the shipping length, and nothing on the site says so

The single most consequential mapping here. Swift publish **one** length per layout and
never label it. Two independent sources settle it:

- The 2026 brochure's "Specification at a glance" table *does* label its columns, and
  gives the Sprite Alpine 4 an **Internal Length** of 4.74m against an **Overall Length**
  of 6.45m.
- FMLV holds that product as `internal_length_mm=4740`, `shipping_length_mm=6450`.

The site publishes `"length":"6.45m"`. So it is the overall figure, and it maps to
`shipping_length_mm` alone. Reading it as the internal length would overstate every
caravan's habitable space by 1.5-1.7m while looking entirely plausible on any one product
— which `docs/adapters/README.md` names as the most likely single way to get a caravan
adapter wrong. **This was checked, not reasoned about**, and it is the reason the survey
opened the retired brochure at all.

## Payload is derived from the two masses — reversed 4 September 2026

The adapter shipped on 3 September emitting no payload at all, reasoning that Swift's one
published figure is a *total* and FMLV splits it on the Elegance Grande. **The requester
overruled that the next day, on seeing the field arrive blank beside the two masses that
determine it:** MTPLM and MRO are published on every layout, `MTPLM - MRO` is the payload,
and that is the same arithmetic `swift.py` already does for `mh_payload_kilograms`. A gap
beside the figures that fill it is the wrong answer.

So `personal_effects_payload_kilograms` is now derived, and corroborated rather than merely
computed: the quick guide's `Max Payload` matches the subtraction on all 26, so the
provenance quotes the guide's figure alongside the arithmetic —
`Payload: 145kg, derived as MTPLM - MRO (1247 - 1102); quick guide agrees: Max Payload
145kg`. Where the guide has nothing to say the payload is still emitted and the provenance
says the subtraction stands alone.

**And where FMLV holds a split, the adapter asks for it to be cleared.** FMLV has *two*
payload columns and expects them to sum to `MTPLM - MRO`. On the four Elegance Grandes it
uses both: `personal_effects` 160kg plus `optional_equipment` 41kg makes 201kg. Since the
derived total goes into the personal-effects column, leaving that 41kg in place would make
the row read 242kg against 201kg of real capacity.

The requester's rule, given the same day: *where a model previously had a split and no
longer does, take the one published figure and use it as the personal-effects total.* So
the adapter records provenance for `optional_equipment_payload_kilograms` **with no
value** — "Swift publish one payload figure and no split, so there is no separate
optional-equipment payload" — and `diff.compare` turns that into a confirm-or-clear row
wherever the baseline holds one. The reviewer clears it with **Leave blank**.

Asked for rather than done silently, deliberately: `diff.compare` routes a
value-to-nothing change down the confirm-or-replace path precisely so no field is emptied
by an "accept". On the other 22 products FMLV already holds it blank, so the field comes
back confirmed and no row appears — run #68 raised exactly four, one per Elegance Grande.

Verified end to end on that run: accepting the 835's payload and clearing its optional
column writes `personal_effects_payload_kilograms=201`,
`optional_equipment_payload_kilograms=` (empty) against MTPLM 2123 and MRO 1922, and
`_validate_caravan_payload` reports nothing — 201 is exactly `MTPLM - MRO`. Accepting the
payload *without* clearing the split reports
`published payload 242kg does not match mtplm - mro (201kg)`, naming the product, which is
the backstop working.

**This falsifies `docs/adapters/README.md`'s "blank on all 92 real caravan products"** —
true of Bailey and Adria, not of Swift.

## The self-check is cross-document, and came out an exact bijection

The JSON has MTPLM and MRO but no payload; the quick guide
(`/media/jcelqit3/2027-swift-caravan-quick-guide.pdf`) has payload, length, width and
MTPLM but no MRO. So `payload == MTPLM - MRO` is a real check across two documents rather
than an arithmetic tautology, and the guide's length and width corroborate the site's on
top of it.

On 3 September 2026: **26 guide blocks, 26 site products, every one agreeing on all three
figures, none left over.**

Entries are keyed on **MTPLM, not on the model name**, because Swift's own two documents
disagree about names — the guide calls the Elegance layouts `Grande 850 L` and
`Grande 860 L` where the site *and FMLV* call them `850` and `860`, and it prefixes
`Grande ` to every model the site leaves bare. MTPLM is published identically by both and
is near-unique: the only repeat across all 26 is 1886kg, shared by Conqueror Grande 645
and 650L, which carry the same payload as each other anyway.

The guide corroborates two more things it is not read for. Its per-range counts
(Challenger 7 single / 3 twin, Conqueror 5 single / 2 twin, Sprite 4 / 1, Elegance Grande
0 / 4) reproduce the site's 26 `axleType` values exactly, and its 8ft-wide counts
reproduce the widths.

## Range names needed no corrections — because the export was fetched first

`docs/adapters/README.md` says to fetch the baseline before choosing `manufacturer_range`
and `model`. Doing so answered the one question the site could not:

FMLV already holds `Sprite`, `Challenger`, `Challenger Grande`, `Conqueror`,
`Conqueror Grande` and `Elegance Grande` exactly as the site's range pages divide them —
`Conqueror Grande` + `560L` with no space, `Elegance Grande` + `850` with no `L`. And
`Sprite Grande` is already in the export from an earlier model year, so 2027's Quattro FB
joins a range FMLV knows.

The **brochure** files every Grande as a *model* under its parent range ("Challenger /
Grande 580"). Following the printed document instead of the site would have proposed nine
renames FMLV does not want, and per the README's "Let the FMLV export decide the range and
model strings" each would have had to move both halves of the identity to avoid corrupting
the name. `RANGE_NAME_CORRECTIONS` is therefore absent from this module — the one place
where Swift's caravans are simpler than its motorhomes, where the Trekker collision needs
it.

## Three fields Swift published and no longer publish

All three were in the retired brochure; none appears anywhere on the 2027 site or in the
quick guide. Each is left unset so it arrives as a `MissingField`, showing a reviewer
FMLV's own figure beside "nothing scraped" and leaving the stored value alone.

| Field | Where it used to be | FMLV holds |
|---|---|---|
| `internal_length_mm` | brochure "Internal Length (At Bed Box Height)" | 3420-6360 |
| `height_mm` | brochure "Overall Height (Inc. Tv Aerial)" | 2590 / 2610 |
| `awning_length_mm` | brochure "Awning A/A Dimension" | 7950-10590 |

`personal_effects_payload_kilograms` was a fourth row here until 4 September 2026 — it is
now derived from the two masses instead. See above.

Back-filling any of them from the 2026 brochure was considered and rejected for the same
reason `swift.py` rejects it for motorhome heights: last season's document is not 2027
evidence, and FMLV's figures are already good. If Swift start publishing any of them
again, `collect`'s closing narration is the line that should stop being printed.

## Headroom is scraped, and is the one range-level figure

Every range page states `1.95m (6'5") headroom` in its own highlights, and FMLV holds
1950mm on all 26 — the brochure confirms 1.95m for every model of every range going back.
It is read off each page rather than hard-coded so a range that changes it, or a page that
stops saying it, comes out narrated instead of silently wrong.

## Width: the JSON, not the construction prose

The Sprite page's "Exterior & Construction" list says **`Overall body width 2.25m/7'5"`**
and it is wrong. That page's own JSON, the quick guide and FMLV's baseline all say 2.23m
for all four Sprites; 2.25m is the figure Swift use for the Challenger — a CMS
copy-paste. Conqueror Grande's prose says 2.45m where its JSON says 2.46m on all four.

Per-layout JSON is the only width source read. Covered by a test that asserts the wrong
prose figure is present in the fixture and absent from the output.

## `optionalWeightPlateUpgrade` is not the MTPLM

Every layout carries one — 1300kg beside the Alpine 4's real 1247kg. It is an optional
dealer upgrade, and the site says so: *"If a higher payload is required, then the MTPLM
can be increased on certain models."* `docs/adapters/README.md` says record the base
figure, so nothing here reads it. Named in the docstring and covered by a test because it
sits immediately beside `weightMtplm` in the same object and is the obvious wrong pick.

## Everything is rigid, and the micro trap is live

All 26 are `type_rigid`. The micro rule needs **the manufacturer's own naming and MTPLM
of 1250kg or lower**, and the weight half fires here: Challenger 390 is 1118kg and Sprite
Alpine 4 is 1247kg. Swift market no micro. Their one genuinely small caravan, **Basecamp**
at 1043kg MTPLM, was held by FMLV as rigid too — and is discontinued for 2027.

## The bug the first live run found — in the pipeline, not the adapter

The first run diffed 26 caravans against the **motorhome** export and classified all 26 as
new and all 31 motorhomes as disappeared.

`cli.latest_export` takes a `vehicle_class` and its docstring is explicit that "the area
is part of the filter, not a nicety", predicting this exact symptom. It was correct and had
three tests. **The one line calling it from the `run` command omitted the argument**, so
every caravan run silently took the motorhome default. The apply path passed it correctly;
only `run` did not.

Bailey never showed it because `data/exports/28_Bailey/` only ever held the caravan sheet,
so newest-file-wins happened to be right. It *had* already bitten once —
`deploy/discard_run.py` exists precisely because Bailey's first caravan run recorded 24
invented products this way on 3 September 2026 — but the cleanup script was written and the
root cause was not fixed. Swift's directory holds both sheets, which is what exposed it.

Fixed by passing `vehicle_class=vehicle_class`, and covered by
`test_the_run_command_asks_for_the_baseline_of_the_area_it_is_sweeping`, which drives the
command rather than the function, because the seam was the bug. The bad run was discarded
with `deploy/discard_run.py 65 --apply` (57 product rows: 31 motorhomes misfiled as
caravans plus the 26 real caravans that had matched nothing) and re-run.

## First run — 3 September 2026, run #65

26 scraped against 26 baseline; **24 changed, 2 new, 2 disappeared**, 172 proposals, 234
fields verified unchanged. Everything predicted by the survey, and nothing else:

- **2 new:** Conqueror 565 (the guide's "NEW 565 LAYOUT FOR 2027") and Sprite Grande
  Quattro FB (the guide's "For 2027, a new 8ft-wide model").
- **2 disappeared:** Basecamp 2 and Conqueror 645 — the latter replaced in the base range
  by the 565, with Grande 645 continuing.
- **26 price rises**, e.g. Sprite Alpine 4 £21,645 -> £22,585, Elegance Grande 835
  £49,695 -> £51,935.
- **2 twin-axle corrections**, both `True` -> `False`: Challenger Grande 580 and Conqueror
  Grande 580. Three Swift sources agree against FMLV's field — the 2027 JSON's
  `axleType`, the 2027 guide's per-range axle counts, and the 2026 brochure's own "Number
  of Axles" column, which already said 1. This is the adapter working.
- **Real 2027 spec changes:** Conqueror 480 lengthened 6450 -> 6530mm with MTPLM 1459 ->
  1460; Conqueror 580 MTPLM 1660 -> 1675 and MRO 1503 -> 1518. All corroborated by the
  guide.
- **96 in-scope fields not found** = the four then-withdrawn fields times the 24 products
  with a baseline, each a flagged no-op that preserves FMLV's figure. The two new products
  have no baseline to preserve, so those four stayed blank on them. From 4 September this
  is **72**, payload having become a derived field rather than a gap.

## No layout flags, and the bed-size tables do not change that

The quick guide carries a **structured bed-size table** per range, one row per model,
naming positions explicitly — Front Double, Front Single (Nearside/Offside), Side Single,
Side Bunk, Side Double, Side Fixed Upper/Lower Bunk, Rear Double, with dimensions. It is a
table, not marketing prose, and it covers all 26 models. That is more than Bailey's pages
give, so it was examined for the layout flags on 3 September 2026 and **rejected**.

It gives bed *position and size*, not bed *type*, and the FMLV columns need type:

- **A caravan's front lounge converts to a double on almost every model**, so "Front
  Double" appears on nearly all 26 rows. The table cannot say whether it is a
  `fixed_bed` or one of the `make_up_beds` — which is the whole distinction.
- **`island_bed` against `transverse_bed` is orientation**, and the table never states it.
  Bed dimensions hint at it, which is exactly the "enough to guess from and not enough to
  be right" trap `bailey_caravan.py` refuses.
- The guide's one fixed-bed signal is a **range-level footnote**, `^Fixed beds` against
  equipment lines like "Exclusive Duvalay Duvalite Strato mattress^". It marks which
  equipment applies to fixed-bed models, not which models have one.
- Nearside/offside is stated, and per the requester's standing rule it is never recorded
  from a table without the drawing.

So Swift's caravans take the same line as Bailey's: no layout flags, and
`sleeping_area_*` stays blank. Filling them needs the floorplan drawings, which is the
habitation-layout-pack job, not the adapter's. Recorded here so the bed-size table is not
re-proposed as a shortcut to it.

## Re-verify after the NEC show

Same caveat as the motorhomes: the guide is stamped "Issued September 2026" and carries
*NEW* flags on the Conqueror 565 and the Sprite Grande. Specs may still move. If a
2027 full brochure ever appears, the four withdrawn fields become collectable again — but
`/brochures/` must still never be read for product data.
