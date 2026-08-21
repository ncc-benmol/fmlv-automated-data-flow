# Elddis — site survey and adapter notes

Surveyed 21 August 2026. `manufacturer_id` **8**, `fmlv_manufacturer` **`Elddis (EHG UK)`**,
`ncc_supplier_name` **`Elddis Motorhomes`** (both confirmed against the real export, not guessed).

Elddis is the British arm of Erwin Hymer Group UK Ltd, built at Consett, County Durham. It is
**not** a "non-core brand" in the sense `README.md` describes — there is no European parent
roster to reconcile against, and `elddis.co.uk` is the whole of the range.

**Verdict: the single safest source surveyed so far.** One product per URL, a labelled
`key: value` technical specification block in server-rendered HTML, no JavaScript, no PDF, and
a published self-check. Attribution is free — there are no columns to align, so the entire
class of failure that dominates the PDF adapters cannot occur here.

## What the requester brought to the survey

Francis gave this over the course of the survey rather than up front:

- **The site**: `https://elddis.co.uk/` — correct, and the only source needed.
- **`ncc_supplier_name` is `Elddis Motorhomes`** — confirmed working; `fetch-export` logged in
  and downloaded on the first attempt.
- **The manufacturer list names it `Elddis (EHG UK)`**, which settled a three-way ambiguity in
  `resources/manufacturers-full-list.csv` (see below).
- **Scope is the Elddis brand only, motorhomes and campervans.** Elddis caravans are out of
  scope (prototype-wide), and so are **Xplore** and **Buccaneer** — two other EHG UK brands
  that Elddis builds. Both have their own sites, so `elddis.co.uk` happens to be exactly the
  right scope, but this was worth stating.
- **"Like Auto-Trail, it sometimes uses the same name in different areas."** This is the most
  valuable thing in the survey and is written up under *Name collisions* below. It turned out
  to be not just a naming annoyance but a live matcher hazard.

### The three-way ID ambiguity, and why guessing would have been wrong

`resources/manufacturers-full-list.csv` holds three rows that a search for "Elddis" hits:

| ID | `Name` | `DisplayName` |
|---|---|---|
| **8** | **Elddis (EHG UK)** | **Elddis** |
| 234 | Elddis (EHG UK) | Xplore |
| 246 | EHG UK Ltd | Elddis |

ID 8 is correct. Note that 234 shares ID 8's `Name` exactly and differs only in `DisplayName`,
so matching on the name alone picks between them by luck. The export confirms it: every row
carries `manufacturer` = `Elddis (EHG UK)` and `manufacturer_display_name` = `Elddis`.

## Where the data lives: one labelled block per product, in plain HTML

Every model page carries a numbered "Detailed Specification" narrative and then, as section 8,
a technical block of `Label: value` lines. From
`https://elddis.co.uk/motorhomes/whirlwind-gt/whirlwind-gt-155`, verbatim:

```
Technical Specification
Year: 2026
Model: Whirlwind GT 155
Base Vehicle: Peugeot X250 Boxer Euro 6E Engine Motorhome Chassis
Number of Berths : 4
Number of Seat Belts: 4
Exterior Length: 7373mm/24'2"
Overall Width Including Wing Mirrors: 2678mm/8'9"
Overall Body Width: 2239mm/7'4"
Overall Height Including Aerial: 2925mm/9'7"
Maximum Headroom: 2080mm/6'10"
Interior Width: 2074mm/6'10"
Maximum Front Axle Weight: 1850kgs/36.42cwt
Maximum Rear Axle Weight: 2000kgs/39.37cwt
Mass in Running Order (MIRO): 2926kgs/57.60cwt
Maximum User Payload: 530kgs/10.43cwt
Mass Available for Optional Payload: 191kgs/3.76cwt
M.T.P.L.M: 3500kgs/68.89cwt
NOTES
```

**There is no PDF anywhere on the site** — no price list, no brochure, no downloads page, no
`.pdf` link on any page fetched. `README.md` says to ask the PDF question first; the answer
here is a clean no, and it costs nothing, because the HTML already does what a good PDF does.

`needs_javascript` is **no**. The site is Kirby with Alpine.js sprinkled on for carousels and
the enquiry form; every number above is in the initial HTML response.

