# Rimor — site survey and adapter notes

Surveyed 13 August 2026, against the **2025-26 season** website and leaflets
(`RIMOR - Pieghevole <range> 2025-26 ... WEB.pdf`, versions V2–V4).

Fifth manufacturer, and the first to break the pattern the previous four established.
`README.md` opens with "is there a brochure or price list PDF?" — for Rimor the answer
is *yes, and it is still the worse source*.

Be precise about why, because the obvious reading is wrong. **The catalogue is not
thin**: it publishes everything the website does plus wheelbase, MTPLM, engine, tank
capacities and equipment. It loses because it cannot say *which model a number belongs
to* — see "Do not read per-model columns out of the catalogue" below. The website wins
on **attribution**, not on content: one URL per model, one set of numbers on it.

The leaflets are the different case: those really do carry a strict subset of what a
model's own page gives, and earn their fetch only as the self-check.

**41 layouts across 5 ranges**, all in server-rendered HTML. No JavaScript, no login,
no AJAX, no state blob.

| Range | Body styles | Layouts |
|---|---|---|
| Horus | vans | 7 |
| Kilig | low-profile 7, overcab 5 | 12 |
| Sarus | low-profile 7, overcab 6 | 13 |
| Sailer | low-profile | 5 |
| Super Brig | overcab | 4 |

## The headline problem: no prices, and no usable payload

**Rimor publishes no price anywhere.** Not the HTML, not the leaflets, not the 60-page
catalogue — zero hits for `€`, `EUR`, `£`, `price` or `prezzo` across the whole
catalogue. The FAQ answers "Where can I find information on vehicle prices and delivery
times?" by pointing at a dealership. `rrp_pounds` and the price-range fields are
**never proposed**, exactly as for Swift.

**Masses are nearly as thin.** The catalogue gives `Maximum overall weight (kg)` —
MTPLM — but there is **no mass in running order and no payload figure per model**. All
the catalogue carries is a general note that the calculated MRO "has a tolerance of
+/- 5%". So `mro_kilograms` and `mh_payload_kilograms` stay empty, and the usual
`payload == MTPLM − MRO` check is unavailable.

And the MTPLM that *is* published is uniform: **3500 kg on every one of the 16 spec
pages**, i.e. every one of the 41 layouts. Every Rimor is a 3500 kg chassis. It is a
real field worth filling, but it carries almost no information and will never move
between runs. (An uprated 4400 kg chassis is offered on at least Sarus 9, quoted inside
the seats cell as `6 (+1 opt 4400 kg)` — an option, not the standard figure, and not
proposed.)

### The catalogue is presented behind a form, but the PDF is not protected

