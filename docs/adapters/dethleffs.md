# Dethleffs — site survey and adapter notes

Surveyed and built 2 September 2026. Twelfth adapter.

Dethleffs is an **Erwin Hymer Group** brand, like Etrusco, Bürstner, Carado and Eriba.
Unlike those, it is **not** a "non-core" case in the sense [`README.md`](README.md)
describes: `dethleffs.co.uk` is a full GB market edition of the manufacturer's own site,
carrying a GBP on-the-road price and UK-spec weights for every layout it lists, and its
roster reconciles exactly against the sitemap and against the GB technical-data PDFs.

## What the requester brought to the survey

Given directly, and all four points held up:

- **The site is `https://www.dethleffs.co.uk/`.** Confirmed as the source — see below.
- **Motorhomes and campervans only; ignore the caravans.** Worth recording that **the UK
  site has no caravans at all** — the navigation offers only "Motorhomes" and "Camper
  Vans", and the sitemap contains no caravan pages. There is nothing to exclude. (The
  group sites `dethleffs.com` and `dethleffs.de` do sell caravans; the GB edition does
  not list them.)
- **Each model page carries the technical, pricing and everything data.** Exactly right,
  and it is the reason this adapter is the cheapest of any brand so far.
- **"The names can be confusing — the Just Van is actually not a van but a motorhome."**
  Confirmed by the site itself, which tags Just Van **`Low Profile`**, not `Camper Van`.
  It is a 2.20 m-wide GRP coach-built on a Fiat Ducato Light Low Platform, not a panel-van
  conversion. This is the single most important naming trap on the site and the reason
  **body type must be read from the page's own tag, never inferred from the model name.**
- **"It has the mass in running order."** It does, and it is printed with its ±5%
  tolerance band, which is the adapter's self-check.

## Where the data lives

**One plain HTTP fetch per model page. No JavaScript, no PDF, no login.** Confirmed by
fetching with `Fetcher` alone — every number below is in server-rendered HTML.
`robots.txt` allows everything except one competition page.

Each model page carries the full specification **twice**, in two independently rendered
places, which is the second self-check:

1. **The technical-data modal** — a `<table class="… has-columns--1+">` whose `<thead>`
   holds two `<th>` cells, **range then model** (`Just Van` / `T 1`), and whose `<tbody>`
   is a flat run of `<tr><td>label</td><td>value</td></tr>`. This is the primary source:
   clean two-cell rows, with none of the column-alignment risk that dominates the Morelo,
   Swift and Rimor adapters. Footnote markers appear as `<sup>1</sup>` *inside* the value
   cell and must be stripped.
2. **The "main facts" card** — `<dd class="m-mainfacts__label">` / `<dt
   class="m-mainfacts__text">` pairs repeating Length, Width, Height, Sleeping berths max.,
   Technically permissible maximum laden mass and Price.

**Body type** is published explicitly as `<span class="a-tags__label …">`, one of exactly
four values across all 48 layouts:

| Site tag | Count | FMLV `body_type` |
|---|---|---|
| `A Class` | 12 | `a_class` |
| `Coachbuilt` | 5 | `coach_built_over_cab_bed` |
| `Low Profile` | 19 | `coach_built_low_profile` |
| `Camper Van` | 12 | campervan family — see below |

`Coachbuilt` means the alcove/over-cab body, confirmed independently: **exactly those 5
layouts, and no others, carry a `Bed dimension alcove, L x W, approx. cm` row.**

### The family name decides motorhome vs campervan — the chassis does not

**Rule from the requester, 2 September 2026: Globebus is always a motorhome, Globetrail is
always the campervan name.** Verified against all 48 layouts with **zero violations**, and
it is not the tautology it first looks like, because **VW Crafter vehicles sit in both
families**:

| Family | Section | Body tag | Chassis |
|---|---|---|---|
| **Globebus** (7) | `/motorhomes` | A Class ×3, Low Profile ×4 | Fiat ×3, **VW ×4** |
| **Globetrail** (12) | `/camper-van` | Camper Van ×12 | Fiat ×10, **VW ×2** |

