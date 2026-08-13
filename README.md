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
open questions still being worked through.

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

```bash
uv sync                          # install dependencies
uv run playwright install chromium   # one-time, needed for JS-rendered manufacturer sites
uv run pytest -q                 # run the test suite
```

Run the pipeline for one manufacturer:

```bash
uv run fmlv run Adria
```

Start the review website locally:

```bash
uv run uvicorn src.webapp.serve:app --port 8000
```

See [TESTING.md](TESTING.md) for a fuller walkthrough, including how to point the
pipeline at a real export and inspect what it produces.

## Deployment (Windows Server VM)

The app runs as a **Windows service**, not in a container — see
[DESIGN.md §8.2](DESIGN.md) for why. It's installed with [NSSM](https://nssm.cc/) as
service **`FMLVReviewApp`**, listening on port **8000**, running as `LocalSystem`.

Full deploy instructions, including a Windows-onboarding smoke test that should be run
once on any new VM before the real app goes anywhere near it, live in
[`deploy/windows/README.md`](deploy/windows/README.md). In short, from an elevated
PowerShell on the VM, in order:

```powershell
cd deploy\windows
.\01-bootstrap.ps1            # installs uv + Python 3.14, checks outbound internet
.\04-provision-app.ps1        # uv sync, playwright install chromium, creates data\
.\05-install-app-service.ps1  # registers and starts the FMLVReviewApp service
```

`04` and `05` both need a real `.env` in the repo root first (copy `.env.example`,
fill in `NCC_LOGIN_EMAIL`/`NCC_LOGIN_PASSWORD`) and must be run elevated — the shared
cache under `C:\fmlv` is only writable by `SYSTEM`/`Administrators`.

**Updating a running deployment:**

```powershell
cd C:\apps\fmlv-automated-data-flow
git pull
.\deploy\windows\05-install-app-service.ps1   # elevated; safe to re-run, restarts the service
```

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
