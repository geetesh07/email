import pytest
from processing.deduplicator import deduplicate_body

def test_exact_deduplication():
    # Identical texts
    text1 = "Here are the new specs for the motor."
    text2 = "Here are the new specs for the motor."
    
    assert len(deduplicate_body(text1, [])) > 0
    # Add text1 to seen_hashes manually to simulate the deduplication process
    # Because deduplicate_body modifies the passed set
    seen = set()
    deduplicate_body(text1, seen)
    assert len(deduplicate_body(text2, seen)) == 0
    
def test_fuzzy_deduplication():
    # Slightly different texts (due to formatting/forwarding)
    text1 = "Here are the new specs for the motor:\n- Torque: 50Nm\n- RPM: 3000"
    text2 = ">> Here are the new specs for the motor:\n>> - Torque: 50Nm\n>> - RPM: 3000\n"
    seen = set()
    deduplicate_body(text1, seen)
    
    # Should be detected as a duplicate because > are stripped
    assert len(deduplicate_body(text2, seen)) == 0

def test_no_dedup_different():
    text1 = "The motor rpm is 3000."
    text2 = "The pump pressure is 150 psi."
    seen = set()
    
    deduplicate_body(text1, seen)
    assert len(deduplicate_body(text2, seen)) > 0