So `Globebus Performance` and `Globebus Performance 4x4` are **low-profile motorhomes on a
VW Crafter**, while `Globetrail VW Performance` is a **campervan on the same base vehicle**.
Anything that classifies by chassis gets four of them wrong. Together with the Just Van
trap — a "Van" that is a coach-built — this is why body type is read from the page tag and
never inferred from a name or a base vehicle.

It also gives the adapter a fourth self-check: **family name, URL section and body tag must
all agree**, and a product where they do not is dropped rather than proposed.

**This is what identifies the misfiled baseline row.** FMLV holds
`Globetrail VW Performance 4X4 / T 46` as `coach_built_low_profile` — a low-profile
motorhome under a Globetrail range name, which the rule forbids. Its figures (length
6850 mm, MTPLM 3880 kg, 3 berths) match the site's **`Globebus Performance 4x4 / T 46`**
exactly, so the body type is right and the *range name* is wrong. Per
[`README.md`](README.md), both halves of the identity must be proposed together.

## The roster: 48 layouts, and it reconciles exactly

Take the roster from `sitemap.xml` → `sitemap.site_38.xml`, per the rule in
[`README.md`](README.md). Here, unusually, **every source agrees**: the 48 model URLs in
the sitemap and the union of the layout links on the 11 range pages are the *same set*,
with nothing missing in either direction. Etrusco's every-menu-is-short problem does not
occur on this site. The `/motorhomes` and `/camper-van` index pages link only to range
pages, not to layouts, so the range pages are the layout source.

### Motorhomes — 36 layouts, 9 range paths

| Range page | Site heading(s) | Layouts |
|---|---|---|
| `/motorhomes/just-van` | Just Van | T 1, T 4, T 5 |
| `/motorhomes/globebus-active` | Globebus Active A Class | I 1, I 4, I 6 |
| `/motorhomes/globebus-performance` | Globebus Performance | T 16, T 46 |
| `/motorhomes/globebus-performance-4x4` | Globebus Performance 4x4 | T 16, T 46 |
| `/motorhomes/just-camp-active` | Just Camp Active Low Profile | T 6752 DBL, T 6762, T 6812 EB, T 7052 DBL, T 7052 DBM, T 7052 EB, T 7052 EBL |
| `/motorhomes/trend-active` | Trend Active Low profile **and** Trend Active A class | T 6817 EB, T 6877, T 7057 DBL, T 7057 EB, T 7057 EBL; I 6817 EB, I 6877, I 7027, I 7057 DBL, I 7057 EB, I 7057 EBL |
| `/motorhomes/xl-a` | XL Family A | A 6822-2, A 7822-2, A 7872-2 Family |
| `/motorhomes/xl-i` | XL Family I | I 7812-2 |
| `/motorhomes/alpa` | Alpa A Class **and** Alpa Coachbuilt | I 6820-2, I 7820-2; A 6820-2, A 7820-2 |

**Two range pages carry two range headings each.** `/motorhomes/trend-active` serves both
`Trend Active Low profile` (T models) and `Trend Active A class` (I models);
`/motorhomes/alpa` serves both `Alpa Coachbuilt` (A models) and `Alpa A Class` (I models).
The range name must come from each layout page's own `<th>`, **not** from the range URL —
deriving it from the path would collapse two ranges into one on 17 of the 36 motorhomes.

### Campervans — 12 layouts, 3 range paths, all under `/camper-van` (singular)

| Range page | Site heading | Layouts |
|---|---|---|
| `/camper-van/globetrail` | Globetrail Fiat | 540 DR, 600 DS, 600 ER, 640 ES, 640 HR |
| `/camper-van/globetrail-active-plus` | Globetrail Active Plus Fiat | 540 DS, 600 DS, 600 ES, 600 KS, 640 ES Active |
| `/camper-van/globetrail-performance` | Globetrail VW Performance | 600 DR, 600 DR Classic |

