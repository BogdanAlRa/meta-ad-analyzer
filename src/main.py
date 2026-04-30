"""
Meta Ad Library Video Analyzer - Apify Actor

Main entry point. Orchestrates the full pipeline:
  1. Discover ads (manual URLs or Meta API)
  2. For each ad: download video, extract frames + audio
  3. Transcribe audio (Whisper API)
  4. Analyze frames visually (Gemini Vision)
  5. Extract claims & proofs (Gemini, constrained to direct quotes)
  6. Compute deterministic scores (mechanism, proof strength, tensions)
  7. [Deep mode] Adversarial validation
  8. Generate cross-ad strategic report

Architecture adapted from the Meta Ads Intelligence Platform
(5-pass pipeline) for serverless execution on Apify.
"""

import asyncio
import logging
import os
import shutil
import tempfile

from apify import Actor

from .ad_discovery import discover_ads
from .media_processor import process_ad_media
from .transcriber import transcribe_audio
from .visual_analyzer import analyze_frames_with_gemini, collect_ocr_text
from .extractor import extract_claims_and_proofs
from .scorer import compute_all_scores
from .validator import validate_extraction
from .report_generator import generate_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    async with Actor:
        # ---------------------------------------------------------------
        # 1. Read input
        # ---------------------------------------------------------------
        input_data = await Actor.get_input() or {}

        brand_input = input_data.get("brandInput", "")
        max_videos = input_data.get("numberOfVideos", 5)
        depth = input_data.get("analysisDepth", "standard")

        # API keys from environment variables (set by actor owner)
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        openai_key = os.environ.get("OPENAI_API_KEY", "")

        if not gemini_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not configured. "
                "Please contact the actor developer."
            )

        if not brand_input:
            raise ValueError(
                "Please provide a brand Ad Library link or brand name."
            )

        # Parse brand input to get the name for reporting
        from .ad_discovery import parse_brand_input
        parsed = parse_brand_input(brand_input)
        brand_name = parsed["name"]

        # Proxy configuration - auto-use residential proxies for ad discovery
        # to avoid Facebook rate limiting on datacenter IPs
        proxy_config = input_data.get("proxyConfiguration")
        proxy_url = None

        if proxy_config:
            # User-provided proxy
            try:
                proxy_url_list = await Actor.create_proxy_configuration(
                    actor_proxy_input=proxy_config
                )
                if proxy_url_list:
                    proxy_url = await proxy_url_list.new_url()
                    Actor.log.info("Using user-provided proxy configuration")
            except Exception as e:
                Actor.log.warning(f"Could not create user proxy config: {e}")

        if not proxy_url:
            # Auto-configure residential proxies for ad discovery
            try:
                proxy_url_list = await Actor.create_proxy_configuration(
                    actor_proxy_input={
                        "useApifyProxy": True,
                        "apifyProxyGroups": ["RESIDENTIAL"],
                    }
                )
                if proxy_url_list:
                    proxy_url = await proxy_url_list.new_url()
                    Actor.log.info("Using auto-configured residential proxy")
            except Exception as e:
                Actor.log.warning(
                    f"Could not auto-configure residential proxy: {e}. "
                    "Proceeding without proxy (may hit rate limits)."
                )

        Actor.log.info(
            f"Starting analysis: brand='{brand_name}', "
            f"max_videos={max_videos}, depth={depth}"
        )

        # ---------------------------------------------------------------
        # 2. Discover video ads
        # ---------------------------------------------------------------
        Actor.log.info("Discovering video ads from Ad Library...")

        try:
            ads = await discover_ads(
                brand_input=brand_input,
                max_videos=max_videos,
                proxy_url=proxy_url,
            )
        except Exception as e:
            Actor.log.error(f"Ad discovery failed: {e}")
            raise

        if not ads:
            Actor.log.warning("No video ads found. Check your inputs.")
            kv_store = await Actor.open_key_value_store()
            await kv_store.set_value(
                "report",
                f"# No Video Ads Found\n\nNo video ads were found for "
                f"'{brand_name}' on the Meta Ad Library.",
                content_type="text/markdown",
            )
            return

        # Update brand name from discovered ads (API response has actual page name)
        for ad in ads:
            pn = ad.get("page_name", "")
            if pn and pn != "Unknown Brand":
                brand_name = pn
                break

        Actor.log.info(f"Found {len(ads)} video ads to analyze")

        # ---------------------------------------------------------------
        # 3. Process each ad
        # ---------------------------------------------------------------
        all_analyses = []
        processed = 0
        failed = 0

        for i, ad_info in enumerate(ads):
            ad_id = ad_info.get("ad_id", f"unknown_{i}")
            Actor.log.info(
                f"[{i + 1}/{len(ads)}] Processing ad {ad_id}..."
            )

            tmp_dir = tempfile.mkdtemp(prefix=f"ad_{ad_id[:12]}_")

            try:
                analysis = await _process_single_ad(
                    ad_info=ad_info,
                    work_dir=tmp_dir,
                    brand_name=brand_name,
                    depth=depth,
                    gemini_key=gemini_key,
                    openai_key=openai_key,
                    proxy_url=proxy_url,
                )

                if analysis.get("error"):
                    Actor.log.warning(
                        f"[{ad_id}] Partial failure: {analysis['error']}"
                    )
                    failed += 1
                else:
                    processed += 1

                all_analyses.append(analysis)

                # Push to dataset immediately (streaming output)
                await Actor.push_data(_make_dataset_item(analysis))

                # Charge per ad analyzed (Pay-Per-Event)
                try:
                    await Actor.charge(event_name="ad-analyzed", count=1)
                except Exception:
                    pass  # charge() not available in local testing

                Actor.log.info(
                    f"[{ad_id}] Done. Score: "
                    f"{analysis.get('scores', {}).get('persuasion_score', 0):.1f}/100"
                )

            except Exception as e:
                Actor.log.error(f"[{ad_id}] Failed: {e}")
                failed += 1
                all_analyses.append({
                    "ad_info": ad_info,
                    "error": str(e),
                })

            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # ---------------------------------------------------------------
        # 4. Generate cross-ad report
        # ---------------------------------------------------------------
        Actor.log.info("Generating strategic report...")

        successful_analyses = [a for a in all_analyses if not a.get("error")]

        if successful_analyses:
            report_md = await generate_report(
                brand_name=brand_name,
                all_analyses=successful_analyses,
                gemini_api_key=gemini_key,
            )

            # Save report to key-value store
            kv_store = await Actor.open_key_value_store()
            await kv_store.set_value(
                "report",
                report_md,
                content_type="text/markdown",
            )

            # Also save as a dataset item
            await Actor.push_data({
                "_type": "report",
                "brand_name": brand_name,
                "ads_analyzed": len(successful_analyses),
                "ads_failed": failed,
                "report_markdown": report_md,
            })

            # Charge for report generation
            try:
                await Actor.charge(event_name="report-generated", count=1)
            except Exception:
                pass

        # ---------------------------------------------------------------
        # 5. Summary
        # ---------------------------------------------------------------
        Actor.log.info(
            f"Analysis complete. "
            f"Processed: {processed}/{len(ads)}, Failed: {failed}"
        )