### Field mapping, confirmed against the export rather than assumed

The mapping below is not inferred — it was checked against the 29 products FMLV already holds,
and it agrees on **every** field except price:

| FMLV field | Elddis label | Agreement on 29 matched products |
|---|---|---|
| `berths` | `Number of Berths` | 29 / 29 |
| `mh_passenger_seats_inc_driver` | `Number of Seat Belts` | 29 / 29 |
| `mro_kilograms` | `Mass in Running Order (MIRO)` | 29 / 29 |
| `mtplm_kilograms` | `M.T.P.L.M` | 29 / 29 |
| `mh_payload_kilograms` | `Maximum User Payload` | 28 / 29 |
| `mh_length_mm` | `Exterior Length` | 29 / 29 |
| `mh_width_mm` | **`Overall Body Width`** | 29 / 29 |
| `mh_height_mm` | `Overall Height Including Aerial` | 27 / 29 |
| `base_vehicle_manufacturer` | `Base Vehicle` (Fiat / Peugeot) | — |
| `rrp_pounds` | headline price | **0 / 29** — see below |

Two things worth drawing out:

- **`Overall Body Width` is the right width field, not `Overall Width Including Wing Mirrors`.**
  Elddis publishes both, and FMLV holds the body figure on all 29. This is the base-vehicle rule
  in `README.md` agreeing with the existing data for once, rather than contradicting it.
- **`Maximum Headroom` and `Interior Width` are decoys.** Both are always present and both are
  plausible-looking mm figures. `Maximum Headroom` is 2080 on every single motorhome, which is
  the tell.

## The self-check: a published tolerance, and why it must be a band

Elddis publishes MIRO, MTPLM *and* `Maximum User Payload`, so the parse can be checked without
a second source. But `payload == MTPLM − MIRO` **fails on most models**, and the page says why:

> Note 9: A MIRO tolerance of +1.5% is permitted as per the NCC COP 304/402 regulation to
> account for build variance

So most models publish `payload = MTPLM − MIRO × 1.015`, and a minority publish the plain
`MTPLM − MIRO`. Both appear, so the check is a **band**, not an equality:

```
MTPLM − MIRO × 1.015   ≤   payload   ≤   MTPLM − MIRO
```

Worked, from the survey:

| Model | MTPLM | MIRO | Payload | `−MIRO×1.015` | `−MIRO` | Which |
|---|---|---|---|---|---|---|
| Whirlwind GT 155 | 3500 | 2926 | 530 | **530** | 574 | tolerance |
| Autoquest APEX 105 | 3500 | 2824 | 634 | **634** | 676 | tolerance |
| Whirlwind GT Evolve 196+ | 3650 | 2951 | 655 | **655** | 699 | tolerance |
| Avalon 250 | 3500 | 3090 | 410 | 364 | **410** | plain |
| Whirlwind GTV 560 | 3500 | 2756 | 744 | 700 | **744** | plain |

**46 of 49 products pass the band on the raw labels**; the three that do not are the Whirlwind
GTVs, which fail only because they use different labels (below) — with those handled, it is
49 / 49.

**This is a real check, not a formality.** It ties three independently-parsed numbers together,
so a label picked up from the wrong row cannot pass. It is the defence against the failure
`README.md` describes: plausible, internally consistent motorhomes carrying each other's weights.

### A consequence worth knowing: `payload_mismatch` will fire, and already does

`validation._validate_payload` checks `payload == mtplm − mro` exactly, so it warns on any
product using the tolerance. That is **pre-existing, not introduced here** — FMLV's own baseline
already carries the tolerance-adjusted figures (Whirlwind GT 155 is held as MRO 2926 / MTPLM
3500 / payload 530, which fails that check today). Recording what Elddis publishes therefore
keeps faith with both the manufacturer and the existing data; the warning is noise on this brand.

## Name collisions — the requester's warning, and the hazard it exposed

Elddis reuses range names across vehicle types exactly as Auto-Trail does with Expedition:

- **Whirlwind** is a motorhome range (**Whirlwind GT**), a campervan range (**Whirlwind GTV**)
  *and* a caravan range.
