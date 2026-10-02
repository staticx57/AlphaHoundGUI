"""ML identifier: energy-grid resampling, and end-to-end on synthetic spectra (no real data, no PyRIID)."""
import numpy as np
import pytest

import ml_analysis as ml


def test_resample_preserves_total_and_moves_line_to_right_channel():
    ident = ml.MLIdentifier(model_type="hobby", detector="alphahound")      # 3.0 keV/channel
    n = 1024
    energies = 5.0 + 2.4 * np.arange(n)                                       # a Radiacode-like axis
    counts = np.zeros(n)
    counts[int((661.7 - 5.0) / 2.4)] = 1000.0
    out = ident.resample(counts, energies)
    assert out.sum() == pytest.approx(1000.0, rel=1e-6)
    assert abs(int(np.argmax(out)) * 3.0 + 1.5 - 661.7) < 6.0                  # within ~1 model channel


def test_resample_without_energies_pads_or_truncates():
    ident = ml.MLIdentifier()
    assert len(ident.resample(np.ones(10))) == ident.n_channels
    assert len(ident.resample(np.ones(5000))) == ident.n_channels


def test_features_are_unit_norm_and_zero_safe():
    x = ml.MLIdentifier.features(np.array([[4.0, 9.0], [0.0, 0.0]]))
    assert np.linalg.norm(x[0]) == pytest.approx(1.0)
    assert not np.isnan(x).any()


@pytest.fixture(scope="module")
def trained():
    ident = ml.MLIdentifier(model_type="hobby", detector="radiacode_110")
    ident.lazy_train()
    return ident


def test_synthetic_cs137_and_thorium_are_identified(trained):
    rng = np.random.default_rng(7)
    cs = trained.synthesize([(661.7, 85.0)], rng)
    assert trained.identify(cs)[0]["isotope"] == "Cs-137"
    th = trained.synthesize(trained._lines("Tl-208", [583.2, 2614.5, 510.8]) + trained._lines("Ac-228", [338.3, 911.2, 969.0])
                            + trained._lines("Pb-212", [238.6, 300.1]), rng)
    assert trained.identify(th)[0]["isotope"] in ("Th-232 series", "Th-232")


def test_series_daughters_are_not_standalone_classes(trained):
    assert "Pb-214" not in trained.classes_ and "Ac-228" not in trained.classes_
    assert "Th-232 series" in trained.classes_
