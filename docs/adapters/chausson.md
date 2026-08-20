# Chausson — site survey and adapter notes

Surveyed and built 19 August 2026, against the **2027 range** on the UK site
`www.motorhomes-chausson.co.uk`.

Eighth manufacturer surveyed. Chausson is French, part of **Trigano VDL** — the same group
as Auto-Trail, though nothing about the two sites is shared. The canonical NCC name is
**Trigano VDL Chausson** (id 53), display name **Chausson**.

**19 models across 5 lines, all in scope.** No caravans; Chausson build motorhomes only.

| Line | Models |
|---|---|
| Low profiles | 627, 630, 640, 650, 660, 720, 777, 788, 798 |
| S Low Profiles | s514, s614, s697 |
| Overcab | c514, c656, c727 |
| Vans | v594 |
| X | x550, x640, x650 |

## What the requester brought to the survey

**The single most valuable thing here**, because it changed the source outright.

Left to my own devices I found `www.chausson-motorhomes.com` — via Trigano VDL's own brands
page, so a defensible route — and had begun surveying it. The requester then supplied
`www.motorhomes-chausson.co.uk`, "the source website for the current range", and afterwards
noted the `.com` English pages are useful too.

**They are different ranges, not subsets of one another:**

| | UK site | Global `.com` |
|---|---|---|
| Models | **19** | 25 |
| Lines | 5 | 6 |
| A-class | **absent** | present (7057, 7068) |
| Only there | x650 | fs, v594m, v594s, v690, v697, 7057, 7068 |
| Prices | **sterling** | none at all |

So the `.com` would have proposed **seven vehicles Chausson do not sell in the UK**, and
would have missed the x650. The UK site is the source; the `.com` is reference only — useful
because it is the same platform in English and carries the A-class line, should that ever be
imported.

## Where the data lives

**Plain server-rendered HTML. No JavaScript, no PDF, no login.** Each `/model/<slug>/` page
carries an accordion of specification rows:

```html
<li>
  <span class="caracteristique-nom">Overall width (m)</span>
  <span class="caracteristique-separateur">:</span>
  <span class="caracteristique-valeur">2.35</span>
</li>
```

Verbatim from `/model/650/`, the Low profiles 650:

```
Overall width (m)                                        : 2.35
Overall height (excl. roof rack) (m)                     : 2.92
Interior height (m)                                      : 2.11
Wheelbase (m)                                            : 3.75
Max technically permissible laden mass (kg)              : 3500
Vehicle bodycoach weight in running order (+/- 5%) (kg)  : 2896
```

Note `Overall height (excl. roof rack)` — the base-vehicle rule in
[`README.md`](README.md) is already satisfied by Chausson's own choice of figure.

**Berths, travelling seats, price, length and base vehicle are not in the accordion.** They
come from the listing cards, which appear on the homepage, `/ranges/`, every `/line/` page,
and in the carousel on each model page — see "The listing cards are the richer source":

```html
<span class="places_route picto">... <span> 4 </span></span>      <- travelling seats
<span class="couchages picto">...   <span> 2+1* </span></span>    <- berths
```

## The range comes from the H1, and it has to

The model page heading carries the line as a prefix:

```
Low profiles 650      Vans V594      Overcab C514      X X550      A-class 7057
```

That is the only reliable source for it, and it is not optional: **model numbers collide.**
`640` is both a Low profile (`/model/640/`) and an X (`/model/x640/`). Taking the range from
the number alone would merge two different vehicles, exactly as Coachman's `545` and
Auto-Trail's two Expeditions would.

**The `/line/<line>/` pages are no help.** Every one links all 19 models, because the model
list is global navigation rather than a per-line listing. Attribution must come from the
model's own page.

A useful consequence: the lines map almost directly onto FMLV's `body_type`, so getting the
line right supplies the body type nearly for free — the same gift Rimor's body-style URL
segment gives.

| Line | Body type |
|---|---|
| Low profiles, S Low Profiles | `coach_built_low_profile` |
| Overcab | `coach_built_over_cab_bed` |
| Vans | `campervan_high_top`, by the roof-height rule in [`README.md`](README.md) |
| X | `coach_built_low_profile` — decided 19 August 2026 |
| A-class (`.com` only) | `a_class` |

## The trap: the labels and the values do not come in matching numbers

