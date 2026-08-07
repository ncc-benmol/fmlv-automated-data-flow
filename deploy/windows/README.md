# Windows Server deployment

The application runs as a **Windows service on a Windows Server VM**, not in a Docker
container — see [DESIGN.md §8.2](../../DESIGN.md) for the decision and what it changed.

This directory holds two things:

- The **deployment smoke test** (DESIGN.md §8.3, scripts `01`–`03`): a deliberately
  trivial service that proved the VM could run and serve a Python web service at all,
  before the real application went anywhere near it. **Already run and confirmed
  working (TODO.md 8a, 2026-08-05)** — kept here so it can be re-checked and torn down.
- The **real deployment** (TODO.md Phase 8b, scripts `04`–`05`): provisions the actual
  checkout and installs the FMLV review app itself as a service.

## Deploying the real app for the first time

1. Re-run the smoke test's checks below ("Run it") to confirm the VM still works
   exactly as it did on 2026-08-05, since nothing about it should have changed.
2. Provision the app (no admin needed):
   ```powershell
   cd <repo>\deploy\windows
   powershell -ExecutionPolicy Bypass -File .\04-provision-app.ps1
   ```
   This needs a real `.env` in the repo root first (copy `.env.example`, fill in the
   NCC credentials) — the script warns but doesn't fail if it's missing, so fix it
   before continuing to step 3.
3. Install and start the app as a service (**elevated PowerShell**):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\05-install-app-service.ps1
   ```
   Finishes by polling `http://127.0.0.1:8000/` and reporting success, same shape as
   the smoke test's step 2.
4. Check it from your own machine — `http://192.168.16.43:8000/` (see TODO.md 8a for
   why that address and not the other one) — and trigger a real run from the browser.
5. Once that's confirmed, tear down the smoke test — it has no business outliving the
   question it answered:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\03-uninstall-smoketest.ps1
   ```
   This leaves `C:\fmlv\tools\nssm.exe` and the uv cache in place; both `05-install-
   app-service.ps1` and any future re-provisioning reuse them.

`04`/`05` run as **`LocalSystem`**, the same account the smoke test proved works here —
see the docstring in `05-install-app-service.ps1` for how to switch to a dedicated
account later without any code change, if `.env` holding NCC credentials under
LocalSystem ever becomes a concern.

---

## The deployment smoke test (`01`–`03`)

## What the smoke test proves

Four things, each independently capable of derailing the deployment, and none of them
worth discovering while also debugging FMLV logic:

1. `uv` installs on the host and can fetch dependencies from PyPI.
2. A Python process can be registered as an auto-starting Windows service.
3. The service comes back on its own after a reboot, with nobody logged in.
4. The port is reachable from your own machine.

It answers the inbound half of open question 9. The outbound half — whether the VM can
reach ~100 manufacturer sites, the NCC site and the Anthropic API without a proxy — is
checked by `01-bootstrap.ps1` and is a question for the client's IT.

## Run it

You'll need to RDP onto the VM with local administrator rights. The repo needs to be on
the VM — either `git clone` it there, or copy the `deploy\` folder across; the smoke test
only needs `deploy\smoketest\smoke_service.py` and these scripts, nothing else.

### On the VM

```powershell
cd <repo>\deploy\windows

# 1. Inventory the box, install uv, check outbound internet. No admin needed.
powershell -ExecutionPolicy Bypass -File .\01-bootstrap.ps1

# 2. Install and start the service. MUST be an ELEVATED PowerShell.
powershell -ExecutionPolicy Bypass -File .\02-install-smoketest.ps1
```

Step 2 finishes by calling the service on the VM's own loopback and printing the reply,
so if it says "Service is up" then points 1 and 2 above are settled.

### From your own machine

```powershell
cd <repo>\deploy\windows
.\check-from-local.ps1 -VmHost <vm-hostname-or-ip>
```

Or just open `http://<vm>:8099/` in a browser. `check-from-local.ps1` is worth preferring
on the first attempt because it distinguishes DNS failure from routing failure from a
closed port, which a browser's error page does not.

### Then reboot

```powershell
Restart-Computer
```

Wait for the VM to come back, **without logging in**, and re-run `check-from-local.ps1`.
That's point 3, and it is the one that most often surprises people.

### Then clean up

```powershell
powershell -ExecutionPolicy Bypass -File .\03-uninstall-smoketest.ps1
```

## What gets created

| Path | What |
|---|---|
| `C:\fmlv\tools\nssm.exe` | The service wrapper. Kept after uninstall — Phase 8b wants it. |
| `C:\fmlv\uv-cache\` | uv's package cache, shared so the service account doesn't re-download. |
| `C:\fmlv\python\` | uv-managed Python builds. |
| `C:\fmlv\logs\smoketest.*.log` | Rotating stdout/stderr. **First place to look when a service starts then stops.** |
| Service `FMLVSmokeTest` | Auto-start, restarts on failure after 5s. |
| Firewall rule `FMLVSmokeTest (TCP 8099)` | Inbound, local Windows Firewall only. |

Everything is under `C:\fmlv` rather than in the repo, so a `git clean` can't take the
service's own state with it. Paths and the port are parameters on every script if IT
wants them elsewhere: `-RootDir`, `-Port`, `-ServiceName`.

## Useful commands on the VM

```powershell
Get-Service FMLVSmokeTest                      # is it running?
Restart-Service FMLVSmokeTest
Get-Content C:\fmlv\logs\smoketest.err.log -Tail 50
C:\fmlv\tools\nssm.exe edit FMLVSmokeTest      # GUI for every setting the script made
Invoke-RestMethod http://127.0.0.1:8099/api/time
```

## Running it without installing a service

Useful for a first look, or to see the error the service would have hidden:

```powershell
uv run deploy\smoketest\smoke_service.py --host 0.0.0.0 --port 8099
```

This works on your dev machine too — it has no Windows-specific code, and no dependency
on the FMLV project itself (its dependencies are declared inline, PEP 723 style).

## Troubleshooting

**"The service started and then stopped."** Almost always uv failing to prepare its
environment as the service account: check `C:\fmlv\logs\smoketest.err.log`. The install
script pre-warms the cache as *you* and points the service at the same
`UV_CACHE_DIR`/`UV_PYTHON_INSTALL_DIR` specifically to avoid this — if you changed
`-RootDir` between runs, that's the likely cause.

**Port open from the VM, closed from your machine.** The host firewall rule is not the
network firewall. `check-from-local.ps1` will tell you the port is filtered; the fix is a
request to the client's IT, and it's worth asking for the *real* application's port at the
same time rather than twice.

**A proxy is in the way.** If `01-bootstrap.ps1` reports `HTTP_PROXY`/`HTTPS_PROXY`, the
service needs the same variables — add them to the `AppEnvironmentExtra` line in
`02-install-smoketest.ps1`. Note it in TODO.md, because it affects all of Phase 3's
fetching, not just this.

## Record the outcome

TODO.md Phase 8a has two open items waiting on this run: confirming the four things
above, and recording the VM hostname/IP, the chosen port, and whether a firewall change
beyond the local rule was needed.
