# To be deleted

Everything in this folder is dead: nothing in the app, the tests or the launch scripts uses it (checked 2026-10-03 with a
search for every file name and module name, and the 629+ backend tests pass with these files in this folder).

It is here, and not deleted, only because the tool that moved it could not delete files. Delete the whole folder when you are ready:

    git rm -r TO_BE_DELETED
    git commit -m "Remove dead files"

Git history keeps all of it if you ever need a file back (`git log --follow -- TO_BE_DELETED/<path>`).

| Folder | What it is |
|--------|-----------|
| `root/` | Old backups and run output that sat in the repository root: `old_main_backup.js`, three `*.js.tmp` chart copies, result text files, a dated CSV, a package-research note |
| `backend/` | `3.1` (a pip log), a Becquerel test output, five unused modules (`enhanced_analysis.py`, `radiacode_src.py`, `generate_testing_spectrum.py`, `verify_roi_api.py`, `spectrum_wrapper.py`), the `.bakg` icon, the old `backend/archive/` |
| `backend/static/` | 19 images nothing refers to (17 PNG icons of 0.5-1.5 MB beside the SVGs the page uses, an unused banner, two JPG duplicates of the README images) and a scraped web page (`# NuDat 3.0.md`): 16 MB in all, checked against every tracked text file and with the page loaded in headless Chrome (272 requests, no errors) |
| `archive/` | The former `archive/` folder: 42 debug and exploration scripts from the PyRIID era, orphaned code, icon backups, old batch scripts, printed test results, PyRIID planning documents, demo and synthetic `.n42` files |

Kept, moved out of the old `archive/` on purpose:

- `legacy/AlphaHound-main/`: the upstream project by NuclearGeekETH (MIT licence); keep its `LICENSE` with the repository
- `docs/alphahound_probes/`: raw AlphaHound `G` command captures from 2025-11
- `docs/abundance_weighting_research.md`: the sources behind the isotope abundance weights
- `backend/tests/data/real_csv/`: two real CSV spectra, used by `tests/test_real_csv.py`
