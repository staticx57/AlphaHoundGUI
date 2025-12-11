
import pytest
from backend.n42_parser import parse_n42
from backend.csv_parser import parse_csv_spectrum

def test_parse_n42(mock_n42_content):
    result = parse_n42(mock_n42_content)
    assert "error" not in result
    assert len(result["counts"]) == 7
    assert len(result["energies"]) == 7
    # E = 2.0 * Ch (implied B=0 from XML 0 2.0)
    assert result["energies"][1] == 2.0 * 1 # Channel 1 * 2 = 2.0? 
    # Wait, XML: <Coefficient>0</Coefficient> <Coefficient>2.0</Coefficient> -> E = C0 + C1*x + ...
    # E = 0 + 2*x. x=0 -> 0, x=1 -> 2.
    assert result["energies"][5] == 10.0

def test_parse_csv_simple():
    csv_content = b"Energy,Counts\n0,10\n10,20\n20,50"
    result = parse_csv_spectrum(csv_content, "test.csv")
    assert len(result["counts"]) == 3
    assert result['energies'] == [0.0, 10.0, 20.0]
    assert result['counts'] == [10, 20, 50]

def test_parse_csv_headerless():
    # Heuristic detection
    csv_content = b"0,10\n10,20\n20,50"
    result = parse_csv_spectrum(csv_content, "test_noheader.csv")
    assert len(result["counts"]) == 3
    assert result['energies'] == [0.0, 10.0, 20.0]
