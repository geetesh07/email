import pytest
from processing.spec_extractor import extract_all_specs

def test_extract_dimensions():
    text = "The shaft should be 45.5mm in diameter and length is 120 cm."
    specs = extract_all_specs(text, [], "Alice", "alice@example.com", "2023-01-01", "test.eml")
    
    assert len(specs) >= 2
    cats = [s.category for s in specs]
    assert "Dimensions" in cats
    
    # Check specific values
    vals = [s.value for s in specs]
    assert "45.5" in vals
    assert "120" in vals

def test_extract_torque():
    text = "Tighten the bolts to 50 Nm."
    specs = extract_all_specs(text, [], "Alice", "alice@example.com", "2023-01-01", "test.eml")
    assert any(s.category == "Torque" and s.value == "50" for s in specs)

def test_extract_temperature():
    text = "Operating temp is -20 C to 85°C."
    specs = extract_all_specs(text, [], "Alice", "alice@example.com", "2023-01-01", "test.eml")
    
    vals = [s.value for s in specs if s.category == "🌡️ Temperature"]
    assert "-20" in vals
    assert "85" in vals

def test_extract_materials():
    text = "Housing must be made of Aluminum 6061-T6."
    specs = extract_all_specs(text, ["Aluminum 6061-T6", "Steel"], "Alice", "alice@example.com", "2023-01-01", "test.eml")
    assert any(s.category == "Material" for s in specs)

def test_false_positives_filtered():
    # Looks like a dimension, but is a part number or date
    text = "Part 12x456 is due on 24/11/2023."
    specs = extract_all_specs(text, [], "Alice", "alice@example.com", "2023-01-01", "test.eml")
    assert len(specs) == 0