The catalogue is fronted by a lead-generation form at
`/int/en/sfoglia-il-catalogo-richiesta` — name, email, city, phone and three consent
checkboxes, posting back to itself with `lead-generation=1`. Only `privacy_1` ("I have
read the privacy policy") is actually validated; `privacy_2` (profiling) and
`privacy_3` (marketing) are optional.

**None of that is necessary.** The PDF itself is unauthenticated and sits at a
predictable path:

```
/public/local/simplex/Marchi/rimor/Lingue/catalogo/raw/RIMOR - Catalogo 2025-26 - EU - V7.pdf
```

`EU` is the English edition; `FR` (V6) and `DE` (V5) also exist, each on its own version
number. No form, no cookie, no token.

**But it is linked from no page on the site.** This is the one genuinely awkward thing
about it, and it inverts the rule every other adapter follows: there is nothing to
rediscover the URL *from*, so it has to be probed by season and version. The season
(`2025-26`) and the per-language version (`V7`) will both move.

The adapter therefore treats the catalogue as **optional enrichment**: probe descending
version numbers for the current and next season, and if nothing resolves, still emit all
41 products from the HTML with `mtplm_kilograms` and `base_vehicle_manufacturer` left
empty. A 404 here must never fail a run.

### Do not read per-model columns out of the catalogue

The spec tables look parseable and are not. pypdf returns an entire row as a **single
text run**:

```
y=546: x=45: 'Wheelbase (mm) 3450 4035'
y=533: x=45: 'Outside length (mm) 5413 5998'
y=520: x=45: 'Outside width - inside width (mm) 2050 - 1850'
```

That page covers **three** models (Horus 12, 38, 45) but the length row has **two**
values, because the layout prints a value once where it spans several columns. The x
coordinates give nothing — every run starts at x=45 — so there is no way to recover
which column a merged value spans. This is precisely the silent-misalignment failure
`README.md` warns about, and here it is unrecoverable rather than merely fiddly.

The way out is that **the two fields worth having are page-constant**: MTPLM (3500) and
engine (one per range) are the same for every column on the page, so they can be taken
without solving alignment at all. Everything varying per model — lengths, widths,
heights, seats, berths — comes from the HTML, where each model has its own page and no
alignment question exists.

## Site shape

Three levels, all plain HTML:

```
/int/en                                  # homepage nav — the only list of the 5 ranges
  /int/en/gamma/<range>                  # links body-style pages + the range leaflet PDF
    /int/en/gamma/<range>/<body-style>   # lists the models (name, seats, berths)
      /int/en/gamma/<range>/modello/<slug>   # dimensions, bedding solution
```

Two things to know about the entry point: **there is no `/int/en/gamma` index — it
404s** — and there is no sitemap, so the five ranges have to be read from the homepage
navigation. Body styles are `low-profile`, `overcab` and `vans`.

**Body type comes free from the URL segment.** No other manufacturer surveyed has
handed this over so cleanly — Swift and Sunlight need it inferred from which catalogue
a layout appeared in.

Model slugs are not all numeric: `modello/5` and `modello/9` sit alongside
`modello/66-plus` and `modello/suite`. An early version of this survey used `\d+` and
silently found 18 of the 41 layouts — a good illustration of why 1.5's public count
matters, except that Rimor never states one, so see below.

## The self-check

There is no payload arithmetic to lean on, because there are no masses. The redundancy
is **cross-document**: each range's leaflet independently republishes every layout's
`length x width`, and the model pages publish the same two numbers individually.

Crucially this check is **order-independent** — compare the two as an unordered
multiset, never by position. That matters because the leaflet text extracts in scrambled
reading order, exactly as `README.md` warns. The Kilig leaflet's page 1 renders as:

```
7
from 6970
to 7308 mm
...
5
from 6449
to 7338 mm
```

where the count `7` belongs with the `6449–7338` band (low-profile, 7 layouts) and `5`
with `6970–7308` (overcab, 5 layouts). Read in order, both are wrong. Matching
`(length, width)` pairs as a multiset sidesteps this entirely: it never asks where on
the page a number sat.

Verified at survey time across all four leaflets — **41/41 layouts, exact multiset
equality, nothing missing in either direction**:

| Leaflet | Covers | Layouts | HTML ∖ leaflet | leaflet ∖ HTML |
|---|---|---|---|---|
| Horus UK | Horus | 7 | — | — |
| Kilig | Kilig | 12 | — | — |
| Sarus | Sarus | 13 | — | — |
| SuperBrig-Sailer | Sailer + Super Brig | 9 | — | — |

Note the fourth: **Sailer and Super Brig share one leaflet**, so the check is applied to
the union of those two ranges, not per range.

A layout whose dimensions do not appear in its leaflet's multiset is dropped with an
`on_progress` warning rather than proposed.

**The catalogue was tested as a one-fetch replacement for the four leaflets and
rejected.** It carries the same `length x width` pairs, but only **39 of the 41** — its
Horus section is short by two `5998 x 2050` layouts. The leaflets are complete and the
catalogue is not, so the self-check keeps the four leaflet fetches even though the
catalogue is being fetched anyway for MTPLM and engine. Cheaper would have been wrong.

## Traps

**Seats and berths are only distinguishable by an Italian `title` attribute.** The
listing card renders two visually identical spans:

```html
<div title="numero posti omologati" class="caratteristica-modello">
  <span class="valore-caratteristica-modello">6</span>
<div title="numero posti letto" class="caratteristica-modello">
  <span class="valore-caratteristica-modello">4 (+ 2 opt)</span>
```

`posti omologati` is homologated **seats**, `posti letto` is **berths**. Anchor on the
title, never on position — the site is English-language but this attribute is not
translated.

**Berths are strings, not integers.** `4 (+ 2 opt)`, `4 (+2+1 opt)`, `2 (+2 opt)`. The
standard figure is the leading integer; the optional extras are exactly the "OPT"
convention Sunlight uses and are dropped the same way. Seats are usually a bare integer
but not always — Sailer and Super Brig layouts publish `4 (+1 opt)` for seats too.

**Whitespace inside the optional suffix is inconsistent** — `4 (+ 2 opt)` on Kilig 5,
`4 (+2 opt)` on Kilig 77 Plus, `1150 x 650` vs `1150x650` for bed sizes on Kilig 9 and
Kilig 79 Plus. Normalise before comparing.

**The dimensions block pairs outside with inside.** It reads `outside width - inside
width 2340 - 2200 mm` and `maximum outside height inside height 3040 - 2060 mm`. Only
the first of each pair is the FMLV figure. One page (Sarus 8) omits the spaces entirely:
`3050-2075 mm`.

**The models list appears twice** in every body-style page — once in the main content
and once in a footer block. Deduplicate on URL.

## Leaflets

Linked from each range page under
`/public/local/simplex/Marchi/rimor/Veicoli/Gamme/BrochureGamme/brochure/raw/`, with
spaces and the season in the filename. **Rediscover per run from the range page** rather
than hardcoding — the filename carries both a season (`2025-26`) and a version (`V2`,
`V3`, `V4`) and the versions already differ between ranges.

Horus's is a **UK edition** (`- UK - V3 -`); the other three are `- EU -`. This is the
only market-specific document Rimor publishes, and since no leaflet carries a price it
buys nothing today — worth re-checking if prices ever appear, per the Sunlight lesson.

## Product count

Rimor **does not publish a layout count anywhere** — no "41 layouts across 5 ranges"
claim on any index page, and there is no models index at all. This is the first
manufacturer where 1.5 has no answer, so the count the tests assert (41) is the count
observed on 13 August 2026, not a manufacturer claim. It is a weaker anchor than the
other four adapters have, and a drift in it should be treated as "check the site"
rather than "the manufacturer changed the range".

The per-range and per-body-style counts above are the more useful assertion, since a
selector breaking on one body-style page is the realistic failure and would show up
there before it showed up in the total.

## First run

13 August 2026, all five ranges, ~130 seconds for 55 fetches:

```
catalogue found (RIMOR - Catalogo 2025-26 - EU - V7.pdf): MTPLM and chassis for 5 range(s)
[Horus]      leaflet lists 7 layout size(s)   /vans 7            -> 7 product(s)
[Kilig]      leaflet lists 12 layout size(s)  /low-profile 7, /overcab 5  -> 12 product(s)
[Sarus]      leaflet lists 13 layout size(s)  /low-profile 7, /overcab 6  -> 13 product(s)
[Sailer]     leaflet lists 9 layout size(s)   /low-profile 5     -> 5 product(s)
[Super Brig] leaflet lists 9 layout size(s)   /overcab 4         -> 4 product(s)
41 product(s) collected
```

**41/41, nothing dropped**, and every per-range count matches the survey. Nine fields
per product (369 proposed changes across 41 new products).

Three hand-checked against the source:

| | Horus 12 | Kilig 5 | Super Brig Suite |
|---|---|---|---|
| L / W / H (mm) | 5413 / 2050 / 2659 | 6970 / 2340 / 3040 | 6970 / 2340 / 3080 |
| Seats / berths | 4 / 3 | 6 / 4 | 4 / 4 |
| Body type | campervan | over-cab | over-cab |
| Bed type | French bed → fixed | Transverse | Rear suite → fixed |
| MTPLM / chassis | 3500 / Fiat | 3500 / Ford | 3500 / Ford |

All three agree with the website and catalogue exactly. Note Kilig 5's berths: the page
says `4 (+ 2 opt)` and the stored value is `4`, with the full string kept in provenance.

The run was made against an **empty baseline**, since no FMLV export for Rimor exists
yet — so all 41 classified as new and the `fmlv_manufacturer` join is still unproven.
That is the one thing a real export will test that this run could not.

## What is unverified

- **`ncc_supplier_name`** is `Rimor`, inherited from the seed list and **not confirmed**
  against the NCC site's export dropdown.
- **`fmlv_manufacturer`** is `Rimor` from `resources/manufacturers-full-list.csv` (id
  `75`); it has not been checked against a real FMLV export, so the baseline join is
  unproven.
- **Model-year timing.** The season is labelled `2025-26` and the site was surveyed in
  August 2026, so this is likely to be close to a changeover. Nobody has confirmed when
  Rimor publishes a new season.