**The path is `/camper-van`, not `/campervans`** — `/campervans` returns 404.

## Model year: 2027

The GB technical-data PDFs are served from a `…/mj27/` folder ("Modelljahr 27") and their
own cover reads **"TECHNICAL INFORMATION / Motorhomes / 2027 / Valid from August 1st,
2026 / 02/2027 | GB"**. Consistent with Morelo, Sunlight, Etrusco and Bürstner all having
moved to MY2027. Per [`README.md`](README.md), re-check at the end of September.

## Self-checks — there are three, which is the most of any brand so far

1. **The ±5% mass band (arithmetic, internal to one row).** `Mass in running order
   (+/-5%)*` prints as `2611 (2480 to 2742)*` — 2611 × 0.95 = 2480.45, × 1.05 = 2741.55.
   The band is a *function* of the mass, so a slipped value pairs one mass with another's
   band and fails. Same device as Sunlight, Etrusco and Bürstner. **All 48 pass**, with
   3 kg of slack for printed rounding.
2. **The main-facts card (redundancy, internal to one page).** Six fields — length, width,
   height, MTPLM, MRO and price — are rendered a second time in a different DOM structure.
   **All 48 × 6 = 288 comparisons agree exactly.** This is the check that would catch a
   mis-keyed spec row, which the band check alone cannot.
3. **The GB technical-data PDFs (redundancy, cross-document).** Two MY2027 GB PDFs
   republish the same figures. Spot-checked Just Van T 1: length 599, width 220, height
   273, headroom 190, towable 2000/750, wheelbase 3450, berths 2/3, MRO 2611 (2480 to
   2742) — identical to the website. The PDFs also supply the **units**, which the website
   omits: dimensions are **cm**, wheelbase **mm**, masses **kg**.

## Field mapping, and the traps in it

| FMLV field | Source row | Note |
|---|---|---|
| `manufacturer_range` / `model` | the two `<th>` cells | see the naming caveat below |
| `rrp_pounds` | `Price (incl. VAT)` | GBP **on the road** — see below |
| `mh_length_mm` | `Overall length, approx.` | **cm → ×10** |
| `mh_width_mm` | `Overall width, approx.` | **cm → ×10**; see mirrors trap |
| `mh_height_mm` | `Overall height, approx.` | **cm → ×10**; see dual-height trap |
| `mro_kilograms` | `Mass in running order (+/-5%)*` | take the figure before the bracket |
| `mtplm_kilograms` | `Technically permissible maximum laden mass*` | |
| `payload_kilograms` | *derived* MTPLM − MRO | as for Etrusco and Bürstner |
| `berths` | `Sleeping berths standard / max.` | lower figure |
| `seats` | `Permitted number of seats (including driver)*` | lower figure; matches FMLV's basis exactly |
| `base_vehicle_manufacturer` | `Standard chassis` | Fiat Ducato (5 variants) or VW Crafter (3) |
| `body_type` | the `a-tags__label` tag | never from the model name |

**Trap — `Manufacturer-specified mass for optional equipment*` is not payload.** It sits
*between* MRO and MTPLM in the table, exactly where payload would go, and is a cap on
factory-fitted extras: 555 kg on the Just Van T 1 against a real payload of 888 kg. The
identical trap is documented for Sunlight, Etrusco and Bürstner.

**Trap — dual height on all 10 Fiat Globetrail campervans.** `Overall height, approx.`
reads `265 / 278 (○)`, the second figure being the optional pop-top roof. Take **265** per
the base-vehicle rule; the main-facts card independently says `265 cm`, which confirms it.
A third row, `Overall height (open pop-top roof) 358`, must not be confused with either.

**Trap — width with mirrors.** 10 layouts (the Fiat Globetrails) add `Overall width with
mirrors, approx.` — 265 against a body width of 205. [`README.md`](README.md) requires the
body width; the labels are distinct, so match the exact label rather than a prefix.

