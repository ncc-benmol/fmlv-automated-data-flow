# Le Voyageur — site survey and adapter notes

Surveyed 2 September 2026. `manufacturer_id` **104**, from
`resources/manufacturers-full-list.csv` (`104,Le Voyageur,Le Voyageur,,,`).

French builder of exclusively **A-class** motorhomes, premium end, founded 1980. Part of
the **Pilote Group** — `resources/francis-doyle-list-of-manufacturers.csv` already holds a
contact for the brand, `Miles Storey, m.storey@group-pilote.com`, which is where that
group membership came from rather than from the website. The brand publishes a UK-market
site in English, which is what this adapter is built on.

**Status: survey only.** No adapter written yet. Everything below was verified by fetching,
on 2 September 2026, unless it says otherwise.

## What the requester brought to the survey

Given at the outset, and all of it held up:

- **The UK site is `https://www.levoyageur-motorhome.uk/`.** Verified, and it is the right
  starting point — see the range-naming and market-subset notes below.
- **Two ranges: Heritage and Eterna.** Confirmed exactly. The site's own catalogue page
  calls it the "Eterna/Heritage catalogue", and the 18 layouts divide 10 Eterna / 8
  Heritage with nothing left over. This mattered, because the site still serves a third
  range path and an entire stale sitemap that say otherwise — see below.
- **There is a 2026 catalogue to download.** Confirmed, and it is a **glossy brochure, not
  a spec document**. It is the near-miss this repo's README warns about every time. See
  "The 2026 catalogue is the near-miss".
- **The site is being updated to the 2027 models as we speak.** This is the single most
  load-bearing thing the requester said, and it shapes the whole design: nothing about the
  current page structure can be assumed stable, the catalogue URL must be **rediscovered
  per run** rather than pinned, and the whole survey needs re-running once 2027 lands.
  Recorded in the registry `notes` as well as here.

The **NCC supplier name was not supplied** and remains the one open blocker; the registry
row's `ncc_supplier_name` is empty and `fmlv fetch-export` cannot run until it is filled.
See "What is unverified".

## Scope: two ranges, and the site contradicts itself about that

There are three places on the UK site that purport to list the range, and **only one of
them is right**. This is the "no single menu is a complete roster" problem from
[README.md](README.md), except here the extra entries are stale rather than missing.

| Source | Says | Verdict |
|---|---|---|
| `/find-your-motorhome/` | 18 layouts, 10 Eterna + 8 Heritage | **Correct — use this** |
| `/sitemap.xml` | 64 URLs, all on `levoyageur.fr`, ranges **LV / LVX / Liner** | Stale, and not even this domain |
| Nav + homepage links | a third range path `/find-your-motorhome/lv` | Dead — HTTP 500 |

Three things to take from that:

- **`sitemap.xml` on the `.uk` domain describes the French site.** Every `<loc>` is
  `http://www.levoyageur.fr/...`, and the ranges it names — `gamme-lv`, `gamme-lvx`,
  `gamme-liner` — are the **previous generation's** naming, before Eterna and Heritage.
  It lists a `Liner` range (824/874/924/1000/1050 layouts on Iveco and MAN chassis) that
  does not appear on the UK site at all. **Do not drive anything off this sitemap.** This
  is a direct counter-example to the usual advice to prefer the sitemap: the rule is
  "reconcile the roster against a second count", and here the sitemap is the source that
  loses.
- **The `/find-your-motorhome/<range>` links are not pages.** All three of
  `/heritage`, `/eterna` and `/lv` return a WordPress **HTTP 500** with a body byte-identical
  to the one `/robots.txt` returns. They are client-side filter anchors on the index. Only
  the index itself, `/find-your-motorhome/`, resolves. An adapter must take the roster from
  the index and never construct a range URL.
