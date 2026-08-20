# Setting up a development environment (Windows)

This is a one-time setup for anyone who's going to work on this project locally on
Windows — whether that's writing code by hand or using Claude Code to do it. If you've
done this before on your machine, skip to [Getting started](../README.md#getting-started-for-developers)
in the main README.

## 1. Install Git

Git is how you get a copy of this repository and share changes.

1. Download the installer from [git-scm.com/download/win](https://git-scm.com/download/win).
2. Run it. The default options are fine for everyone; if asked to pick a default editor,
   choose whatever you're comfortable in (Visual Studio Code is a reasonable default once
   you've installed it in step 3).
3. Confirm it worked — open PowerShell and run:
   ```powershell
   git --version
   ```

## 2. Install uv

[uv](https://docs.astral.sh/uv/) manages the Python version and packages this project
needs, so you don't have to install Python yourself.

1. Open PowerShell and run:
   ```powershell
   winget install --id=astral-sh.uv -e
   ```
   (No `winget`? Use the installer script on the [uv install page](https://docs.astral.sh/uv/getting-started/installation/) instead.)
2. Close and reopen PowerShell so it picks up the new `uv` command.
3. Confirm it worked:
   ```powershell
   uv --version
   ```

You don't need to install Python separately — `uv sync` (covered in the main README)
downloads the exact version this project needs (3.14+) the first time you run it.

## 3. Install Visual Studio Code

1. Download from [code.visualstudio.com](https://code.visualstudio.com/) and run the
   installer.
2. During install, it's worth ticking **"Add to PATH"** if offered — this lets you type
   `code .` from a terminal to open a folder in VS Code.

## 4. Sign in to GitHub from VS Code

This lets VS Code (and the Claude Code extension) push/pull this repository and open pull
requests on your behalf, without you re-entering credentials.

1. Open VS Code.
2. Click the **Accounts** icon in the bottom-left corner of the window.
3. Choose **Sign in with GitHub**.
4. A browser window opens asking you to authorize "Visual Studio Code" — sign in with
   your GitHub account and approve it.
5. You should see your GitHub username appear in the Accounts menu once it's connected.

If you don't already have a GitHub account, create one first at
[github.com/signup](https://github.com/signup), and ask whoever manages this repository
to give you access to it.

## 5. Install the Claude Code extension

1. In VS Code, open the Extensions view (`Ctrl+Shift+X`).
2. Search for **Claude Code** and click **Install**.
3. Once installed, open it (the Claude icon in the sidebar, or `Ctrl+Esc`) and sign in
   with your Anthropic/Claude account when prompted.

## 6. Clone this repository

From PowerShell, navigate to the folder where you want to keep your coding projects. Then run:

```powershell
git clone https://github.com/ncc-benmol/fmlv-automated-data-flow
cd fmlv-automated-data-flow
code .
```

## Next steps

With all of the above done, follow
[Getting started (for developers)](../README.md#getting-started-for-developers) in the
main README to install the project's Python packages and run it for the first time.