- **Autoquest** is a motorhome range (**Autoquest APEX**) and three campervan ranges
  (**Autoquest CV**, **Autoquest CV Evolve**, **Autoquest APEX CV**).

Always qualify the range. But there are two sharper consequences.

### Layout numbers repeat across ranges, so `model` alone is not an identity

`105 / 115 / 120 / 150 / 155 / 185 / 194 / 196 / 196+` appear in **Whirlwind GT**, **Whirlwind
GT Evolve** *and* **Autoquest APEX**. `250 / 255 / 285 / 295` appear in **Avalon** and **Avalon
Evolve**. `CV20 / CV40 / CV60 / CV80` appear in four campervan ranges. Nothing can be keyed on
the model half.

### The matcher can pair a base model with its Evolve variant

`diff/matching.py` scores Jaccard on the range-plus-model word bag and accepts from 0.5. The
Evolve ranges differ from their base range by exactly one token:

| Pair | Tokens | Jaccard | Accepted at 0.5? |
|---|---|---|---|
| `Whirlwind GT 155` vs `Whirlwind GT Evolve 155` | 3 vs 4, 3 shared | **0.750** | yes |
| `Avalon 250` vs `Avalon Evolve 250` | 2 vs 3, 2 shared | **0.667** | yes |

Both score **above** Adria's documented good match of 0.667, so `README.md`'s warning applies
in full: this cannot be fixed by raising `DEFAULT_THRESHOLD`. It matters because all 13 Evolve
motorhomes are new products whose obvious wrong partner is already in the baseline — a
mismatch would report a new vehicle as a price rise on an existing one, and simultaneously
hide the fact that nothing disappeared.

In practice the current run is safe, because the base ranges match at 1.000 and are claimed
first. It is recorded here because it is one renamed range away from biting.

## Range and model strings: FMLV folds campervans into the motorhome range

Per `README.md`, the export decides. It says something the website does not suggest:

| Site range | Site model | FMLV `manufacturer_range` | FMLV `model` |
|---|---|---|---|
| Autoquest APEX | Autoquest APEX 105 | `Autoquest Apex` | `105` |
| Autoquest APEX CV | Autoquest APEX CV20 | **`Autoquest Apex`** | `CV20` |
| Autoquest CV | Autoquest CV20 | **`Autoquest`** | `CV20` |
| Whirlwind GT | Whirlwind GT 155 | `Whirlwind GT` | `155` |
| Avalon | Avalon 250 | `Avalon` | `250` |

So **`Autoquest Apex` holds both the 8 motorhomes and the 4 campervans**, distinguished only by
the `CV` prefix on the model half — and the site's separate `Autoquest CV` range collapses to
range `Autoquest`. Emitting the site's own range names would have proposed a rename on all 12
Apex products and orphaned the four `Autoquest` campervans.

Two further string details:

- **`196+` on the site is `196P` in FMLV.** Both Autoquest Apex and Whirlwind GT have one.
  Getting this wrong costs twice: the product reads as new, *and* its baseline row reads as
  disappeared. Note also that `matching.py` tokenizes letters and digits only, so the `+`
  vanishes and `Whirlwind GT 196+` collapses to the same token bag as `Whirlwind GT 196` —
  a second reason to normalise deliberately rather than rely on the matcher.
- **Case differs**: the site writes `APEX`, FMLV writes `Apex`.

Per `README.md`'s Bailey lesson, both halves of the identity get provenance, and each snippet
says they belong together.

## The roster: 49 products, from the sitemap, reconciled twice

`sitemap.xml` is complete and clean — no `robots.txt` (404), no sitemap index. Model pages match
`/(motorhomes|campervans)/<range>/<model>`:

| | Ranges | Layouts |
|---|---|---|
| Motorhomes | Whirlwind GT 9, Whirlwind GT Evolve 9, Autoquest APEX 8, Avalon 4, Avalon Evolve 4 | **34** |
| Campervans | Autoquest CV 4, Autoquest CV Evolve 4, Autoquest APEX CV 4, Whirlwind GTV 3 | **15** |
| | | **49** |