- **`/lv-range/` and `/lv-range-2/` are marketing pages, not a range.** They hold the
  Eterna and Heritage feature copy respectively (`/lv-range/confort/`,
  `/lv-range-2/streamlined-design/`), and carry no layouts. The `lv` in the path is a
  leftover from the old naming, not a live LV range.

The UK site is a **deliberate market subset** in the sense [README.md](README.md) means:
its Yoast schema declares `isPartOf` `https://www.wohnmobil-levoyageur.de/#website`, so the
UK, German, Korean and Swedish sites are one WordPress multilingual install (WPML). The UK
range is the 18 layouts the UK index lists, and it should be taken as authoritative rather
than reconciled against the French roster.

## Where the data lives: per-layout pages, in plain static HTML

**Plain HTTP, no JavaScript.** Everything below came out of a `Fetcher(...).fetch(url)` and
a tag-split of the HTML. `needs_javascript=no`.

The 18 layout pages sit at `/motorhome/<range>/<slug>/`, e.g.
`/motorhome/eterna/lv7-8cf/` and `/motorhome/heritage/lvxh7-9-gjf/`. The slugs are
irregular — `lv7-5cf-2`, `lvxh7-6-gjf-2`, `lvxh-6-9-lf` — with stray `-2` suffixes and
inconsistent hyphenation, so **read them from the index's `href`s, never build them.**

Each page carries the numbers twice over, in two separate blocks. A summary block:

```
Dimensions
Length : 7.85 m      Width : 2.24 m
Exterior  height : 2.95 m            Interior height : 2 m
Places
Seated places : 4    Sleeping places : 4
Extra sleeping places : 1            Eating places : 4     Seat in : F
Weight
Payload : 760 kg     MTPLM (Gross Weight) : 4500 kg
Information
Chassis : Fiat AL-KO                 Side compartement volume : 2550 l
```

— that is the real LV7.8CF, verbatim, from
`https://www.levoyageur-motorhome.uk/motorhome/eterna/lv7-8cf/`. Note `Exterior  height`
carries a **double space**, and `Side compartement volume` is misspelled; both are
consistent across all 18 and both must be matched as-is.

And a `Detailed specifications` block of labelled rows, grouped under headings:

```
AUTONOMY
Diesel tank capacity in liters      90L
Fresh water maximum in liters       200L
Waste water maximum in liters       120L
DIMENSIONS
Overall width (in cm) with external mirrors opened (in cm)   280
Wheelbase (in cm)                   455
INTERIOR
Interior height living room (in cm) ?   200
Rear permanent bed (in cm)          1450x1950
Pull-down bed (in cm)               1400x1900
```

**All 18 layouts carry the full summary block** — length, width, exterior height, interior
height, seated, sleeping, extra sleeping, eating, payload, MTPLM, chassis and side
compartment volume, with no gaps. That is the field set to build on.

### Prices are not published anywhere

No `£`, no `GBP`, no price on any of the 18 layout pages, on the index, or in the 2026
catalogue. Le Voyageur joins Swift, Rimor and Chausson: `rrp_pounds` stays unset, and
`output.build._mirror_guide_price` correctly leaves both price columns blank.

### The `Detailed specifications` block is ragged, in three ways

Verified across all 18. None of this is fatal, but a parser that assumes any of it will
break:

- **Section order differs by range.** Eterna: `AUTONOMY`, `DIMENSIONS`, `EXTERNAL STORAGE`,
  `INTERIOR`. Heritage: `TYPE OF CHASSIS`, `AUTONOMY`, `INTERIOR`, `DIMENSIONS`. Match on
  the row label, never on position within the block.
- **Units are inconsistently suffixed.** The same row reads `200` on Eterna and `200cm` on
  Heritage; `2800` against `2800L`; `455` against `455cm`; and `Fresh water maximum when
  driving` is `20L` on Eterna and a bare `20` on Heritage. Strip suffixes, don't require them.
