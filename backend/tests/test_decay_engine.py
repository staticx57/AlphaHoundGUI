import pytest
from decay_engine import DecayEngineManager, BuiltinEngine, BaseDecayEngine

def test_decay_engine_manager_list():
    manager = DecayEngineManager()
    engines = manager.list_engines()
    assert len(engines) >= 4
    
    names = [e["name"] for e in engines]
    assert "builtin" in names
    assert "radioactivedecay" in names
    assert "curie" in names
    assert "pyne" in names
    
    # Builtin should always be available
    builtin_info = next(e for e in engines if e["name"] == "builtin")
    assert builtin_info["available"] is True

def test_builtin_decay_prediction():
    manager = DecayEngineManager()
    result = manager.predict_decay(
        isotope="Cs-137",
        activity=1000.0,
        duration_seconds=86400,
        points=10,
        engine_name="builtin"
    )
    
    assert result["isotope"] == "Cs-137"
    assert result["initial_activity"] == 1000.0
    assert result["engine_used"] == "builtin"
    assert "series" in result
    assert len(result["time_points"]) == 10

def test_fallback_behavior():
    manager = DecayEngineManager()
    # Requesting non-existent or unavailable engine should fall back gracefully
    engine = manager.get_engine("non_existent_engine")
    assert isinstance(engine, BaseDecayEngine)
    assert engine.name == "builtin"