**Trap — dual seats on 9 layouts.** `Permitted number of seats (including driver)*` reads
`4 - 5 (○)` on eight layouts and `2 - 3 (○)` on Trend Active A class I 7027. Take the
lower figure and carry the raw wording into the provenance snippet.

**Trap — berths print in two different forms.** 30 layouts give `standard / max.`
(`2 / 3 (○)`); the other 18 give a **single number** (`4`), meaning standard and max are
the same. A parser expecting `n / n` silently drops the 18.

**Trap — footnote superscripts inside value cells.** `<td>273 <sup>1</sup></td>`. Strip
`<sup>` before reading the number, or Just Van T 1 becomes 2731 mm tall.

## Price: GBP, on the road, and the two footnotes disagree

`Price (incl. VAT)` is in **sterling** — no currency conversion, so none of the Morelo
exchange-rate problem. The page carries **two different footnotes both labelled `a)`**,
and they say different things:

- The **spec table's** footnote: *"This is a recommended retail price based on German
  retail prices. Prices in other countries may differ due to currency…"*
- The **main-facts card's** modal: *"All prices are recommended retail prices in GBP
  including legal applicable VAT, On The Road Charges (OTR including delivery from
  Germany, registration and PDI). Possible import duties are not included and will be
  charged separately."*

The second is the specific one and describes the number actually printed: **a GBP
on-the-road price including VAT, delivery, registration and PDI**. That is the same basis
Auto-Trail publishes and the basis [`README.md`](README.md) prefers for `rrp_pounds`.
Recorded here so that a future change of basis is diagnosable rather than reading as a
real price move across all 48 layouts.

## The FMLV baseline — fetched 2 September 2026

`ncc_supplier_name` is **`Dethleffs`**, the same string as `fmlv_manufacturer`, confirmed
by the requester and then by `fmlv fetch-export` running successfully. It returned **186
products, 50 of them model year 2026**, which is the set to compare against.

### FMLV is inconsistent about where the body letter sits

This is the single most important thing the export says, and no amount of reading the
website would have revealed it. FMLV splits the vehicle's identity **differently in
different ranges**:

| FMLV range | FMLV model | Website range | Website model | Letter lives in |
|---|---|---|---|---|
| `Alpa A` | `6820-2` | Alpa Coachbuilt | `A 6820-2` | **range** |
| `Alpa I` | `6820-2` | Alpa A Class | `I 6820-2` | **range** |
| `Trend Active T` | `7057 EB` | Trend Active Low profile | `T 7057 EB` | **range** |
| `Trend Active I` | `7057 EB` | Trend Active A class | `I 7057 EB` | **range** |
| `XL Family I` | `7812-2` | XL Family I | `I 7812-2` | **range** |
| `Just Camp Active` | `T 7052 EB` | Just Camp Active Low Profile | `T 7052 EB` | **model** |
| `Globebus Active` | `I 1` | Globebus Active A Class | `I 1` | **model** |
| `XL` | `A 7872-2 Family` | XL Family A | `A 7872-2 Family` | **model** |
| `Globetrail Classic` | `540 DR` | Globetrail Fiat | `540 DR` | n/a |
| `Globetrail Active` | `600 DS` | Globetrail Active Plus Fiat | `600 DS` | n/a |
| `Globetrail VW Performance` | `600 DR` | Globetrail VW Performance | `600 DR` | n/a |

Per [`README.md`](README.md) the export decides these strings, so **the adapter follows
FMLV's convention per range** rather than imposing one of its own. Note the site's range
headings (`Alpa Coachbuilt`, `Trend Active Low profile`, `Just Camp Active Low Profile`,
`Globetrail Fiat`) are **never** what FMLV holds, so the marketing name survives only in
the provenance. Two site ranges have no FMLV counterpart at all — **Just Van** (a genuinely
new range, tagged "New" in the site nav) and **Globebus Performance** — and take the
convention of their nearest sibling.

