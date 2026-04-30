"""
Deterministic Scoring module (Pass 3 equivalent).

All scoring is deterministic -- same inputs always produce same outputs.
No LLM calls. Ported from meta-ads-intelligence scoring modules:
  - MechanismExplicitnessScorer
  - ProofStrengthScorer
  - TensionDetector

Also includes simplified hook archetype classification based on
Gemini visual analysis output.
"""

import re
import uuid
from datetime import datetime, timezone

from .vocabularies import (
    STEPWISE_MARKERS,
    CAUSAL_VERBS,
    NAMED_SYSTEMS,
    IO_MARKERS,
    CONDITION_MARKERS,
    TENSION_MARKERS,
    PROOF_SOURCE_WEIGHTS,
    ARCHETYPE_NAMES,
    NEGATION_MARKERS,
    CURIOSITY_MARKERS,
    URGENCY_MARKERS,
)


# ===================================================================
# Mechanism Explicitness Scorer
# ===================================================================

class MechanismExplicitnessScorer:
    """
    Scores how explicitly a mechanism of action is described in text.

    Formula: explicitness = max(0, min(1,
        0.10 + 0.20*F1 + 0.20*F2 + 0.20*F3 + 0.20*F4 + 0.10*F5
    ))

    F1: Stepwise markers, F2: Causal verbs, F3: Named systems,
    F4: I/O links, F5: Condition markers.
    """

    def __init__(self):
        self._stepwise_re = self._build_pattern(STEPWISE_MARKERS)
        self._causal_re = self._build_pattern(CAUSAL_VERBS)
        self._systems_re = self._build_pattern(NAMED_SYSTEMS)
        self._io_re = self._build_pattern(IO_MARKERS)
        self._condition_re = self._build_pattern(CONDITION_MARKERS)

    @staticmethod
    def _build_pattern(markers: list[str]) -> re.Pattern:
        escaped = [re.escape(m) for m in markers]
        combined = "|".join(rf"\b{e}\b" for e in escaped)
        return re.compile(combined, re.IGNORECASE)

    def _has(self, pattern: re.Pattern, text: str) -> bool:
        return pattern.search(text) is not None

    def compute_explicitness(self, text: str) -> float:
        if not text or not text.strip():
            return 0.10

        f1 = float(self._has(self._stepwise_re, text))
        f2 = float(self._has(self._causal_re, text))
        f3 = float(self._has(self._systems_re, text))
        f4 = float(self._has(self._io_re, text))
        f5 = float(self._has(self._condition_re, text))

        score = max(0.0, min(1.0,
            0.10 + 0.20 * f1 + 0.20 * f2 + 0.20 * f3 + 0.20 * f4 + 0.10 * f5
        ))
        return round(score, 4)


# ===================================================================
# Proof Strength Scorer
# ===================================================================

class ProofStrengthScorer:
    """
    Scores proof primitives for strength and specificity.

    Formula: strength = max(0, min(1,
        0.15 + 0.35*specificity + 0.30*verifiability
        + 0.20*source_weight - 0.25*penalty
    ))
    """

    def compute_strength(self, proof: dict) -> float:
        cues = proof.get("specificity_cues", {})
        penalties = proof.get("penalty_flags", {})
        source_class = proof.get("source_class", "unknown")

        specificity = self._mean_bools(cues)

        verifiability = (
            float(cues.get("has_link_or_citation", False)) * 0.4
            + float(cues.get("has_named_institution", False)) * 0.3
            + float(cues.get("has_method", False)) * 0.3
        )

        source_weight = PROOF_SOURCE_WEIGHTS.get(source_class, 0.25)
        penalty = self._mean_bools(penalties)

        strength = max(0.0, min(1.0,
            0.15 + 0.35 * specificity + 0.30 * verifiability
            + 0.20 * source_weight - 0.25 * penalty
        ))
        return round(strength, 4)

    def compute_specificity_level(self, cues: dict) -> float:
        return round(self._mean_bools(cues), 4)

    @staticmethod
    def _mean_bools(d: dict) -> float:
        if not d:
            return 0.0
        values = [float(bool(v)) for v in d.values()]
        return sum(values) / len(values)


# ===================================================================
# Tension Detector
# ===================================================================

class TensionDetector:
    """
    Detects cognitive tensions by finding co-occurring marker pairs.
    A tension fires when markers from BOTH poles are present.
    """

    CONFIDENCE = 0.4
    CONFIDENCE_BASIS = "implied"

    def detect_tensions(self, text: str, ad_id: str) -> list[dict]:
        if not text or not text.strip():
            return []

        text_lower = text.lower()
        results = []

        for tension_name, poles in TENSION_MARKERS.items():
            pole_keys = list(poles.keys())
            if len(pole_keys) != 2:
                continue

            pole_a_found = [m for m in poles[pole_keys[0]] if m.lower() in text_lower]
            pole_b_found = [m for m in poles[pole_keys[1]] if m.lower() in text_lower]

            if pole_a_found and pole_b_found:
                results.append({
                    "id": str(uuid.uuid4()),
                    "ad_id": ad_id,
                    "tension_name": tension_name,
                    "pole_a_markers": pole_a_found,
                    "pole_b_markers": pole_b_found,
                    "confidence": self.CONFIDENCE,
                    "confidence_basis": self.CONFIDENCE_BASIS,
                })

        return results


# ===================================================================
# Urgency Detector
# ===================================================================