async def _process_single_ad(
    ad_info: dict,
    work_dir: str,
    brand_name: str,
    depth: str,
    gemini_key: str,
    openai_key: str,
    proxy_url: str | None,
) -> dict:
    """
    Process a single ad through the full analysis pipeline.

    Returns a complete analysis dict.
    """
    ad_id = ad_info.get("ad_id", "unknown")

    # Step 2: Download video + extract frames + audio
    media = await process_ad_media(
        ad_info=ad_info,
        work_dir=work_dir,
        analysis_depth=depth,
        proxy_url=proxy_url,
    )

    if media.get("error") and not media.get("frames"):
        return {
            "ad_info": ad_info,
            "error": media["error"],
        }

    # Step 3: Transcribe audio
    transcription = await transcribe_audio(
        audio_path=media.get("audio_path"),
        openai_api_key=openai_key,
    )

    # Step 4: Visual analysis with Gemini
    visual_analysis = await analyze_frames_with_gemini(
        frames=media.get("frames", []),
        gemini_api_key=gemini_key,
        ad_context={
            "brand_name": brand_name,
            "ad_title": ad_info.get("ad_title", ""),
            "ad_body": ad_info.get("ad_body", ""),
        },
    )

    # Collect OCR text from visual analysis
    ocr_text = collect_ocr_text(visual_analysis)

    # Step 5: Extract claims and proofs
    extraction = await extract_claims_and_proofs(
        transcript=transcription.get("transcript", ""),
        ocr_text=ocr_text,
        gemini_api_key=gemini_key,
        ad_id=ad_id,
    )

    claims = extraction.get("claims", [])
    proofs = extraction.get("proofs", [])
    source_text = extraction.get("source_text", "")

    # Step 6: Compute deterministic scores
    scores = compute_all_scores(
        transcript=transcription.get("transcript", ""),
        ocr_text=ocr_text,
        claims=claims,
        proofs=proofs,
        visual_analysis=visual_analysis,
        ad_id=ad_id,
    )

    # Step 7 (deep mode only): Adversarial validation
    if depth == "deep" and (claims or proofs):
        validation = await validate_extraction(
            claims=claims,
            proofs=proofs,
            source_text=source_text,
            gemini_api_key=gemini_key,
            ad_id=ad_id,
        )
        claims = validation.get("updated_claims", claims)
        proofs = validation.get("updated_proofs", proofs)
        scores["validation_flags"] = validation.get("total_flags", 0)
    else:
        scores["validation_flags"] = None

    return {
        "ad_info": ad_info,
        "transcript": transcription,
        "visual_analysis": visual_analysis,
        "claims": claims,
        "proofs": proofs,
        "scores": scores,
        "video_duration_s": media.get("video_duration_s"),
        "frames_analyzed": len(media.get("frames", [])),
        "error": None,
    }


