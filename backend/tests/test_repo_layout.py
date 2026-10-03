"""Repository layout guard: fails when clutter creeps back in.

It reads the list of tracked files from git (skipped outside a git checkout) and checks:
  - the repository root holds only files on an allow-list (new top-level files need a deliberate decision);
  - no backup / temp / log files are tracked (old_*, *.tmp, *.bak, ...);
  - no tracked file is large (an unreferenced 1 MB icon is how this repository once carried 15 MB of dead weight);
  - every tracked image is referenced by some tracked text file;
  - relative links between the Markdown documents are not broken.

TO_BE_DELETED/ (files waiting for deletion) and legacy/ (third-party code kept for its licence) are exempt."""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXEMPT = ("TO_BE_DELETED/", "legacy/")

ROOT_FILES_ALLOWED = {
    ".gitignore", ".gitattributes", "LICENSE", "README.md", "CHANGELOG.md", "INSTALL.md", "TODO.md", "TECHNICAL_DEBT.md",
    "requirements.txt", "requirements_lightweight.txt",
    "install.bat", "install_deps.bat", "install_lightweight.bat", "run.bat", "run_lightweight.bat",
    "download_iaea_data.py",
}
MAX_TRACKED_BYTES = 800 * 1024
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp")
TEXT_SUFFIXES = (".py", ".js", ".html", ".css", ".md", ".bat", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ps1", ".sh")
CLUTTER = re.compile(r"(\.(tmp|bak|bakg|orig|rej|swp|log|pyc)$)|(~$)|((^|/)(old|older|backup)[_-])", re.IGNORECASE)


def tracked_files():
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    return [f for f in out.split("\0") if f and not f.startswith(EXEMPT) and (ROOT / f).is_file()]


def test_repository_root_holds_only_allowed_files():
    extra = sorted(f for f in tracked_files() if "/" not in f and f not in ROOT_FILES_ALLOWED)
    assert not extra, (
        "new top-level files: put them in docs/, backend/ or tools/, or add them to ROOT_FILES_ALLOWED on purpose: " + ", ".join(extra))


def test_no_backup_temp_or_log_files_are_tracked():
    found = sorted(f for f in tracked_files() if CLUTTER.search(f))
    assert not found, "move out or delete: " + ", ".join(found)


def test_no_tracked_file_is_large():
    big = sorted((f, (ROOT / f).stat().st_size) for f in tracked_files() if (ROOT / f).stat().st_size > MAX_TRACKED_BYTES)
    assert not big, "files over %d KB (compress, or keep out of git): %s" % (
        MAX_TRACKED_BYTES // 1024, ", ".join(f"{f} ({size // 1024} KB)" for f, size in big))


def test_every_tracked_image_is_referenced():
    files = tracked_files()
    corpus = {}
    for f in files:
        if f.lower().endswith(TEXT_SUFFIXES):
            corpus[f] = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
    unreferenced = []
    for image in (f for f in files if f.lower().endswith(IMAGE_SUFFIXES)):
        # as the page, a stylesheet or a document would write it: the full path, or the path under backend/ or backend/static/
        spellings = {image, image.removeprefix("backend/"), image.removeprefix("backend/static/")}
        if not any(s in text for other, text in corpus.items() if other != image for s in spellings):
            unreferenced.append(image)
    assert not unreferenced, "images that nothing refers to: " + ", ".join(sorted(unreferenced))


def test_relative_links_between_documents_are_not_broken():
    broken = []
    for f in tracked_files():
        if not f.endswith(".md") or f.startswith("backend/static/vendor/"):
            continue
        text = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(ROOT, os.path.dirname(f), target))):
                broken.append(f"{f} -> {target}")
    assert not broken, "broken links: " + "; ".join(broken)


def test_user_acquisitions_are_not_tracked():
    """backend/data/acquisitions/ is where the app saves the user's own measurements; fixtures live in tests/data/."""
    saved = sorted(f for f in tracked_files() if f.startswith("backend/data/acquisitions/"))
    assert not saved, "user data in git (use backend/tests/data/real_spectra for fixtures): " + ", ".join(saved[:5])


BACKEND_TOP_LEVEL_MODULES = {"main.py", "core.py"}


def test_backend_modules_live_in_packages():
    """backend/ holds the entry point and shared settings; everything else belongs in formats/, spectroscopy/, nuclides/,
    devices/, ml/ or routers/ (47 modules once sat side by side)."""
    loose = sorted(f for f in tracked_files()
                   if f.startswith("backend/") and f.count("/") == 1 and f.endswith(".py")
                   and f.split("/")[1] not in BACKEND_TOP_LEVEL_MODULES)
    assert not loose, "put these in a package: " + ", ".join(loose)
