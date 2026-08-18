# Coachman — site survey and adapter notes

Surveyed 16 August 2026 against the 2026 site; **adapter written 17 August 2026** against
the 2027 site, once Coachman had published it.

Coachman is the seventh manufacturer surveyed and the first that makes **both caravans and
motorhomes**. It is also the first where the identity of a product and the specification of
that product come from two different systems and must be joined through a **taxonomy term
ID** — the page itself never states which range a motorhome belongs to.

**6 motorhomes across 4 ranges, in scope. 20 touring caravans, out of scope.**

| | Ranges | Models |
|---|---|---|
| Motorhomes (in scope) | Avventura, Sportivo, Travel Master, Travel Master Imperial | 6 |
| Caravans (out of scope) | Acadia, VIP, Laser, Lusso | 20 |

## What the requester brought to the survey

Recorded because none of it is discoverable from the site, and two points changed the plan:

- **Coachman make motorhomes as well as caravans.** Worth stating plainly because the
  surveyor's first assumption was that they were a caravan-only brand — they are best known
  for touring caravans, and the NCC contact list has them under *both* headings with the
  same contact. They are in scope.
- **The site is due to be updated on 17 August 2026** to the 2027 range, and **may add a new
  campervan model**. Everything below describes the 2026 site; it is a day from changing.
- **Some weights are missing from the 2027 data.** Expected, and handled: an unfound figure
  must surface blank and narrated, never inherited — see the missing-data rule in
  [`README.md`](README.md). Gaps here are a data condition, not a parse failure.
- Contact is **Jackie Shipley**, `jackie@coachman.co.uk`.

## The 2027 range, from the preview spec sheet

The requester supplied *Coachman, 2027 preview floorplan and spec sheet A4 v2.3* on
16 August 2026 — a document that is **not on the website**, and which the site was due to
catch up with on 17 August. It changes the roster substantially and is the reason this
adapter should be written against 2027 rather than the 2026 site.

**In scope grows from 6 to 10**, and a whole new campervan range appears:

| Range | 2026 site | 2027 preview | Change |
|---|---|---|---|
| Avventura | 545, 565 | 545, 565 | — |
| Sportivo | 565 | 565 Compact *(new)*, 565, 565 TRAQ *(new)* | 1 → 3 |
| Travel Master | 545, 565 | 545, 565, 565 L *(new)* | 2 → 3 |
| Travel Master Imperial | 845 | **absent** | likely discontinued |
| **Veloce** (campervan) | — | VR65 *(new)*, VL65 *(new)* | 0 → 2 |
| | **6** | **10** | |

Caravans move too, and are still out of scope: Acadia gains a 655 Xtra and loses the 460,
Laser loses the 480 Xtra, Lusso gains a III. Nineteen caravans in the preview against
twenty on the 2026 site.

### The site can show a model that is not in the current line-up

**Travel Master Imperial 845 was in Coachman's 2025 line-up and *not* in 2026** — yet on
16 August 2026 it is live on the site, priced at £206,650, indistinguishable from the five
genuinely current motorhomes. The requester was surprised to see it there.

This is the most important thing learned about this source, and it generalises beyond one
model: **presence on the website is not evidence that a model is current.** An adapter that
takes the site's product list as the roster will propose a discontinued vehicle as a live
one, and nothing downstream would question it — it has a price, a weight and a page.

Two consequences:

- The roster needs corroboration from something with a model year on it. The preview spec
  sheet and the dated price list both qualify; the website does not.
- A model on the site but absent from the current-year documents is a **candidate for
  archiving**, not a product to propose.

**The rule for this one, agreed 16 August 2026:** if the 845 is still on the site tomorrow
alongside the other 2027 models, treat it as back for 2027 and include it. If it is gone,
exclude it. Either way the ambiguity is resolved by tomorrow's update rather than guessed
at now.

### The identity collision gets much worse

The 2026 site already had `545` twice. **In 2027 the string `565` belongs to five different
vehicles** across three ranges — Avventura 565, Sportivo 565, Sportivo 565 Compact,
Sportivo 565 TRAQ, Travel Master 565 — plus a Travel Master 565 L. A card heading is
useless on its own, and this is no longer an edge case but the dominant pattern. The
taxonomy-ID join described below is not defensive over-engineering; without it most of the
2027 range would be unidentifiable.

