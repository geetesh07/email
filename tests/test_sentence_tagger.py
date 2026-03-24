import pytest
from processing.sentence_tagger import tag_sentences, extract_unresolved

def test_tag_sentences_decisions():
    text = "We agreed to use the 5V power supply. The team approved."
    tagged = tag_sentences(text, ["power supply", "agreed"], ["?"], "Alice", "alice@test.com", "2023-01-01", "test.eml")
    
    triggers = [t.trigger_keywords for t in tagged if getattr(t, 'trigger_keywords', None)]
    
    # Check if 'agreed' keyword triggered
    found = False
    for t_list in triggers:
        if "agreed" in t_list:
             found = True
    assert found

def test_extract_unresolved_question():
    text = "Can we use the 10mm bolt instead?"
    unresolved = extract_unresolved(text, ["?"], "Bob", "bob@test.com", "2023-01-01", "test.eml", ["bolt"])
    
    assert len(unresolved) == 1
    assert "10mm bolt instead?" in unresolved[0].sentence

def test_extract_unresolved_todo():
    text = "ACTION: Verify the thermal limits by Tuesday."
    unresolved = extract_unresolved(text, ["ACTION", "TODO"], "Bob", "bob@test.com", "2023-01-01", "test.eml", ["thermal"])
    
    assert len(unresolved) == 1
    assert "ACTION: Verify" in unresolved[0].sentence

def test_extract_unresolved_false_positive():
    text = "How are you? I'm doing fine."
    # With engineering keywords required, this should return empty if no keyword
    unresolved = extract_unresolved(text, ["?"], "Bob", "bob@test.com", "2023-01-01", "test.eml", ["bolt", "thermal"])
    
    assert len(unresolved) == 0
