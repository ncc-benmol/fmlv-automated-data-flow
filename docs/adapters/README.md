# Adapters — the general pattern

Six data points now: [Adria](adria.md), [Morelo](morelo.md), [Swift](swift.md),
[Sunlight](sunlight.md), [Rimor](rimor.md) and [Auto-Trail](auto-trail.md). They differ
enough that the ordering of the questions below matters more than any of the individual
answers.

## Data rules that apply to every manufacturer

These are **domain decisions, not technical ones.** They come from the NCC side, they hold
for every adapter present and future, and they were previously scattered across individual
brand surveys where the next person would not find them. Do not re-decide them per
manufacturer — if one genuinely does not fit, raise it rather than quietly diverging.

### One column, so record the base vehicle

FMLV has a single column per spec. Where a manufacturer publishes two figures for the same
measurement, record the vehicle **as standard** — not the variant with optional or bolt-on
equipment. The base figure is the honest one, and it is how vehicle specs are
conventionally quoted.

| Spec | Rule | Example |
|---|---|---|
| **Width** | **Exclude wing/door mirrors, and exclude awnings.** Where both figures are given, take the narrower body width. | Auto-Trail `Width (excl. door mirrors) 2373mm` with `(2408mm with awning)` → **2373** |
| **Berths** | **The lower figure of a range.** The higher figure is usually reached only with options. | `Sleeps 4-6` → **4**; Rimor's `4 (+1 opt)` → **4**; Sunlight's `2 - 3 OPT` → **2** |
| **Seats** | The standard figure, on the same reasoning | `Seatbelts 4-6 (inc. driver)` → **4** |
| **Dual height / weight values** | Base figure by default, but confirm per case — a *no-cost* uprate is arguably not an "extra" | `Height 3030/3106mm` → 3030; `Max. gross weight … 3500/3650kg` → 3500 |

Whenever a single number cannot express the whole truth, carry the manufacturer's **raw
published wording into the `Provenance` snippet** — a reviewer needs to see `4-6` even
though `berths` records `4`. Sunlight and Rimor already do this.

> **Auto-Trail currently diverges and needs changing.** `auto_trail.py` takes the *upper*
> `Sleeps` figure, on the evidence that Auto-Trail's own `Max. No. of berths` row agrees
> with it on all 21 motorhome models. That establishes the true *maximum*, which is a
> different question from what the vehicle sleeps as standard, and the rule above governs.
> Note the upper figure is also load-bearing in that adapter's `_reconciles` self-check
> (it drops any product where `berths != stated_max_berths`), so the check must be rewired
> to compare the two published maxima with each other rather than against the recorded
> `berths`. Sunlight and Rimor already comply.

### Campervans are ordinary products with a different set of body types

A campervan needs **no special handling anywhere in the pipeline**. It is a `Motorhome`
record with the same fields, the same validation and the same required columns; FMLV's
specification criteria are identical. The only thing that differs is `body_type`, which
draws from the campervan half of `BodyType` rather than the motorhome half.

**The rule, from the NCC side, 16 August 2026.** Two independent questions, giving a 2×2:

| | No elevating roof | Elevating roof (pop-top) |
|---|---|---|
| **Standard / low roof height** | `campervan` | `campervan_elevating_roof` |
| **High top (extended roof)** | `campervan_high_top` | `campervan_high_top_elevating_roof` |

- **High top** means the roof line is *materially higher than the side windows* — visible at
  a glance in a photograph. A published height around **2680 mm** is characteristically an
  extended high top.
- **An elevating roof can sit on either body height**, which is why the fourth combination
  exists and why "has a pop-top" is not by itself enough to classify a van.

**Read it together with the base-vehicle rule above.** An elevating roof offered as a *cost
option* does not change what the vehicle is — Auto-Trail's Expedition Van lists
`Colour coded elevating pop-top roof … Cost option`, so it stays `campervan_high_top`,
while the Adventure lists the same line as `Included` and is therefore
`campervan_high_top_elevating_roof`. The word after the feature decides it.

**And silence means "option", not "standard".** Rule from the NCC side, 21 August 2026: if a
model's page does not state that the elevating roof is *included*, assume it is an option and
therefore not part of the standard specification. A pop-top is a headline selling feature —
a manufacturer fitting one as standard says so, and usually more than once — so an
unmentioned roof is a missing feature, not an undocumented one.

This is the opposite default to the missing-data rule below, and deliberately so. The
question is not "what is this vehicle's roof height?", which is unknown when unstated; it is
"does the standard specification include an elevating roof?", and *that* has a safe default,
because the base vehicle is the vehicle without the extras. Elddis is the worked example:
the CV20, CV40 and CV60 layouts mention a pop-top **zero** times and are plain high tops,
while the three CV80s say "comes with a pop-top" and get the elevating variant. FMLV held
Autoquest CV60 as `campervan_high_top_elevating_roof`; that was wrong, and the absence of
any mention is sufficient grounds to correct it.

Note the corollary: a model that prices the pop-top as an *alternative configuration* — its
own weights, its own berth count — is also offering an option, however prominently. The
three Whirlwind GTVs mention a pop-top six to eleven times each and still take the
fixed-roof body type and the fixed-roof berth count. The GTV 554 puts it in the label:

```
Overall Height Excluding Aerial: 2.61m
Overall Height Including Pop Top (If option is selected): 2.81m
```

