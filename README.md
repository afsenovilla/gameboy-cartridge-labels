# Game Boy labels

Clean, straight-on images of Game Boy cartridge labels, made from photos of cartridges: my own, and ones found online.

## Setup

Needs Python 3. Run `make setup` once: it creates the Python environment, `.venv/`, with the packages in
`requirements.txt`. Run `make` to list the steps.

### Windows

Everything runs on Windows 10/11 (it also runs on macOS and Linux; the tests run on all three in CI).

1. Install Python 3.13 from python.org (tick "Add python.exe to PATH") and Git for Windows.
2. In PowerShell, in the project folder, without `make`:

   ```
   python run.py setup
   python run.py test
   python run.py all
   ```

   `run.py` takes the same targets as the Makefile, with the same options: `python run.py read-text SAMPLE=1`,
   `python run.py refreeze ID=DMG-TS-USA-mike`, `python run.py clean-prints`. `python run.py` lists them.
3. If you prefer `make`, install it (`winget install ezwinports.make`, or `scoop install make`) and use Git Bash: `make`
   then works as on Linux. `make publish` (publish.sh) needs Git Bash either way.

4. The steps read a serials database from `../gb-game-list/database/releases.json` (the `gb-game-list` repo, next to this
   one). If you don't have it, `python src/bootstrap_database.py` builds a stand-in from the published site's
   `index.json`; it only knows the cartridges the site already lists.

Put new photos in `save-new-images-here/` and run `python run.py add-photos`; they are filed in `photos/` (HEIC works
through `pillow-heif`). Text files are read and written as UTF-8 with LF line
endings on every system, so the JSON files are the same ones as on other systems; `.gitattributes` keeps Git from
turning them into CRLF.