### The existing FMLV body types are wrong in several places

The website publishes an explicit, self-consistent body tag; the 2026 baseline disagrees
with it, and with FMLV's own earlier data, in ways that are demonstrably errors rather
than judgement calls:

- **Alpa is swapped.** FMLV 2026 has `Alpa A` = `a_class` and `Alpa I` =
  `coach_built_over_cab_bed`. That is backwards: `A` is *Alkoven* (over-cab bed) and `I` is
  *Integriert* (A-class), which is what the site says and what **FMLV's own 2022 rows say**
  (`Alpa A` 2022 = `coach_built_over_cab_bed`, `Alpa I` 2022 = `a_class`). Something
  transposed them for 2026.
- **`Trend Active I 7057 DBL` is `coach_built_low_profile`** where all five of its `Trend
  Active I` siblings are `a_class`. The site says A Class.
- **`Globetrail VW Performance 4X4 / T 46` is not a Globetrail.** It is the **Globebus
  Performance 4x4 T 46**, a low-profile motorhome, filed under a campervan range name.
- **Four 2024 `Esprit I` rows are `campervan_high_top`** — an Esprit I is a 7.79 m A-class.

So unlike Bürstner, `body_type` here should be **collected and allowed to propose
corrections**, not left unset: the site tag is unambiguous, internally consistent across
all 48, and independently corroborated (exactly the 5 `Coachbuilt` layouts carry an alcove
bed row). Per [`README.md`](README.md), proposing the correction is the adapter working.

**This resolves the campervan-body-type question.** FMLV already holds **every** Globetrail
as `campervan_high_top`, which agrees with the reading from published height and the
campervan PDF's "VW Crafter high roof". The adapter emits `campervan_high_top` for all 12
and proposes no change on the matched ones.

### Other data-quality problems visible in the baseline

- **`Globebus T Camp` and `Globebus T Camp Active` are duplicates** — T1 and T4 appear
  under both range names with identical prices and weights. Four rows, two vehicles.
- **`Globetrail Classic 640 ER` appears twice** at different prices (£62,690 and £64,590).

### Expect a large diff, and expect the matcher to need watching

A crude Jaccard pass at the repo's 0.5 threshold matches 37 of 48, leaving 11 new and 19
disappeared — but **several of those matches are wrong**, in exactly the ways
[`README.md`](README.md) documents:

- **`Alpa A Class` and `Alpa Coachbuilt` both score highest against FMLV's `Alpa A`**
  (0.667 and 0.800). They are different vehicles; the A Class one belongs to `Alpa I`. The
  word bags collide because the site puts "A Class" in the range name.
- **All three `XL Family A` layouts match FMLV's single `XL / A 7872-2 Family`** at 0.667.
- **`Globebus Performance 4x4 T 46` matches `Globetrail VW Performance 4X4 T 46`** at
  0.571 — right vehicle, wrong FMLV range name.
- **`Globetrail VW Performance 600 DR Classic` matches `600 DR`** at 0.833, and
  `Just Camp Active T 6752 DBL` matches `T 7052 DBL` at 0.556 — a differing number or
  suffix is one token of several and cannot outvote the rest.

Emitting FMLV's own range strings removes most of this by construction, because the
colliding words ("A Class", "Low profile") disappear from the range. The remainder needs a
reviewer's eye on any proposal that changes body type *and* dimensions together.

Genuinely gone from the site (so genuine deactivations, not parse failures): **Esprit I**
(4), **Globetrotter XL I** (2), **Globebus T Camp** / **T Camp Active** (4), five
`Globetrail Classic` layouts, and `Trend Active T/I 6617 EB` (2). Genuinely new: the whole
**Just Van** range (3), **Globebus Performance** (2) and **4x4** (2), `Trend Active A class
I 7027`, `Just Camp Active T 6762`, and three Globetrail layouts.

## Resolved: Trend Active Plus is not on the UK site