- **Rows go missing.** `Overall width (in cm) with external mirrors opened` is present on
  all 10 Eterna layouts and on 3 of 8 Heritage layouts — absent on both 7.6s and both
  7.9 CF/GJF. This one costs nothing, because FMLV wants the mirrors-**excluded** body
  width and that lives in the summary block, present on all 18. But it is the concrete
  reminder to **stop at the next row's label** when slicing: a naive "take the value after
  the label" probe silently returned the string `Wheelbase (in cm)` as the mirror width on
  the two 7.6 layouts. That is exactly the failure [README.md](README.md) describes, caught
  here in the survey's own throwaway script.

### Multi-value and compound cells

- **Seats: `4+1 optional`** on LV7.8CL and LV7.8GJL, against a plain `4` on the other 16.
  Per the base-vehicle rule, this records **4**, with `4+1 optional` carried into the
  provenance snippet.
- **Pipe-separated alternatives** in the detailed block on Heritage: `22|24` inches of TV,
  `80x190|80x200cm` of bed. Only relevant if bed dimensions are ever collected.
- **Additive wheelbases** on the triple-axle layouts: `459+80` (LV8.5) and `459 + 80`
  (LVXH8.7) — the tag axle offset, with inconsistent spacing between the two ranges.

### Chassis: two mappings, both already known traps

Only two values across the 18, and each one is a documented trap from
[README.md](README.md):

- **`Fiat AL-KO`** on all 10 Eterna layouts. This must map to **`Fiat`**. AL-KO is the
  chassis maker, not the base vehicle, and `bailey.md` records AL-KO being correctly
  rejected as a `base_vehicle_manufacturer` — it is deliberately absent from
  `base.fmlv_base_vehicle` and mapping it would legitimise it.
- **`MERCEDES`** on all 8 Heritage layouts. FMLV holds **`Mercedes`**, never
  `Mercedes-Benz`. Route it through `base.fmlv_base_vehicle` like every other adapter;
  `tests/adapters/test_registry_wiring.py` enforces that.

Heritage publishes the chassis **twice** — once in the summary `Information` block and
again as a `TYPE OF CHASSIS` / `Chassis` row in the detailed block — which is a free
cross-check on that field for that range. Eterna publishes it once.

## The self-check: the model name encodes the length

Le Voyageur names every layout after its own overall length, and this turns out to be the
strongest redundancy on the site. `LV7.8CF` is 7.85 m; `LVXH8.7 GJF` is 8.75 m. Across all
18 layouts:

| Model | Name implies | Published length | Difference |
|---|---|---|---|
| LV6.8LF | 6.8 | 6.8 m | 0.00 |
| LV7.0 GJF | 7.0 | 7.05 m | 0.05 |
| LV7.5CF / GJF | 7.5 | 7.55 m | 0.05 |
| LV7.8 CF/CL/GJF/GJL | 7.8 | 7.85 m | 0.05 |
| LV8.5 CF/GJF | 8.5 | 8.55 m | 0.05 |
| LVXH 6.9 LF | 6.9 | 6.9 m | 0.00 |
| **LVXH7.6 CF / GJF** | **7.6** | **7.91 m** | **0.31** |
| LVXH7.9 CF/GJF/GJL | 7.9 | 7.91 m | 0.01 |
| LVXH8.7 CF | 8.7 | 8.73 m | 0.03 |
| LVXH8.7 GJF | 8.7 | 8.75 m | 0.05 |

**16 of 18 agree to within 0.05 m. The two that fail miss by 0.31 m**, and there is a clean
gap between the two groups — so a tolerance of **0.10 m** separates them with margin either
side. That is the `_reconciles()` check: parse the decimal out of the model name, compare
against the published length, drop the product with an `on_progress` warning if it is
outside tolerance.

It is a genuinely good self-check because it is *positional*: it catches a length read from
the wrong row or the wrong layout, which is the failure mode that otherwise produces
plausible, internally consistent motorhomes carrying each other's dimensions.

### And it immediately catches a real error on the website

