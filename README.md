# FMLV Automated Data Flow

Automates the manual work of keeping [Find My Leisure Vehicle](https://findmyleisurevehicle.org)
(FMLV) — the NCC's public tool for comparing UK caravan and motorhome specs and prices —
up to date.

## The problem this solves

FMLV is only useful if its data is current. Today, keeping it current means someone
downloading the live export, then working through roughly 100 manufacturer websites by
hand, model by model, checking prices, weights and dimensions against it and noting what
has changed. It's slow, repetitive, and the kind of task a person's attention drifts on
by the fiftieth model.

The data itself is well suited to automation — it's almost entirely numbers and hard
facts. What makes it hard is the sheer number of sources, each published in a different
place and a different shape.

## What it does

For one manufacturer at a time, the pipeline:

1. Takes the current FMLV export as the baseline.
2. Visits the manufacturer's website and reads what's currently published there.
3. Works out every difference from the baseline — new products, changed prices,
   changed weights, changed dimensions.
4. Puts those differences in front of a human reviewer, one field at a time, with the
   source page alongside it, to accept, reject, or correct.
5. Produces a CSV in the exact format FMLV expects, containing only the changes a
   reviewer approved.

The system never publishes anything on its own. A person always makes the final call,
and a person still uploads the finished file — this just removes the tedious
find-and-compare work beforehand.

See [DESIGN.md](DESIGN.md) for the full design, the reasoning behind each decision, and
open questions still being worked through, and
[docs/architecture-overview.html](docs/architecture-overview.html) for a high-level
diagram of how it all fits together (open the file directly in a browser).

## Scheduled runs

Runs can be scheduled by adding them to `config/schedule.csv`. 
One row per scheduled manufacturer (optionally narrowed to specific ranges). 
It's a plain CSV file so it can be opened and edited directly in Excel: add a row for a new
item, delete one to stop it, or flip `enabled` to pause/resume without touching any code.

See [config/schedule.README.md](config/schedule.README.md) for the full
column-by-column field guide and how "due" is worked out.

## Project layout

| Folder | What it's for |
|---|---|
| `src/product_model/` | The canonical vehicle record — what a "product" is, its 68 fields, and the rules for reading and writing FMLV's export format. |
| `src/registry/` | The list of manufacturers to check, and where/how to reach each one. |
| `src/fetch/` | Downloads pages, PDFs, and the FMLV export itself. |
| `src/adapters/` | One file per manufacturer, turning that manufacturer's page into a vehicle record. The only manufacturer-specific code. |
| `src/diff/` | Works out what's new, what's changed, and what's stayed the same. |
| `src/webapp/` | The review website reviewers use to accept, reject or correct proposed changes. |
| `src/store/` | The database: run history, proposed changes, reviewer decisions. |
| `src/scheduling/` | Loads `config/schedule.csv` and works out which entries are due to run. |
| `src/cli.py` | The command-line entry point (`fmlv run <manufacturer>`) that ties the above together. |
| `deploy/` | Scripts for installing and running this on a Windows server. |
| `tests/` | Automated tests, one folder per component above. |
| `data/` | Runtime data: downloaded exports, saved pages, the database, generated upload files. Not committed to the repository. |

## Getting started (for developers)

This project uses [uv](https://docs.astral.sh/uv/) to manage its Python environment and
requires Python 3.14+.

Set up your developer environment - see [docs/setup-dev-environment.md](docs/setup-dev-environment.md) for a full walkthrough.
(Git, uv, VS Code, the Claude Code extension, and connecting VS Code to GitHub). If
you've already got all that set up, skip straight to the next step.

Install the required packages:
```bash
uv sync                              # install dependencies
uv run playwright install chromium   # one-time, needed for JS-rendered manufacturer sites
```

Start the review app for local testing:

```bash
uv run uvicorn src.webapp.serve:app --port 8000
```

Run the pipeline for one manufacturer using command line (this can also be triggered in the web app):

```bash
uv run fmlv run Adria
```

Run the test suite

```bash
uv run pytest -q                
```

## Adding a manufacturer

Two things have to exist before a manufacturer's products flow into FMLV: a row in
`config/manufacturers.csv`, and an adapter — the one file that knows how to read that
particular manufacturer's website.

The easiest way to get both is to ask Claude Code:

```
# 1. Set the underlying AI model to Claude Opus - the second-most powerful tier of model. Appropriate for a complex coding task like this
/model opus 

# 2. Run the add-manufacturer skill (.claude\skills\add-manufacturer\SKILL.md)
/add-manufacturer <manufacturer_name>
```

The process is designed to have three steps:
1. **It asks what you know.** What's worth watching out for with this manufacturer, which
   ranges are unusual, anything that's caught people out before — and any URLs you already
   have. Both are optional, but **this is the highest-value thing you can do.** 
2. **It goes and looks.** It finds where the specs actually live — usually a price list or
   brochure PDF — and downloads it to check the weights and prices are really in there
   rather than assuming.
3. **It comes back and asks you to confirm** before writing any code: here's the document
   I plan to read, here's a real row from it, here's how many products I expect. You're
   the expert — if it's picked the wrong brochure, this is where you catch it in seconds.

Only after you say yes does it write, wire up and test the adapter.


## Deployment (Windows Server VM)

The app runs as a **Windows service**, not in a container — see
[DESIGN.md §8.2](DESIGN.md) for why. It's installed with [NSSM](https://nssm.cc/) as
service **`FMLVReviewApp`**, listening on port **8000**, running as `LocalSystem`.

- Quick instructions are here: [`docs/deploy-app-on-server.md`](docs/deploy-app-on-server.md)
- Full README here: [`deploy/windows/README.md`](deploy/windows/README.md)


**Useful commands on the VM:**

```powershell
Get-Service FMLVReviewApp                     # is it running?
Restart-Service FMLVReviewApp
Get-Content C:\fmlv\logs\fmlv-app.err.log -Tail 80   # first place to look when a run fails
Get-Content C:\fmlv\logs\fmlv-app.out.log -Tail 80
```

**Where the logs are:** `C:\fmlv\logs\fmlv-app.err.log` / `fmlv-app.out.log` — NSSM
redirects the service's stdout/stderr there and rotates them, since a Windows service
has no console to print to. A failed *run* (as opposed to the service itself not
starting) also records its error message against that run in the review app —
`/runs/<id>` — so check there first; the log file is for tracebacks the review app
doesn't show, or for the service failing to start at all.

`deploy/windows/README.md`'s own Troubleshooting section covers the two failures
already hit deploying this: a service that starts and immediately stops (usually a
missing [VC++ redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist),
surfacing as `ImportError: DLL load failed while importing _greenlet`), and a
triggered run failing with `BrowserType.launch: Executable doesn't exist` (Chromium
installed under the wrong Windows account's profile — LocalSystem can't see it).

## Status

Prototype, under active development. See [DESIGN.md](DESIGN.md) §2 for current success
criteria and [TODO.md](TODO.md) for what's built versus outstanding.

**Built by:** Ben Molyneaux (Apogee Consulting Services Ltd)
**Project Sponsor:** Francis Doyle (NCC)
