"""
Claim & Proof Extraction module (Pass 2 equivalent).

Uses Gemini 2.0 Flash for structured extraction of claims and proof
primitives from transcript and OCR text.

HARD RULE: All claim_text and instance_quote values must be exact quotes
from the source text. No paraphrasing allowed.

Ported from meta-ads-intelligence/backend/app/pipeline/pass2_extraction.py
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

import google.generativeai as genai

from .vocabularies import (
    CLAIM_TYPES,
    CLAIM_SCOPES,
    POLARITY_TYPES,
    QUANTIFICATION_TYPES,
    CONFIDENCE_BASIS_LEVELS,
    PROOF_PRIMITIVE_TYPES,
    PROOF_SOURCE_CLASSES,
)

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_PROMPT = """You are a claim extraction system. Extract all claims from the provided source text.

RULES:
1. claim_text MUST be an exact quote from the source text. Do not paraphrase.
2. If you cannot find a direct quote, do NOT create the claim.
3. Every claim must have an evidence_pointer with source_type.
4. Use ONLY these controlled vocabularies:

claim_type: {claim_types}
claim_scope: {claim_scopes}
polarity: {polarity_types}
quantification: {quantification_types}
confidence_basis: {confidence_basis}

SOURCE TEXT:
---TRANSCRIPT---
{transcript}
---OCR TEXT---
{ocr_text}
---END---

Return a JSON object with a single key "claims" containing a list of claim objects.
Each claim object must have:
  - claim_text: str (exact quote from source)
  - canonical_form: str (normalized/simplified version)
  - claim_type: str (from vocabulary)
  - claim_scope: str (from vocabulary)
  - polarity: str (from vocabulary)
  - quantification: str (from vocabulary)
  - confidence: float (0.0-1.0)
  - confidence_basis: str (from vocabulary)
  - source_type: str ("transcript" or "ocr_text")
"""

PROOF_EXTRACTION_PROMPT = """You are a proof primitive extraction system. Extract all proof elements from the provided source text.

RULES:
1. instance_quote MUST be an exact quote from the source text. Do not paraphrase.
2. If you cannot find a direct quote, do NOT create the proof.
3. Use ONLY these controlled vocabularies:

primitive_type: {proof_types}
source_class: {source_classes}
confidence_basis: {confidence_basis}

SOURCE TEXT:
---TRANSCRIPT---
{transcript}
---OCR TEXT---
{ocr_text}
---END---

Return a JSON object with a single key "proofs" containing a list of proof objects.
Each proof object must have:
  - primitive_type: str (from vocabulary)
  - instance_quote: str (exact quote from source)
  - source_class: str (from vocabulary)
  - confidence: float (0.0-1.0)
  - confidence_basis: str (from vocabulary)
  - specificity_cues: object with bool fields:
      has_numbers, has_baseline, has_timeframe, has_sample_size,
      has_method, has_link_or_citation, has_named_institution,
      has_named_person_credentials
  - penalty_flags: object with bool fields:
      numbers_without_context, before_after_without_controls,
      testimonial_without_specifics, authority_without_credentials,
      comparison_without_named_alternative
  - source_type: str ("transcript" or "ocr_text")
