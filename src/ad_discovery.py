"""
Ad Discovery module.

Discovers video ads from the Meta Ad Library for a given brand.
Uses Playwright to load the Ad Library page and intercept GraphQL
API responses to extract ad IDs reliably.

Two input modes:
  1. Brand Ad Library URL (direct link to the brand's page)
  2. Brand name (constructs a search URL)
"""

import json
import re
import logging
import urllib.parse

logger = logging.getLogger(__name__)


def extract_ad_id_from_url(url: str) -> str | None:
    """Extract the ad ID from a Meta Ad Library URL."""
    patterns = [
        r'[?&]id=(\d+)',
        r'/ads/library/\?.*id=(\d+)',
        r'ads/archive/render_ad/\?.*id=(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def parse_brand_input(brand_input: str) -> dict:
    """
    Parse the brand input to determine if it's a URL or a name.

    Returns dict with:
      - type: "url" or "name"
      - url: the Ad Library URL to scrape
      - name: the brand name (extracted or as-is)
      - page_id: Facebook page ID if found in URL
    """
    brand_input = brand_input.strip()

    # Check if it's a URL
    if brand_input.startswith("http") or "facebook.com" in brand_input:
        url = brand_input
        if not url.startswith("http"):
            url = "https://" + url

        # Try to extract page_id
        page_id = None
        pid_match = re.search(r'view_all_page_id=(\d+)', url)
        if pid_match:
            page_id = pid_match.group(1)

        # Try to extract brand name from URL
        name = "Unknown Brand"
        q_match = re.search(r'[?&]q=([^&]+)', url)
        if q_match:
            name = urllib.parse.unquote_plus(q_match.group(1))

        return {"type": "url", "url": url, "name": name, "page_id": page_id}

    else:
        # It's a brand name - construct the search URL
        encoded_name = urllib.parse.quote(brand_input)
        url = (
            f"https://www.facebook.com/ads/library/"
            f"?active_status=active&ad_type=all&country=ALL"
            f"&q={encoded_name}"
        )
        return {"type": "name", "url": url, "name": brand_input, "page_id": None}


def _parse_proxy_url(proxy_url: str) -> dict:
    """Parse a proxy URL with embedded credentials into Playwright's format."""
    from urllib.parse import urlparse
    parsed = urlparse(proxy_url)

    result = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        result["username"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password

    return result


async def discover_video_ads(
    brand_input: str,
    max_videos: int = 5,
    proxy_url: str | None = None,
) -> list[dict]:
    """
    Discover video ads from the Meta Ad Library.

    Uses Playwright to load the Ad Library page and intercept the
    internal GraphQL API responses that contain ad data.

    Args:
        brand_input: Brand name or Ad Library URL.
        max_videos: Maximum number of video ads to return.
        proxy_url: Optional proxy URL.

    Returns:
        List of ad info dicts sorted by most recent first.
    """
    from playwright.async_api import async_playwright

    parsed = parse_brand_input(brand_input)
    search_url = parsed["url"]
    brand_name = parsed["name"]

    # Ensure media_type=video is in the URL for video filtering
    if "media_type=" not in search_url:
        sep = "&" if "?" in search_url else "?"
        search_url += f"{sep}media_type=video"

    logger.info(f"Discovering video ads for '{brand_name}' at: {search_url}")

    # Collect ad data from intercepted API responses
    collected_ads = []
    graphql_count = 0

    try:
        async with async_playwright() as p:
            browser_args = {}
            if proxy_url:
                # Parse proxy URL to separate credentials for Playwright
                proxy_config = _parse_proxy_url(proxy_url)
                browser_args["proxy"] = proxy_config
                logger.info(f"Using proxy server: {proxy_config.get('server', 'unknown')}")

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
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )

            # Remove webdriver flag to reduce bot detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            page = await context.new_page()

            # Intercept API responses to capture ad data
            async def handle_response(response):
                nonlocal graphql_count
                url = response.url
                # Facebook's GraphQL API endpoint for loading ads
                if "/api/graphql" in url or "ads/library/async" in url:
                    try:
                        if response.status == 200:
                            body = await response.text()
                            graphql_count += 1
                            before = len(collected_ads)
                            _parse_api_response(body, collected_ads)
                            after = len(collected_ads)
                            if after > before:
                                logger.info(
                                    f"GraphQL response: found {after - before} "
                                    f"new ads (total: {after})"
                                )
                    except Exception as e:
                        logger.debug(f"Error parsing response: {e}")

            page.on("response", handle_response)

            try:
                # Navigate to the Ad Library page
                logger.info("Navigating to Ad Library page...")
                try:
                    await page.goto(search_url, wait_until="networkidle", timeout=60000)
                except Exception:
                    # networkidle can timeout on slow proxies, try with load event
                    logger.info("networkidle timed out, trying with load event...")
                    await page.goto(search_url, wait_until="load", timeout=60000)

                # Handle cookie consent dialog
                await _handle_cookie_consent(page)

                # Wait for the page to fully render (SPA needs time)
                logger.info("Waiting for page to render...")
                await page.wait_for_timeout(10000)

                logger.info(
                    f"After initial load: {len(collected_ads)} ads from "
                    f"{graphql_count} GraphQL responses"
                )

                # If no ads yet, try waiting longer for lazy-loaded content
                if not collected_ads:
                    logger.info("No ads yet, waiting for additional loading...")
                    await page.wait_for_timeout(5000)

                    # Try to find and click "See results" or similar buttons
                    for selector in [
                        'div[role="button"]:has-text("See results")',
                        'a:has-text("See all")',
                        'div[role="button"]:has-text("Show more")',
                    ]:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=2000):
                                logger.info(f"Clicking button: {selector}")
                                await btn.click()
                                await page.wait_for_timeout(5000)
                        except Exception:
                            pass

                # Scroll to load more ads
                scroll_attempts = 0
                max_scrolls = max(15, max_videos * 2)
                no_change_count = 0

                while len(collected_ads) < max_videos * 3 and scroll_attempts < max_scrolls:
                    prev_count = len(collected_ads)

                    # Smooth scroll down (with null check for document.body)
                    await page.evaluate("""
                        if (document.body) {
                            window.scrollBy({top: window.innerHeight, behavior: 'smooth'});
                        }
                    """)
                    await page.wait_for_timeout(2000)

                    # Also try scrolling to absolute bottom
                    await page.evaluate(
                        "if (document.body) window.scrollTo(0, document.body.scrollHeight)"
                    )
                    await page.wait_for_timeout(2000)

                    if len(collected_ads) == prev_count:
                        no_change_count += 1
                        if no_change_count >= 3:
                            logger.info("No new ads after 3 consecutive scrolls, stopping")
                            break
                    else:
                        no_change_count = 0

                    scroll_attempts += 1

                logger.info(
                    f"After scrolling: {len(collected_ads)} ads from "
                    f"{graphql_count} GraphQL responses"
                )

                # If API interception didn't work, fall back to DOM scraping
                if not collected_ads:
                    logger.info("API interception got 0 ads, trying DOM extraction...")

                    # Log page title and URL for debugging
                    title = await page.title()
                    current_url = page.url
                    logger.info(f"Page title: {title}")
                    logger.info(f"Current URL: {current_url}")

                    # Take a screenshot of the current page state for debugging
                    try:
                        content_preview = await page.evaluate(
                            "document.body ? document.body.innerText.substring(0, 500) : 'NO BODY'"
                        )
                        logger.info(f"Page text preview: {content_preview[:200]}")
                    except Exception:
                        pass

                    collected_ads = await _extract_ads_from_dom(page, brand_name)

            finally:
                await context.close()
                await browser.close()

    except Exception as e:
        logger.error(f"Ad Library discovery failed: {e}")
        raise RuntimeError(
            f"Could not discover ads from Meta Ad Library. Error: {e}. "
            "Make sure the URL is correct and the brand has active ads."
        )

    # Deduplicate by ad_id
    seen = set()
    unique_ads = []
    for ad in collected_ads:
        ad_id = ad.get("ad_id", "")
        if ad_id and ad_id not in seen:
            seen.add(ad_id)
            unique_ads.append(ad)

    logger.info(f"Discovered {len(unique_ads)} unique ads total")

    # Take the most recent ones (they're already in page order = most recent)
    selected = unique_ads[:max_videos]

    if not selected:
        logger.warning(f"No ads found for '{brand_name}'")

    logger.info(f"Returning {len(selected)} ads for analysis")
    return selected