`/model/650/` has **26 `caracteristique-nom` and only 21 `caracteristique-valeur`.** Five
rows carry a label with no value — the chassis and option-price blocks at the top of the
accordion.

Pairing the two lists positionally therefore **drifts by five and silently produces wrong
numbers.** This is not hypothetical: the first attempt at this survey paired
`Overall width (m)` with `1845x605` (a side-locker aperture) and
`Max technically permissible laden mass (kg)` with `100L` (the waste water tank). Both look
like plausible measurements of something.

**Pair strictly within each `<li>`.** That is the whole of the fix, and with it all 21 rows
came out correct.

## The self-check: the graphic beside the floor plan

The model page's **Technical characteristics** block, next to the floor plan, renders the
same figures **twice** — once as an infographic and once as the text accordion. The
requester supplied the graphic for the X550, which reads:

```
5,99m  (length)      2,1m  (width)      2,75 m / 1,98 m  (overall / interior height)
kg 2822/3500         4 travelling seats     5 dining places     140 x 190 beds
```

Every one of those is in the page text too, and they agree exactly:

| From the graphic | From the accordion | |
|---|---|---|
| width 2,1 m | `Overall width (m) : 2.1` | ✅ |
| height 2,75 m | `Overall height (excl. roof rack) (m) : 2.75` | ✅ |
| interior 1,98 m | `Interior height (m) : 1.98` | ✅ |
| kg **2822**/3500 | `Vehicle bodycoach weight in running order : 2822` | ✅ |
| kg 2822/**3500** | `Max technically permissible laden mass (kg) : 3500` | ✅ |
| 5,99 m length | the listing card's `porteur` picto: `5.99m` | ✅ |

So the graphic confirms the parse rather than being needed for it, and the `kg 2822/3500`
notation confirms the reading of the pair: **running order first, maximum laden second.**

**There is still no arithmetic self-check.** Chausson publish MTPLM and MRO but no payload,
and the `(+/- 5%)` is only a label — unlike Sunlight, which prints the band itself. What is
available instead:

1. **Two renderings of the same numbers on one page** — the graphic and the accordion. A
   parse that disagrees with the graphic is wrong, though comparing them automatically would
   mean reading an image.
2. **The listing cards republish** berths, seats, length, price and chassis on the homepage,
   `/ranges/`, all five `/line/` pages and every model page's carousel.
3. **Each line's nav "From" price equals the cheapest per-model card price in that line** —
   a genuine cross-check between two independently rendered figures.
4. Per-product bounds: `MRO < MTPLM`, and a derived payload in a plausible band.

Note that x550 and x640 genuinely publish **identical** width, heights, wheelbase, MTPLM and
MRO despite different lengths. That was checked rather than assumed — the two pages have
different content hashes, different `<h1>`s and one accordion each — so it is Chausson's own
data, not a parse picking up the neighbouring model.

### On the "technical information PDF"

The requester described the graphic as coming from a link that "creates a PDF". No
PDF-generating endpoint was found: the UK model pages carry no `.pdf` href, no
`admin-ajax` action for a document, and the only `pdf` strings on the page belong to an SEO
plugin's file-extension list. The two-column equipment list in the supplied image ("EXCLUSIVE
LINE ★★★ FIAT") looks like a catalogue page rather than the website.

**It does not matter**, because every number on it is already in the page's own HTML, as the
table above shows. If a per-model PDF does exist it would be a second source for the same
figures, not a source for anything new.

## The listing cards are the richer source

**Corrected 19 August 2026, after the requester supplied two screenshots.** An earlier pass
of this survey concluded that Chausson publish no per-model price, no overall length and no
base vehicle. All three were wrong. The cards carry them, and the price was missed for a
plain reason worth recording: **the site writes `GBP`, not a pound sign**, so a search for
`£` found only the nav block and none of the 68 real occurrences.

One card, in full:

```html
<span class="titre-modele">S614</span>
<div class="modele-details">
  <div class="prix"><p class="prix">From 58 790 GBP</p></div>
  <p class="accroche">The Slim Low-Profile S614 has been designed for families...</p>
  <div class="pictos pictos-modele">
    <span class="places_route picto">  ... 4      </span>   <- travelling seats
    <span class="couchages picto">     ... 4      </span>   <- berths
    <span class="places_repas picto">  ... 4      </span>   <- dining places
    <span class="porteur picto ford">
      <img alt="Ford"> <span>6.59m</span>                   <- base vehicle AND length
    </span>
  </div>
  <a href=".../model/s614/">View the model</a>
  <a data-finition="titanium line" data-titre="S614">Compare</a>
</div>
```

So between the card and the model page, the record is essentially complete:

| Field | Source |
|---|---|
| `rrp_pounds` | card, `p.prix` — `From 58 790 GBP` |
| `berths` | card, `span.couchages` — standard figure of `2/3*` |
| `mh_passenger_seats_inc_driver` | card, `span.places_route` |
| `mh_length_mm` | card, inside `span.porteur` — `6.59m` |
| `base_vehicle_manufacturer` | card, `span.porteur picto <make>` and the `img alt` |
| `mh_width_mm`, `mh_height_mm` | model page accordion |
| `mtplm_kilograms`, `mro_kilograms` | model page accordion |
| `mh_payload_kilograms` | derived |
| `manufacturer_range` | model page `<h1>` prefix |

**The base vehicle varies by model and is worth having**: Ford for most, **Citroën** for the
big overcabs (C656, C727), **Fiat** for the V594 van and the whole X line.

### The price is a per-model "From", which is usable

Ruling from the NCC side, 19 August 2026: **a "From" price shown against one specific model
may be used as the guide price; a "From" price shown against a group of models may not.**
Chausson's cards are the former — each names one model — so `rrp_pounds` is proposed.

The five line-level figures in the page's nav block are the latter, and are not used. They
do, however, give a **free cross-check**: each line's nav "From £" equals the cheapest
per-model price in that line.

### The new trap: the details follow the title

A card's `modele-details` block comes **after** its `titre-modele`, and the cards are
siblings in one container. Associating a details block with the nearest *preceding* title
therefore attributes **the previous model's** price, berths and length. It happened on the
first attempt here: S614's figures were read as S697's, and only the screenshots caught it,
because both cost £58,790 and differ solely in berths (4 against 2/3*).

Anchor on the title and read **forward**, ending at that card's own `/model/<slug>/` link.
Verified: all 18 cards then match, including both models the requester screenshotted.


## First run — 19 August 2026

**18 products, one skipped, none dropped.** 19 fetches: `/ranges/` once, then one page per
linked model.

| Line | Models | Prices | Body type |
|---|---|---|---|
| Low profiles | 9 | 8 of 9 | coach built low profile |
| S Low Profiles | 3 | 3 | coach built low profile |
| Overcab | 3 | 3 | coach built over cab bed |
| Vans | 1 | 1 | **campervan high top**, from the roof rule |
| X | 2 | 2 | coach built low profile |

The skip is `x650`, narrated with its reason. Exactly **one required field is blank across
all 18 products**: the Low profile 640's price, which Chausson do not publish.

Three products hand-checked against material the requester supplied:

| | Source | Adapter |
|---|---|---|
| S614 | card: £58,790, 4 berths, 4 seats, Ford, 6.59 m | 58790, 4, 4, Ford, 6590 ✅ |
| S697 | card: £58,790, **2/3\*** berths, 4 seats, Ford, 6.59 m | 58790, **2**, 4, Ford, 6590 ✅ |
| X550 | graphic: 2,1 m wide, 2,75 m high, kg **2822/3500** | 2100, 2750, MRO 2822, MTPLM 3500 ✅ |

The S614/S697 pair is the one that matters: they cost the same and differ only in berths, so
they are the check that a card's details were read forward from its own title rather than
backwards from the next one.

### A bug worth recording, because it was mine and not the site's

The overall length came out blank for all 18 on the first run. The cause was a stray
**backspace character** (`0x08`) at the end of the length pattern — a `` written into a
non-raw string by the script that patched the file, so the regex demanded a literal backspace
after `m` and could never match. Every component of the pattern matched in isolation, which
made it look like a site problem for far longer than it should have.

Two things to take from it: compare a compiled pattern against a known-good literal with
`repr()` when it fails inconsistently, and prefer editing source with a proper editor over
patching it with escaped strings.

## First run against the real FMLV baseline — 20 August 2026, run #12

**Nothing matched: 0 changed, 18 new, 25 disappeared.** The scrape itself was clean — 18
products, 19 fetches, one warning for the Low profile 640's missing price, exactly as the
build run behaved. The diff is the problem, and it has two causes, one now fixed and one open.

### `ncc_supplier_name` was wrong, so no run had ever been possible

The registry recorded it as `Trigano VDL Chausson` and this file's notes said it was confirmed
on 19 August. It was not: Nova's "Export Products by Supplier" dropdown has 112 labels and the
one for this brand is plain **`Chausson`**. `fetch-export` failed with a Playwright timeout on
`select_option`, which reads as a site problem rather than a bad value — the real message is
buried in "did not find some options".

Corrected to `Chausson`, after which the export downloads: **129 products, 25 of them 2026.**
Two things that export settles:

- **`fmlv_manufacturer = "Trigano VDL Chausson"` is right** — that is the literal `manufacturer`
  value on all 129 rows, with `Chausson` as the display name. The two strings genuinely differ,
  which is exactly the case `manufacturers.README.md` warns about.
- **Confirming a supplier label by eye is not confirming it.** The only proof is a successful
  `fetch-export`. Enumerating the dropdown takes one Playwright call and is worth doing for any
  brand whose label has not actually been used.

### FMLV keys Chausson by finish line, the adapter by body style — nothing overlaps

| | Ranges |
|---|---|
| The adapter emits | `Low profiles`, `S Low Profiles`, `Overcab`, `Vans`, `X` |
| FMLV holds | `First`, `Sport`, `Titanium`, `Exclusive`, `Ultimate` |

Model numbers line up well — FMLV's `650`, `640`, `X550`, `C514`, `S614`, `V594` are the
adapter's — but the ranges share no token, so `Low profiles 650` against `Titanium 650` scores
0.25 and falls below the 0.5 threshold. Hence 18 new and 25 disappeared with nothing in between.

**FMLV's model is layout × finish line, and it is not a mistake.** The same layout appears under
two lines at different prices: `S514` is £55,790 as a First and £58,290 as a Sport; `640` is
£67,290 as a Titanium and £69,290 as an Ultimate. That is 25 rows from roughly 18 layouts.

**The site publishes the lines, but prices only one of them.** Each model page carries a
Body / Furnishings / Fabrics block pairing decors with lines — "Alto — Sport Line", "Sarinen —
Ultimate Line", "Sydney — First Line" — so which lines a layout is offered in *is* discoverable.
What is not discoverable is a price or a weight per line: the card price is a single figure, and
it matches the cheapest line (the S514 card says £55,790, the First price; the Low profiles
"From £66,590" is the Titanium 650). So the site can currently support the entry-line variant of
each layout and no more.

**This is left as an open decision, not guessed at** — see the last item under Known gaps.

## Known gaps

- **`x650` is a stale link, not a model. The real count is 18, not 19.** `/model/x650/`
  returns HTTP 200 but soft-404s: its `<title>` is the `/ranges/` page's, its `<h1>` reads
  "Find your ideal Chausson camper", and it has **no specification accordion at all**. It is
  linked from `/ranges/` and has no card. Treat a model page without an accordion as absent
  rather than as a product with no data.
- **`/model/640/` publishes two vehicles' figures in the same cells**, separated by ` / `:

  ```
  Overall width (m)                  : 2.35 / 2.05
  Overall height (excl. roof rack)   : 2.92 / 2.65
  Interior height (m)                : 2.11 / 1.89
  Wheelbase (m)                      : 3.95 / 4.035
  running order (+/- 5%) (kg)        : 3007 / 3085
  Fresh water capacity               : 105L / 85L
  ```

  The second column is not a variant of the 640 — a 2.05 m wide, 2.65 m high vehicle on a
  4.035 m wheelbase is a **van**, and those three figures match the V594 exactly. Something
  in Chausson's CMS is merging two models into one page. The base-vehicle rule already gives
  the right answer (take the first figure, which agrees with the card's 6.99 m low-profile
  length), but a parser that took the last would put a van's dimensions on a coachbuilt and
  nothing downstream would question it.
- **The low-profile `640` has no price** on its card; all 17 other real models have one.
- **`x640` has no length** in its `porteur` picto, though it has a price.
- **The card's displayed name is not unique.** `x550` and `x640` render as `550` and `640`,
  and `640` is *also* a Low profile — two cards show `640` with different prices, chassis and
  berths. The **slug** is the identity; the displayed name is not.
- ~~**`ncc_supplier_name`** unconfirmed~~ — **confirmed 19 August 2026 as
  `Trigano VDL Chausson`**, the same string as `fmlv_manufacturer`. Worth noting that it
  matches here, because Adria's does not (`Adria Caravans & Motorhomes` against
  `Adria Mobil`), so the two columns cannot be assumed equal in general.
- **`fmlv_manufacturer = "Trigano VDL Chausson"`** is the canonical NCC name for id 53 and
  is not confirmed against a real FMLV export. The export may well say just "Chausson".
- ~~**The X line's body type** is undecided~~ — **decided 19 August 2026: coach built, and
  specifically `coach_built_low_profile`.** FMLV offers no plain "coach built", only low
  profile and over cab bed, and the X has no over-cab bed — it is a compact on a 3.8 m
  wheelbase with a 1.98 m interior height. Its 2.1 m width is what made this a judgement
  rather than a lookup, sitting between a van's 2.05 and a coachbuilt's 2.35.
- **`data-finition`** on the compare button records a trim line ("titanium line"), which the
  screenshots show under the model name. Not currently mapped to any FMLV field, but it is
  there if wanted.
- **No PDF found anywhere on the UK site** — zero `.pdf` hrefs on `/catalog/`, `/ranges/`,
  `/schedule/`, `/sitemap/`, `/end-of-season-offers/` or any model page, and no document-
  generating endpoint. The HTML is the source, and it is sufficient — see "On the technical
  information PDF" above.
- Because prices are quoted in sterling on the UK site, **there is no currency to convert** —
  Morelo's fixed exchange rate has no equivalent here.

- **OPEN DECISION: how the finish lines should be modelled.** Until this is settled, a Chausson
  run cannot produce a usable diff. Four routes, for the NCC side to choose between:

  1. **Emit range = finish line, entry line only.** Matches roughly 18 of FMLV's 25 rows and
     leaves the higher-line rows reported as disappeared every run, which is noise a reviewer
     would have to learn to ignore.
  2. **Emit one product per (layout, line) the site lists**, carrying the entry price for all of
     them. Reaches all 25, at the cost of a knowingly wrong price on the dearer lines - which
     the guide-price rule in [README.md](README.md) may or may not tolerate.
  3. **Ask Trigano for a price list per line.** No PDF price list exists anywhere on the UK site,
     so this is the only route to real per-line prices.
  4. **Leave Chausson scrape-only** until FMLV's own trim-level modelling is revisited.

## Traps found while surveying

1. **Three wrong Chaussons, all plausible.** `chausson.fr` is a **building-materials**
   company; `chausson.co.uk` is **Central Motorhomes**, an Irish dealer in Lisburn whose
   brochures stop at **2020**; `chausson.de` is a German dealer. None is the manufacturer.
   The real sites were confirmed from Trigano VDL's own brands page — worth doing for any
   manufacturer whose brand name is also a common word or surname.
2. **The English site is only part-translated.** `Portillon latéral côté droit`,
   `Capacité réservoir carburant`, `Feux de cuisson`, `Poids tractable maximal` and
   `Implantation` are still French on the UK site. Match the English labels for the fields
   wanted, and do not assume a label will be translated tomorrow.
3. **Berths use two different separators and a footnote.** `2+1*`, `4+1*`, `2/3*`, `3/4*`,
   and plain `4`, `6`, `7`. Per the data rules the standard (lower) figure is recorded and
   the published string goes into the provenance.
4. **MRO can be a dual value** — `2858 / 2951` on the `.com` v594 — so take the first, as
   the base-vehicle rule requires.
5. **`/line/` pages are global navigation, not listings.** All five link all 19 models.

## What this would add to the general pattern

- **Confirm the brand's own domain through the parent company.** Three different businesses
  hold plausible Chausson domains. Trigano VDL's brands page settled it in one fetch.
- **A market site can be a different range, not a subset.** The UK and global sites differ
  in both directions — seven models the UK lacks, one it uniquely has. Checking for a
  market-specific edition is already in the guidance for *currency*; this is the same check
  mattering for the *roster*.
- **When labels and values are separate elements, count them before pairing them.** A
  mismatch of five between two lists is invisible in the output and yields values that look
  like measurements of something.
