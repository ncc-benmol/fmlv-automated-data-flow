# Etrusco — site survey and adapter notes

Surveyed and built 19 August 2026, against the **2027 model year** UK site at
`www.etrusco.com/gb/en/`. Ninth manufacturer, and the cleanest source since Sunlight.

Etrusco is an **Erwin Hymer Group** brand, built in Italy. **28 layouts across 8 families**,
all motorhomes and campervans; Etrusco build no caravans, so nothing needs excluding.

| | Families | Layouts |
|---|---|---|
| Campervans | CV-Model Fiat 5, CV-Model Plus 3, V-Model Ford 2 | 10 |
| Motorhomes | T-Model Fiat 4, T-Model Base 5, T-Model Ford 4, A-Model Base 2, I-Model Fiat 3 | 18 |

The survey originally counted 24 layouts across 7 ranges, from the price list PDFs. Both
figures were wrong, and the correction is the most useful thing in this document — see
[the roster](#the-roster-comes-from-the-sitemap-because-neither-menu-is-complete).

## What the requester brought to the survey

The UK URL, `www.etrusco.com/gb/en/modeloverview`, supplied before any fetching — which is
why this survey never went near the wrong market. Everything else below is theirs too, and
none of it is discoverable from the site.

**Etrusco is a "non-core" brand, and the UK site is a deliberate subset.** Etrusco, Bürstner,
Carado and Eriba are European brands of which only **a selection of the full range** is
offered in the UK, and the `/gb/en/` path is that selection. This is the explanation for what
the path segmentation only hints at: the UK roster is not an incomplete rendering of the
European one, it **is** the UK range. So it should be taken as authoritative and **not**
reconciled against a European roster, which would show models Etrusco do not sell here.

**They build every motorhome type** — A-class, coach-built low profile and over-cab bed — plus
campervans. The campervans are **very popular**, on price: they are regarded as good value.
The **CV 540** in particular sells well, which is worth knowing when reviewing a change to it.

**Do not plan on getting this data from the manufacturer.** Asking Erwin Hymer directly is
possible but **slow and not dependable**. The strategy for these brands is explicitly the
opposite of the one adopted for Coachman and Chausson, where the answer to a gap was to ask:
here, **build against the website, record the range as 2027, and re-run when the site
changes.** The website is the source of truth.

**Expect the roster to move.** August and September are when these brands are "intensely busy
deciding on their ranges", so a run today is a snapshot of a moving target — which is the same
window [`README.md`](README.md) describes for the model-year rollover generally.

Two decisions taken during the build, both theirs:

- **Payload is `MTPLM − MRO`**, in the knowledge that other derivations exist. Etrusco's table
  offers two tempting alternatives that are not payload.
- **A "from" price specific to one layout may be used as that layout's guide price.** Where a
  layout has no price of its own the choice would be to apply the base price to all, ask EHG,
  or leave FMLV as it is. In the event the question did not arise: all 28 layouts carry their
  own price.

## The site is market-segmented by path, which settles a question up front

Everything sits under `/gb/en/`, so there is a genuine UK edition rather than a global site to
be interpreted. That is a meaningfully better position than Chausson, where the UK and global
sites turned out to be **different ranges in both directions** and the global one had no
sterling at all. Here the question does not arise.

## Where the data lives — one source, the eight family pages

Plain HTTP, no JavaScript, no PDF, no login, and `robots.txt` is `Disallow:` with nothing
disallowed. **Eight fetches for the whole range.**

Each family page renders every layout's specification as **two tables**: the first holds the
labels, one `<td>` per row, and the second the values in the same order. Tables therefore pair
even-with-odd, and within a pair the two cell lists are zipped by position. That is safe in a
way zipping across the page would not be — each pair is one layout's own table, generated from
one row list — and the layout count is reconciled against the name count before anything is
paired.

The value table for the CV 540 DB, cleaned of markup:

```
Pricea)                                                    £59,099
Length | Width | Height (cm)                               541 | 205 | 270
Chassis                                                    Fiat Ducato
Mass in running order* (kg)                                2751 (2613 - 2889)*
Manufacturer-specified mass for optional equipment* (kg)   400
Technically permissible maximum laden mass* (kg)           3500
Permitted number of seats (including driver)*              4
Sleeping places                                            2 - 5 OPT
```

Mapping to `Motorhome`:

| Field | Source |
|---|---|
| `manufacturer_range` | the family's label — `CV-Model Fiat`, `T-Model Base`, `I-Model Fiat` |
| `model` | `h4.o-floorplan__subline` — `CV 540 DB`, `T 7400 SBC`, `CV 640 PB+` |
| `rrp_pounds` | `Pricea)`, the layout's own sterling figure |
| `mh_length_mm` / `mh_width_mm` / `mh_height_mm` | one cell, `541 \| 205 \| 270`, in **centimetres** |
| `mh_passenger_seats_inc_driver` | `Permitted number of seats (including driver)` — the exact FMLV basis |
| `berths` | `Sleeping places`, `2 - 5 OPT` → the standard figure, 2 |
| `mtplm_kilograms` | `Technically permissible maximum laden mass` |
| `mro_kilograms` | `Mass in running order`, leading figure, band kept for the self-check |
| `mh_payload_kilograms` | **derived**, `MTPLM − MRO` |
| `base_vehicle_manufacturer` | `Chassis` — first word of `Fiat Ducato` / `Ford Transit` |
| `body_type` | the range's **model letter** — see below |

**The layout name comes from the subline, not the slider.** Each layout is named twice: once in
the floorplan slider as `h3.o-floorplan__headline`, and once as `h4.o-floorplan__subline`
inside its own content item, beside its own tables. Only the second pairs with the tables.

**Body type comes from the model letter**, which is Etrusco's own taxonomy and travels with the
vehicle name: `I 6900 SB` is an A class, `T 7.3 SCF` a coach-built low profile, `A 6.9 DB` an
over-cab bed. `CV` and `V` ranges instead go through the roof-height rule in
[`README.md`](README.md), and every Etrusco campervan clears it comfortably — 2700 mm on the
Fiats, 2870 mm on the Ford vans, against a 2300 mm threshold. The letter is used rather than the
URL path because **the paths disagree with each other**: `overcab-fiat` and
`model-overview/t-modelle-fiat_base` are both real, and a rule keyed on the path segment worked
on one shape and returned nothing on the other.

## The roster comes from the sitemap, because neither menu is complete

This is the part worth carrying to the next brand. Etrusco publish eight family pages, and
**no single menu lists them all**:

| Family | In `sitemap.xml` | On `/gb/en/modeloverview` | Path shape |
|---|---|---|---|
| CV-Model Fiat | yes | yes | `/models/campervans-fiat` |
| **CV-Model Plus** | yes | yes | `/models/model-overview/cv-modelle-fiat_plus` |
| V-Model Ford | yes | yes | `/models/vans-ford` |
| T-Model Fiat | yes | yes | `/models/semi-integrated-fiat` |
| **T-Model Base** | yes | yes | `/models/model-overview/t-modelle-fiat_base` |
| **T-Model Ford** | yes | **no** | `/models/semi-integrated-ford` |
| A-Model Base | yes | yes | `/models/overcab-fiat` |
| I-Model Fiat | yes | yes | `/models/integrated-fiat` |

Two traps, and between them the three bolded families are **12 of the 28 layouts**:

1. **`semi-integrated-ford` is in neither menu** — not the page navigation, not the model
   overview. It is only in the sitemap. Four Ford semi-integrateds, and the newest family
   Etrusco sell here.
2. **Two families sit under a longer path with German-spelt slugs**, `cv-modelle-fiat_plus` and
   `t-modelle-fiat_base`. They are linked from the overview, so a menu scrape finds them, but
   anything that builds a URL by assuming one path shape does not.

The overview's seven range cards were what exposed the gap: seven "from" prices, of which two
matched no layout the adapter had collected, and one collected family had no card at all. Both
loose ends came from the same cause.

## Why the price lists are not the source

Etrusco publish two UK price lists on `/gb/en/service/downloads`. Both extract as real text and
both look authoritative — 31 pages for the motorhomes, 17 for the campervans, spec pages laid
out two layouts to a page exactly like Sunlight's. They are still the wrong source:

- **They are labelled 2026 on the public page**, whatever the filenames say. The files are
  `etrusco_pim_pricelist_2027_uk.pdf` and their own footers read `ENG - 2027`, which is what
  this survey first reported. The requester challenged it and supplied the download page: the
  visible titles say **2026**, and the `2027` is an internal PIM asset code. My probe had read
  only the `<a>` text ("Download") and never the sibling title.
- **They are a model year behind the site.** They lack the four Ford T-models the site lists,
  and their weights are last season's.
- **They carry no prices at all** — zero currency symbols in either text layer, despite the
  "Prices and technical data" heading. The website is the only price source.

The general rule this produced is in [`README.md`](README.md): **the website over-rules the
PDFs, which are usually the last thing on a site to be updated.**

## The self-check: a printed tolerance band

The strongest self-check of any manufacturer so far, and the only *arithmetic* one since Swift.
The site states the rule and then prints it per layout:

```
Mass in running order* (kg)   2799 (2659 - 2939)*
```

2799 × 0.95 = 2659.05 and 2799 × 1.05 = 2938.95. The band is a **function of the mass**, so the
pair must be self-consistent, which makes it a free test that both were read from the same
column. A slipped column pairs one layout's mass with another's band and fails: the T 7.3 SF's
2858 kg against the T 7.3 SCF's `(2725 - 3011)` is two real figures from two neighbouring
vehicles, and nothing downstream would question the result. The arithmetic does. Three
kilograms of slack is allowed for the printed rounding. **All 28 layouts pass.**

Plus one cross-document check: **each range's "Price from" figure on the model overview equals
the cheapest layout price in that range** — two independently rendered numbers, verified on all
seven ranges that carry a card. T-Model Ford has no card, so it has no figure to check against,
which is the same fact that nearly lost the family.

## Traps found while surveying and building

1. **`Manufacturer-specified mass for optional equipment` is not payload.** It sits directly
   between the two masses and looks like it belongs there. It is a cap on factory-fitted extras
   — 341 kg on the T 6.9 SF, against a real payload of 701 kg — and on the I 7400 SBC it is
   47 kg, which would have been a startling payload. [`sunlight.md`](sunlight.md) records the
   same field and the same warning.
2. **The Plus range repeats the base range's names with a trailing `+`.** `CV 600 DB` and
   `CV 600 DB+` are different vehicles at different prices (£59,999 and £60,999). Dropping the
   suffix collides six campervans onto three names, and the join back to FMLV is on the name.
3. **Dimensions are one cell, in centimetres** — `541 | 205 | 270`. Split on the pipe and
   multiply by ten. The same shape as Sunlight's `596 / 214 / 274`, with a different separator.
4. **Each layout is named twice**, in the slider and beside its tables. Only the subline pairs.
5. **The two `model-overview/` pages single-quote their head attributes** where the other six
   double-quote them, so patterns anchored on markup must accept either.
6. **The overview's prices are range-level.** Seven figures, seven ranges — easy to mistake for
   per-model, since a range card looks no different from a layout row.
7. **Two layouts can share a price legitimately.** The CV 640 SB and 640 PB are both £61,499
   and the A 6.9 DB and SB both £68,399; they differ only in bed arrangement. A duplicate price
   is not evidence of a collapsed parse.

## First run — 19 August 2026

**28 products across 8 families. Nothing skipped, nothing dropped, and zero blank fields** —
price, berths, seats, all three dimensions, both masses, payload, chassis and body type
populated on all 28. Eight fetches. Payload spans 421–749 kg, every layout on a 3500 kg chassis.

| Family | Layouts | Prices | Body type |
|---|---|---|---|
| CV-Model Fiat | 5 | £59,099 – £61,499 | **campervan high top**, from the roof rule |
| CV-Model Plus | 3 | £60,999 – £63,799 | **campervan high top** |
| V-Model Ford | 2 | £71,590 | **campervan high top** |
| T-Model Fiat | 4 | £68,399 – £72,799 | coach built low profile |
| T-Model Base | 5 | £66,499 – £68,399 | coach built low profile |
| T-Model Ford | 4 | £67,100 – £68,400 | coach built low profile |
| A-Model Base | 2 | £68,399 | coach built over cab bed |
| I-Model Fiat | 3 | £75,999 – £81,399 | a class |

Three products hand-checked against the page text, one per URL shape and chassis:

| | Source | Adapter |
|---|---|---|
| CV 540 DB | £59,099, `541 \| 205 \| 270`, Fiat Ducato, 2751 (2613 - 2889), 3500, 4 seats, 2 - 5 OPT | 59099, 5410×2050×2700, Fiat, MRO 2751, MTPLM 3500, payload 749, 4, **2** ✅ |
| T 6.9 SF | £67,100, `698 \| 232 \| 287`, Ford Transit, 2799 (2659 - 2939), 3500, 4 seats, 2 - 5 OPT | 67100, 6980×2320×2870, Ford, MRO 2799, MTPLM 3500, payload 701, 4, **2** ✅ |
| I 7400 SBC | £81,399, `740 \| 232 \| 295`, Fiat Ducato, 3079 (2925 - 3233), 3500, 4 seats, 4 - 5 OPT | 81399, 7400×2320×2950, Fiat, MRO 3079, MTPLM 3500, payload 421, 4, **4** ✅ |

The berth column is the one to look at: all three publish a range, and the standard figure is
what is recorded, per the data rules in [`README.md`](README.md).

### Two mistakes of mine worth recording, because neither was the site's fault

**The parser looked for an attribute that does not exist.** The first version read layout names
from `data-tab-title`, and the live run returned **zero products** with all six families
narrated as skipped. The attribute is nowhere on the page. What made it survive to a live run
was my own verification probe: it had a fallback regex I had forgotten writing, so the probe
found 20 layouts while the adapter found none. A probe that does not fail where the adapter
fails proves nothing. `tests/adapters/test_etrusco.py` now asserts the attribute is absent.

**The roster was short by two families and I inferred the wrong reason.** Reading the price
lists against the six family pages I had found, I concluded that T-Model Base and CV-Model Plus
had been *dropped* from the UK range — and wrote that into the adapter's docstring as evidence
that the PDFs were stale. They had not been dropped; they were on the site at a URL shape I had
not looked for. The PDFs were stale for a different reason. The lesson is narrow and practical:
**an absence you cannot explain is a gap in the search, not a fact about the manufacturer.**
The overview's own count — seven cards against six families — was sitting there the whole time.

## Known gaps and what is unverified

- **`ncc_supplier_name`** unconfirmed, and left blank rather than guessed. It is what
  `fmlv fetch-export` needs, so there is no baseline export for id 45 yet and this run was
  verified by collecting directly rather than by diffing. Note that Adria's differs from its
  `fmlv_manufacturer`, so the two cannot be assumed equal.
- **`fmlv_manufacturer = "Etrusco"`** is the canonical NCC name for id 45 and is not confirmed
  against a real FMLV export.
- **The `Pricea)` footnote text has not been read**, so the price basis — on-the-road or
  ex-works — is not recorded, which the guide-price rule in [`README.md`](README.md) asks for
  where it is known.
- **The T 7.4 SBC is priced £68,339** where its siblings T 7.4 SB and T 7.4 QBC are £68,399.
  Most likely a typo on Etrusco's side; recorded as published rather than corrected.
- **Model year is asserted, not stated.** Nothing on the site says 2027; the range is recorded
  as 2027 on the requester's instruction and the rollover timing in [`README.md`](README.md).

## What this adds to the general pattern

- **Take the roster from the sitemap, and reconcile the count against a second menu.** Neither
  Etrusco menu is complete, and one URL shape is not enough. The overview's card count is what
  caught it — a cheap check any brand with a range index can supply.
- **A path-segmented site answers the market question for free.** `/gb/en/` is unambiguous,
  where Chausson needed a supplied URL and a comparison of two rosters to establish the same
  thing. Check for a market path before assuming a single global site.
- **A live page can beat a good PDF.** The survey planned to parse the price lists because
  [`README.md`](README.md) says to look for one first, and that ordering is still right — but
  the test is whether the document is *current*, and the answer here was on the download page
  rather than in the file. See the PDF-versus-website rule in [`README.md`](README.md).
- **Verify with the code that will ship, not with a probe that has fallbacks.** A probe more
  forgiving than the adapter hides exactly the failure it was written to find.