The two failures are **LVXH7.6 CF** and **LVXH7.6 GJF**, both published as **7.91 m** —
byte-identical to the LVXH7.9 layouts sitting next to them in the index. Three independent
things say the website is wrong and the 7.6s are really ~7.65 m:

1. **The model name**, on the convention the other 16 layouts follow exactly.
2. **The 2026 catalogue**, page 29, which gives the XH 7.6 family
   `4 500 kg / double axle/ 7.65 m`. Read with `extract_positioned_text`, the attribution
   is unambiguous: that run sits at `y=476.3` directly beside `XH 7.6` at the same `y`, and
   the `LVXH 7.6 CF` / `LVXH 7.6 GJF` captions are the next thing below it at `y=363.5`.
3. **The 7.9 pair's own figure**, which is the same 7.91 m — the tell of a copy-paste
   between two adjacent model pages.

This is the [Elddis exception](README.md) in shape: the site normally overrules the PDF, but
the test is *"can I show one of them is wrong?"* and here that can be shown. **The decision
is still to drop the two products rather than substitute 7.65 m**, because the honest state
is that Le Voyageur publishes two contradictory lengths and only they can settle which is
right — and this is exactly the kind of thing to raise with the contact above. Two dropped
products, narrated every run, is the correct visible gap.

### Two more redundancies, both holding 18/18

Weaker than the length check, but free, and they cover fields the length check does not:

- **Side compartment volume is published twice.** The summary block's
  `Side compartement volume : 2550 l` equals the detailed block's `Rear storage hold - in
  litres (min / max) : 2550`, on all 18 layouts (2440, 2550, 2620 and 2800 all appear).
  Two different blocks, two different labels, same number — so it checks that the two
  blocks were read off the same vehicle.
- **Interior height is published twice, in different units.** Summary `Interior height :
  2 m` against detailed `Interior height living room (in cm) ? : 200`, on all 18. Note the
  literal `?` in that label, and that the value is a constant 2 m across the whole range,
  which makes it weak evidence on its own but a valid cross-block check.

### What is *not* a self-check here

**Payload against MTPLM minus MRO is unavailable: Le Voyageur publishes no MRO.** Payload
and MTPLM are both given (`Payload : 760 kg`, `MTPLM (Gross Weight) : 4500 kg`) and MRO is
absent from every page and from the catalogue, so the usual arithmetic cannot be run in
either direction. If FMLV derives MRO as `MTPLM − payload`, that is a derivation, not a
check — nothing corroborates it.

## The 2026 catalogue is the near-miss, not the source

`https://www.wohnmobil-levoyageur.de/wp-content/uploads/flipbooks/pdf/EN_LE-VOYAGEUR-CATALOGUE-2026_web.pdf`
— 6.3 MB, 76 pages, English, and **hosted on the German domain** even when linked from the
UK site. Text extracts cleanly (not rasterised), so it *looks* like a viable source. It is
not.

**It publishes per-family headline figures only**: gross weight, axle count and length, for
each of the nine size families, e.g. page 59:

```
LIGHT VEHICLE
3500 kg  /  double axle  /  7,05 m      7.0        LV 7.0 GJF
```

No MRO, no payload per layout, no berths, no seats, no width, no height, no price. And the
figures are attached to the **family**, not the layout — the four LV 7.8 layouts share one
`4 500 kg / 7.85 m` line. Against 18 layouts × 12 fields on the website, the catalogue is
strictly worse on every axis except one: it is the second opinion that settles the 7.6
length dispute above, and it agrees with the website on MTPLM and length for all eight
other families.

So it is kept as a **cross-document check and nothing else**, exactly as Rimor's leaflets
are.

Two mechanical notes if it is ever parsed further. Decimal separators are **inconsistent
within the one document** — `7,05 m` on page 59, `7.91 m` on page 29 — and the thousands
separator is a **non-breaking space** (`4\xa0500 kg`). Family labels also run into the
value in the extracted text (`4 500 kg / double axle / 7.91 mXH 7.9`), so positioned text
is required to attribute anything.