async def _handle_cookie_consent(page):
    """Dismiss cookie consent dialogs that may block the page."""
    consent_selectors = [
        'button[data-cookiebanner="accept_button"]',
        'button:has-text("Allow all cookies")',
        'button:has-text("Accept All")',
        'button:has-text("Allow essential and optional cookies")',
        'button:has-text("Accept")',
        'button[title="Allow all cookies"]',
        '[aria-label="Allow all cookies"]',
        '[data-testid="cookie-policy-manage-dialog-accept-button"]',
    ]

    for selector in consent_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=3000):
                logger.info(f"Dismissing cookie consent: {selector}")
                await btn.click()
                await page.wait_for_timeout(2000)
                return
        except Exception:
            continue

    logger.info("No cookie consent dialog found (or already dismissed)")


def _parse_api_response(body: str, collected_ads: list):
    """
    Parse Facebook's internal API response to extract ad data.

    The response format is typically JSON with ad entries containing
    ad IDs, snapshot URLs, page info, and media type indicators.
    Facebook prefixes responses with "for (;;);" as CSRF protection.
    """
    # Facebook API responses can be prefixed with "for (;;);" as CSRF protection
    cleaned = body
    if cleaned.startswith("for (;;);"):
        cleaned = cleaned[len("for (;;);"):]

    # Try to parse as JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON objects in the response
        json_match = re.search(r'\{[\s\S]*\}', cleaned)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                return
        else:
            return

    # Extract ad IDs from the response using recursive search
    _extract_ads_recursive(data, collected_ads)


