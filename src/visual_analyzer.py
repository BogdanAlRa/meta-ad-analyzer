"""
Visual Analysis module.

Uses Gemini 2.0 Flash Vision to analyze keyframes.
Replaces the 10+ local ML models (YOLO, MediaPipe, PaddleOCR, etc.)
from the full Meta Ads Intelligence platform with a single vision API call.
"""

import base64
import json
import logging
from pathlib import Path

import google.generativeai as genai

logger = logging.getLogger(__name__)

VISUAL_ANALYSIS_PROMPT = """You are an expert video ad analyst. Analyze these keyframes from a video advertisement.

For each frame, provide a structured analysis. Then provide a cross-frame summary.

IMPORTANT: Be extremely precise and factual. Only describe what you can actually see.

Return a JSON object with this exact structure:
{
  "frames": [
    {
      "timestamp_s": <float>,
      "description": "<1-2 sentence description of what's happening>",
      "people": {
        "count": <int>,
        "faces_visible": <bool>,
        "direct_gaze_at_camera": <bool>,
        "emotions": ["<emotion1>", ...],
        "demographics_guess": "<brief, e.g. 'woman 30s' or 'diverse group'>"
      },
      "text_overlays": ["<exact text visible in frame>", ...],
      "objects": ["<object1>", "<object2>", ...],
      "product_visible": <bool>,
      "product_description": "<what the product looks like, if visible>",
      "setting": "<indoor/outdoor/studio/etc + brief description>",
      "colors": {
        "dominant": ["<color1>", "<color2>"],
        "brightness": "<dark/moderate/bright>",
        "saturation": "<muted/moderate/vivid>"
      },
      "visual_hierarchy": "<what draws the eye first>"
    }
  ],
  "cross_frame_analysis": {
    "hook_type": "<one of: direct_address, rapid_montage, problem_agitation, demonstration, social_proof, curiosity_gap, offer_led, before_after, other>",
    "hook_type_confidence": <float 0-1>,
    "hook_description": "<1 sentence explaining the hook strategy>",
    "pacing": "<slow/moderate/fast/rapid>",
    "scene_changes": <int, number of distinct scenes/cuts detected>,
    "narrative_arc": "<brief description of the visual story progression>",
    "production_quality": "<low/medium/high/professional>",
    "format": "<talking_head/product_demo/montage/testimonial/animation/ugc/lifestyle/other>",
    "brand_visibility": "<when and how the brand appears>",
    "cta_present": <bool>,
    "cta_text": "<call-to-action text if visible, else null>",
    "overall_tone": "<energetic/calm/urgent/aspirational/educational/emotional/humorous>"
  }
}

Analyze these frames carefully:"""


async def analyze_frames_with_gemini(
    frames: list[dict],
    gemini_api_key: str,
    ad_context: dict | None = None,
) -> dict:
    """
    Send keyframes to Gemini 2.0 Flash Vision for comprehensive analysis.

    Args:
        frames: List of dicts with "timestamp_s" and "path" keys.
        gemini_api_key: Gemini API key.
        ad_context: Optional dict with ad metadata (brand, title, body).

    Returns:
        Structured visual analysis dict.
    """
    if not frames:
        logger.warning("No frames to analyze")
        return _empty_visual_result()

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    # Build the prompt with frame images
    content_parts = [VISUAL_ANALYSIS_PROMPT]

    if ad_context:
        context_str = ""
        if ad_context.get("brand_name"):
            context_str += f"\nBrand: {ad_context['brand_name']}"
        if ad_context.get("ad_title"):
            context_str += f"\nAd Title: {ad_context['ad_title']}"
        if ad_context.get("ad_body"):
            context_str += f"\nAd Copy: {ad_context['ad_body'][:500]}"
        if context_str:
            content_parts.append(f"\nAd Context:{context_str}\n")

    # Add each frame as an image
    for frame in frames:
        frame_path = frame["path"]
        timestamp = frame["timestamp_s"]

        content_parts.append(f"\n--- Frame at {timestamp}s ---")

        try:
            with open(frame_path, "rb") as f:
                image_data = f.read()

            image_part = {
                "mime_type": "image/jpeg",
                "data": image_data,
            }
            content_parts.append(image_part)
        except Exception as e:
            logger.warning(f"Could not read frame at {timestamp}s: {e}")
            content_parts.append(f"[Frame at {timestamp}s could not be loaded]")

    try:
        response = await model.generate_content_async(
            content_parts,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        result_text = response.text.strip()

        # Parse JSON response
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                logger.error(f"Could not parse Gemini response as JSON: {result_text[:500]}")
                return _empty_visual_result()

        logger.info(
            f"Visual analysis complete: {len(result.get('frames', []))} frames analyzed, "
            f"hook_type={result.get('cross_frame_analysis', {}).get('hook_type', 'unknown')}"
        )
        return result

    except Exception as e:
        logger.error(f"Gemini visual analysis failed: {e}")
        return _empty_visual_result()


def collect_ocr_text(visual_analysis: dict) -> str:
    """
    Collect all text overlays detected in visual analysis into a single string.
    Deduplicates while preserving order.
    """
    seen = set()
    texts = []

    for frame in visual_analysis.get("frames", []):
        for text in frame.get("text_overlays", []):
            normalized = text.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                texts.append(text.strip())

    cfa = visual_analysis.get("cross_frame_analysis", {})
    cta = cfa.get("cta_text")
    if cta and cta.strip().lower() not in seen:
        texts.append(cta.strip())

    return " ".join(texts)


def _empty_visual_result() -> dict:
    """Return an empty visual analysis result."""
    return {
        "frames": [],
        "cross_frame_analysis": {
            "hook_type": "unknown",
            "hook_type_confidence": 0.0,
            "hook_description": "",
            "pacing": "unknown",
            "scene_changes": 0,
            "narrative_arc": "",
            "production_quality": "unknown",
            "format": "unknown",
            "brand_visibility": "",
            "cta_present": False,
            "cta_text": None,
            "overall_tone": "unknown",
        },
    }
