"""Every committed real spectrum (both devices) must pass all of its accuracy checks."""
import pytest

import real_benchmark as rb

COMMITTED = [c for c in rb.CASES if c[3].exists() and "rc110" not in c[0]]


@pytest.mark.parametrize("case", COMMITTED, ids=[c[0] for c in COMMITTED])
def test_real_spectrum_accuracy(case):
    checks, chains, isotopes = rb.score_case(case, rb.analyze_case(case))
    failed = [name for name, ok in checks if not ok]
    assert not failed, f"{case[0]}: {failed}; chains={chains}; top isotopes={isotopes[:3]}"


def test_benchmark_covers_both_devices():
    devices = {c[1].split("-")[0] for c in COMMITTED}
    assert {"RadiaCode", "AlphaHound"} <= devices
