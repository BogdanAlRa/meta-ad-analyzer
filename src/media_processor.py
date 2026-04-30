"""
Media Processor module.

Handles:
  1. Visiting ad snapshot URLs with Playwright to extract video source URLs
  2. Downloading video files
  3. Extracting keyframes via ffmpeg
  4. Extracting audio track via ffmpeg
"""

import asyncio
import logging
import os
import tempfile
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Keyframe timestamps in seconds
STANDARD_KEYFRAMES = [0, 1.5, 3, 5, 10]
DEEP_KEYFRAMES = [0, 1, 2, 3, 5, 7, 10, 14]


async def extract_video_url_from_ad(
    ad_url: str,
    proxy_url: str | None = None,
) -> str | None:
    """
    Use Playwright to visit an ad library page and extract the video source URL.

    Args:
        ad_url: The Facebook Ad Library URL for the ad.
        proxy_url: Optional proxy URL for Playwright.

    Returns:
        Direct video URL or None if extraction fails.
    """
    from playwright.async_api import async_playwright

    video_url = None

    try:
        async with async_playwright() as p:
            browser_args = {}
            if proxy_url:
                # Parse proxy URL to separate credentials for Playwright
                from urllib.parse import urlparse
                parsed_proxy = urlparse(proxy_url)
                proxy_config = {
                    "server": f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}"
                }
                if parsed_proxy.username:
                    proxy_config["username"] = parsed_proxy.username
                if parsed_proxy.password:
                    proxy_config["password"] = parsed_proxy.password
                browser_args["proxy"] = proxy_config

            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
                **browser_args,
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            # Reduce bot detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            page = await context.new_page()

            # Intercept network requests to catch video URLs
            video_urls = []

            async def handle_response(response):
                url = response.url
                content_type = response.headers.get("content-type", "")
                if (
                    "video" in content_type
                    or url.endswith(".mp4")
                    or "video" in url
                    or "fbcdn" in url and (".mp4" in url or "video" in url)
                ):
                    video_urls.append(url)

            page.on("response", handle_response)

            try:
                try:
                    await page.goto(ad_url, wait_until="networkidle", timeout=30000)
                except Exception:
                    await page.goto(ad_url, wait_until="load", timeout=30000)
                await page.wait_for_timeout(5000)

                # Handle cookie consent
                for selector in [
                    'button[data-cookiebanner="accept_button"]',
                    'button:has-text("Allow all cookies")',
                    'button:has-text("Accept All")',
                    'button:has-text("Accept")',
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass

                # Try to find and click play button if video isn't auto-playing
                try:
                    play_btn = page.locator('div[aria-label="Play"]').first
                    if await play_btn.is_visible(timeout=2000):
                        await play_btn.click()
                        await page.wait_for_timeout(3000)
                except Exception:
                    pass

                # Try to find video element directly
                try:
                    video_el = page.locator("video").first
                    if await video_el.is_visible(timeout=2000):
                        src = await video_el.get_attribute("src")
                        if src and src.startswith("http"):
                            video_urls.insert(0, src)
                except Exception:
                    pass

                # Also search the page HTML for video URLs
                if not video_urls:
                    html = await page.content()
                    import re
                    # Look for video URLs in the HTML
                    fbcdn_videos = re.findall(
                        r'(https://video[^"\'\\]+\.fbcdn\.net[^"\'\\]+\.mp4[^"\'\\]*)',
                        html
                    )
                    video_urls.extend(fbcdn_videos)

                    # Also look for blob or data video sources
                    src_videos = re.findall(
                        r'src="(https://[^"]+(?:\.mp4|video)[^"]*)"',
                        html
                    )
                    video_urls.extend(src_videos)

                # Pick the best video URL (prefer .mp4, longer URLs tend to be actual videos)
                if video_urls:
                    # Filter for actual video URLs
                    candidates = [
                        u for u in video_urls
                        if ".mp4" in u or "video" in u.lower()
                    ]
                    video_url = candidates[0] if candidates else video_urls[0]
                    logger.info(f"Found video URL: {video_url[:100]}...")

            finally:
                await context.close()
                await browser.close()

    except Exception as e:
        logger.error(f"Playwright video extraction failed: {e}")

    return video_url


async def download_video(
    video_url: str,
    output_dir: str,
    filename: str = "video.mp4",
) -> str | None:
    """
    Download a video file from URL.

    Returns the path to the downloaded file, or None on failure.
    """
    output_path = os.path.join(output_dir, filename)

    try:
        async with httpx.AsyncClient(
            timeout=120,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5),
        ) as client:
            async with client.stream("GET", video_url) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

        file_size = os.path.getsize(output_path)
        if file_size < 1000:  # Less than 1KB is suspicious
            logger.warning(f"Downloaded file suspiciously small: {file_size} bytes")
            return None

        logger.info(f"Downloaded video: {file_size / 1024 / 1024:.1f} MB")
        return output_path

    except Exception as e:
        logger.error(f"Video download failed: {e}")
        return None


