# Rimor — site survey and adapter notes

Rebuilt 5 September 2026 against the UK importer's site plus a redesigned factory site.
The original survey (13 August 2026) read only `rimor.it`; see "What changed in
September" at the end for why that no longer works and what it cost.

Rimor is the first adapter to read **two different sites and let each decide different
fields**. That is not an optimisation — neither site can answer the whole question.

| | decides | because |
|---|---|---|
| **MNC** (`motorhomesandcaravansltd.co.uk`) | which products exist, and the price | Rimor's exclusive UK importer, and Rimor publishes no price anywhere on earth |
| **`rimor.it`** | every specification number | MNC's specs are a sales description, and demonstrably wrong in places |

**34 products**: Horus 7 (including the Rimor Van 238), Kilig 15, Sarus 3, Sailer 5,
Super Brig 4. Both sites are plain server-rendered HTML — no JavaScript, no login.

Confirmed with the requester on 5 September 2026: **MNC defines the UK range.** A layout
MNC does not list is not a UK product and is not emitted, however complete its factory
page. Today that excludes five factory layouts — `horus/45`, `kilig/73-plus`,
`sarus/50`, `sarus/69-plus`, `sarus/95-plus` — each of which the run names explicitly
rather than dropping silently.

## Why MNC cannot supply the specifications

This is the load-bearing part of the design, so it is evidenced rather than asserted.
All three findings come from comparing the 28 layouts both sites describe.

**MNC's berth figure is not a berth count.** On the coachbuilts it repeats its own
travel-seat count in the berth position:

| | MNC says | rimor.it says |
|---|---|---|
| Kilig 5 | 6 berth with 6 travel seats | 6 seats (`6 / 5`), **4** berths |
| Kilig 79 | 7 berth with 7 travel seats | 7 seats (`7 / 6`), **4** berths |
| Kilig 67 | 4 berth with 4 travel seats | 4 seats, **2** berths |