**The reconciliation is free and exact.** `/motorhome-specification` and
`/campervan-specification` each list every layout as a card with its name, price, berths and
MTPLM — 34 and 15 cards respectively, agreeing with the sitemap on both count and name. Two
independent sources for the roster, which is more than any brand surveyed so far offered.
These two pages are also the cheapest possible completeness check: two fetches.

Against the baseline this gives **29 matched, 20 new, 0 disappeared**.

- **20 new**: Whirlwind GT Evolve (9), Avalon Evolve (4), Autoquest Evolve CV (4),
  Whirlwind GTV (3) — the Evolve trim packs and the new GTV campervan.
- **0 disappeared**, and the reason is worth recording because the raw export is
  misleading. It holds 203 rows, of which 77 are un-archived — 48 more than the site
  sells, in whole ranges Elddis no longer lists: Masters Collection (10), Autoquest GTS
  (10), the Encore family (12), the Accordo family (6), Evolution (3), Supreme (3) and
  single rows for Avantgarde, Majestic, Prestige and Vogue.

  **`cli._is_current_model_year` already discards them.** Those 48 rows carry `year` 2024
  or 2022; the 29 the site still sells all carry 2026. Since the filter keeps only this
  calendar year and next, the baseline the diff actually sees is 29 and nothing is reported
  as disappeared. This was initially written up here as "48 disappeared" needing a
  decision, which was wrong — the pipeline handles it, and no reviewer ever sees them.

## The price question, resolved: record what is published

Elddis labels its headline figure "OTR" and then charges the OTR fee on top. From the
Whirlwind GT 155 page:

```
Whirlwind GT 155                       £66,195
...
Whirlwind GT 155 Price:   £66,195
OTR Charges:              £1,690
Total Price:              [computed client-side]
```

and the footnote on both listing pages:

> On-the-road (OTR) charge of £1,690 RRP includes delivery, registration and PDI charges.

So the card's `£66,195 OTR` is **not** an on-the-road price; the true on-the-road figure is
£67,885 and appears nowhere as a single published number.

**FMLV holds a third figure.** Its Whirlwind GT 155 is £64,505 — the headline **minus** £1,690.
That is not a coincidence of one row: across the 29 matched products the gap is exactly £1,690
on 26 of them, and £1,291 on one (Autoquest Apex CV80, i.e. a genuine £399 move on top). So
whoever populated FMLV read the "OTR" label at face value and subtracted the charge.

Three defensible figures, then, and they are £1,690 apart.

**Decision from the NCC side, 21 August 2026: record what is published**, i.e. £66,195.
This follows `README.md`'s standing rule that whatever the manufacturer prints on the page
is the guide price, taken as-is. The consequence is accepted deliberately: the first run
proposes a **+£1,690 change on all 29 matched products**, which is not a real price move
but a correction of the basis FMLV was holding. Autoquest Apex CV80 is the one product
whose gap differs — £1,291, i.e. a genuine £399 increase on top of the basis change.

The basis is recorded in the registry `notes` and in every `rrp_pounds` provenance snippet,
which also states the true on-the-road figure. That matters for the failure `README.md`
warns about: if Elddis ever changes how it labels this, the diff is diagnosable in seconds
rather than reading as a real price move across the whole range.

## Body type: not stated, but derivable — and FMLV's existing values are inconsistent

The site never uses the words "low profile", "coach built", "high top" or "A-class" — zero
occurrences across every page fetched. It says "overcab pod" 29 times, but that is a styling
feature, not a bed, and it appears on ranges FMLV holds as low profile.

What the baseline shows:

- **All 21 baseline motorhomes are `coach_built_low_profile`**, across Whirlwind GT, Autoquest
  Apex and Avalon. Elddis's current range has no overcab-bed or A-class model.
- **The campervan values are inconsistent in FMLV itself.** The same physical vehicle —
  5998 × 2050 × 2670 — is held as `campervan` (Autoquest GTS CV20), `campervan_high_top`
  (Autoquest CV20) and `campervan_elevating_roof` (Masters Collection CV20) depending on range.
  FMLV also holds Autoquest CV60 as `campervan_high_top_elevating_roof`, but the CV60 page
  mentions no pop-top at all — that one looks simply wrong.