Note also that the three Sportivos differ **only** by suffix and carry different weights:
565 Compact and 565 at 3500 kg, 565 TRAQ at 4500 kg (its spec page says
`3500kg AL-KO chassis (option to upgrade to 3900kg) on 565` and `4500kg AL-KO chassis
(TRAQ only)`). Truncating or normalising away the suffix would merge a 3500 kg van with a
4500 kg one.

### What the preview does and does not publish

For every motorhome and campervan it gives exactly **three** fields:

```
Base vehicle    Mercedes-Benz
Berths          2
MTPLM           4500kg
```

No mass in running order, no payload, no length, no width, no height, and **no prices at
all**. This is the concrete form of the requester's warning that "some weights are missing":
MRO is absent for the entire 2027 range, so payload cannot be derived from this document.
The website remains the only source for price, length, seats and MRO — which is why the
adapter is built against the site, with this document as the roster and the cross-check.

The caravan pages publish a different trio again — Berths, Axles, Width in feet — so a
caravan phase cannot reuse the motorhome field mapping.

The document is explicitly provisional: *"reserves the right to, and does from time to time
alter technical specifications, prices and model ranges"*. Treat the roster as firm and the
figures as pending the site.

### Coachman state their model year

> *"Touring caravans are designated by the model year. The model year runs from the 1st
> September to the 31st August."*

An unusually precise statement of something the project had only inferred, and it sits
squarely inside the July–September rollover window described in
[`README.md`](README.md) — a 2027 preview circulating in mid-August, with the year turning
on 1 September. Stated for caravans; whether Coachman apply the same convention to
motorhomes is not said.

## Scope: keeping the caravans out

The prototype covers motorhomes and campervans only. Coachman separate the two cleanly at
every level, so this costs nothing:

- Two WordPress post types, `motorhome` and `caravan`, with separate REST endpoints and
  separate Yoast sitemaps (`motorhome-sitemap.xml`, `caravan-sitemap.xml`).
- Two taxonomies, `motorhome_model` and `caravan_model`.
- Homepage sections tagged `listings--posts-<n>-motorhome-<id>` against
  `listings--posts-<n>-caravan-<id>`.

`categories=motorhome` on the registry row, and every fetch below is motorhome-only. The 20
caravans are listed in the registry notes so the caravan phase has a starting point.

## Where the data lives — three places, and a join

Nothing here is behind JavaScript, but only because of the route chosen. **The two pages a
person would reach for are both useless to a parser:**

- `/coachman-motorhomes/` — the models index. 213 KB of HTML containing **no products, no
  prices, no specs and not a single product link**. Client-side rendered.
- `/motorhome/<slug>/` — the per-model pages. 192 KB each, and equally empty: no MTPLM, no
  price, no berths.

The data is in three other places:

**1. Identity — `/wp-json/wp/v2/motorhome?per_page=100`.** The WordPress REST API is open,
unauthenticated and returns all six products with their full titles:

```
slug=avventura-565            title="Avventura 565"       class_list=[… motorhome_model-avventura]
slug=travel-master-imperial-845  title="Travel Master Imperial 845"
```

**2. Ranges — `/wp-json/wp/v2/motorhome_model`.** Four terms, each carrying a `count`:

```
id=49  avventura                Avventura                count=2
id=9   sportivo                 Sportivo                 count=1
id=8   travel-master            Travel Master            count=2
id=56  travel-master-imperial   Travel Master Imperial   count=1
```

**3. Specifications — the homepage.** Every product is server-rendered into a card, twice
(52 cards for 26 products). A motorhome card reads:

```html
<div class="listings--posts--grid …">
  <h3><div class="title-box"><img src="…/sportivo-logo.svg" alt=""> 565</div></h3>
  <div class="listing--features"><ul>
    <li><span>Price</span><span>£117,075.00<span class="otr-price-span">*</span></span></li>
    <li><span>Berths</span><span>2</span></li>
    <li><span>Travelling seats</span><span>2</span></li>
    <li><span>Length</span><span>7445mm</span></li>
    <li><span>MTPLM</span><span>3500 kg</span></li>
    <li><span>Mass In Running Order</span><span>3020 kg</span></li>
  </ul></div>
```

That is price, berths, seats, length, MTPLM and MRO for every model — the fields FMLV
actually chases, minus width, height and payload.

## The trap: a motorhome card never says which range it belongs to

**The card's heading is the model number alone.** `545`, `565`, `845`. And `545` appears
**twice on the same page as two different vehicles**:

| Card heading | Price | Length | MRO | Actually |
|---|---|---|---|---|
| `545` | £110,725 | 7996 mm | 3250 kg | **Avventura 545** |
| `545` | £128,890 | 8391 mm | 3571 kg | **Travel Master 545** |

Reading the heading alone merges two products, or attaches one's weights to the other. This
is the same class of failure as Auto-Trail's two Expeditions, but worse: there, the model
numbering differed (`68` against `C73`); here the two collide exactly.

**The range is recoverable only from the enclosing section's class**, which carries the
taxonomy term ID:

```html
<div class="listings--posts bg-lightgray-2 listings--posts-0-motorhome-49">   <- 49 = Avventura
```

Two things make that safe rather than fragile:

- The ID is joined to `/wp-json/wp/v2/motorhome_model`, so the **name comes from the API**,
  not from a hardcoded mapping. If Coachman renumber their terms, the join still holds.
- The reconstructed `"<range> <model>"` must equal a title in the API roster. `Avventura` +
  `545` = `Avventura 545`, which exists; a mis-attribution produces a string that does not.

**The caravan route does not work here.** Caravan cards carry a range logo
(`acadia-logo.svg`) and a product photo filename (`2026-Acadia-460-300x154.png`) that both
name the range. Motorhome cards have **neither** — no photo filename at all, and a logo only
for Sportivo. Anything relying on the image filenames would work in testing against caravans
and silently fail on the products actually wanted.

## The self-check

**There is no arithmetic self-check.** Coachman publish MTPLM and MRO but no payload, so
payload is derived and cannot verify itself — the same position as Auto-Trail and Sunlight.
What replaces it is unusually good, because the manufacturer's own CMS counts its products:

1. **The taxonomy publishes a `count` per range** — 2, 1, 2, 1. The cards found in each
   homepage section must match it. This is a completeness check Coachman maintain against
   themselves, and it is per-range rather than per-document.
2. **The API roster is the authority on what exists** — six titles. Every card must join to
   exactly one, and every title must be claimed by exactly one card.
3. **Range + model must reconstruct the API title exactly**, which is what makes the
   term-ID join self-verifying rather than trusted.
4. **The price list PDF independently republishes five of the six prices**, so it is a
   cross-document check on price — see below.

Per-product sanity beyond that: `MRO < MTPLM`, and a derived payload in a plausible band.

## The price list, and what it is good for

`/downloads/2026-motorhomes-price-list/` →
`…/2025/09/Motorhome-Price-list-Options-2026-02-09-UK.pdf`. One page, real extractable text,
effective 9 February 2026:

```
Avventura 545 £110,725.00
Avventura 565 £110,725.00
Sportivo 565 £117,075.00
Travel Master 545
Travel Master 565
…
OTR Price* (Inc. VAT)
£128,890.00
£128,890.00
* Includes First Registration, Vehicle Excise Duty and Registration Plates
* Prices exclude Northern Ireland
```

Two reasons it is a **cross-check and not the source**:

- **Its text extracts out of order.** The two Travel Master names are separated from their
  two prices, which arrive several lines later under the column header. Pairing them by
  reading order is exactly the mistake that defeated Rimor's catalogue.
- **It is missing a product.** Travel Master Imperial 845 does not appear at all, though the
  homepage prices it at £206,650.

What it does settle is the **basis**: `OTR Price* (Inc. VAT)`, including first registration,
VED and plates. That is the on-the-road figure FMLV records as its guide price, so the
homepage prices can be taken as published. Note the Northern Ireland exclusion.

## Traps found while surveying

1. **The models index and the model pages are client-side rendered** and contain nothing.
   Concluding "Coachman needs a browser" from those two pages would be wrong — the REST API
   and the homepage give everything without one.
2. **`545` is two different motorhomes.** See above. The single most dangerous thing here.
3. **Motorhome cards carry no range identifier of their own** — not in the heading, not in
   an image filename, and the logo `alt` attributes are empty.
4. **Broken current download links, with the correct path hidden in the oEmbed parameter.**
   The 2026 caravan price list hrefs `…/2025/09/Price-list-Options-2026-Season.pdf` and the
   2026 handbook hrefs `…/2025/11/Coachman-2026-Handbook-and-Techinal-Data.pdf` — **both
   return an HTML 404 page**. The working URLs (`…/2026/01/…`, and note the misspelling
   `Techinal`) appear only inside the `wp-json/oembed` links on the same page. Fetch and
   check the content type; do not assume a `.pdf` href is a PDF.