Checked again after the requester reported the pages working. The page they opened,
`/motorhomes/trend-active/t-7057-eb`, has a modal headed **"Trend Active Low profile /
T 7057 EB"** at **£85,090.00** — that is the *plain* Trend Active, and it is already one of
the 48. Every plausible Plus URL 404s (`/motorhomes/trend-active-plus`,
`…/trend-active-plus/t-7057-eb`, `…/i-7057-eb`, `/motorhomes/trend-plus`, and both
configurator paths), the `/motorhomes/trend-active` range page links only to its 11 layouts
and to the two non-Plus configurator entries, and the string "Trend Active Plus" appears
nowhere on the site. It exists only in the MY2027 GB technical PDF.

Per the website-overrules-the-PDF rule, **Trend Active Plus is out of scope** — and there
is no price for it anywhere, so it could not be published in full even if included. Worth a
question to the brand, since the PDF suggests it is a real MY2027 product. If it is ever
added, `T 7057 EB` and `I 7057 EB` **collide on model name** with existing Trend Active
layouts and are separated only by the range.

## The first real run — #8, 2 September 2026

**48 of 48 collected. Nothing dropped, nothing skipped, no field left blank.** 50 plain
HTTP fetches (2 sitemap + 48 model pages), no browser, 177 seconds. Every layout passed all
four self-checks.

```
  baseline    49 products      scraped     48 products
  classified  36 changed, 0 unchanged, 12 new, 13 disappeared
  proposed    358 changes for review, of which 36 are year bumps
  verified    302 fields checked and unchanged
```

The baseline is 49 rather than the export's 50 because `_dedupe_baseline` collapsed the
duplicated `Globetrail Classic 640 ER` — the survey predicted that row and the pipeline
handled it without being told.

### Hand-checked against the site

| Product | Checked | Result |
|---|---|---|
| Just Van T 1 | £61,990, 5990 × 2200 × 2730, MRO 2611, MTPLM 3499, payload 888, 2 berths, 4 seats | all correct, all new |
| Globetrail Classic 540 DR | MRO 2780 → **2740**, price £63,590 → **£62,790**, berths 5 → **2** | all three match the page; berths is the standard figure from `2 / 5 (○)` |
| Alpa A 6820-2 | MRO 3646 → **3585**, price £134,890 → **£138,590** | both match the page |

### The predicted corrections were proposed

- **Alpa's swapped body types, both ways**: `Alpa A` 6820-2 and 7820-2 from `a_class` to
  `coach_built_over_cab_bed`, and `Alpa I` 6820-2 and 7820-2 the reverse. Four corrections,
  restoring what FMLV's own 2022 rows already said.
- **`Trend Active I 7057 DBL`** from `coach_built_low_profile` to `a_class`, the one layout
  filed against all five of its siblings.
- **The misfiled range**: `Globetrail VW Performance 4X4` → **`Globebus Performance 4x4`**
  on `T 46`, which is the Globebus/Globetrail rule doing its work.

Those five body-type corrections are the only ones proposed on all 48 — the site tag agrees
with the baseline everywhere else, which is the strongest evidence that reading the tag is
right and that the disagreements are real errors rather than a taxonomy mismatch.

### Three matches a reviewer must not accept blind

The matcher's documented weakness in [`README.md`](README.md), and it bit in three places.
Each is a **replacement reported as a revision**, so the honest outcome is one new product
plus one deactivation:

| Scraped | Matched baseline | The tell |
|---|---|---|
| `Globetrail VW Performance / 600 DR Classic` | `Globetrail Classic / 600 DR` | **base vehicle Fiat → VW.** Chassis do not change under a vehicle mid-life — the surest tell there is. A different range, a different base vehicle and £8,200 apart |
| `Trend Active I / 7027` | `Trend Active I / 6617 EB` | 700 mm longer, berths 4 → 2, seats 5 → 2, £6,000 dearer |
| `Globetrail Classic / 600 ER` | `Globetrail Classic / 600 DK` | same number, different bed code |