async def extract_keyframes(
    video_path: str,
    output_dir: str,
    timestamps: list[float] | None = None,
) -> list[dict]:
    """
    Extract keyframes from a video at specified timestamps using ffmpeg.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save extracted frames.
        timestamps: List of timestamps in seconds. Defaults to STANDARD_KEYFRAMES.

    Returns:
        List of dicts: [{"timestamp_s": float, "path": str}, ...]
    """
    if timestamps is None:
        timestamps = STANDARD_KEYFRAMES

    # First, get video duration
    duration = await _get_video_duration(video_path)
    if duration is None:
        logger.warning("Could not determine video duration, using all timestamps")
        duration = 999

    frames = []
    for ts in timestamps:
        if ts > duration:
            continue

        frame_path = os.path.join(output_dir, f"frame_{ts:.1f}s.jpg")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(ts),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            frame_path,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0 and os.path.isfile(frame_path):
                frames.append({
                    "timestamp_s": ts,
                    "path": frame_path,
                })
            else:
                logger.debug(f"Frame extraction failed at {ts}s: {stderr.decode()[:200]}")
        except Exception as e:
            logger.warning(f"ffmpeg frame extraction error at {ts}s: {e}")

    logger.info(f"Extracted {len(frames)} keyframes from video")
    return frames


async def extract_audio(
    video_path: str,
    output_dir: str,
    max_duration_s: float = 15.0,
) -> str | None:
    """
    Extract the audio track from a video using ffmpeg.

    Extracts only the first max_duration_s seconds to save on
    transcription costs (Whisper API charges per minute).

    Returns path to the audio file, or None on failure.
    """
    audio_path = os.path.join(output_dir, "audio.mp3")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-t", str(max_duration_s),
        "-vn",               # No video
        "-acodec", "libmp3lame",
        "-ar", "16000",      # 16kHz sample rate (good for speech)
        "-ac", "1",          # Mono
        "-q:a", "6",         # Lower quality = smaller file
        audio_path,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode == 0 and os.path.isfile(audio_path):
            file_size = os.path.getsize(audio_path)
            if file_size < 500:
                logger.info("Audio file too small - video may have no audio track")
                return None
            logger.info(f"Extracted audio: {file_size / 1024:.0f} KB")
            return audio_path
        else:
            logger.warning(f"Audio extraction failed: {stderr.decode()[:300]}")
            return None

    except Exception as e:
        logger.error(f"ffmpeg audio extraction error: {e}")
        return None


async def _get_video_duration(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0:
            duration = float(stdout.decode().strip())
            return duration
    except (ValueError, Exception) as e:
        logger.debug(f"Could not get video duration: {e}")

    return None


async def process_ad_media(
    ad_info: dict,
    work_dir: str,
    analysis_depth: str = "standard",
    proxy_url: str | None = None,
) -> dict:
    """
    Full media processing pipeline for a single ad.

    Steps:
      1. Extract video URL from ad page (Playwright)
      2. Download video
      3. Extract keyframes
      4. Extract audio

    Args:
        ad_info: Ad discovery dict with ad_url, ad_id, etc.
        work_dir: Temporary working directory for this ad.
        analysis_depth: "standard" or "deep" (affects keyframe count).
        proxy_url: Optional proxy for Playwright.

    Returns:
        Dict with:
          - video_path: str | None
          - frames: list[dict]  (timestamp_s, path)
          - audio_path: str | None
          - video_duration_s: float | None
          - error: str | None
    """
    ad_url = ad_info.get("ad_url", "")
    ad_id = ad_info.get("ad_id", "unknown")

    result = {
        "video_path": None,
        "frames": [],
        "audio_path": None,
        "video_duration_s": None,
        "error": None,
    }

    # Step 1: Extract video URL (try ad page, then snapshot URL)
    logger.info(f"[{ad_id}] Extracting video URL from ad page...")
    video_url = await extract_video_url_from_ad(ad_url, proxy_url)

    if not video_url:
        # Try snapshot URL as fallback
        snapshot_url = ad_info.get("snapshot_url", "")
        if snapshot_url and "access_token=" not in snapshot_url:
            logger.info(f"[{ad_id}] Trying snapshot URL...")
            video_url = await extract_video_url_from_ad(snapshot_url, proxy_url)

    if not video_url:
        result["error"] = "Could not extract video URL from ad page"
        logger.warning(f"[{ad_id}] {result['error']}")
        return result

    # Step 2: Download video
    logger.info(f"[{ad_id}] Downloading video...")
    video_path = await download_video(
        video_url, work_dir, filename=f"ad_{ad_id}.mp4"
    )

    if not video_path:
        result["error"] = "Video download failed"
        logger.warning(f"[{ad_id}] {result['error']}")
        return result

    result["video_path"] = video_path

    # Get duration
    duration = await _get_video_duration(video_path)
    result["video_duration_s"] = duration

    # Step 3: Extract keyframes
    timestamps = DEEP_KEYFRAMES if analysis_depth == "deep" else STANDARD_KEYFRAMES
    logger.info(f"[{ad_id}] Extracting {len(timestamps)} keyframes...")
    frames = await extract_keyframes(video_path, work_dir, timestamps)
    result["frames"] = frames

    # Step 4: Extract audio (first 15s)
    logger.info(f"[{ad_id}] Extracting audio track...")
    audio_path = await extract_audio(video_path, work_dir, max_duration_s=15.0)
    result["audio_path"] = audio_path

    return result
