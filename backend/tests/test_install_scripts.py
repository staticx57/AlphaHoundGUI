"""
The install and run scripts (install_deps.bat, install_lightweight.bat, run.bat, run_lightweight.bat) and the self-check they use
(backend/tools/check_install.py). They are Windows batch files, so what is tested is what went wrong or could silently drift:

- a batch file that runs another batch file without CALL never gets control back. `python` is a .bat shim under pyenv-win, so the old
  scripts ended silently after their first Python line;
- bare LF line endings break labels and GOTO on some Windows setups;
- a GOTO to a label that is not there, a requirements file or tool that was renamed;
- requirements_lightweight.txt, backend/requirements.txt and the self-check disagreeing about what is required;
- the browser opener probing `localhost`, which takes two seconds a request on a machine that tries IPv6 first (longer than the probe's timeout:
  the browser then never opened).
"""
import os
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "tools"))

import check_install   # noqa: E402

BATS = ["install_deps.bat", "install_lightweight.bat", "run.bat", "run_lightweight.bat"]


def text(name):
    return (ROOT / name).read_bytes().decode("ascii")


def normalise(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_names(path):
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            names.add(normalise(re.split(r"[<>=!~\[; ]", line)[0]))
    return names


@pytest.mark.parametrize("name", BATS)
def test_batch_files_use_windows_line_endings_and_plain_ascii(name):
    raw = (ROOT / name).read_bytes()
    assert raw.replace(b"\r\n", b"").count(b"\n") == 0, "bare LF"
    raw.decode("ascii")


@pytest.mark.parametrize("name", BATS)
def test_python_is_always_called_with_call(name):
    """`python` may be a .bat (pyenv-win's shim): without CALL the script ends there."""
    for number, line in enumerate(text(name).split("\r\n"), 1):
        assert not re.match(r"\s*(python|pip)\s", line, re.I), f"{name}:{number}: {line}"


@pytest.mark.parametrize("name", BATS)
def test_every_goto_has_its_label(name):
    body = text(name)
    labels = set(re.findall(r"(?m)^:([A-Za-z]\w*)\s*$", body))
    for target in re.findall(r"(?i)GOTO\s+:(\w+)", body):
        assert target in labels, f"{name}: GOTO :{target} has no label"


def test_the_files_the_scripts_name_exist():
    for name in ("install_deps.bat", "install_lightweight.bat"):
        for ref in re.findall(r'"%~dp0([^"]+)"', text(name)):
            assert (ROOT / ref.replace("\\", "/")).exists(), f"{name}: {ref}"
    assert (BACKEND / "main.py").exists() and (BACKEND / "tools" / "check_install.py").exists()
    run = text("run.bat")
    assert "tools\\check_install.py" in run and "main.py" in run


def test_run_starts_on_the_port_the_server_listens_on():
    main_port = re.search(r"port=(\d+)", (BACKEND / "main.py").read_text(encoding="utf-8")).group(1)
    run = text("run.bat")
    assert run.count(f":{main_port}") >= 3 and f"localhost:{main_port}" in run


def test_the_browser_opener_probes_127_0_0_1_and_opens_localhost():
    """localhost takes ~2 s a request where IPv6 is tried first, longer than the probe's timeout: the opener never fired. The browser opens
    localhost, where its saved settings and history live."""
    line = next(l for l in text("run.bat").split("\r\n") if l.startswith('START "" /B powershell'))
    assert "Invoke-WebRequest" in line and "http://127.0.0.1:" in line
    assert "Start-Process http://localhost:" in line
    assert int(re.search(r"-TimeoutSec (\d+)", line).group(1)) >= 5


def test_run_has_no_automatic_reload():
    """--reload restarts the server on any code change, dropping a connected device and an acquisition."""
    assert "--reload" not in text("run.bat").replace("python -m uvicorn main:app --reload --port 3200", "")   # only as the printed development hint


def test_the_lightweight_start_is_the_same_server():
    assert 'call "%~dp0run.bat"' in text("run_lightweight.bat")


def test_the_requirement_lists_and_the_self_check_agree():
    full = requirement_names(BACKEND / "requirements.txt")
    light = requirement_names(ROOT / "requirements_lightweight.txt")
    required = {normalise(pip) for _, pip in check_install.REQUIRED}
    optional = {normalise(pip) for _, pip, _ in check_install.OPTIONAL}
    assert light == required                      # what the lightweight install brings is what the app cannot start without
    assert required <= full and optional <= full  # the full install has all of it
    assert full - required - optional == set()    # nothing in the full list that the self-check does not know


def test_the_root_requirements_file_includes_the_backend_one():
    assert "-r backend/requirements.txt" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- the self-check
def test_the_self_check_passes_on_this_installation(capsys):
    assert check_install.main([]) == 0
    out = capsys.readouterr().out
    assert "Required packages: 12 of 12 present" in out and "Peak finder:" in out


def test_the_self_check_reports_a_missing_required_package_and_fails(monkeypatch, capsys):
    monkeypatch.setattr(check_install, "present", lambda module: module != "fastapi")
    assert check_install.main(["--quiet"]) == 1
    out = capsys.readouterr().out
    assert "PROBLEM" in out and "fastapi" in out and "install_deps.bat" in out


def test_a_missing_optional_package_is_not_a_problem(monkeypatch, capsys):
    monkeypatch.setattr(check_install, "present", lambda module: module not in {m for m, _, _ in check_install.OPTIONAL})
    assert check_install.main([]) == 0
    assert capsys.readouterr().out.count("absent") == len(check_install.OPTIONAL)


def test_the_self_check_fails_on_an_old_python(monkeypatch, capsys):
    monkeypatch.setattr(check_install.sys, "version_info", (3, 9, 1, "final", 0))
    assert check_install.main(["--quiet"]) == 1
    assert "too old" in capsys.readouterr().out


def test_interspec_default_path_follows_the_home_folder():
    from spectroscopy import interspec_peaks
    assert interspec_peaks.DEFAULT_BATCH.startswith(os.path.expanduser("~"))
    assert "stati" not in interspec_peaks.DEFAULT_BATCH.replace(os.path.expanduser("~"), "")
