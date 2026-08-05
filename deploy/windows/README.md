# Windows Server deployment

The application runs as a **Windows service on a Windows Server VM**, not in a Docker
container — see [DESIGN.md §8.2](../../DESIGN.md) for the decision and what it changed.

This directory currently holds the **deployment smoke test** (DESIGN.md §8.3): a
deliberately trivial service that proves the VM can run and serve a Python web service
*before* the real application is deployed to it. Scripts for the real deployment come
later (TODO.md Phase 8b).

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