A fourth model change, `Globetrail Active / 640 ES` → `640 ES Active`, **is** benign: the
site simply added the trim word to the layout's name.

So the true counts are nearer **15 new and 16 disappeared** than the reported 12 and 13 — a
wrong match cannot also be reported as a disappearance, exactly as the Etrusco write-up
warns.

**Both halves of the identity are proposed together wherever both differ.** Each of
`manufacturer_range` and `model` carries provenance saying so, which is what avoids the
Bailey trap of accepting a range rename that leaves the old model behind. Four products had
only one half proposed, and in every one of them only that half actually differs.

### `--range` needs its own baseline scope, and the first smoke run proved it

A `--range` run narrows the baseline through `cli.baseline_scope`, which by default matches
FMLV's `manufacturer_range` against the selector label. That is wrong here in both
directions — a selector is a URL *path*, `motorhomes/alpa` serves two FMLV ranges, and every
site heading is renamed by `RANGE_MAP` before it reaches FMLV — so `--range Alpa` found an
empty baseline and would have proposed both Alpa layouts as new, uploading duplicates. Fixed
with a `baseline_in_scope` hook and `RANGE_PATH_TO_FMLV_RANGES`; `--range Alpa` now matches
4 against 4 with nothing new and nothing disappeared. Adria needs the same hook for the same
class of reason.

## Cost

The 11 range pages need not be fetched at all if the roster comes from the sitemap: **2
fetches for the sitemap plus 48 model pages = 50 plain HTTP fetches**, no browser, no PDF
required for the collect path. The two PDFs are worth fetching only as an occasional
cross-check; the motorhome one is 17.6 MB.

## The habitation pack — floorplans, and the ~40 layout fields the adapter never collects

Built 2 September 2026, after the adapter, as the same post-build step Knaus got. Two
outputs, both under `data/` and neither tracked:
`data/dethleffs-2027-habitation-layouts.csv` and `data/dethleffs-2027-floorplans.html`,
the page generated from the CSV so the two cannot drift.

These cover the fields flagged out of scope in `config/field_guide_motorhome.csv` — bed
types, sleeping area, bathroom layout, kitchen location, lounge, rear garage, fridge and
microwave. `collect()` has no business with any of it; this is human data-entry support.

### Finding the floorplans: the `is-active` variant

Each model page carries an `m-model-variants` block listing **every layout in the range**
with a floorplan thumbnail and a link. The one for *this* layout is the item whose class is
`m-model-variants__item is-active`; its `<img src>` is the drawing. All 48 resolve, and
each `is-active` item's `href` matches its own page URL, which is the check that the
convention holds. Expect a fresh convention per manufacturer — Knaus identified floorplans
by German `alt` text, not by markup.

Three images are shared by two layouts each, and all three are legitimate: Globebus
Performance and Performance 4x4 have the same habitation layout on different drivetrains
(T 16 and T 46), and Globetrail VW Performance 600 DR and 600 DR Classic differ in trim,
not layout.

**Site bug**: `motorhomes/trend-active/i-7027` points its floorplan at
`…/2027/trend/grundrisse/neu_trend-i-7027_v2.svg`, which **404s**. The working file is the
same path without the `neu_` prefix, which is what the sibling Trend pages link to.

Most drawings are SVG, some are PNG. Reading the SVGs needs a render pass — headless
Chromium via the `playwright` already in the dev environment.

### Reading a drawing: what is safe to state, and what is not

**Never nearside/offside.** Dethleffs' renders are left-hand drive, UK vehicles are not.
Side-versus-corner-versus-rear is safe; left-versus-right flips.

**Bed orientation cannot be read from the published dimension string alone.** The drawing
is the arbiter, and it uses a consistent idiom:

* two duvets drawn *across* the body with the pillows side by side against one wall = a
  **transverse** double;
* two duvets running *fore and aft* with a pillow at the rear wall of each = **twin single
  beds**;