**Which is also the rule for the height itself:** record 2610, not 2810. Where a
manufacturer publishes a second, taller figure conditional on an option, the base vehicle's
figure is the one FMLV holds — the same reasoning that takes the mirrors-excluded width and
the lower berth count. A raised pop-top is not the vehicle's height any more than an
extended awning is its width. Confirmed for Elddis on 21 August 2026, where the requester
also settled the classification: 2610 mm on a Peugeot Boxer **is** a high top, so the shared
`HIGH_TOP_ABOVE_MM = 2300` needed no adjustment — worth knowing, because 2610 sits below the
"around 2680 mm" figure quoted above and the temptation was to treat it as a plain campervan.

**Where the body height cannot be established, leave `body_type` unset** rather than
assuming a high top. The missing-data rule applies here as it does to any other field.

**And how the body is *built* is not the test — how it looks and what it measures are.**
Rule from the NCC side, 26 August 2026, on Wingamm's City Pro. That vehicle's own catalogue
says the bodywork "is not the sheet metal of the van, but a fiberglass monocoque", which by
construction makes it a coachbuilt exactly like the Oasi it sits beside; the requester
classified it `campervan_high_top` from the photograph and the copy, which calls it "a
camper live in, a van to drive" and says "the van" throughout. It is van-shaped, on van
external measures, and 2050 mm wide against the coachbuilts' 2240 mm.

So a moulded or composite body does not promote a van-shaped vehicle to a coachbuilt, and
the practical division of labour is: **whether it is a campervan is a judgement about shape
and proportions that an adapter should take as declared, while high top and elevating roof
stay derived** from the published height and the standard-fit wording. `wingamm.py`'s
`WingammProduct.body_type` is the worked example. Read the manufacturer's photograph before
reasoning from its construction paragraph — they can point opposite ways, and the picture
wins.

### Price is a guide price, so a consistent basis is preferred but not required

`rrp_pounds` is the **on-the-road price** where a manufacturer publishes one — the figure a
buyer sees and pays. Auto-Trail's price list makes this explicit, breaking out ex works
excluding VAT, VAT, ex works including VAT, and on the road; the last is what FMLV records.

**Where the basis is not published, record the price anyway.** FMLV presents this as a
*Guide Price*, not a factual RRP, so a basis that varies between manufacturers is tolerable
— and often unavoidable, since many manufacturers never state whether a figure is ex works
or on the road. Leaving the field blank because the basis is unstated serves a reader worse
than an approximate figure does. Decision from the NCC side, 16 August 2026.

The scale supports it: Auto-Trail's on-the-road premium is a flat £635, which is 0.9% of a
£69,005 motorhome, while the fixed EUR→GBP rate in `morelo.py` can drift several percent in
a year. The inconsistency being accepted here is far smaller than one already accepted.

**But record the basis in the survey document and the registry `notes` wherever it is
known.** It costs nothing, it documents the inconsistency rather than hiding it, and it
guards against a failure the guide-price framing does not cover: if a manufacturer changes
basis between runs, every one of its products shows a price change that is not a price
change. Auto-Trail moving from on-the-road to ex works would look like £635 off all 37
layouts. With the basis recorded that is diagnosable in seconds; without it, it reads as a
real price move.

**Whatever the manufacturer publishes on the page is the guide price, and it goes into
`rrp_pounds`.** Rule restated from the NCC side, 20 August 2026: the field is *labelled*
RRP, but what FMLV offers a reader is a guide price, so the published figure is taken as-is
rather than adjusted towards some notional recommended retail price.

**FMLV carries that one price in two columns, and no adapter should read the second.**
The column headings are not meaningful — the figure is neither strictly an RRP nor
strictly a minimum — and `price_min_range_pounds` holds the same figure as `rrp_pounds`
on **every product in every real export**: 179 of 179 active rows across six
manufacturers on 20 August 2026, never differing, never one blank. Its companion
`price_max_range_pounds` is blank throughout, so there is no genuine price *range* being
expressed at all.

So `price_min_range_pounds` is deliberately **out of scope** in
`config/field_guide_motorhome.csv`, and `output.build._mirror_guide_price` copies
`rrp_pounds` into it when the upload row is built. Deriving it at *output* rather than at
*collect* is the whole point: an in-scope field no adapter populates prompts the reviewer
to confirm it by hand on every matched product, and collecting it instead just replaces
that with a second, always-identical price row to accept. Neither is worth a reviewer's
attention. Mirroring at the end keeps both columns in step with whatever price they
actually approved.

**A brand with no published price gets no mirrored value.** Swift, Rimor and Chausson
publish none, so both columns stay blank rather than being filled with a figure nobody
read.

### A figure that could not be found must be visible, and must never be inherited

Where a manufacturer normally publishes a spec and it is **absent for a particular model**,
the run must say so and the upload must leave it **blank**. Never carry the previously held
value forward on the assumption it is still correct: once it is in FMLV, an inherited
figure is indistinguishable from a confirmed one, and stale data presented as current is
worse than an obvious gap a human can chase.

This does **not** mean deleting figures a manufacturer never publishes at all — Morelo
publishes no berths, Swift and Rimor no prices. Those stay as they are. The rule is about
gaps *within* the data we do collect.

**Not yet implemented.** Two things stand in the way, and they are worth understanding
before relying on this:

- `diff/compare.py` iterates only `extracted.provenance`, so a field the adapter did not
  find is never compared and never proposed.
- `output/build.py` builds the upload from the baseline row and applies approved changes
  on top, so an un-proposed field keeps its old value.

Fixing it means separating two cases the model currently conflates: **"never attempted"**
(Adria's adapter never looks at the ~40 layout flags, and those must keep their baseline
values — this is why the present design exists) versus **"attempted and not found"** (the
weight was searched for and is absent). Only the second should propose a blank. New
products already behave correctly, since there is no baseline to inherit from, and
`validation.py` flags the blank as `missing_required` — but only for a field the adapter
attempted at all; see the next section for the third case, which is silent.

### Spell the base vehicle FMLV's way, not the manufacturer's

`base_vehicle_manufacturer` is compared against FMLV's own stored string, so the spelling
decides whether a run confirms the field or proposes a rename. **FMLV holds `Mercedes` —
never `Mercedes-Benz`** (35 rows across Adria, Bürstner, Coachman and Moto-Trek; the
requester confirmed it 27 August 2026: "we say Mercedes not Mercedes Benz in FMLV, meaning
the same thing but shorter"). The full legal name proposes a pointless rename on every
existing product and leaves every new one inconsistent with the rest of the database.

The second rule, confirmed the same day: **`Citroën` with the diaeresis, for Chausson and
every other brand.** Chausson reads its make from a CSS class (`porteur picto citroen`),
which cannot carry the accent, so nothing but an explicit mapping can recover it.

**Match the source's spelling, then record FMLV's — and do it in one place.**
`base.fmlv_base_vehicle` holds the whole mapping and every adapter routes its make
through it, so the decision is made once rather than thirteen times. That is precisely
what went wrong: four adapters each picked a spelling locally, and every choice was
reasonable in isolation. An unrecognised make passes through **unchanged rather than
blanked** — a chassis nobody has met yet is likelier than a parse error, and this is a
`schema.REQUIRED` field.

The makes in the baseline exports as of August 2026 are `Fiat`, `Peugeot`, `Ford`,
`Mercedes`, `Citroën`, `Renault`, `MAN` and `IVECO`. Add a new spelling to the map, not to
an adapter.

`tests/adapters/test_registry_wiring.py` asserts the mapping and, separately, that **no
adapter setting `base_vehicle_manufacturer` bypasses the helper** — so a new adapter
picking its own spelling fails a test rather than reaching a reviewer.

**Still unreconciled:** `bailey.py` once proposed `AL-KO` — a chassis maker, not a base
vehicle — which was correctly rejected and is recorded in [`bailey.md`](bailey.md). It is
deliberately *not* in the map: mapping it would legitimise it.

### A field is only real if it has provenance

`ExtractedMotorhome` carries the value and the provenance separately, and **the provenance
dict is the pipeline's only record of what the adapter looked at.** Both consumers key off
it, not off the model:

- `diff/compare.py` compares only the fields the dict names. A value set on the model but
  not registered is never compared against the baseline and never proposed — so on an
  existing product it is also never *confirmed*, and the baseline's own value carries
  through untouched however wrong it has become.
- `store/changes.py` proposes only those fields for a `NEW_PRODUCT`, and `output/build.py`
  seeds a new product's row with nothing but `manufacturer`, `manufacturer_display_name`,
  `manufacturer_range` and `model`. Anything else that is not proposed lands **blank**.

So an unregistered field fails in the way that is hardest to notice: correct-looking on
every product FMLV already holds, blank on every genuinely new one. Bürstner 27 August
2026 — `base_vehicle_manufacturer` was set for all 20 layouts from the first run and
registered for none, so run #11 proposed it 0 times; the 13 with a baseline row looked
right and all 7 new layouts arrived with a REQUIRED field empty. The same omission was
sitting in `morelo.py` and `sunlight.py`.

**Register every field you set, including the ones that come from a per-range constant
rather than a parsed cell.** A constant is still a claim about the vehicle, and a reviewer
needs to see what it rests on — and where the document does state it somewhere, read it
from there and keep the constant as a cross-check, so a chassis change is caught rather
than asserted over. Note the qualification this puts on the section above: new products
behave correctly only for a field the adapter *attempted*. Set-but-unregistered is a third
case, and it is silent in both directions.

### Model year rolls over gradually, July to early September

The transition varies by brand and is driven by the show calendar: next year's models
appear at the **Caravan Salon in Düsseldorf in early September** and at the **NEC in
Birmingham in October**, and only the following year's models are shown — so manufacturers
settle the range just before. Material published from around August onwards is taken to be
the *next* year's range.

Three qualifications: trust what the manufacturer actually publishes; expect two model
years to be live at once during the window; and **re-check at the end of September**, when
revisions often arrive. Morelo and Sunlight had both moved to MY2027 by 6 August 2026
while Auto-Trail was still publishing "2026 SEASON" — the whole spread in one snapshot.

### A "non-core" brand's UK site is a deliberate subset, not a partial rendering

Some European manufacturers are **non-core** to the UK market: Etrusco, Bürstner, Carado and
Eriba are Erwin Hymer Group brands of which only **a selection of the full European range** is
sold here. Where such a manufacturer publishes a market path — Etrusco's is `/gb/en/` — that
path **is** the UK range, and it should be taken as authoritative rather than reconciled
against the European roster, which lists models the UK does not get.

Two practical consequences, from the NCC side on 19 August 2026:

- **Do not treat a shorter UK roster as evidence of a parse failure.** It is the point.
  Chausson makes the same trap concrete from the other direction: its UK and global sites are
  different ranges *in both directions*, seven models the UK lacks and one it uniquely has.
- **For these brands the website is the source of truth, not the manufacturer.** Asking Erwin
  Hymer directly is possible but slow and undependable, so the strategy is to build against
  the site, record the model year, and re-run when the site changes — rather than to write to
  the contact, which is the right move for Coachman and Chausson but not here.

### The website overrules the PDF, and a document's year is what the page says

> **One documented exception, Elddis, 25 August 2026.** The rule below rests on a reason —
> a PDF is usually the last thing updated, so it is usually the stale one. Where that
> reason demonstrably does not hold, the rule does not either. Elddis's website publishes
> the *base* range's weights on every Evolve page, byte for byte, while its current 2026
> brochure gives the real figures, internally consistent and matching the equipment
> difference. There the PDF wins, and `elddis.py` says why in `apply_brochure_weights`.
>
> The test to apply is not "which source is newer" but **"can I show one of them is
> wrong?"** — here, that the Evolve figures are a different vehicle's, and that every
> non-Evolve range agrees between the two sources exactly. Diverge from a rule only with
> that kind of evidence, and write it down where the next person will see it.

Where a site and its downloadable documents disagree, **the site wins**. A PDF is usually the
last thing on a website to be updated, so a price list can be a model year behind the pages
around it. Rule from the NCC side, 19 August 2026.

**Establish a document's model year from the page that links it, not from its filename.**
Etrusco's price lists are served from `etrusco_pim_pricelist_2027_atvi_uk.pdf` and carry
`ENG - 2027` in their own footer, yet the download page labels them **2026** — the 2027 is an
internal PIM asset code. They are a model year behind the site: they lack four of the families
it lists, and their weights are last season's. Building on them would have put year-old
figures on the whole range while missing a tenth of it.

When checking, read what a **customer** sees. The year sat in the card's title element; the
text inside the `<a>` tag was only the word "Download".

### A source can be retired outright, and a clean skip hides it

Every rule above is about choosing between sources that exist. Swift, 28 August 2026, is
the first case of a source simply **ceasing to exist mid-life**, and the failure mode is
worth knowing before it happens to another adapter.

Swift retired the annual brochure. For 2027 the motorhome, campervan and caravan
catalogues were all replaced by a two-page *quick guide*, and the per-layout data moved
onto the website. `swift.py` had been built on the brochure's "Specification at a glance"
table, matched `_brochure.pdf`, and so collected **zero products**:

```
[Motorhomes] SKIPPED: no brochure link found on https://www.swiftgroup.co.uk/motorhomes/
0 product(s) collected
```

Three things follow, none of them about parsing.

**A zero-product run is a *successful* run.** Narrated skips, no exception, status
`succeeded`. That default is right — on any given run a missing link is usually a
transient site change, and raising would be worse — but it means a permanently dead
source is indistinguishable from a quiet week. When adding a manufacturer, note its
expected product count somewhere a human will compare against, which is what
`config/manufacturers.csv`'s `notes` is for.

**Presence in the review app's trigger dropdown is not health.** That list is filtered by
`adapter_for()`, which only checks a module is registered under the manufacturer name.
Swift stayed in the dropdown throughout, and looked entirely normal.

**The superseded document usually stays live**, which makes the obvious fix the wrong
one. Swift's 2026 brochure still resolves — 20MB — and is still linked from
`/brochures/` beside 69 other archived PDFs. Loosening the pattern enough to match
`2027-swift-motorhome-quick-guide.pdf` also matches
`2026_swift_motorhome_brochure.pdf`, and would have proposed last season's whole range
as current: plausible, internally consistent, entirely stale, and nothing downstream
would flag it.

So when a document pattern stops matching, **do not widen it**. Establish what the
manufacturer publishes *now*, from the pages a customer sees, and anchor the new pattern
on whatever distinguishes the current document from the archive — for Swift,
`quick-guide` rather than `.pdf`. Then add a negative test that feeds the adapter the
superseded URL and asserts it is not matched; `test_swift.py` has one, and it is the most
valuable test in that file.

### No single menu is a complete roster

**Take the list of ranges from the sitemap, then reconcile it against a second count.** Rule
from Etrusco, 19 August 2026, where every individual source was short:

| Source | Families listed | Missing |
|---|---|---|
| Page navigation | 5 of 8 | the three below |
| `/gb/en/modeloverview` | 7 of 8 | `semi-integrated-ford`, four layouts |
| `sitemap.xml` | 8 of 8 | — |
| The 2026 price lists | 7 of 8 | the same family, plus stale weights |

Two failure modes, and they compound:

- **A range can be in no menu at all.** Etrusco's Ford semi-integrateds are their newest
  family and appear only in the sitemap. Nothing on the site links them.
- **URL shape is not uniform.** Six Etrusco families sit at `/models/<segment>`, two at
  `/models/model-overview/<german-slug>`. Code that builds a URL from a pattern finds the six
  and silently misses the two — and anything deriving meaning from the path (body type, for
  instance) needs a rule that survives both shapes. Prefer the manufacturer's own naming, such
  as the model letter every Etrusco layout carries.

The reconciliation is the point, not the sitemap. A range index that publishes a count, a card
per range, or a "from" price per range gives a free check that the roster is complete: seven
overview cards against six collected families is what exposed the gap. **An absence you cannot
explain is a gap in the search, not a fact about the manufacturer** — do not write it up as a
discontinued range until a second source agrees.

### Let the FMLV export decide the range and model strings, not the website

**Fetch the baseline export before choosing what to put in `manufacturer_range` and `model`.**
`fmlv fetch-export "<name>"` needs only `ncc_supplier_name`, and it answers a question no amount
of reading the manufacturer's site can: what FMLV already calls these vehicles.

Etrusco's site markets `CV-Model Plus` and names the vehicle `CV 600 DB+`. FMLV holds range
`CV`, model `600 DB+`. Emitting the site's form would have cost twice over — a weaker fuzzy
match on every product, and then a proposed range rename on all 27 that did match. The
manufacturer's own family name still belongs in the provenance, where a reviewer can see it.

**Two things to check in the export while it is open:**

- **How the identity is split.** Which half carries the range letter, prefix or trim name.
- **Whether the existing data is right.** FMLV recorded Etrusco's whole V range as coach built
  low profile; they are 2870 mm Ford vans. Proposing the correction is the adapter working, not
  a parse error — but know which of the two you are looking at before accepting it.

**If you propose one half of the identity, propose both.** The two are a single name split
across two columns, and moving one without the other corrupts it. Bailey is the worked
example: FMLV holds the XL layouts as range `Adamo XL` + model `I`, the site as range
`Adamo` + model `XL-I`. The adapter proposed the range alone, so accepting it left the
baseline's `I` in place and wrote back **`Adamo I`** — the XL gone from the vehicle's name
altogether.

**And some renames cannot be delivered at all.** A rename that removes most of the
identity's words takes the product below the matching threshold, so the run proposes it as
*new* and reports the original as *disappeared* — an upload would then create a duplicate
of a product the NCC already holds. Wingamm 26 August 2026: FMLV files its Brownie under
range `Coach Built low profile`, a body type in the range column, and correcting it to
`Brownie` scores `{brownie}` against `{coach, built, low, profile, brownie}` — **0.200**.
Run #30 orphaned `product_id` 5855 exactly as arithmetic predicts.

**So check the score before proposing an identity change, and where it fails, emit the
baseline's own wrong value with no provenance on either half.** Nothing is then proposed,
the product matches at 1.000, and its weights and dimensions update normally; the rename
becomes a one-line manual edit on the FMLV site, narrated every run until someone makes it.
Wingamm's City Pro is the same class of error and *is* proposed, because `Campervan` +
`City Pro` to `City Pro` + `City Pro` scores 0.667 — the asymmetry is the matcher's, not the
manufacturer's.

Note this closes the other door too: Etrusco shows `DEFAULT_THRESHOLD` cannot be *raised*
to reject its bad matches, and 0.200 is far below anything that could be *lowered* to admit
this one while still separating real vehicles. A rename is a different operation from a
match, and the token bag cannot express it.

**And `model` will not warn you.** `compare_fields` walks only fields that *have
provenance*, while the in-scope missing-field check fires only where the adapter found
**nothing at all** — so a `model` that was read but never given a provenance entry is
neither compared nor reported missing. It falls between the two and is silently invisible.
Record provenance for both halves, and say in each snippet that they belong together, so a
reviewer accepting one knows to accept the other.

**And know the matcher's limits.** `diff/matching.py` scores a Jaccard similarity on the
range-plus-model word bag and accepts anything from 0.5 up. It tokenizes letters and digits only,
so a trailing `+` disappears and `6.6` collapses to `{6}`. Two consequences, both seen on
Etrusco's first run:

- **A differing bed code is one token of three or four**, so `6.9 SF` against `6.9 BB` scores
  0.600 and `600 SB` against `600 BB` scores 0.500 — both matched.
- **A differing number can score higher still**: `6.8 SF` against `6.6 SF` scores 0.750, because
  the repeated digit in `6.6` collapses to a single token.

All three were *replacement* vehicles reported as revisions of the ones they replaced. The names
tell you: each shared one half of its identity — number or bed code — and differed in the other.
**A base vehicle changing manufacturer is the surest tell**, since chassis do not change under a
vehicle mid-life. Check any match whose proposal includes one, and any where only half the model
name lines up.

**Do not try to fix this by raising `DEFAULT_THRESHOLD`.** Adria's documented good match scores
**0.667** — lower than Etrusco's worst bad match at 0.750 — so the two cannot be separated by a
number. Anything high enough to reject the Etrusco pairs orphans Adria's product ID. A
per-manufacturer threshold would work (Etrusco's good matches are all 1.000) and is the shape to
reach for if a third brand hits this.

**A wrong match also hides a discontinuation**, which is easy to miss when reading the counts: a
claimed baseline row cannot also be reported as disappeared. Etrusco's run said 4 new and 3
disappeared where the truth was 7 and 6.

## Start here: is there a brochure or price list PDF?

**Ask this before looking at the website's rendering behaviour at all.** It was the
last thing tried for Adria and the first thing that worked for the four after it:

| | Adria | Morelo | Swift | Sunlight | Rimor | Auto-Trail |
|---|---|---|---|---|---|---|
| JavaScript needed | Yes (Livewire, scroll-triggered) | No | No | No | No | No |
| Fetches | 2 per product | 2 total | 2 per catalogue | 2 per catalogue | 1 per product + 1 per range | 3 per range |
| Products | 54 | 61 | 30 | 26 | 41 | 37 |
| Price | AJAX JSON | In the PDF (EUR) | **Not published anywhere** | In the PDF (**GBP**) | **Not published anywhere** | **Price list is a scanned image** |
| Berths / seats | Per-product PDF | Not published | In the PDF | In the PDF | In the HTML | In the PDF |
| Weights + dimensions | Per-product PDF | In the PDF | In the PDF | In the PDF | Dimensions in the HTML; MTPLM only, from the catalogue | In the PDF |

Three of five publish everything in a PDF, and where they do, the PDF has been the
better source every time — cheaper (one fetch, no browser, no per-product work) *and*
more complete than the website.

**But ask the question, don't assume the answer.** Rimor is the counter-example, and it
is worth being precise about *why*, because the obvious reading is wrong.

Rimor's catalogue is not thin. It publishes everything the website does **plus**
wheelbase, MTPLM, engine, tank capacities and equipment — on field count it beats the
HTML comfortably. What it cannot do is say **which model a number belongs to**. Its spec
pages set two or three models side by side and print a value once where it spans several
columns:

```
HORUS 12    HORUS 38    HORUS 45      <- three models
Outside length (mm) 5413 5998         <- two values
```

pypdf returns that whole row as a single run at a single x, so there is nothing to
recover the spans from. The numbers are present and unattributable.

The website wins because **attribution is free**: one URL per model, one set of numbers
on it. That is what the question at the top of this section is really asking. "Is there
a PDF?" is a proxy for *where can I get many products in one fetch, with each number
unambiguously attached to one of them?* For Adria, Morelo, Swift and Sunlight the PDF
was that place. For Rimor it is the place where attribution collapses, so the PDFs are
demoted: the catalogue is kept for the two fields that are **constant down the page**
(MTPLM, engine) and so need no alignment at all, and the leaflets — which genuinely do
carry a strict subset of the HTML — are kept only as the cross-check.

Two things to carry forward:

- **Rank sources by attribution, not by field count.** A document with fewer fields and
  one product per page beats a richer one whose columns cannot be separated.
- **A PDF that looks parseable may not be.** Check whether the value you want varies per
  column *before* planning to read columns. If it does, and the layout merges cells, no
  amount of effort recovers it — but a page-constant value is still safe to take.

Adria's shape, a JS-rendered catalogue plus a per-product PDF, remains the other
exception.

**Auto-Trail is the opposite pole from Rimor**, and worth knowing as the best case. Its
per-range spec PDFs give each model a run of *whole pages* with the model name as a
running header — no columns at all, so attribution is free in the PDF and every
alignment defence below is unnecessary. When a document looks like this, the parsing
risk moves entirely from "which column is this?" to "which *label* is this?" — and
Auto-Trail's labels are the trap: `Max. gross train weight` sits one row from
`Max. gross weight` and is 1250–2500 kg larger, one model omits the latter entirely, and
the campervans call it `Max. authorised weight` instead.

Two more general lessons from it:

- **A PDF being present is not the same as its numbers being extractable.** Auto-Trail
  publishes a price and options list, and it is a rasterised image: `extract_text`
  returns headings and footnotes, and the whole of page 2 yields four text runs, none of
  them a price. Check `extract_positioned_text` on a page you *expect* to be dense
  before concluding a document is a usable source — an almost-empty page is the tell.
- **A stated roster beats any heuristic for finding record boundaries.** Every
  Auto-Trail document names the models it covers (`Applicable to Excel 620S, 620G,
  690T`). Matching headings against that roster both filters out the section headings
  that look identical (`POWER`, `SAFETY`) and gives a free completeness check. Look for
  a document's own table of contents before writing a pattern for "what a record header
  looks like".

Two follow-on questions the later surveys added:

- **Is there a market-specific edition?** Sunlight is German but publishes a UK & Ireland
  price list in sterling, which removes the exchange-rate problem that is the single
  worst piece of data in the Morelo adapter. Check before converting a currency.
- **Does the downloads page list more than the current document?** Every one so far has
  had a near-miss sitting beside the file actually wanted — Morelo's catalogue in a
  directory called `kataloge_preislisten`, Swift's opaque media key, Sunlight's three
  superseded model years *and* a differently-named glossy catalogue. Match precisely,
  prefer the newest, and rediscover per run rather than hardcoding.
- **Ask the PDF question against the `sitemap.xml`, not against the pages you have
  fetched.** Elddis's survey concluded "there is no PDF anywhere on the site" on the
  strength of finding no `.pdf` link on any page it had fetched. That was wrong: the
  downloads page holds 30+ PDFs, and it is an **orphan** — in no menu, linked from nothing,
  reachable only from the sitemap or a search engine. A link-following search cannot find
  an unlinked page by construction, so absence of a link is not absence of a document.
  Grep the sitemap for `brochure`, `download`, `specification` and `price` before concluding
  a manufacturer publishes nothing. It cost a wrong conclusion in the write-up and, worse,
  nearly cost 17 products their correct weights.

  Elddis has three such orphans — `/help-support/brochures` and two `*-specification`
  comparison pages listing every layout with its price. Orphan pages are *useful*: they are
  often exactly the roster or comparison view an adapter wants, and nobody links to them
  because they are not part of the sales funnel.

### If the document is behind a name/email form

Two things, in this order.

**First, check whether the form is actually protecting anything.** Rimor's catalogue is
fronted by a lead-generation form (name, email, city, three consent boxes) and the PDF
itself sits unauthenticated on a public asset path — no token, no cookie. The form was
a front door, not a lock. A web search for the filename found it in a minute. Try that
before anything else; a gated-looking document may not be gated at all.

**If it really is gated, use Ben's details.** `config/reviewers.csv` holds them, and
there is standing permission to submit them to a manufacturer's catalogue or brochure
request form. This is what the form is for: a real person at the NCC asking a
manufacturer for their catalogue.

Two rules when doing so:

- **Never invent details.** Fabricated names and addresses go into a real CRM under a
  real consent flow, and they poison the manufacturer's data. Use the real ones or
  don't submit.
- **Tick only the consent that is required.** Read the labels: there is usually one
  mandatory "I have read the privacy policy" box and one or two optional marketing and
  profiling consents. Rimor's form validates `privacy_1` only. Leave the optional ones
  unticked — the permission is to request a document, not to sign the NCC up for a
  manufacturer's marketing.

Say in the survey document which route was used, and if a form was submitted, say so
explicitly at the checkpoint.

## Then: parsing a spec table is where the real risk is

For a PDF-sourced manufacturer, finding the numbers is easy and *attaching them to the
right product* is hard — and it fails silently. Swap two columns of a Morelo page or
misjoin two Swift tables and you get plausible, internally consistent motorhomes
carrying each other's weights and prices. Nothing downstream flags it and a reviewer
accepts the change.

Three defences, all of which earned their place:

- **Never infer a column from reading order alone.** pypdf emits runs in content-stream
  order, which on some Morelo pages is right-to-left. `fetch.pdf.extract_positioned_text`
  gives coordinates — but note that pypdf also fails to place *some* runs (reporting
  (0, 0)), so coordinates can't be trusted blindly either. See [`morelo.md`](morelo.md)
  for the rule that satisfies both.
- **Parse runs, not lines, wherever cell boundaries carry meaning.** A line is a lossy
  rendering of a table: joined up, `CLIFF 540 V` and `CLIFF 540` followed by a stray
  `V` are the same string, and Sunlight sells both. Where a value can contain a space,
  run boundaries are the only thing that says where a cell ends.
- **Look for arithmetic the manufacturer publishes against itself.** Morelo and Swift
  give MTPLM, MRO *and* payload, so `payload == MTPLM − MRO` is a free check on the
  parse — per column for Morelo, per join for Swift. Sunlight publishes no payload but
  prints each mass with its ±5% tolerance band, which is self-consistent in the same
  way and serves the same purpose. Look for *some* redundancy in the document; there
  has been one every time. Products that fail it are dropped rather than proposed. It
  catches misaligned columns, not mislabelled ones.

  Rimor publishes no payload *and* no MRO, so its redundancy is **cross-document**: the
  range leaflet republishes every layout's `length x width`, and the body-style listing
  republishes the seats and berths that the model's own page states. Where one document
  has no internal arithmetic, look for a second that says the same thing twice — and
  compare as an **unordered multiset**, since the leaflets extract in scrambled reading
  order and any position-dependent comparison would be checking noise.

One trap common to all of them: when slicing a row's values, **stop at the next row's
label** rather than taking a fixed count. A short row otherwise swallows the following
label, padding the count back to what was expected and defeating the very check meant
to catch it.

Anchor row patterns on whichever end of the row is **typed and fixed-width**. Swift's
rows have ragged engine prose on the left and a fixed run of metres/integers/`kg` on the
right, so every pattern anchors right and never parses the left at all.

## What Adria's survey found

Kept because it is still the pattern for a JS-driven catalogue, and some manufacturer
will have one.

A model-range page's plain HTML is nearly useless: no price, no specs, sometimes not
even the layout list, because the actual data loads via client-side JS after the page
renders. This should be checked first for every manufacturer — fetch the page with
plain `httpx` (`fetch/http.py`) and look for the numbers before reaching for a browser.

Two different pieces of data lived in two different places, discovered by two different
means:

1. **Layout, trim, berths, price** — inside a JSON blob attached to a scroll-triggered
   AJAX call (a Laravel Livewire component, in Adria's case), invisible to a plain HTTP
   fetch and invisible to a browser fetch that only waits for `networkidle` — it had to
   be found by watching the network panel while actually scrolling the rendered page.
2. **Weights and dimensions** — nowhere in that JSON. Found only by chasing a "download
   technical data" button through to its PDF, which turned out to sit at a predictable,
   unauthenticated URL keyed by a product ID that *was* in the JSON. Once known, that
   PDF is a plain deterministic fetch — no browser needed for it at all.

**A scroll-triggered load can be missed by scrolling too fast, and it looks identical to
having no data.** Adria's three 60Y range pages returned zero captures for a reason that
was not in the adapter at all: `BrowserFetcher` scrolled in 2000px steps against a 720px
viewport, which tiles a page with gaps, and the element carrying `x-intersect` is 20px
tall. It fell in a gap, was never on screen while the page was still, and its
intersection observer never fired. The same element on the ordinary range pages happens
to land inside a rest position — which is the only reason the adapter ever worked.

Two things generalise:

- **Never scroll further than a viewport per step.** `_scroll_to_bottom` now caps every
  step at half a viewport so consecutive positions overlap. Fixed in the shared fetcher,
  so no adapter has to know about it.
- **Narrate "no captures", because silence is ambiguous.** A page that yields nothing
  looks exactly like a page with no lazy-loaded data, so this presents as "those pages
  must be built differently" rather than as a defect. Any adapter capturing XHR should
  say out loud when a page it expected to fire made no matching call.

The general shape this suggests: **expect two fetches per product, not one** — a
JS-rendered page (or its underlying AJAX response) for identity/price/layout, and a
separate, often-plain-HTTP, document for the numeric technical spec. Don't assume the
spec sheet is reachable from a static URL pattern alone; it was only found by reading
what a real interaction (the "download" button) actually requested.

## Adapter interface

`adapters/base.py` defines the shared shape:

- `Provenance(source_url, snippet)` — where one field's value came from, for the reviewer.
- `ExtractedMotorhome(motorhome, provenance)` — a `Motorhome` plus a `{field_name:
  Provenance}` map. Not every field needs an entry.
- `Adapter.collect(http, browser, snapshot_dir) -> list[ExtractedMotorhome]` — one
  method, not fetch/parse split. For a JS-driven catalogue, deciding what to fetch next
  (e.g. which PDF) depends on content already fetched, so the adapter owns its whole
  fetch-then-parse sequence. Every fetch still goes through `Fetcher`/`BrowserFetcher`,
  so everything is still snapshotted to disk regardless (DESIGN.md §6.6).

`fetch/browser.py`'s `BrowserFetcher.fetch_with_capture()` is the one genuinely
manufacturer-agnostic addition this required: render a page, optionally scroll it in
steps, and snapshot any XHR/fetch response whose URL matches a substring. Scroll-
triggered lazy loading is common enough on modern marketing sites that this is written
as a generic capability, not something specific to Adria.

## What to check for the next manufacturer

- **Is there a brochure or price list PDF with a spec section?** Check this first — see
  the top of this file.
- Does the plain-HTML page already have the numbers? (Don't reach for the browser
  before checking.)
- If not, is the real data in a JS framework's own state/AJAX payload (React/Vue
  hydration data, a Livewire snapshot, a GraphQL call)? Read the rendered DOM's
  `<script>` tags for a state blob before assuming a browser render alone is enough —
  Adria's data only appeared after triggering a *scroll*, not just a load.
- Is there a "download spec sheet" / "compare" / "brochure" button? Follow it — it may
  resolve to a stable, unauthenticated, non-JS URL that's cheaper to fetch directly than
  scripting the interaction that produces it every time.
- Are weights/dimensions ever in the HTML/JSON path at all, or always PDF-only? This
  was Adria's answer; DESIGN.md §9 open question 6 expects this to vary by manufacturer.
- **Does the roster agree across the sitemap, the navigation and the range index?** Take it
  from the sitemap and reconcile — see "No single menu is a complete roster" above.
- **Does your verification probe fail where the adapter fails?** A throwaway script with a
  fallback the adapter lacks will report a healthy parse while the adapter collects nothing.
  Etrusco's first live run returned zero products for exactly this reason.
- **Does the same site label the same field differently per vehicle type?** Elddis heads its
  spec block `Technical Specification` on motorhomes and `Technical Specifications` on
  campervans, with `NOTES` against `Notes` — one plural away from silently dropping all 15
  campervans while collecting all 34 motorhomes. A count that looks plausible is the only
  symptom. Check one page of *each* type before trusting a label, and prefer the roster's
  own count over "it parsed" as the success condition.
- **Check the units per range, not per site.** Elddis publishes millimetres everywhere
  except its three newest campervans, which use metres to two decimal places — so a
  pattern anchored on `mm` returns nothing for those three, and their dimensions are
  genuinely only good to the nearest 10mm. A brand-new range is where a template
  convention breaks.
- **If a `--range` selector is not an FMLV range, declare `baseline_in_scope`.**
  `cli.baseline_scope` matches the selector against `manufacturer_range` by default, which
  is right whenever the two coincide. Wingamm's don't: three of its five documents are one
  range (`Oasi`) and `cli.resolve_ranges` keys on a *unique* label, so the labels must name
  documents (`Oasi 690`) instead. The default then scoped a two-product run to **zero**
  baseline rows and proposed both as new. Scope on `model` where the range column is the
  thing you are proposing to change — scoping on a column mid-rename misses the row you are
  renaming and duplicates it.
- **Run `--range` before calling an adapter done.** A completeness check that compares a
  run against the manufacturer's full published roster will cry wolf on every legitimate
  single-range run unless it is gated on what was actually *requested*. Elddis's did, and a
  check that fires on correct runs trains a reviewer to ignore it — which is worse than not
  having one.
- **Read the export's `year` column before writing up "disappeared".** Elddis's export has
  77 un-archived rows against 49 products on sale, which reads as 48 discontinued vehicles
  — but `cli._is_current_model_year` already drops them, because they carry 2024 and 2022.
  The baseline the diff sees was 29 and nothing disappeared. Count against the *filtered*
  baseline, not the raw export.
