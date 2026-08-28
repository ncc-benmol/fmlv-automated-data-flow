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

## Not emitted, and why

- **`body_type`** — as in the brochure version. With no published height the campervan
  height-threshold rule has nothing to work on for the Carrera and Trekker, and FMLV's
  existing values are better than a guess. Merlin's 9 new products need it filled by
  hand, as Chausson's new products did — and the page gives whoever does it the one fact
  that is easy to get wrong: **the elevating roof is standard on 212, 244, 264 and 274
  only.** With heights of 2720/2790, comfortably above the ~2680mm the
  [README](README.md) calls characteristic of an extended high top, that makes the four
  `2xx` models `campervan_high_top_elevating_roof` and the five `1xx` models
  `campervan_high_top`.
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

## Re-verify after the NEC show

Swift are mid-launch: the guides are stamped "Issued September 2026", three vehicles
carry *New for 2027* badges, and prices are already up. Specs may still move.