### Finding the catalogue, and the form that does not gate it

The catalogue is linked from `/brochure-request/`, whose visible furniture is a Gravity
Forms lead-capture form (`gform_6`, name/email). **The form is a front door, not a lock** —
the same as Rimor's. The PDF is a plain `<a href>` on the same page, on an unauthenticated
public asset path, and it fetched with a bare GET and no cookie:

```html
<a href="https://www.wohnmobil-levoyageur.de/.../EN_LE-VOYAGEUR-CATALOGUE-2026_web.pdf"
   target="_blank" rel="noopener">Discover our Eterna/Heritage catalogue</a>
```

No form was submitted and none needs to be. **Rediscover this link per run** rather than
pinning it: the filename carries the model year (`CATALOGUE-2026`), the requester says 2027
is being loaded now, and the same page also links `Leaflet-45-years.pdf`, so a loose
`.pdf` match would take the wrong document. Anchor on `CATALOGUE` and prefer the newest
year, and add the negative test that `Leaflet-45-years.pdf` is not matched.

## The anniversary edition is an options pack, not a product

`/special-anniversary-edition/` markets a 45-years edition, and the catalogue flags
`VEHICLE AVAILABLE IN ANNIVERSARY EDITION` against the LV 7.8 spread. It is **not** a
separate layout and must not become separate products. The page says it plainly:

> Available on all LV 7.8 models this, very special edition offers many details, options
> and finishes

— a logo, embroidery and a gift pack (keyring, bottle cooler, wine glasses) over the four
existing LV 7.8 layouts. It has no layout, no page under `/motorhome/`, and no entry in the
index. **The roster stays at 18.**

Worth contrasting with Adria's 60Y anniversary editions, which *are* separate products with
their own pages and their own weights, filed under the ordinary range with `60Y` in the
model. The difference is real, not a judgement call: Adria published distinct vehicles,
Le Voyageur published a trim pack.

## Expected product count: 18

**10 Eterna + 8 Heritage = 18**, taken from the `href`s on `/find-your-motorhome/` on
2 September 2026 and cross-checked against the 2026 catalogue, whose model captions name
the same 18 layouts across the nine size families.

| Range | Count | Layouts |
|---|---|---|
| Eterna | 10 | LV6.8LF, LV7.0 GJF, LV7.5CF, LV7.5GJF, LV7.8CF, LV7.8CL, LV7.8GJF, LV7.8GJL, LV8.5CF, LV8.5GJF |
| Heritage | 8 | LVXH 6.9 LF, LVXH7.6 CF, LVXH7.6 GJF, LVXH7.9 CF, LVXH7.9 GJF, LVXH7.9 GJL, LVXH8.7 CF, LVXH8.7 GJF |

**A run should collect 16 and narrate 2 drops** while the 7.6 length conflict stands. The
index publishes no count of its own, so 18 is a roster count rather than a stated claim —
worth re-deriving each run rather than asserting.

Note the model names as the site writes them are **irregularly spaced**: `LV7.8CF` closed
up, `LV7.0 GJF` and `LVXH 6.9 LF` spaced, `LVXH7.6 CF` spaced only before the bed code.
Normalise for comparison, but see the range/model question below before deciding what to
emit.

## Body type: A-class, for all 18

Le Voyageur builds nothing else. The brand's own history page describes "the first A-Class
model on a Mercedes Benz base: Le Voyageur 600", and the measurements agree — 2.24–2.25 m
body width and 2.59–3.09 m exterior height are coachbuilt dimensions, not van ones, and
every layout is a fully integrated cab. `BodyType.A_CLASS` for the whole range.

This is a per-range constant rather than a parsed cell, which means it still needs
**registering in the provenance dict** with the manufacturer's own words in the snippet —
per [README.md](README.md), a constant is still a claim about the vehicle, and an
unregistered field is silent in both directions.