**26 of 34** MNC listings have `berths == seats`, and where the factory can be checked
MNC is too high in **11 of 21** cases — always too high, never too low. Berths therefore
always come from the factory. (Horus is the exception that proves it is a coachbuilt
template bug: MNC's Horus pages do print two different figures, and they agree.)

**MNC truncates dimensions to whole centimetres.** Kilig 55 Plus is 7338 mm on the
factory page and `7.33m` on MNC — truncated, not rounded, so MNC is systematically 0–9 mm
low. That cap is what makes the cross-site check below usable.

**At least two MNC layouts carry another layout's figures.**

* Kilig 79 — MNC prints `6.75m`, which is the *78*'s length; the factory says 6970 mm.
* Kilig 99 — MNC prints `7.44m × 2.90m` against the factory's 7308 × 2845 mm.

Both are caught by the self-check on every run and narrated, with the factory figure
kept.

## Why the factory cannot supply the price

**Rimor publishes no price anywhere** — not the HTML, not the leaflets, not the 60-page
catalogue (zero hits for any currency symbol), and the FAQ directs price questions to
dealers. MNC's is the only price that exists.

Prices are **banded by range** rather than set per layout: Horus and Kilig £56,995–61,995,
Sarus £64,995, Sailer and Super Brig £69,995. That is worth knowing before reading a
uniform column as a parse failure.

## Site shapes

```
MNC     /product-category/new-motorhomes-for-sale/new-rimor-motorhomes/<range>
          -> /product/rimor-<range>-<layout>-<year>[-variant]    price, body type
rimor.it /int/en/gamma/<range>
          -> /int/en/gamma/<range>/<body-style>
               -> /int/en/gamma/<range>/modello/<layout>         every specification
```

Two entry-point quirks. **MNC spells Sailer's category `sailer`, not `rimor-sailer`** —
the other four carry the prefix, and guessing costs a 404. And the factory has no
`/int/en/gamma` index (it 404s) and no sitemap, so the five ranges are listed in the
adapter rather than discovered.

`DEFAULT_RANGES` therefore carries **three** elements per entry — MNC slug, factory slug,
label — where every other adapter carries two. `cli.resolve_ranges` was changed to read
only the entry's *last* element as the label and pass the rest back untouched, which
leaves the other adapters exactly as they were.

## Stock units are not products

MNC sells actual vehicles alongside its layout listings, which is the thing to get right
here. **48 URLs reduce to 34 products.**

* **Demo vans** carry a struck-through price and `Demo` in the title.
* **`-copy` slugs** are WordPress duplicates whose slug is the only thing wrong with them.
* **`-automatic` variants** are a transmission option on the same layout.
* **10 URLs are 301s** onto a sibling that is already listed.

`select_listings` groups every URL by `(range, layout)` and prefers a plain listing, then
a duplicate, then a demo unit; within that, the latest model year and then the shortest
slug, which favours the base vehicle over an optioned variant.

**A demo or copy listing is still used when it is all a layout has.** Four layouts are in
that position — Sailer 55 Plus, Sailer 56 Plus, Kilig 50 and Kilig 695 — and dropping
them would lose layouts MNC genuinely sells.

### Which price a discounted page gives

Two discounts that look identical in the markup mean opposite things, and the difference
is what is being discounted:

| | MNC shows | take | why |
|---|---|---|---|
| Sailer 55 Plus (demo unit) | £69,995 → £64,995 | **£69,995** | the discount is on one van; £69,995 is exactly what the other three Sailers cost |
| Horus 40 (range promotion) | £61,990 → £59,995 | **£59,995** | the whole Horus range is promoted, and £59,995 is the figure MNC's page leads with |

**`is_demo` must be read from the fetched page's title, never from the requested slug.**
Several plain layout URLs 301 *onto* a demo listing — `rimor-sailer-55-plus-2026` lands on
`rimor-sailer-55-plus-2026-automatic-demo-van`, and `rimor-horus-40-2026` lands on
`-automatic` — so the slug asked for and the page returned routinely disagree. Only the
page that comes back can say what was actually read.

## The join, and Rimor's renaming

Rimor moved its **whole Kilig low-profile line** from `<n>` to `<n> Plus` for the new
season while MNC still lists the old names. `_factory_slug` tries `<layout>`, then
`<layout>-plus`, then `<layout>` with `-plus` removed, and only ever returns a slug the
factory actually publishes — nothing is invented. Six Kilig layouts join that way today
(66, 67, 69, 77, 78, 79), each reported in the run output.

This is exactly the "name drift is not a new model" case: treating those as new products
would have proposed six creations and six disappearances instead of six matches.

**The dimension check is what proves the join** rather than assuming it. `rimor.it` and
MNC publish each layout's dimensions independently, so comparing them is a genuine second
source and not the same number read twice. MNC's truncation caps an honest disagreement at
9 mm, so the tolerance is 10 mm; anything larger is a real conflict, narrated loudly, with
the factory figure kept. A conflict does **not** drop the product — MNC being wrong about
a dimension says nothing about whether the layout is on sale.

## Body type: `/vans` does not settle it

The body-style URL segment settles `low-profile` and `overcab` outright. **`vans` does
not** — it says the vehicle is a panel-van conversion, and FMLV splits those four ways on
what the roof does. Height decides it, on the same **2300 mm** threshold the NCC side set
on 16 August 2026 and every other campervan-producing adapter applies:

| Height | Body type |
|---|---|
| > 2300 mm | campervan high top |
| ≤ 2300 mm | campervan |

Every Rimor van is 2659 mm (the Van 238 is 2800 mm), so **all of them are high tops**, and
none is anywhere near the threshold — the closest clears it by 359 mm.

This was wrong until 5 September 2026: the adapter mapped `vans` straight to plain
`campervan`, and Rimor was the **only** adapter emitting a campervan without applying the
rule. Two notes for anyone tempted to re-derive the threshold from FMLV's own data, as I
briefly was:

* **Height does not separate the two classes in the baseline.** Across 237 campervan rows,
  `high_top` spans 1900–3120 mm and plain `campervan` spans 2580–3050 mm — the plain class
  has the *higher* median. That is not evidence the rule is wrong; it is a picture of the
  errors the rule exists to correct, and reading it as ground truth argues for keeping
  them.
* **A missing height yields no body type at all**, rather than a guess. The four campervan
  types are mutually exclusive columns.

The two elevating-roof types never arise: no Rimor van publishes a pop-top, as standard or
as an option. If one appears, the elevating question is independent of the height one, and
`body_type_for` is where both belong — `auto_trail._campervan_body_type` has the full
four-way table.

## MNC writes its dimensions two ways

Most listings read `Height: 2.65m` — whole centimetres, truncated. **A few read
`Overall height: 2,659mm`**, which is exact, comma-separated, and agrees with the factory
to the millimetre. Today that is Horus 12 and Horus 54; the other 36 use metres.

Missing the second form is not harmless. It left Horus 12 — a layout with no factory page
— looking as though nobody published its dimensions, when MNC publishes them exactly.
`mnc_dimensions` tries the exact form first and reports which it found, and all three axes
must come from the same form so that `dimensions_are_exact` cannot be true of one axis and
false of another.

### Dimensions fall back to MNC

Where the factory has no page for a layout, its dimensions come from MNC rather than being
left blank. The requester's ruling, 5 September 2026: *"if you can't get the specification
on the manufacturer's site, plan B would be to use the MNC site for the dimensions — in
that case we wouldn't have fields where you can't validate them."*

The fallback only ever fills a gap. Where the factory has a figure it always wins, so this
does not reintroduce MNC's truncation or its two wrong layouts anywhere the factory can
speak. Where a fallback figure *is* truncated, the run and the provenance snippet say so,
because that is the one thing a reviewer cannot see from the value itself.

## Traps on the factory site

**Seats and berths are distinguishable only by Italian icon classes.** The two widgets
are otherwise identical, and the site's English does not reach either:

```html
<span class="lc-icons-posti-omologati ..."></span>   <!-- homologated SEATS -->
  <a href="#nota-numero_posti_omologati" ...>2</a>   <!-- footnote, skip it -->
  <span class="valore-caratteristica-modello">6 / 5</span>
<span class="lc-icons-posti-letto ..."></span>       <!-- BERTHS -->
  <span class="valore-caratteristica-modello">4</span>
```

Anchor on the name, never on position. These were `title="numero posti omologati"`
attributes until the 2026 redesign; the Italian words survived the move to class names,
and so does the rule.

**Two fields publish a list, and the first entry is the FMLV figure.**

* Seats read `6 / 5` — the `5` is a reduced-seat homologation Rimor offers to free up
  payload (85 kg per seat removed), not the standard figure.
* MTPLM reads `3500 / 3550 / 4100` — the first is the standard chassis; the rest are paid
  uprates. Sarus reads `3500 / 3650`, Horus a bare `3500`.

**The dimension rows pair outside with inside.** `outside width - inside width
2340 - 2200 mm` and `maximum outside height inside height 3040 - 2060 mm`. Only the first
of each pair is the FMLV figure.

**The overview block must be scoped to.** Every model page also carries an "other range
models" list, and the range and body-style links that name this layout appear again in the
navigation. `_OVERVIEW` brackets on `id="panoramica-modello"` and an `END PANORAMICA
MODELLO` **HTML comment** — worth knowing when trimming fixtures, since stripping comments
destroys the closing marker.

**Footnote links sit inside the label cell**, before its `</td>`, on any row carrying a
note. `_spec_row` allows for that and for the padding described below, which is why all
five table fields are built from one helper rather than written out five times.

## The two products with no factory page

Both keep MNC's price, body type, base vehicle and dimensions:

* **Horus 12** — `/int/en/gamma/horus/modello/12` now 302s to `/`. MNC sells it as a 2027
  and publishes its dimensions in the exact millimetre form, `5413 × 2050 × 2659 mm`.
* **Rimor Van 238** — the factory gives it a standalone `/int/en/special/rimor-van` page
  with no spec table. MNC files it under its **Horus** category, and MNC decides the
  range, so `manufacturer_range` is Horus and the model is `Van 238`. Its dimensions come
  from MNC's truncated metres, which the run flags.

For these two, MNC's seats and berths are taken **only when the two figures differ**
(both publish `3 berth with 4 travel seats`). Two equal figures cannot be told apart from
the repeat-the-seat-count bug, so they are left empty rather than guessed. Masses are
never taken from MNC, which publishes no MRO at all and no MTPLM for these two.

Worth a second look one day: Horus 12's MNC dimensions are **identical to Horus 54's**,
and MNC demonstrably copy-pastes between layouts elsewhere. Both are sub-6m Ducato vans
that plausibly share a shell, and the factory dropped Horus 12 before this could be
checked against it.

## What changed in September, and what it cost

The factory redesigned its model pages between 13 August and 5 September 2026 — a
changeover consistent with Caravan Salon Düsseldorf running 28.08–06.09.2026. **Five of
the previous adapter's six field extractors stopped matching**, leaving bed type as the
only field still parsing:

* The dimension cells gained `class="uc-first"` and newline padding, so `outside
  length</td>` no longer matched `outside length\n    </td>`.
* `title="numero posti omologati"` became `class="lc-icons-posti-omologati"`.

A run in that state would have failed safe — every field absent, so every change a no-op
and the stored figures preserved — but it would have silently stopped updating. That is
the argument for the plausibility floor and for asserting per-range counts, not just a
total.

The range also moved **41 → 37 layouts**, with Sarus dropping 13 → 6 while Kilig gained
12 → 16. Given the wholesale rename, that looks like a reshuffle between ranges rather
than seven deletions, and it is worth re-checking rather than believing.

**Two things got better.** The redesigned pages publish **MRO per model** (Kilig 5:
`MRO 2961 kg` against `3500 / 3550 / 4100 kg`), so `mro_kilograms` and
`mh_payload_kilograms` are available for the first time — 30 of 34 products carry a
payload now. And that removed the last reason to fetch the catalogue PDF, which existed
only for MTPLM and the chassis; the chassis now comes from MNC's `Vehicle:` line. **The
catalogue and leaflet machinery is gone entirely**, along with its season-and-version URL
probing, its unrecoverable column alignment, and the four leaflet fetches per run.

The old cross-document check (each range's leaflet republishing every layout's
`length × width`, compared as an unordered multiset) is replaced by the cross-site
dimension check, which is cheaper, needs no PDF parsing, and immediately found two errors
the leaflet check never could — because it compares MNC against the factory rather than
the factory against itself.

## First run

5 September 2026, all five ranges, **34 products and 396 fields with provenance**. Every
per-range count matches the survey above. Body types come out **7 campervan high top, 17
low profile, 10 over-cab** — every van a high top, as the height rule requires.
Hand-checked against both sources:

| | Kilig 66 Plus | Sailer 55 Plus | Van 238 |
|---|---|---|---|
| MNC lists it as | Kilig 66 2026 | 55 Plus, demo van only | Van 238 2026-Automatic |
| Price | £59,995 | £69,995 (pre-discount) | £56,995 |
| L / W / H (mm) | 7338 / 2340 / 2845 | 7338 / 2340 / 2845 | 5980 / 2050 / 2800 (MNC) |
| Seats / berths | 4 / 4 | 4 / 4 | 4 / 3 |
| MTPLM / MRO / payload | 3500 / 3017 / 483 | 3500 / 3051 / 449 | — |
| Body type | low profile | low profile | campervan high top |

Note Kilig 66 Plus: MNC calls it "Kilig 66", the factory now calls it "66 Plus", and the
stored model is the factory's current name. Its 7330 mm on MNC against 7338 mm on the
factory is truncation, within tolerance, and is what confirms the rename join is right.

Horus 54 is the useful case for the other direction: its MNC page gives exact
millimetres, so the check runs at **zero tolerance**, and the two sites agree on all three
axes exactly.

## What is unverified

* **`ncc_supplier_name`** is `Rimor`, inherited from the seed list and **not confirmed**
  against the NCC site's export dropdown.
* **`fmlv_manufacturer`** is `Rimor` from `resources/manufacturers-full-list.csv` (id
  `75`); it has not been checked against a real FMLV export, so the baseline join is still
  unproven and every run to date has classified all products as new.
* **The Rimor Van 238's range.** Filed under Horus because MNC files it there; the factory
  treats it as a standalone "RIMOR VAN". If FMLV would rather see a Rimor Van range, this
  is a one-line change to `RANGE_LABELS`.
* **Whether MNC's prices are on-the-road or ex-works.** The pages say only "£ 59,995" with
  options priced separately, and carry a "check our full current and technical
  specifications with us before placing your order" disclaimer.
* **The Sarus gap.** MNC lists 3 of the factory's 6 Sarus layouts. Read as a deliberate
  importer decision, per the rule that MNC defines the range — but it is the largest gap
  of the five and worth confirming it is not simply a page MNC has not finished building.