5. **The downloads page lists 62 documents back to 2009**, including price lists and
   technical specifications for most years. Match on the current year and rediscover per run.
6. **The 180-page "2026 Handbook and Technical Data" is caravans only.** It mentions MTPLM 69
   times and payload 42 times, which looks ideal — and contains the strings `Travel Master`,
   `Sportivo` and `Avventura` exactly **zero** times. A promising-looking document that
   covers the wrong product line.
7. **Every product appears twice on the homepage** (52 cards, 26 products), so cards must be
   deduplicated rather than counted.

## What the 2027 site actually published — and the first run

Checked on **17 August 2026**, once Coachman had updated. The answer to each of the four
questions below, and one finding that was not anticipated at all.

**The motorhome roster did not grow.** Still the same six, *not* the eight in the preview:
Sportivo has only its 565 (no Compact, no TRAQ) and Travel Master only 545 and 565 (no
565 L). The three new models are not published yet.

**But 2027 pricing has been applied**, so the update is real rather than absent:

| | 2026 | 2027 site | |
|---|---|---|---|
| Sportivo 565 | £117,075 | **£120,831** | +£3,756 |
| Travel Master 545 / 565 | £128,890 | **£133,030** | +£4,140 |
| Avventura 545 / 565 | £110,725 | £110,725 | — |
| Travel Master Imperial 845 | £206,650 | £206,650 | — |

**The Imperial is present alongside the 2027 models, so it is included** — the rule agreed
on 16 August. It was in the 2025 line-up, absent from 2026, and is back.

**Veloce exists but has nothing to publish.** Coachman created a `campervan` post type and a
`campervan_model` taxonomy (term 60, `Veloce`, count 2) holding `Veloce VL 65` and
`Veloce VR 65`. But there is **no campervan section on the homepage** and the campervan model
pages are as empty as the motorhome ones, so the two products have a name, a range and no
numbers whatsoever. The adapter reads them, finds no card, and skips them with a narrated
reason rather than proposing two blank products. They will start working the moment the
cards appear, with no code change.

**The taxonomy IDs survived** — 49, 9, 8, 56 unchanged, and Veloce simply added 60. The join
reads them from the API rather than hardcoding, which is why a new range cost nothing.

**There is no 2027 motorhome price list**, only the 2026 one, which now disagrees with the
site (£117,075 against £120,831). **That costs a planned cross-check**: the price list can no
longer verify price. Downloads do have a 2027 caravan brochure and a 2027 caravan price list,
so the caravans are further ahead than the motorhomes.

### The unanticipated finding: `TBC` in a weight field

The 2027 caravan cards publish this:

```
Price                  £35,500.00*
Berths                 4
Length                 7390mm / 24′ 3″
Axles                  Single axle
MTPLM                  TBC
Mass In Running Order  TBC
```

**`TBC` where a weight should be.** This is the concrete form of the warning that some 2027
weights are missing, and it is a shape no previous manufacturer has produced. Three
consequences, all covered by tests:

- `TBC` must parse to **absent**, never to zero and never to an exception. It does.
- A product with `TBC` weights must still be **proposed with the weights blank**, not
  dropped: `_reconciles` treats missing figures as nothing to contradict rather than a
  contradiction. Dropping it would lose a real price and length over an unset weight.
- The blank then surfaces as `missing_required` for a human, which is the missing-data rule
  in [`README.md`](README.md) working as intended.

No motorhome card carries `TBC` today, but the caravans show it is Coachman's house style
for an unsettled figure, so the motorhomes are one publication away from it.

### First run — 17 August 2026

**6 products collected, 2 skipped, none dropped.**

| Range | Model | Berths | Seats | MTPLM | MRO | Payload | Length | Price |
|---|---|---|---|---|---|---|---|---|
| Avventura | 545 | 4 | 4 | 4500 | 3250 | 1250 | 7996 | £110,725 |
| Avventura | 565 | 4 | 4 | 4500 | 3250 | 1250 | 7996 | £110,725 |
| Sportivo | 565 | 2 | 2 | 3500 | 3020 | 480 | 7445 | £120,831 |
| Travel Master | 545 | 4 | 4 | 4500 | 3571 | 929 | 8391 | £133,030 |
| Travel Master | 565 | 4 | 4 | 4500 | 3571 | 929 | 8391 | £133,030 |
| Travel Master Imperial | 845 | 4 | 4 | 5880 | 5147 | 733 | 8822 | £206,650 |