def _make_dataset_item(analysis: dict) -> dict:
    """
    Flatten an analysis dict into a clean dataset item for Apify output.
    """
    ad_info = analysis.get("ad_info", {})
    scores = analysis.get("scores", {})
    claims = analysis.get("claims", [])
    proofs = analysis.get("proofs", [])
    transcript = analysis.get("transcript", {})
    visual = analysis.get("visual_analysis", {})
    cross_frame = visual.get("cross_frame_analysis", {})

    return {
        "_type": "ad_analysis",
        "ad_id": ad_info.get("ad_id", ""),
        "ad_url": ad_info.get("ad_url", ""),
        "brand_name": ad_info.get("page_name", ad_info.get("brand_name", "")),
        "delivery_start": ad_info.get("delivery_start", ""),

        # Scores
        "persuasion_score": scores.get("persuasion_score", 0),
        "mechanism_explicitness": scores.get("mechanism_explicitness", 0),
        "missing_mechanism_flag": scores.get("missing_mechanism_flag", False),
        "avg_proof_strength": scores.get("avg_proof_strength", 0),
        "proof_to_claim_ratio": scores.get("proof_to_claim_ratio"),

        # Hook & format
        "hook_archetype": scores.get("hook_archetype", "unknown"),
        "hook_confidence": scores.get("hook_archetype_confidence", 0),
        "format": scores.get("format", "unknown"),
        "production_quality": scores.get("production_quality", "unknown"),
        "overall_tone": scores.get("overall_tone", "unknown"),
        "pacing": scores.get("pacing", "unknown"),

        # Content
        "transcript": transcript.get("transcript", ""),
        "transcript_language": transcript.get("language", "unknown"),
        "video_duration_s": analysis.get("video_duration_s"),
        "frames_analyzed": analysis.get("frames_analyzed", 0),

        # Claims
        "claims_count": len(claims),
        "claims": [
            {
                "text": c.get("claim_text", ""),
                "type": c.get("claim_type", ""),
                "scope": c.get("claim_scope", ""),
                "confidence": c.get("confidence", 0),
                "flagged": c.get("confidence_basis") == "conflict_present",
            }
            for c in claims
        ],

        # Proofs
        "proofs_count": len(proofs),
        "proofs": [
            {
                "quote": p.get("instance_quote", ""),
                "type": p.get("primitive_type", ""),
                "source_class": p.get("source_class", ""),
                "strength": p.get("strength", 0),
                "flagged": p.get("confidence_basis") == "conflict_present",
            }
            for p in proofs
        ],

        # Tensions
        "tensions": [
            {
                "name": t.get("tension_name", ""),
                "pole_a": t.get("pole_a_markers", []),
                "pole_b": t.get("pole_b_markers", []),
            }
            for t in scores.get("tensions", [])
        ],

        # Urgency
        "has_urgency": scores.get("urgency", {}).get("has_urgency", False),
        "urgency_markers": scores.get("urgency", {}).get("markers_found", []),

        # Validation (deep mode)
        "validation_flags": scores.get("validation_flags"),

        # Visual analysis summary
        "visual_narrative": cross_frame.get("narrative_arc", ""),
        "hook_description": cross_frame.get("hook_description", ""),
        "brand_visibility": cross_frame.get("brand_visibility", ""),
        "cta_text": cross_frame.get("cta_text"),

        # Error
        "error": analysis.get("error"),
    }


if __name__ == "__main__":
    asyncio.run(main())
