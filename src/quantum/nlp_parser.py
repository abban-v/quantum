"""Natural-language triage parsing.

Rules are the primary path and must work with no LLM installed. An optional
Ollama adapter can refine low-confidence text; it talks only to localhost and
always falls back to the rules on failure.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import requests

from quantum.problem import Equipment

ALLOWED_SPECIALTIES = {"burn", "trauma", "stroke", "cardiac", "pediatric"}

# (regex, severity lambda, label)
SEVERITY_TERMS: list[tuple[str, float, str]] = [
    (r"cardiac arrest|respiratory arrest|not breathing|apn(?:ea|eic)", 50.0, "arrest"),
    (r"snake ?bite|viper|envenom", 50.0, "envenomation"),
    (r"anaphyla|airway compromise|cyanotic|unconscious|unresponsive", 50.0, "airway"),
    (r"severe smoke inhalation|smoke inhalation", 50.0, "smoke inhalation"),
    (r"massive trauma|multi[- ]system|severe (?:bleeding|hemorrhage)", 40.0, "major trauma"),
    (r"difficulty breathing|shortness of breath|dyspnea|respiratory distress", 20.0, "respiratory distress"),
    (r"chest pain|heart attack|myocardial", 20.0, "chest pain"),
    (r"stroke|facial droop|aphasia|head injury|seizure", 20.0, "neuro"),
    (r"burn", 20.0, "burn"),
    (r"fracture|deep laceration|dislocation", 10.0, "orthopedic"),
    (r"fever|dehydration|mild|minor|sprain|walking wounded", 1.0, "low acuity"),
]

EQUIPMENT_TERMS = [
    r"respiratory distress",
    r"difficulty breathing",
    r"shortness of breath",
    r"dyspnea",
    r"smoke inhalation",
    r"anaphyla",
    r"airway",
    r"not breathing",
    r"apn(?:ea|eic)",
    r"ventilator",
    r"cyanotic",
]

SPECIALTY_TERMS: list[tuple[str, str]] = [
    (r"burn|fire victim|smoke inhalation", "burn"),
    (r"trauma|collision|mva|mvc|multi[- ]system|head injury|fracture", "trauma"),
    (r"stroke|facial droop|aphasia", "stroke"),
    (r"chest pain|cardiac|heart attack|myocardial", "cardiac"),
    (r"child|infant|pediatric|baby", "pediatric"),
]

NEGATION = re.compile(r"\b(no|not|denies|without|negative for)\b", re.I)


class OllamaError(RuntimeError):
    """Raised when the optional local LLM cannot be used."""


@dataclass
class TriageResult:
    severity: float
    equipment_required: Equipment
    specialty_required: str | None
    confidence: float
    matched_terms: list[str] = field(default_factory=list)
    needs_confirmation: bool = False
    parser: str = "rules"
    notes: list[str] = field(default_factory=list)


def _is_negated(text: str, start: int, window: int = 22) -> bool:
    context = text[max(0, start - window):start]
    if "," in context or ";" in context:
        return False
    return bool(NEGATION.search(context))


def parse_rules(text: str) -> TriageResult:
    if not isinstance(text, str) or not text.strip():
        return TriageResult(
            severity=5.0,
            equipment_required="none",
            specialty_required=None,
            confidence=0.2,
            needs_confirmation=True,
            notes=["Empty or non-text input; defaulting to medium acuity."],
        )

    lowered = text.lower()
    matches: list[tuple[float, str]] = []
    for pattern, severity, label in SEVERITY_TERMS:
        for match in re.finditer(pattern, lowered):
            if not _is_negated(lowered, match.start()):
                matches.append((severity, label))
                break

    if matches:
        severity = max(value for value, _ in matches)
    else:
        severity = 5.0

    equipment: Equipment = "none"
    for pattern in EQUIPMENT_TERMS:
        found = False
        for match in re.finditer(pattern, lowered):
            if not _is_negated(lowered, match.start()):
                equipment = "ventilator"
                found = True
                break
        if found:
            break

    specialty: str | None = None
    for pattern, label in SPECIALTY_TERMS:
        found = False
        for match in re.finditer(pattern, lowered):
            if not _is_negated(lowered, match.start()):
                specialty = label
                found = True
                break
        if found:
            break

    labels = sorted({label for _, label in matches})
    if not matches:
        confidence = 0.35
    elif severity >= 40 or len(labels) >= 2:
        confidence = 0.9
    else:
        confidence = 0.7

    notes: list[str] = []
    if equipment == "ventilator" and specialty is None:
        notes.append("Respiratory support requested; no specialty filter applied.")
    if severity >= 40:
        notes.append("Critical acuity: nearest eligible ALS unit is preferred.")

    return TriageResult(
        severity=severity,
        equipment_required=equipment,
        specialty_required=specialty,
        confidence=confidence,
        matched_terms=labels,
        needs_confirmation=confidence < 0.6,
        parser="rules",
        notes=notes,
    )


class OllamaParser:
    """Minimal local Ollama client with strict validation and a short timeout."""

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        self.model = model or os.environ.get("QEVR_OLLAMA_MODEL", "llama3.2")
        self.host = (host or os.environ.get("QEVR_OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout_s = timeout_s

    def available(self) -> bool:
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=1.5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def parse(self, text: str) -> TriageResult:
        prompt = (
            "You are a 911 triage assistant. Return ONLY JSON with keys: "
            '"severity" (number 0-50, higher is more urgent), '
            '"equipment_required" ("none" or "ventilator"), '
            '"specialty_required" (null or one of "burn","trauma","stroke","cardiac","pediatric"), '
            '"confidence" (0-1).\n\n'
            f"Emergency text: {text}"
        )
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0},
                },
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
            raw = json.loads(payload["response"])
        except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama parse failed: {exc}") from exc

        severity = float(raw.get("severity", 5.0))
        severity = max(0.0, min(50.0, severity))
        equipment = raw.get("equipment_required", "none")
        if equipment not in {"none", "ventilator"}:
            raise OllamaError(f"Invalid equipment_required: {equipment!r}")
        specialty = raw.get("specialty_required")
        if specialty is not None:
            specialty = str(specialty).strip().lower()
            if specialty not in ALLOWED_SPECIALTIES:
                raise OllamaError(f"Invalid specialty_required: {specialty!r}")
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.6))))
        return TriageResult(
            severity=severity,
            equipment_required=equipment,
            specialty_required=specialty,
            confidence=confidence,
            matched_terms=["ollama"],
            needs_confirmation=confidence < 0.6,
            parser="ollama",
        )


def parse_incident(
    text: str,
    use_llm: bool = False,
    llm: OllamaParser | None = None,
) -> TriageResult:
    """Parse free text. Rules always run; the LLM is only a refinement."""
    rules = parse_rules(text)
    if not use_llm:
        return rules
    client = llm or OllamaParser()
    if not client.available():
        rules.notes.append("Ollama requested but not reachable; used rules only.")
        return rules
    if rules.confidence >= 0.75 and rules.severity > 1:
        return rules
    try:
        refined = client.parse(text)
    except OllamaError as exc:
        rules.notes.append(str(exc))
        return rules
    refined.notes.append("Refined by local Ollama; verify before dispatch.")
    return refined
