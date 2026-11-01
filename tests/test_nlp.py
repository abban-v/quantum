from __future__ import annotations

import pytest

from quantum.nlp_parser import parse_incident, parse_rules


@pytest.mark.parametrize(
    "text,severity,equipment,specialty",
    [
        ("Apartment fire victim, severe smoke inhalation, cyanotic.", 50.0, "ventilator", "burn"),
        ("Snake bite with difficulty breathing.", 50.0, "ventilator", None),
        ("Elderly patient with low-grade fever and mild dehydration.", 1.0, "none", None),
        ("Severe motor vehicle collision with massive trauma.", 40.0, "none", "trauma"),
        ("Chest pain and difficulty breathing.", 20.0, "ventilator", "cardiac"),
    ],
)
def test_parse_rules(text, severity, equipment, specialty):
    result = parse_rules(text)
    assert result.severity == severity
    assert result.equipment_required == equipment
    assert result.specialty_required == specialty


def test_negation_does_not_suppress_a_separate_clause():
    result = parse_rules("no difficulty breathing, mild fever")
    assert result.severity == 1.0
    assert result.equipment_required == "none"


def test_empty_input_needs_confirmation():
    result = parse_rules("   ")
    assert result.needs_confirmation
    assert result.confidence < 0.6


def test_llm_disabled_uses_rules():
    result = parse_incident("snake bite, difficulty breathing", use_llm=False)
    assert result.parser == "rules"
