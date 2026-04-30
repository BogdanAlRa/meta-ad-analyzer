"""
Adversarial Validation module (Pass 4 equivalent).

Sends extracted claims and proofs back through Gemini with an adversarial
prompt to identify conflicts, contradictions, and unsupported assertions.

Only used in "deep" analysis mode to keep standard mode cheaper.

Ported from meta-ads-intelligence/backend/app/pipeline/pass4_validation.py
"""

import json
import logging

import google.generativeai as genai

logger = logging.getLogger(__name__)

ADVERSARIAL_VALIDATION_PROMPT = """You are an adversarial validator. Your job is to find problems with previously extracted claims and proofs from a video advertisement.

Given the ORIGINAL SOURCE TEXT and the EXTRACTED DATA below, identify:
1. Claims that are NOT actually supported by the source text
2. Claims that contradict each other
3. Proofs that do not actually support the claims they appear next to
4. Quotes that are paraphrased rather than verbatim from the source
5. Claims or proofs where confidence seems inflated

ORIGINAL SOURCE TEXT:
---
{original_text}
---

EXTRACTED CLAIMS:
{claims_json}

EXTRACTED PROOFS:
{proofs_json}

Return a JSON object with:
{{
  "flagged_claims": [
    {{
      "claim_id": "...",
      "issue_type": "not_in_source|contradiction|inflated_confidence|paraphrased",
      "explanation": "...",
      "conflicting_claim_id": null
    }}
  ],
  "flagged_proofs": [
    {{
      "proof_id": "...",
      "issue_type": "not_in_source|does_not_support|inflated_confidence|paraphrased",
      "explanation": "..."
    }}
  ],
  "contradictions": [
    {{
      "claim_id_a": "...",
      "claim_id_b": "...",
      "explanation": "..."
    }}
  ]
}}

Be thorough but fair. Only flag items with clear issues.
If everything looks correct, return empty lists."""


async def validate_extraction(
    claims: list[dict],
    proofs: list[dict],
    source_text: str,
    gemini_api_key: str,
    ad_id: str = "",
) -> dict:
    """
    Run adversarial validation on extracted claims and proofs.

    When issues are found, affected items have confidence_basis
    downgraded to "conflict_present".

    Args:
        claims: List of claim dicts.
        proofs: List of proof dicts.
        source_text: Original combined source text.
        gemini_api_key: Gemini API key.
        ad_id: Ad identifier for logging.

    Returns:
        Dict with:
          - updated_claims: claims with confidence_basis adjusted
          - updated_proofs: proofs with confidence_basis adjusted
          - validation_report: full validation details
          - total_flags: count of all issues found
    """
    if not claims and not proofs:
        return _empty_result(claims, proofs)

    if not source_text or not source_text.strip():
        return _empty_result(claims, proofs)

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    # Build compact representations for the prompt
    claims_compact = [
        {
            "id": c.get("id", ""),
            "claim_text": c.get("claim_text", ""),
            "claim_type": c.get("claim_type", ""),
            "confidence": c.get("confidence", 0.0),
        }
        for c in claims
    ]

    proofs_compact = [
        {
            "id": p.get("id", ""),
            "primitive_type": p.get("primitive_type", ""),
            "instance_quote": p.get("instance_quote", ""),
            "confidence": p.get("confidence", 0.0),
        }
        for p in proofs
    ]

    prompt = ADVERSARIAL_VALIDATION_PROMPT.format(
        original_text=source_text,
        claims_json=json.dumps(claims_compact, indent=2),
        proofs_json=json.dumps(proofs_compact, indent=2),
    )

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        validation_report = json.loads(response.text)
    except Exception as e:
        logger.error(f"[{ad_id}] Adversarial validation failed: {e}")
        return _empty_result(claims, proofs)

    # Collect flagged IDs
    flagged_claim_ids = set()
    flagged_proof_ids = set()

    for flagged in validation_report.get("flagged_claims", []):
        cid = flagged.get("claim_id", "")
        if cid:
            flagged_claim_ids.add(cid)
        conflict_id = flagged.get("conflicting_claim_id")
        if conflict_id:
            flagged_claim_ids.add(conflict_id)

    for flagged in validation_report.get("flagged_proofs", []):
        pid = flagged.get("proof_id", "")
        if pid:
            flagged_proof_ids.add(pid)

    for contradiction in validation_report.get("contradictions", []):
        for key in ("claim_id_a", "claim_id_b"):
            cid = contradiction.get(key, "")
            if cid:
                flagged_claim_ids.add(cid)

    # Update confidence_basis for flagged items
    updated_claims = []
    for claim in claims:
        c = dict(claim)
        if c.get("id") in flagged_claim_ids:
            c["confidence_basis"] = "conflict_present"
        updated_claims.append(c)

    updated_proofs = []
    for proof in proofs:
        p = dict(proof)
        if p.get("id") in flagged_proof_ids:
            p["confidence_basis"] = "conflict_present"
        updated_proofs.append(p)

    total_flags = len(flagged_claim_ids) + len(flagged_proof_ids)

    logger.info(
        f"[{ad_id}] Validation: {total_flags} flags "
        f"({len(flagged_claim_ids)} claims, {len(flagged_proof_ids)} proofs, "
        f"{len(validation_report.get('contradictions', []))} contradictions)"
    )

    return {
        "updated_claims": updated_claims,
        "updated_proofs": updated_proofs,
        "validation_report": validation_report,
        "total_flags": total_flags,
    }


def _empty_result(claims: list[dict], proofs: list[dict]) -> dict:
    return {
        "updated_claims": list(claims),
        "updated_proofs": list(proofs),
        "validation_report": {
            "flagged_claims": [],
            "flagged_proofs": [],
            "contradictions": [],
        },
        "total_flags": 0,
    }
