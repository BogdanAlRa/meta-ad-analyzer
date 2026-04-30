"""
Audio Transcription module.

Uses OpenAI Whisper API for accurate speech-to-text with timestamps.
Falls back to Gemini-based frame analysis if no OpenAI key provided.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def transcribe_with_whisper(
    audio_path: str,
    openai_api_key: str,
) -> dict:
    """
    Transcribe audio using OpenAI's Whisper API.

    Args:
        audio_path: Path to the audio file (mp3/wav).
        openai_api_key: OpenAI API key.

    Returns:
        Dict with:
          - transcript: str (full text)
          - segments: list[dict] (text, start, end per segment)
          - language: str
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=openai_api_key)

    try:
        with open(audio_path, "rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # Extract segments with timestamps
        segments = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                segments.append({
                    "text": seg.get("text", "").strip() if isinstance(seg, dict) else seg.text.strip(),
                    "start": seg.get("start", 0) if isinstance(seg, dict) else seg.start,
                    "end": seg.get("end", 0) if isinstance(seg, dict) else seg.end,
                })

        transcript_text = response.text if hasattr(response, "text") else str(response)
        language = response.language if hasattr(response, "language") else "unknown"

        logger.info(
            f"Whisper transcription complete: {len(transcript_text)} chars, "
            f"{len(segments)} segments, language={language}"
        )

        return {
            "transcript": transcript_text.strip(),
            "segments": segments,
            "language": language,
        }

    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return {
            "transcript": "",
            "segments": [],
            "language": "unknown",
            "error": str(e),
        }


async def transcribe_audio(
    audio_path: str | None,
    openai_api_key: str | None = None,
) -> dict:
    """
    Main transcription entry point.

    Uses Whisper API if audio exists and key is provided.
    Returns empty result if no audio available.
    """
    if not audio_path:
        logger.info("No audio file provided - skipping transcription")
        return {
            "transcript": "",
            "segments": [],
            "language": "unknown",
        }

    if not openai_api_key:
        logger.info("No OpenAI key - skipping Whisper transcription")
        return {
            "transcript": "",
            "segments": [],
            "language": "unknown",
            "note": "No OpenAI API key provided. Transcription skipped. Visual analysis will still extract text from frames.",
        }

    return await transcribe_with_whisper(audio_path, openai_api_key)