def detect_urgency(text: str) -> dict:
    """Detect urgency markers in text."""
    if not text:
        return {"has_urgency": False, "markers_found": []}

    text_lower = text.lower()
    found = []
    for marker in URGENCY_MARKERS:
        if re.search(marker, text_lower):
            found.append(marker)

    return {
        "has_urgency": len(found) > 0,
        "markers_found": found,
        "urgency_density": round(len(found) / max(len(text.split()), 1), 4),
    }


# ===================================================================
# Main Scoring Function
# ===================================================================

def compute_all_scores(
    transcript: str,
    ocr_text: str,
    claims: list[dict],
    proofs: list[dict],
    visual_analysis: dict,
    ad_id: str = "",
) -> dict:
    """
    Compute all deterministic scores for a single ad.

    Args:
        transcript: Full transcript text.
        ocr_text: Concatenated OCR text from visual analysis.
        claims: List of validated claim dicts from extractor.
        proofs: List of validated proof dicts from extractor.
        visual_analysis: Visual analysis dict from Gemini Vision.
        ad_id: Ad identifier.

    Returns:
        Dict with all computed scores.
    """
    combined_text = f"{transcript} {ocr_text}".strip()

    # Mechanism Explicitness
    mech_scorer = MechanismExplicitnessScorer()
    mechanism_explicitness = mech_scorer.compute_explicitness(combined_text)
    missing_mechanism = mechanism_explicitness < 0.2

    # Proof Strength (score each proof)
    proof_scorer = ProofStrengthScorer()
    proof_scores = []
    for proof in proofs:
        strength = proof_scorer.compute_strength(proof)
        specificity = proof_scorer.compute_specificity_level(
            proof.get("specificity_cues", {})
        )
        proof["strength"] = strength
        proof["specificity_level"] = specificity
        proof_scores.append({
            "proof_id": proof.get("id", ""),
            "strength": strength,
            "specificity_level": specificity,
        })

    # Average proof strength
    avg_proof_strength = (
        round(sum(ps["strength"] for ps in proof_scores) / len(proof_scores), 4)
        if proof_scores else 0.0
    )

    # Proof-to-Claim Ratio
    proof_to_claim_ratio = (
        round(len(proofs) / len(claims), 3) if claims else None
    )

    # Tension Detection
    tension_detector = TensionDetector()
    tensions = tension_detector.detect_tensions(combined_text, ad_id)

    # Urgency Detection
    urgency = detect_urgency(combined_text)

    # Hook archetype (from visual analysis)
    cross_frame = visual_analysis.get("cross_frame_analysis", {})
    hook_archetype = cross_frame.get("hook_type", "unknown")
    hook_confidence = cross_frame.get("hook_type_confidence", 0.0)

    # Classify proof strategy
    proof_types_used = list(set(p.get("primitive_type", "") for p in proofs))
    source_classes_used = list(set(p.get("source_class", "") for p in proofs))

    # Compute overall persuasion score (composite)
    persuasion_score = _compute_persuasion_score(
        mechanism_explicitness=mechanism_explicitness,
        avg_proof_strength=avg_proof_strength,
        proof_to_claim_ratio=proof_to_claim_ratio,
        num_claims=len(claims),
        num_proofs=len(proofs),
        num_tensions=len(tensions),
        has_urgency=urgency["has_urgency"],
    )

    return {
        "mechanism_explicitness": mechanism_explicitness,
        "missing_mechanism_flag": missing_mechanism,
        "proof_scores": proof_scores,
        "avg_proof_strength": avg_proof_strength,
        "proof_to_claim_ratio": proof_to_claim_ratio,
        "tensions": tensions,
        "urgency": urgency,
        "hook_archetype": hook_archetype,
        "hook_archetype_confidence": hook_confidence,
        "proof_types_used": proof_types_used,
        "source_classes_used": source_classes_used,
        "persuasion_score": persuasion_score,
        "format": cross_frame.get("format", "unknown"),
        "production_quality": cross_frame.get("production_quality", "unknown"),
        "overall_tone": cross_frame.get("overall_tone", "unknown"),
        "pacing": cross_frame.get("pacing", "unknown"),
    }


def _compute_persuasion_score(
    mechanism_explicitness: float,
    avg_proof_strength: float,
    proof_to_claim_ratio: float | None,
    num_claims: int,
    num_proofs: int,
    num_tensions: int,
    has_urgency: bool,
) -> float:
    """
    Compute a composite persuasion effectiveness score (0-100).

    Weighted formula:
      - Mechanism clarity: 20%
      - Proof strength: 25%
      - Claim coverage: 15%
      - Proof-to-claim balance: 15%
      - Tension resolution: 15%
      - Urgency: 10%
    """
    # Mechanism clarity (0-1)
    mech = mechanism_explicitness

    # Proof strength (0-1)
    proof = avg_proof_strength

    # Claim density (diminishing returns, cap at 8 claims)
    claim_density = min(num_claims / 8.0, 1.0) if num_claims > 0 else 0.0

    # Proof coverage (ratio capped at 2.0 for scoring)
    if proof_to_claim_ratio is not None:
        coverage = min(proof_to_claim_ratio / 2.0, 1.0)
    else:
        coverage = 0.0

    # Tension usage (having tensions is good - shows narrative depth)
    tension_score = min(num_tensions / 3.0, 1.0)

    # Urgency (binary bonus)
    urgency_score = 1.0 if has_urgency else 0.0

    composite = (
        0.20 * mech
        + 0.25 * proof
        + 0.15 * claim_density
        + 0.15 * coverage
        + 0.15 * tension_score
        + 0.10 * urgency_score
    )

    return round(composite * 100, 1)
