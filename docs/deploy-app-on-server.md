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

5. Pull down the latest copy of the source code from GitHub (NB: this will pull the `master` branch):

   ```powershell
   git pull
   ```

6. Stop and restart the deployed app:

   ```powershell
   .\deploy\windows\05-install-app-service.ps1
   ```