**The pop-top is readable per model, though.** Only the CV80 page mentions one, and it is
standard, not an option: *"Autoquest CV80 comes with a pop-top with an opening Skylight"* and
*"adds a pop-top roof to create a flexible 4-berth campervan under 6m"*. CV20, CV40 and CV60
mention it zero times. Per `README.md`, the word after the feature decides it — "comes with"
is included, so the CV80 genuinely is an elevating-roof van.

The Whirlwind GTV is the opposite case: *"All models are available as a pop-top 5 berth
version"* — an option, so it does **not** change the body type, and berths stay at the fixed-roof
figure. See below.

Height evidence: all Autoquest CV models publish 2670 mm; the Whirlwind GTV publishes
2610 mm fixed roof and 2810 mm with the pop-top raised.

### The rule the adapter uses, and why it reuses the shared threshold

- **Motorhomes: always `coach_built_low_profile`.** No range currently sold has an over-cab
  bed or an A-class body, and this reproduces the baseline on all 21 matched motorhomes.
- **Campervans: `HIGH_TOP_ABOVE_MM = 2300`**, the same constant `auto_trail.py`,
  `bailey.py`, `chausson.py` and `etrusco.py` use. Every Elddis van is 2610 mm or 2670 mm,
  so all of them are high tops on this rule.
- **Plus `_elevating_roof` where the pop-top is standard**, which is the three CV80s only.

**This reproduces FMLV's existing value on all 8 matched campervans**, which is the reason
for reusing the shared threshold rather than inventing an Elddis-specific one. Two notes:

- At the checkpoint the Whirlwind GTV was sketched as a plain `campervan` on the grounds
  that 2610 mm is below `README.md`'s "around 2680 mm" remark. The shared 2300 mm threshold
  makes it `campervan_high_top` instead, and that is what the adapter emits. Worth an eye —
  it is a one-line change if the GTV should be a plain campervan, but a brand-specific
  threshold between 2610 and 2670 would be a suspiciously convenient constant.
- **The adapter corrects Autoquest CV60, and this is confirmed.** FMLV holds it as
  `campervan_high_top_elevating_roof`; its page mentions a pop-top zero times, so the
  adapter proposes `campervan_high_top`. Confirmed by the requester on 21 August 2026:
  *"the Autoquest CV60 doesn't come with an elevating roof pop top as standard"*, with the
  general rule that **if a page does not mention a feature as included, it is normally an
  option and not part of the standard specification.** That rule is now recorded in
  `README.md`, since it applies to every brand and not just this one. So the absence of a
  mention is sufficient grounds here, and this is the adapter correcting FMLV rather than a
  proposal needing further evidence.

The detection across all 15 campervans, for the record:

| Layouts | "pop-top" mentions | Verdict | Body type |
|---|---|---|---|
| CV20, CV40, CV60 (all three families) | **0** | not fitted | `campervan_high_top` |
| CV80 (all three families) | 3, incl. "comes with a pop-top" | standard | `campervan_high_top_elevating_roof` |
| Whirlwind GTV 554 / 560 / 563 | 6 / 8 / 11, as an alternative configuration | option | `campervan_high_top` |

The GTV row is the useful one: mention count is not the signal. Those pages talk about the
pop-top more than the CV80s do, but always as a variant with its own weights and berth
count, which makes it an option however prominent.

## The Whirlwind GTV campervans are the parsing trap

The three GTVs share the block's shape and almost nothing else. Every difference below is a
silent-failure risk:

- **Dimensions in metres, not millimetres.** `Exterior Length: 5.99m`, `Overall Body Width: 2.05m`.
  Everything else on the site is `7373mm/24'2"`. A parser anchored on `mm` returns nothing.
- **Only published to the nearest 10 mm.** The Autoquest CV20 is 5998 mm and is *described* as
  5.99 m; the GTV 560 publishes only `5.99m`. Precision is genuinely lost for these three.
- **Masses carry thousands separators**: `2,710kg`, not `2926kgs`.
- **Height is `Overall Height Excluding Aerial`**, where every other model publishes
  `Overall Height Including Aerial` — and FMLV's held values are the *including*-aerial figure.
