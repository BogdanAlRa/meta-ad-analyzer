"""
Report Generation module.

Generates a comprehensive Markdown analysis report combining all
pipeline outputs. Uses Gemini for the strategic synthesis section.
"""

import json
import logging
from datetime import datetime, timezone

import google.generativeai as genai

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a senior creative strategist analyzing a batch of video ads for the brand "{brand_name}".

Below is the structured analysis data for {num_ads} ads. Generate a strategic synthesis report that covers:

1. **Hook Strategy Patterns**: What opening strategies dominate? Which seem most effective based on proof strength and claim density?

2. **Persuasion Architecture**: How do the ads build their case? What's the typical claims-to-proofs ratio? Where is evidence strong vs. weak?

3. **Common Claims & Proof Gaps**: What claims appear repeatedly? Which claims lack adequate proof support?

4. **Tensions & Narrative Depth**: What cognitive tensions are being leveraged? Are they being resolved or left open?

5. **Production Patterns**: What formats, pacing, and tones are being used? What visual patterns repeat?

6. **Strategic Recommendations**: Based on the data, what should this brand do more of, less of, and try new?

Be data-driven. Reference specific scores, claim types, and proof strategies.
Write in a direct, analytical tone. No fluff.

AD ANALYSIS DATA:
{analysis_data}
"""


async def generate_report(
    brand_name: str,
    all_analyses: list[dict],
    gemini_api_key: str,
) -> str:
    """
    Generate a comprehensive Markdown analysis report.

    Combines per-ad analysis with a cross-ad strategic synthesis.

    Args:
        brand_name: The brand being analyzed.
        all_analyses: List of complete per-ad analysis dicts.
        gemini_api_key: Gemini API key.

    Returns:
        Markdown report string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    num_ads = len(all_analyses)

    report_parts = []

    # =====================================================================
    # Header
    # =====================================================================
    report_parts.append(f"# Meta Ad Video Analysis Report: {brand_name}")
    report_parts.append(f"\nGenerated: {now}")
    report_parts.append(f"Ads analyzed: {num_ads}")
    report_parts.append("")

    # =====================================================================
    # Executive Summary (scores overview)
    # =====================================================================
    report_parts.append("## Executive Summary\n")

    avg_persuasion = _safe_avg([a.get("scores", {}).get("persuasion_score", 0) for a in all_analyses])
    avg_mechanism = _safe_avg([a.get("scores", {}).get("mechanism_explicitness", 0) for a in all_analyses])
    avg_proof = _safe_avg([a.get("scores", {}).get("avg_proof_strength", 0) for a in all_analyses])
    total_claims = sum(len(a.get("claims", [])) for a in all_analyses)
    total_proofs = sum(len(a.get("proofs", [])) for a in all_analyses)

    report_parts.append(f"| Metric | Value |")
    report_parts.append(f"|--------|-------|")
    report_parts.append(f"| Ads Analyzed | {num_ads} |")
    report_parts.append(f"| Avg. Persuasion Score | {avg_persuasion:.1f}/100 |")
    report_parts.append(f"| Avg. Mechanism Explicitness | {avg_mechanism:.2f} |")
    report_parts.append(f"| Avg. Proof Strength | {avg_proof:.2f} |")
    report_parts.append(f"| Total Claims Extracted | {total_claims} |")
    report_parts.append(f"| Total Proof Elements | {total_proofs} |")
    report_parts.append("")

    # Hook type distribution
    hook_counts = {}
    for a in all_analyses:
        hook = a.get("scores", {}).get("hook_archetype", "unknown")
        hook_counts[hook] = hook_counts.get(hook, 0) + 1

    if hook_counts:
        report_parts.append("### Hook Type Distribution\n")
        report_parts.append("| Hook Type | Count |")
        report_parts.append("|-----------|-------|")
        for hook, count in sorted(hook_counts.items(), key=lambda x: -x[1]):
            report_parts.append(f"| {hook} | {count} |")
        report_parts.append("")

    # =====================================================================
    # Per-Ad Analysis
    # =====================================================================
    report_parts.append("## Individual Ad Analysis\n")

    for i, analysis in enumerate(all_analyses, 1):
        ad_info = analysis.get("ad_info", {})
        scores = analysis.get("scores", {})
        claims = analysis.get("claims", [])
        proofs = analysis.get("proofs", [])
        transcript = analysis.get("transcript", {})
        visual = analysis.get("visual_analysis", {})
        cross_frame = visual.get("cross_frame_analysis", {})

        ad_id = ad_info.get("ad_id", f"ad_{i}")
        ad_url = ad_info.get("ad_url", "")

        report_parts.append(f"### Ad {i}: {ad_id}")
        if ad_url:
            report_parts.append(f"URL: {ad_url}")
        report_parts.append("")

        # Scores
        report_parts.append(f"**Persuasion Score:** {scores.get('persuasion_score', 0):.1f}/100")
        report_parts.append(f"**Hook Type:** {scores.get('hook_archetype', 'unknown')} ({scores.get('hook_archetype_confidence', 0):.0%} confidence)")
        report_parts.append(f"**Format:** {scores.get('format', 'unknown')} | **Tone:** {scores.get('overall_tone', 'unknown')} | **Pacing:** {scores.get('pacing', 'unknown')}")
        report_parts.append(f"**Mechanism Explicitness:** {scores.get('mechanism_explicitness', 0):.2f}")
        if scores.get("missing_mechanism_flag"):
            report_parts.append("**WARNING: Missing mechanism** - Claims made without explaining how the product works")
        report_parts.append(f"**Avg. Proof Strength:** {scores.get('avg_proof_strength', 0):.2f}")
        report_parts.append(f"**Proof-to-Claim Ratio:** {scores.get('proof_to_claim_ratio', 'N/A')}")
        report_parts.append("")

        # Transcript
        transcript_text = transcript.get("transcript", "")
        if transcript_text:
            preview = transcript_text[:300]
            if len(transcript_text) > 300:
                preview += "..."
            report_parts.append(f"**Transcript:** _{preview}_")
            report_parts.append("")

        # Claims
        if claims:
            report_parts.append(f"**Claims ({len(claims)}):**\n")
            for j, claim in enumerate(claims, 1):
                conf_flag = " [CONFLICT]" if claim.get("confidence_basis") == "conflict_present" else ""
                report_parts.append(
                    f'{j}. **[{claim.get("claim_type", "?")}]** '
                    f'"{claim.get("claim_text", "")}" '
                    f'(scope: {claim.get("claim_scope", "?")}, '
                    f'conf: {claim.get("confidence", 0):.0%}{conf_flag})'
                )
            report_parts.append("")

        # Proofs
        if proofs:
            report_parts.append(f"**Proof Elements ({len(proofs)}):**\n")
            for j, proof in enumerate(proofs, 1):
                strength = proof.get("strength", 0) or 0
                strength_label = (
                    "STRONG" if strength >= 0.7
                    else "MODERATE" if strength >= 0.4
                    else "WEAK"
                )
                report_parts.append(
                    f'{j}. **[{proof.get("primitive_type", "?")}]** '
                    f'"{proof.get("instance_quote", "")}" '
                    f'(source: {proof.get("source_class", "?")}, '
                    f'strength: {strength:.2f} {strength_label})'
                )
            report_parts.append("")

        # Tensions
        tensions = scores.get("tensions", [])
        if tensions:
            report_parts.append(f"**Cognitive Tensions ({len(tensions)}):**\n")
            for tension in tensions:
                report_parts.append(
                    f'- **{tension.get("tension_name", "?")}**: '
                    f'Pole A markers: {tension.get("pole_a_markers", [])} vs '
                    f'Pole B markers: {tension.get("pole_b_markers", [])}'
                )
            report_parts.append("")

        # Urgency
        urgency = scores.get("urgency", {})
        if urgency.get("has_urgency"):
            report_parts.append(f"**Urgency markers found:** {', '.join(urgency.get('markers_found', []))}")
            report_parts.append("")

        report_parts.append("---\n")

    # =====================================================================
    # Strategic Synthesis (LLM-generated)
    # =====================================================================
    synthesis = await _generate_synthesis(brand_name, all_analyses, gemini_api_key)
    if synthesis:
        report_parts.append("## Strategic Synthesis\n")
        report_parts.append(synthesis)
        report_parts.append("")

    # =====================================================================
    # Footer
    # =====================================================================
    report_parts.append("---")
    report_parts.append(
        "*Report generated by Meta Ad Video Analyzer on Apify. "
        "Powered by Gemini 2.0 Flash + deterministic scoring pipeline.*"
    )

    return "\n".join(report_parts)