The two skips are the Veloces, each narrated with the exact key that found no card. Seven
fetches in total: one homepage, then a taxonomy and a roster per post type.

**The critical case works:** Avventura 545 and Travel Master 545 both come through, with
their own weights and prices, 321 kg and £22,305 apart. Neither borrowed the other's card.

## The four questions this build had to answer first

Agreed with the requester: build against the 2027 range rather than the 2026 site. Before
writing any code, re-run the survey probes and settle these four:

1. **Does Veloce appear under the `motorhome` post type, or a new one?** Check
   `/wp-json/wp/v2/types` for a `campervan` type and `/wp-json/wp/v2/motorhome_model` for a
   Veloce term. If Veloce is a separate post type, the adapter needs a second endpoint and a
   second homepage section family — a structural difference, not a configuration one.
2. **Is Travel Master Imperial 845 still there?** Present alongside the 2027 models means
   include it; gone means exclude it. See the rule above.
3. **Do the homepage cards still carry price, length, MRO and travelling seats** for the new
   models, or only the three fields the preview publishes? The preview has no MRO at all, so
   if the site follows suit, payload cannot be derived for any 2027 product.
4. **Do the taxonomy term IDs survive the update?** 49/9/8/56 are WordPress term IDs; new
   ranges get new ones and Veloce will need one. The join reads them from the API rather
   than hardcoding, so this should cost nothing — but it is worth confirming rather than
   assuming, since it is the mechanism the whole identity story rests on.

## Known gaps

- **No width and no height are published anywhere** — the cards give Length only, and the
  `Technical` / `360°` / `Features` buttons on a model page were chased and are a dead end:
  the button text is not in the server HTML at all, the single-product REST endpoint has
  empty `acf` and `meta`, and every `admin-ajax` reference on the page belongs to a plugin
  (cookie consent, contact form, WhatsApp, popups). The panel is drawn client-side and no
  spec endpoint is discoverable without reading the theme's minified `main.js`. So two of
  FMLV's required fields stay blank on every product and surface as `missing_required`.
  **Asked of Coachman directly** — the right fix.
- ~~**No base vehicle manufacturer published**~~ — **resolved 17 August 2026, manually.**
  Coachman publish it nowhere on the site, but the 2027 preview spec sheet states it, so it
  is transcribed into `_BASE_VEHICLE_BY_RANGE`: Fiat for Avventura and Veloce,
  Mercedes-Benz for Sportivo, Travel Master and Travel Master Imperial. Held **per range**,
  which is how Coachman state it, is the safer assumption, and means the three unpublished
  2027 models inherit the right chassis with no edit — the Sportivo 565 TRAQ stays a
  Mercedes despite its different weight and 4x4 engine, which is the case a per-model table
  would have got wrong. Narrated on every run and flagged in the provenance as read from a
  document on a stated date, because **it cannot notice Coachman changing a chassis**.
  Re-verify at each model-year changeover, and a range not in the table is left blank rather
  than guessed.
- **No payload published**, so it is derived.
- **The 2027 changeover lands on 17 August 2026**, the day after this survey, possibly with a
  new campervan model. Everything above needs re-verifying then — particularly whether the
  new model appears under the `motorhome` post type or a new one.
- **`fmlv_manufacturer = "Coachman"`** is taken from `resources/manufacturers-full-list.csv`
  (ID 25) and is not confirmed against a real FMLV export.
- **`ncc_supplier_name` is unconfirmed** and deliberately left blank rather than guessed.
- The caravan side is mapped but not built. If the caravan phase starts, the same three
  sources serve it, and the caravan cards are *easier* — they name their own range.

## What this adds to the general pattern

- **A JS-rendered site can still be a plain-HTTP source.** Both pages a person would use are
  empty, and yet no browser is needed. Check the CMS's own REST API before concluding a site
  needs rendering — `/wp-json/wp/v2/types` lists every post type in one fetch and cost
  nothing to try.
- **When a listing shows a model number alone, assume it collides.** It did here, within a
  single category and on a single page. Identity must come from a source that states the
  range, and the reconstruction must be checked against a roster.
- **A CMS taxonomy's `count` is a free completeness check** — the manufacturer maintaining
  their own product count, per range, in a machine-readable field.
- **A `.pdf` href is not necessarily a PDF.** Two of Coachman's current documents 404 to an
  HTML page while looking like live links.