- **Weights split four ways**, Fixed Roof / Pop Top × Manual / Automatic:

```
Mass in running order - (Manual) - Fixed Roof: 2,756kg
Mass in running order - (Automatic) - Fixed Roof: 2,816kg
Mass in running order - (Manual) - Pop Top: 2,916kg
Mass in running order - (Automatic) - Pop Top: 2,976kg
Maximum User Payload (Manual) - Fixed Roof: 744kgs
M.T.P.L.M (Fixed Roof): 3500kgs/68.89cwt
```

- **GTV 563 embeds the model name and a seat count in the label**, and no two of its eight
  weight labels share a format:

```
GTV 563 (4-seats) Fixed Roof - Mass in running order - (Manual) - Fixed Roof: 2,856kg
GTV 563 (3-seats) Pop Top -     Mass in running order - (Automatic) - Pop Top: 3,076kg
Maximum User Payload - GTV 563 (4-seats) Fixed Roof (Manual): 644kgs
GTV 563 (4-seats) - M.T.P.L.M (Fixed Roof): 3500kgs/68.89cwt
```

- **Berths and seats are prose**: `Fixed Roof 3 Berth or Pop Top Roof 5 Berth`, and on the 563
  `Fixed Roof (Manual or Automatic) 4 seats or Pop Top (Manual or Automatic) 3 seats`.
- **GTV 554 is automatic-only** — `Base Vehicle: Peugeot Boxer - Automatic as standard` — so it
  publishes no manual figures at all, and "the manual one" is the wrong way to select its base.

**The base vehicle is Fixed Roof + Manual**, falling back to Automatic where no manual figure
exists. Selected that way the self-check passes exactly, with no tolerance:

| Model | MTPLM | MIRO (base) | Payload | `MTPLM − MIRO` |
|---|---|---|---|---|
| GTV 554 | 3500 | 2710 (auto, fixed roof) | 790 | 790 |
| GTV 560 | 3500 | 2756 (manual, fixed roof) | 744 | 744 |
| GTV 563 | 3500 | 2856 (manual, fixed roof) | 644 | 644 |

And berths is **3**, not 5 — the pop-top is an option, per the base-vehicle rule.

## Smaller traps

- **Section heading differs by vehicle type.** Motorhomes head the block
  `Technical Specification` and the footnotes `NOTES`; campervans use
  `Technical Specifications` and `Notes`. An exact-string match on the motorhome spelling finds
  34 of 49 and silently drops every campervan — which is how this was found.
- **`Mass Available for Optional Payload` vs `Mass available for Optional Payload`.** Both
  appear, 34 and 12 times. Not currently a field FMLV holds, but the same casing hazard applies
  to any label match.
- **`Number of Berths :`** has a space before the colon on every page. `Number of Seat Belts:`
  does not.
- **Values carry a dual metric/imperial form** — `7373mm/24'2"`, `2926kgs/57.60cwt` — so the
  imperial half must not be parsed as a second number. Note `24'2"` contains digits and a
  quote character.
- **The `£` figures are the only prices**; option prices (`Gearbox - £3,246`, `Colour - £847`,
  `Tow Bar - £706`) sit in the same page and must not be mistaken for the vehicle price.
- **Automatic-variant data exists for exactly two products.** GTV 560 and 563 publish automatic
  MIRO and payload; the other 47 publish only the option price. Since `AutomaticVariant` is
  all-or-nothing under `validation`, the group should be populated only for those two, or left
  alone entirely.

## Model year

Every one of the 49 pages says `Year: 2026`, as at 21 August 2026. Per `README.md` the site is
authoritative, so this is MY2026 and not a stale document. Elddis rolls over around the
October NEC rather than Düsseldorf, so **re-check late September** — the Evolve ranges are new
enough that a 2027 revision is likely.

## First run — 21 August 2026, run #23

`uv run fmlv run "Elddis (EHG UK)"`, 58 seconds, 52 fetches (one sitemap, 49 model pages,
two index pages).

```
49 product(s) collected
roster cross-check: 34 motorhome(s) in both the sitemap and motorhome-specification
roster cross-check: 15 campervan(s) in both the sitemap and campervan-specification
classified  29 changed, 0 unchanged, 20 new, 0 disappeared
proposed    322 changes for review, of which 29 are year bumps
verified    344 fields checked and unchanged
```