def _extract_ads_recursive(obj, collected_ads: list, depth: int = 0):
    """Recursively search through API response to find ad data."""
    if depth > 20:
        return

    if isinstance(obj, dict):
        # Look for ad archive ID patterns
        ad_id = None

        # Common patterns in Facebook's API responses
        for key in ("adArchiveID", "ad_archive_id", "adid", "collationID"):
            val = obj.get(key)
            if val and isinstance(val, (str, int)):
                val_str = str(val)
                # Ad IDs are typically 10-20 digit numbers
                if re.match(r'^\d{10,20}$', val_str):
                    ad_id = val_str
                    break

        # Also check "id" field but only in ad-like contexts
        if not ad_id and obj.get("id"):
            val_str = str(obj["id"])
            if re.match(r'^\d{10,20}$', val_str):
                # Only treat as ad ID if the object has ad-related fields
                ad_keys = {"adArchiveID", "pageName", "page_name", "snapshot_url",
                           "ad_creative_bodies", "publisherPlatform", "isActive",
                           "startDate", "ad_delivery_start_time", "collationCount"}
                if ad_keys & set(obj.keys()):
                    ad_id = val_str

        if ad_id:
            # Extract page name from various possible locations
            page_name = (
                obj.get("pageName", "")
                or obj.get("page_name", "")
            )
            snapshot = obj.get("snapshot")
            if not page_name and isinstance(snapshot, dict):
                page_name = (
                    snapshot.get("page_name", "")
                    or snapshot.get("page_profile_name", "")
                )

            # Check for video indicator
            has_video = (
                obj.get("isVideo", False)
                or obj.get("has_video", False)
                or "video" in str(obj.get("snapshot_url", "")).lower()
                or "video" in str(obj.get("media_type", "")).lower()
                or obj.get("videos") is not None
                or obj.get("video_url") is not None
                or obj.get("video_hd_url") is not None
            )

            collected_ads.append({
                "ad_id": ad_id,
                "ad_url": f"https://www.facebook.com/ads/library/?id={ad_id}",
                "snapshot_url": obj.get(
                    "snapshot_url",
                    f"https://www.facebook.com/ads/archive/render_ad/?id={ad_id}&access_token="
                ),
                "page_name": page_name or "Unknown Brand",
                "has_video": has_video,
                "source": "api_intercept",
            })

        # Continue searching
        for val in obj.values():
            _extract_ads_recursive(val, collected_ads, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            _extract_ads_recursive(item, collected_ads, depth + 1)


async def _extract_ads_from_dom(page, brand_name: str) -> list[dict]:
    """
    Fallback: extract ad IDs directly from the page DOM and HTML content.

    Searches both visible content and embedded JSON in script tags.
    """
    ads = []
    seen = set()
    collected_from_scripts = []

    content = await page.content()
    logger.info(f"DOM content length: {len(content)} chars")

    # First, try to extract embedded JSON from script tags
    # Facebook embeds ad data in script tags as part of server-side rendering
    script_blocks = re.findall(
        r'<script[^>]*>(\{.*?"adArchiveID".*?\})</script>',
        content,
        re.DOTALL,
    )
    if not script_blocks:
        # Try a broader pattern for any JSON with ad-related keys
        script_blocks = re.findall(
            r'<script[^>]*>(.*?)</script>',
            content,
            re.DOTALL,
        )

    for block in script_blocks:
        if len(block) < 50:
            continue
        # Look for JSON data containing ad information
        if any(key in block for key in [
            "adArchiveID", "collationID", "ad_archive_id",
            "snapshot_url", "AdLibrarySearchPagination",
            "search_results", "forward_cursor",
        ]):
            logger.info(f"Found ad-related script block ({len(block)} chars)")
            # Try to parse JSON from the block
            _parse_api_response(block, collected_from_scripts)

    if collected_from_scripts:
        logger.info(
            f"Extracted {len(collected_from_scripts)} ads from embedded scripts"
        )
        for ad in collected_from_scripts:
            ad_id = ad.get("ad_id", "")
            if ad_id:
                seen.add(ad_id)
                ad["source"] = "embedded_script"
                ads.append(ad)

    # Pattern 1: Find ad IDs in links
    link_ids = re.findall(r'ads/library/\?id=(\d{10,20})', content)
    if link_ids:
        logger.info(f"Pattern 1 (link IDs): found {len(link_ids)}")
    for ad_id in link_ids:
        seen.add(ad_id)

    # Pattern 2: Find ad archive IDs in JSON data within the page
    archive_ids = re.findall(r'"adArchiveID"\s*:\s*"(\d{10,20})"', content)
    if archive_ids:
        logger.info(f"Pattern 2 (adArchiveID): found {len(archive_ids)}")
    for ad_id in archive_ids:
        seen.add(ad_id)

    # Pattern 3: Find collation IDs
    collation_ids = re.findall(r'"collationID"\s*:\s*"?(\d{10,20})"?', content)
    if collation_ids:
        logger.info(f"Pattern 3 (collationID): found {len(collation_ids)}")
    for ad_id in collation_ids:
        seen.add(ad_id)

    # Pattern 4: Find ad IDs in data attributes
    data_ids = re.findall(
        r'data-ad[_-]?(?:archive[_-]?)?id["\s:=]+["\s]*(\d{10,20})', content
    )
    if data_ids:
        logger.info(f"Pattern 4 (data attributes): found {len(data_ids)}")
    for ad_id in data_ids:
        seen.add(ad_id)

    # Pattern 5: Find IDs in ad library link format
    library_ids = re.findall(r'/ads/library/\?.*?id=(\d{10,20})', content)
    if library_ids:
        logger.info(f"Pattern 5 (library links): found {len(library_ids)}")
    for ad_id in library_ids:
        seen.add(ad_id)

    # Pattern 6: Find ad IDs in render_ad URLs
    render_ids = re.findall(r'render_ad/\?.*?id=(\d{10,20})', content)
    if render_ids:
        logger.info(f"Pattern 6 (render_ad): found {len(render_ids)}")
    for ad_id in render_ids:
        seen.add(ad_id)

    logger.info(f"DOM extraction found {len(seen)} unique ad IDs total")

    for ad_id in seen:
        ads.append({
            "ad_id": ad_id,
            "ad_url": f"https://www.facebook.com/ads/library/?id={ad_id}",
            "snapshot_url": (
                f"https://www.facebook.com/ads/archive/render_ad/"
                f"?id={ad_id}&access_token="
            ),
            "page_name": brand_name,
            "has_video": None,  # Unknown from DOM
            "source": "dom_extraction",
        })

    return ads


async def discover_ads(
    brand_input: str,
    max_videos: int = 5,
    proxy_url: str | None = None,
) -> list[dict]:
    """
    Main entry point for ad discovery. Tries with proxy first,
    falls back to no proxy if proxy attempt fails.

    Args:
        brand_input: Brand name or Ad Library URL.
        max_videos: How many video ads to find.
        proxy_url: Optional proxy.

    Returns:
        List of ad info dicts.
    """
    # First attempt: with proxy
    try:
        ads = await discover_video_ads(
            brand_input=brand_input,
            max_videos=max_videos,
            proxy_url=proxy_url,
        )
        if ads:
            return ads
    except Exception as e:
        if proxy_url:
            logger.warning(f"Proxy attempt failed: {e}. Retrying without proxy...")
        else:
            raise

    # Fallback: without proxy (if proxy was being used)
    if proxy_url:
        return await discover_video_ads(
            brand_input=brand_input,
            max_videos=max_videos,
            proxy_url=None,
    )
