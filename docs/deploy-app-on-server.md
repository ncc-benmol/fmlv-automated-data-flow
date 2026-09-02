# Deploy App on Server

1. Log into the server (it's a Windows virtual machine) using Remote Desktop Connection.

   - IP: `192.168.16.43`
   - User: `ben`
   - Password: `$$45A1T3st%`

   NB: tick the option for sharing the clipboard. This lets you copy/paste between your local machine and the VM

2. Make sure you are on the server, the remote desktop connection, before doing the rest of the instructions.

3. Search for the "PowerShell" app, and choose **Run as Administrator**.

4. Navigate to the project folder:

   ```powershell
   cd C:\apps\fmlv-automated-data-flow\
   ```

   **Do this before anything else, and check it worked.** PowerShell opens in
   `C:\WINDOWS\system32`, and every command below is run *from inside the project folder* —
   run them anywhere else and `git pull` answers `fatal: not a git repository` while the
   deploy script answers `is not recognized as the name of a cmdlet`. Neither message
   mentions the directory, so they read like something is broken when nothing is.

   The prompt is the confirmation. It must now read:

   ```
   PS C:\apps\fmlv-automated-data-flow>
   ```

   If it still says `system32`, the `cd` did not work and nothing after this will either.

5. Pull down the latest copy of the source code from GitHub (NB: this will pull the `master` branch):

   ```powershell
   git pull
   ```

   `Already up to date.` is a normal, successful answer — it means the code had already
   arrived. Step 7 confirms what you actually have.

6. Restart the app so the running service picks up the new code:

   ```powershell
   Restart-Service FMLVReviewApp
   ```

   `WARNING: Waiting for service 'FMLV review app (FMLVReviewApp)' to start...` is a normal
   progress message, not an error.

   > **This is enough for an ordinary code change**, and it is the one to reach for. The
   > heavier `.\deploy\windows\05-install-app-service.ps1` *removes and recreates* the
   > Windows service — needed only when first installing it, or when changing the port or
   > the account it runs under. Re-running it for a routine update is unnecessary risk.
   >
   > `uv sync` is only needed when the project's **dependencies** change (`pyproject.toml`
   > or `uv.lock`), which is rare — ask if you are unsure.

7. Confirm the deploy:

   ```powershell
   Get-Service FMLVReviewApp; git log --oneline -1
   ```

   The service must say **Running**, and the commit shown should be the change you were
   expecting. If the service says `Stopped`, the app did not come back up — say so rather
   than re-running the steps.