* one fore-and-aft double set clear of the rear wall, walk-round space at the foot and a
  wardrobe in each rear corner = an **island** bed.

The spec table's `Bed dimension: Rear bed` corroborates the first two — a single `L x W`
figure for a transverse double, `A x 80 / B x 75 / C x W` for twin singles plus their
infill — but it does **not** separate transverse from island: Trend Active T 7057 DBL
publishes `195 x 150`, the same shape of figure as the transverse T 6877, and is an island
bed. Read the drawing.

Panel-van transverse beds are made possible by **widened bed niches**, drawn as bulges on
the body outline at the rear. They are visible on all ten Fiat Globetrails and both VW
Performances.

### The three fields the requester added, and what the sources actually say

**Rear garage — `yes` on the 36 motorhomes, `no` on the 12 campervans.** The motorhomes
have a dedicated rear garage: every range's standard equipment names it ("Large rear
garage: two garage doors/flaps…"), and each model page publishes
`Measurement storage opening right/left (W x H)`. Six Trend layouts publish **two** heights
per side, e.g. `90 x 75 (○) / 90 x 110` — that is the height-adjustable rear bed, not a
parsing artefact. Only the two Alpa Coachbuilts publish
`Clear dimensions of rear garage door/flap`, an *optional* extra flap.

The 12 Globetrail campervans publish no opening row at all: their under-bed space is loaded
through the rear doors, with no external side hatch and no published opening dimensions.
**Requester decision, 2 September 2026: under-bed storage is not a rear garage**, so all 12
are `no`. Note that the two sources on the site disagree and the *marketing copy is the one
to ignore* — Dethleffs' equipment list calls it "rear storage space with 4 integrated
lashing eyes", while the model pages' prose calls it a rear garage. The equipment list is
the specific source and it wins, the same way the specific footnote wins on price.

The first build of this pack recorded all 48 as `yes` on the strength of that marketing
copy, which was wrong. **Any manufacturer whose panel vans are described as having a
"garage" needs the same test**: is there an external hatch and a published opening, or is
it just the space under the bed?

**Fridge — all 48 are fridge/freezer, none is a plain fridge.** The 36 motorhomes publish
`Refrigerator volume (thereof freezer), approx.` on their own page, 83 l to 177 l, always
with a non-zero freezer figure; some print two, the second being an upgrade option. The 12
campervans publish no such row, so theirs comes from the standard-equipment list in the GB
camper-van PDF: 84 l with a 6.1 l freezer on the Globetrail and Active Plus, 90 l with 7 l
on the VW Performance.

**Microwave — a verified `no`, not a blank.** The word appears **nowhere** on
dethleffs.co.uk and nowhere in either MY2027 GB technical-data PDF. That is a real negative
rather than absence of evidence, because those PDFs carry the exhaustive optional-equipment
and accessory price lists, which *do* list "Oven in the kitchen floor units", "Combined hob
and oven with 4 hobs" and "Fridge (137 l) with integrated oven". Dethleffs neither fits nor
offers a microwave on any of the 48.

### Two things the layout data revealed that the adapter's own diff would not

`Just Camp Active T 6762` is the **only one of the 48 with no rear bed** — its rear third
is a full-width divisible washroom with a floor-to-ceiling wardrobe, and it is the single
layout for which the site publishes no `Bed dimension: Rear bed` row. It sleeps two on the
drop-down bed over the front lounge.

**Seven layouts have a rear lounge**, not a rear bed: `Trend Active I 7027` (new for
MY2027), both `XL A 6822-2` and `A 7822-2`, and all four Alpas. Their `Rear bed` figure is
the U-shaped lounge's made-up bed, which on the Trend and both XLs is even marked optional.
Anything that infers a rear sleeping area from the presence of a `Rear bed` row will get
all seven wrong.

Every kitchen in the range is a **side kitchen** — none is rear or corner — so
`fmlv_kitchen_location` does not discriminate for Dethleffs either.
