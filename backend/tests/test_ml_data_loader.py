"""The real-spectrum augmentation used by ML_USE_REAL_DATA=1 is reproducible: it used to draw from NumPy's unseeded global
generator, so a model trained with real data came out different every time."""
import hashlib
import pathlib

import numpy as np
import pytest

from ml import ml_analysis
from ml.ml_data_loader import RealSpectrumLoader, load_real_training_data

FIXTURES = pathlib.Path(__file__).resolve().parent / "data" / "real_spectra"


def _spectra():
    rng = np.random.default_rng(3)
    return [(rng.poisson(40, 256).astype(float), "Cs-137", {"filename": "a.csv"}),
            (rng.poisson(25, 300).astype(float), "Th-232", {"filename": "b.csv"}),
            (rng.poisson(60, 256).astype(float), None, {"filename": "unlabelled.csv"})]


def test_augmentation_is_reproducible_for_a_seed_and_varies_between_seeds():
    loader = RealSpectrumLoader(str(FIXTURES))
    first, labels = loader.prepare_training_data(_spectra(), target_channels=128, augment_count=5, seed=7)
    again, labels_again = loader.prepare_training_data(_spectra(), target_channels=128, augment_count=5, seed=7)
    other, _ = loader.prepare_training_data(_spectra(), target_channels=128, augment_count=5, seed=8)
    assert labels == labels_again == ["Cs-137"] * 5 + ["Th-232"] * 5     # the unlabelled spectrum is skipped
    assert first.shape == (10, 128)
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)


def test_files_are_read_in_a_fixed_order():
    loader = RealSpectrumLoader(str(FIXTURES))
    names = [meta["filename"] for _, _, meta in loader.load_all_from_directory(FIXTURES)]
    assert names, "the fixture folder should hold labelled spectra"
    csvs = [n for n in names if n.endswith(".csv")]
    assert csvs == sorted(csvs)


def _weights_digest(model):
    h = hashlib.sha256()
    for w in model.coefs_ + model.intercepts_:
        h.update(np.ascontiguousarray(w).tobytes())
    return h.hexdigest()


def _labelled_folder(tmp_path):
    """A data folder whose acquisitions/ holds CSV spectra (energy,counts) with the label in the file name, as the loader expects."""
    acquisitions = tmp_path / "acquisitions"
    acquisitions.mkdir()
    rng = np.random.default_rng(5)
    energies = 3.0 + 7.4 * np.arange(1024)
    for name, centre in (("cesium_137_run", 662), ("thorium_run", 2614), ("uranium_glass_run", 609), ("background_run", 1461)):
        lam = 20 + 400 * np.exp(-0.5 * ((energies - centre) / 40.0) ** 2)
        lines = ["Energy (keV),Counts"] + [f"{e:.2f},{c}" for e, c in zip(energies, rng.poisson(lam))]
        (acquisitions / f"{name}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def test_training_with_real_data_gives_the_same_model_twice(tmp_path, monkeypatch):
    folder = _labelled_folder(tmp_path)
    x, labels = load_real_training_data(data_dir=str(folder), target_channels=1024, augment_count=10)
    assert sorted(set(labels)) == ["Background", "Cs-137", "Th-232", "U-238"] and len(labels) == 40   # the data really is used
    monkeypatch.setenv("ML_USE_REAL_DATA", "1")
    monkeypatch.setattr(ml_analysis, "load_real_training_data",
                        lambda data_dir=None, **kw: load_real_training_data(data_dir=str(folder), **kw))
    digests = []
    for _ in range(2):
        ident = ml_analysis.MLIdentifier(model_type="hobby", detector="alphahound")
        ident.lazy_train()
        digests.append(_weights_digest(ident.model))
    assert digests[0] == digests[1]