## Model year

The catalogue is `CATALOGUE-2026`, the site footer reads `© 2026 LE VOYAGEUR`, and the
layout pages' Yoast `dateModified` values cluster in **August 2025**
(`2025-08-22T08:38:23+00:00` on LV7.8CF, `2025-08-18` on the brochure page). So what is
live today is the **2026 model year**.

The requester says the site is being updated to 2027 **now**, which is consistent with the
July–early-September rollover in [README.md](README.md) and with the Caravan Salon
calendar. Two consequences: re-run this survey once 2027 is up, and expect the two 7.6
lengths to be either fixed or newly wrong at that point — check them first.

## Range and model strings: undecided, and blocked

**Not settled, because it cannot be settled without the FMLV export.** Per
[README.md](README.md), `fmlv fetch-export "<ncc_supplier_name>"` is what decides
`manufacturer_range` and `model`, and the supplier name is the missing input.

The question is live rather than theoretical, because the site itself is inconsistent about
the Heritage range's name:

| Where | Writes it |
|---|---|
| URL path | `heritage` |
| Main nav and breadcrumb | `Héritage` (with the acute accent) |
| Catalogue running header | `LE VOYAGEUR HERITAGE` |
| Registry drafted here | `Heritage` |

The accent is the same class of problem as Chausson's `Citroën`, and the answer has to come
from what FMLV already holds, not from the site. Eterna carries no accent and is written
consistently everywhere.

Also undecided: whether the range letters belong in `manufacturer_range` or in `model` —
whether FMLV holds range `Eterna` + model `LV7.8CF`, or range `Eterna` + model `7.8 CF`.
Check both halves of the identity in the export, and if either needs changing, propose
both together and check the Jaccard score first — `LV7.8CF` tokenizes to `{lv, 7, 8, cf}`,
so a rename that drops the `LV` prefix scores 0.500 against the baseline and sits right on
`DEFAULT_THRESHOLD`.

## What is unverified

- **`ncc_supplier_name` — the blocker.** Not supplied, not guessable. `Le Voyageur` is
  what the NCC full list calls the brand, but the README's own example is Adria, whose
  export dropdown says `Adria Caravans & Motorhomes` against an `fmlv_manufacturer` of
  `Adria Mobil`. Until someone reads the dropdown at
  `/nova/resources/products`, `fmlv fetch-export` cannot run, the baseline cannot be
  fetched, and the range/model question above stays open.
- **`fmlv_manufacturer` is inferred, not confirmed.** `Le Voyageur` is the `Name` column
  for ID 104 in the full list, and that column matches `fmlv_manufacturer` exactly for all
  15 existing registry rows — so it is well-founded. It is still not the same thing as
  having seen it in an export.
- **Whether FMLV holds any Le Voyageur products at all.** Unknown until the export runs. If
  the baseline is empty, all 16 collected products arrive as new, and every field the
  adapter sets must be registered or it lands blank.
- **The 7.6 length.** Two sources say 7.65 m, the website says 7.91 m, and nobody has asked
  Le Voyageur which is right. Worth raising with `m.storey@group-pilote.com`.
- **Berths against seats.** `Sleeping places` and `Extra sleeping places` are separate rows,
  and the base rule takes the lower figure — so LV6.8LF records 2 berths despite `2 + 2`,
  and LVXH 6.9 LF likewise. But `Eating places` reaches 6 on layouts with 2 seated places,
  so eating places are emphatically **not** seats, and `Seated places` is the fitment
  figure to use. No page uses the word "permitted", so the Bürstner ceiling trap does not
  appear here — but this has not been corroborated against a baseline.
- **Whether `Seat in : F` means anything useful.** Constant `F` on all 18, so it carries no
  information for the range as it stands. Possibly the cab seat type. Not used.
- **Nothing has been run.** No adapter exists, so there are no run numbers, no real
  product counts and no reviewed diffs. The 18/16 split above is a survey prediction.