async def _generate_synthesis(
    brand_name: str,
    all_analyses: list[dict],
    gemini_api_key: str,
) -> str:
    """Generate the strategic synthesis section using Gemini."""
    # Build a compact summary of the data for the prompt
    compact_data = []
    for i, analysis in enumerate(all_analyses, 1):
        scores = analysis.get("scores", {})
        claims = analysis.get("claims", [])
        proofs = analysis.get("proofs", [])
        compact_data.append({
            "ad_number": i,
            "persuasion_score": scores.get("persuasion_score", 0),
            "hook_type": scores.get("hook_archetype", "unknown"),
            "format": scores.get("format", "unknown"),
            "mechanism_explicitness": scores.get("mechanism_explicitness", 0),
            "avg_proof_strength": scores.get("avg_proof_strength", 0),
            "proof_to_claim_ratio": scores.get("proof_to_claim_ratio"),
            "claim_types": [c.get("claim_type") for c in claims],
            "claim_scopes": [c.get("claim_scope") for c in claims],
            "proof_types": [p.get("primitive_type") for p in proofs],
            "source_classes": [p.get("source_class") for p in proofs],
            "tensions": [t.get("tension_name") for t in scores.get("tensions", [])],
            "has_urgency": scores.get("urgency", {}).get("has_urgency", False),
            "tone": scores.get("overall_tone", "unknown"),
            "pacing": scores.get("pacing", "unknown"),
        })

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    prompt = SYNTHESIS_PROMPT.format(
        brand_name=brand_name,
        num_ads=len(all_analyses),
        analysis_data=json.dumps(compact_data, indent=2),
    )

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.3),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Synthesis generation failed: {e}")
        return "*Strategic synthesis could not be generated.*"


def _safe_avg(values: list[float]) -> float:
    valid = [v for v in values if v is not None and v > 0]
    return sum(valid) / len(valid) if valid else 0.0