**49 of 49 collected, nothing dropped, nothing skipped** — no product failed the
self-check, no page failed to parse, and both roster cross-checks agreed. That is the
cleanest first run of any adapter so far, which is a fact about the source rather than
about the code.

The 322 proposals decompose cleanly, and the shape is the point — nothing unexplained:

| | Count | |
|---|---|---|
| New products | **260** | 13 fields x 20 new products; everything about a new product is a proposal |
| Price basis | **29** | the +£1,690 decided above, on every matched product |
| Year bumps | **29** | pipeline-generated, see below |
| Height | **2** | Autoquest CV80 and Autoquest Apex CV80, 2760 -> 2670 |
| Payload | **1** | Whirlwind GT 196P, 644 -> 655 |
| Body type | **1** | Autoquest CV60, the correction described above |

**The two height changes are the site correcting FMLV, not a misread.** Elddis publishes
2670 mm for every Autoquest CV including the CV80; FMLV holds 2760 for the two CV80s,
which looks like the raised-pop-top height recorded as the vehicle height. The other 27
matched products agree on height exactly.

**The 29 year bumps are pipeline behaviour, not the adapter's, and should be rejected.**
`store.changes` offers a `year` bump for any changed product during
`year_rollover.ROLLOVER_WINDOW` (1 June - 30 September); all 29 changed on price, so all 29
became eligible. Its `source_url` is `None` and its snippet says the suggestion came from
the pipeline noticing the season. **Every Elddis page says `Year: 2026`**, so the honest
answer is to reject them — and `was_previously_rejected` means they will not be offered
again. Revisit after the October NEC, when Elddis may genuinely move to 2027.

### One bug of mine, found by running `--range`

`_cross_check_roster` warned "the sitemap lists 3 but campervan-specification shows 15" on
every single-range run. The guard meant to skip the check for a partial selection counted
the *available* ranges on both sides instead of the *requested* ones, so it never fired.
Fixed to compare `ranges` as passed against `DEFAULT_RANGES`, and it now narrates the skip
instead. Regression test:
`test_roster_cross_check_is_skipped_for_a_partial_range_selection`.

This is the failure mode `README.md` warns about from the other direction — a check that
cries wolf on a legitimate run trains a reviewer to ignore it.

## Open items

1. **Whirlwind GTV body type** — the adapter emits `campervan_high_top` on the shared
   2300 mm threshold; a plain `campervan` is arguable at 2610 mm. One line if it should
   change.
2. **Autoquest CV60's body-type correction** — proposed on the absence of any pop-top
   mention. Worth a human confirming, since absence is weaker evidence than presence.
3. **Autoquest Apex CV80's £399 real price move**, the one product whose gap is not £1,690.
4. **Re-check late September** for MY2027, per the model-year note above.
5. **Automatic-variant figures for GTV 560 and 563.** Those two publish automatic MIRO and
   payload, and the option price is £3,246, so `AutomaticVariant` could be populated for
   them. Not attempted: `validation` treats the group as all-or-nothing, FMLV currently has
   it set on none of the 77 rows, and two products out of 49 is not obviously worth the
   asymmetry. Raised rather than silently skipped.

## Known gaps and what is unverified

- **No caravans.** Out of scope, and the 31 caravan URLs in the sitemap are ignored.
- **Xplore and Buccaneer are untouched** — separate brands, separate sites, separate registry
  rows if they are ever wanted.
- **The GTV metre-precision loss is real and unfixable from this source.** No other document
  publishes those three vehicles' dimensions.
- **The layout flags** (`sleeping_area`, `bed_types`, `kitchen_location`, `bathroom_layout`,
  `lounge_location`, `heating`, `refrigeration`, `rear_garage`, `microwave`) are all derivable
  in principle from the narrative "Detailed Specification" and the mattress-size rows, but none
  of it is structured. Not attempted, so baseline values are preserved — the Adria precedent.
- **`Maximum Towing Limit`, axle weights and tyre data** are published and unused; FMLV has no
  column for them.