"""


async def extract_claims_and_proofs(
    transcript: str,
    ocr_text: str,
    gemini_api_key: str,
    ad_id: str = "",
) -> dict:
    """
    Extract claims and proof primitives from transcript and OCR text.

    Uses Gemini 2.0 Flash for structured extraction, then validates
    that all quotes actually exist in the source text.

    Args:
        transcript: Full audio transcript.
        ocr_text: Concatenated text from visual overlays.
        gemini_api_key: Gemini API key.
        ad_id: Identifier for this ad (for logging/IDs).

    Returns:
        Dict with:
          - claims: list of validated claim dicts
          - proofs: list of validated proof dicts
          - source_text: combined source text used
    """
    transcript = transcript or ""
    ocr_text = ocr_text or ""
    combined_text = f"{transcript} {ocr_text}".strip()

    if not combined_text:
        logger.info(f"[{ad_id}] No source text for extraction")
        return {"claims": [], "proofs": [], "source_text": ""}

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    # Extract claims
    claims = await _extract_claims(model, transcript, ocr_text, combined_text, ad_id)

    # Extract proofs
    proofs = await _extract_proofs(model, transcript, ocr_text, combined_text, ad_id)

    logger.info(
        f"[{ad_id}] Extraction complete: {len(claims)} claims, {len(proofs)} proofs"
    )

    return {
        "claims": claims,
        "proofs": proofs,
        "source_text": combined_text,
    }


async def _extract_claims(
    model,
    transcript: str,
    ocr_text: str,
    combined_text: str,
    ad_id: str,
) -> list[dict]:
    """Extract and validate claims."""
    prompt = CLAIM_EXTRACTION_PROMPT.format(
        claim_types=", ".join(CLAIM_TYPES),
        claim_scopes=", ".join(CLAIM_SCOPES),
        polarity_types=", ".join(POLARITY_TYPES),
        quantification_types=", ".join(QUANTIFICATION_TYPES),
        confidence_basis=", ".join(CONFIDENCE_BASIS_LEVELS),
        transcript=transcript,
        ocr_text=ocr_text,
    )

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        result = json.loads(response.text)
        raw_claims = result.get("claims", [])
    except Exception as e:
        logger.error(f"[{ad_id}] Claim extraction failed: {e}")
        return []

    # Validate each claim
    validated = []
    for raw in raw_claims:
        claim = _validate_claim(raw, combined_text, ad_id)
        if claim is not None:
            validated.append(claim)

    logger.info(f"[{ad_id}] Claims: {len(raw_claims)} extracted, {len(validated)} validated")
    return validated


async def _extract_proofs(
    model,
    transcript: str,
    ocr_text: str,
    combined_text: str,
    ad_id: str,
) -> list[dict]:
    """Extract and validate proofs."""
    prompt = PROOF_EXTRACTION_PROMPT.format(
        proof_types=", ".join(PROOF_PRIMITIVE_TYPES),
        source_classes=", ".join(PROOF_SOURCE_CLASSES),
        confidence_basis=", ".join(CONFIDENCE_BASIS_LEVELS),
        transcript=transcript,
        ocr_text=ocr_text,
    )

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        result = json.loads(response.text)
        raw_proofs = result.get("proofs", [])
    except Exception as e:
        logger.error(f"[{ad_id}] Proof extraction failed: {e}")
        return []

    # Validate each proof
    validated = []
    for raw in raw_proofs:
        proof = _validate_proof(raw, combined_text, ad_id)
        if proof is not None:
            validated.append(proof)

    logger.info(f"[{ad_id}] Proofs: {len(raw_proofs)} extracted, {len(validated)} validated")
    return validated


def _validate_claim(raw: dict, combined_text: str, ad_id: str) -> dict | None:
    """
    Validate a single claim. Hard rule: claim_text must be a direct quote.
    """
    claim_text = raw.get("claim_text", "").strip()
    if not claim_text:
        return None

    # Verify the quote exists in source text (case-insensitive)
    if claim_text.lower() not in combined_text.lower():
        logger.debug(f"[{ad_id}] Claim rejected (not in source): {claim_text[:60]}")
        return None

    # Validate vocabularies with safe defaults
    claim_type = raw.get("claim_type", "descriptive")
    if claim_type not in CLAIM_TYPES:
        claim_type = "descriptive"

    claim_scope = raw.get("claim_scope", "product_performance")
    if claim_scope not in CLAIM_SCOPES:
        claim_scope = "product_performance"

    polarity = raw.get("polarity", "positive")
    if polarity not in POLARITY_TYPES:
        polarity = "positive"

    quantification = raw.get("quantification", "vague")
    if quantification not in QUANTIFICATION_TYPES:
        quantification = "vague"

    confidence_basis = raw.get("confidence_basis", "direct_quote")
    if confidence_basis not in CONFIDENCE_BASIS_LEVELS:
        confidence_basis = "direct_quote"

    return {
        "id": str(uuid.uuid4()),
        "ad_id": ad_id,
        "claim_text": claim_text,
        "canonical_form": raw.get("canonical_form", claim_text),
        "claim_type": claim_type,
        "claim_scope": claim_scope,
        "polarity": polarity,
        "quantification": quantification,
        "confidence": min(max(float(raw.get("confidence", 0.5)), 0.0), 1.0),
        "confidence_basis": confidence_basis,
        "source_type": raw.get("source_type", "transcript"),
    }


def _validate_proof(raw: dict, combined_text: str, ad_id: str) -> dict | None:
    """
    Validate a single proof. Hard rule: instance_quote must be a direct quote.
    """
    instance_quote = raw.get("instance_quote", "").strip()
    if not instance_quote:
        return None

    # Verify the quote exists in source text (case-insensitive)
    if instance_quote.lower() not in combined_text.lower():
        logger.debug(f"[{ad_id}] Proof rejected (not in source): {instance_quote[:60]}")
        return None

    primitive_type = raw.get("primitive_type", "")
    if primitive_type not in PROOF_PRIMITIVE_TYPES:
        return None  # Cannot safely default proof type

    source_class = raw.get("source_class", "unknown")
    if source_class not in PROOF_SOURCE_CLASSES:
        source_class = "unknown"

    confidence_basis = raw.get("confidence_basis", "direct_quote")
    if confidence_basis not in CONFIDENCE_BASIS_LEVELS:
        confidence_basis = "direct_quote"

    # Build specificity cues
    raw_cues = raw.get("specificity_cues", {})
    specificity_cues = {
        "has_numbers": bool(raw_cues.get("has_numbers", False)),
        "has_baseline": bool(raw_cues.get("has_baseline", False)),
        "has_timeframe": bool(raw_cues.get("has_timeframe", False)),
        "has_sample_size": bool(raw_cues.get("has_sample_size", False)),
        "has_method": bool(raw_cues.get("has_method", False)),
        "has_link_or_citation": bool(raw_cues.get("has_link_or_citation", False)),
        "has_named_institution": bool(raw_cues.get("has_named_institution", False)),
        "has_named_person_credentials": bool(raw_cues.get("has_named_person_credentials", False)),
    }

    # Build penalty flags
    raw_penalties = raw.get("penalty_flags", {})
    penalty_flags = {
        "numbers_without_context": bool(raw_penalties.get("numbers_without_context", False)),
        "before_after_without_controls": bool(raw_penalties.get("before_after_without_controls", False)),
        "testimonial_without_specifics": bool(raw_penalties.get("testimonial_without_specifics", False)),
        "authority_without_credentials": bool(raw_penalties.get("authority_without_credentials", False)),
        "comparison_without_named_alternative": bool(raw_penalties.get("comparison_without_named_alternative", False)),
    }

    return {
        "id": str(uuid.uuid4()),
        "ad_id": ad_id,
        "primitive_type": primitive_type,
        "instance_quote": instance_quote,
        "source_class": source_class,
        "specificity_cues": specificity_cues,
        "penalty_flags": penalty_flags,
        "confidence": min(max(float(raw.get("confidence", 0.5)), 0.0), 1.0),
        "confidence_basis": confidence_basis,
        "source_type": raw.get("source_type", "transcript"),
        "strength": None,           # Computed in scorer
        "specificity_level": None,   # Computed in scorer
    }
