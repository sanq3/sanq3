from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

VIDEOS = {
    "heart-crack": "qNfdEAzXImE",
    "down-deeper-hq": "BXuuCuuZtxM",
    "down-deeper-v2": "_9b8AoJWFWc",
}

OUT = Path("karaoke/youtube-embed-output")
OUT.mkdir(parents=True, exist_ok=True)
ORIGIN = "https://sanq3.github.io"


def media_info(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return {
        "host": parsed.netloc,
        "mime": (query.get("mime") or [None])[0],
        "itag": (query.get("itag") or [None])[0],
        "range": (query.get("range") or [None])[0],
        "clen": (query.get("clen") or [None])[0],
        "dur": (query.get("dur") or [None])[0],
        "ratebypass": (query.get("ratebypass") or [None])[0],
        "has_signature": any(k in query for k in ("sig", "lsig", "signature")),
        "url": url,
    }


result: dict[str, object] = {}
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--autoplay-policy=no-user-gesture-required",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )
    context = browser.new_context(
        locale="en-US",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 720},
        extra_http_headers={
            "Referer": f"{ORIGIN}/",
            "Origin": ORIGIN,
        },
    )

    for key, video_id in VIDEOS.items():
        page = context.new_page()
        media_urls: list[str] = []
        player_responses: list[dict[str, object]] = []
        errors: list[str] = []
        console: list[str] = []

        def on_request(request):
            if "googlevideo.com/videoplayback" in request.url and request.url not in media_urls:
                media_urls.append(request.url)

        def on_response(response):
            if "/youtubei/v1/player" not in response.url:
                return
            try:
                payload = response.json()
                player_responses.append({
                    "playability": payload.get("playabilityStatus"),
                    "video_details": payload.get("videoDetails"),
                    "caption_tracks": (((payload.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks") or []),
                    "streaming_data": {
                        "expiresInSeconds": (payload.get("streamingData") or {}).get("expiresInSeconds"),
                        "format_count": len((payload.get("streamingData") or {}).get("formats") or []),
                        "adaptive_format_count": len((payload.get("streamingData") or {}).get("adaptiveFormats") or []),
                    },
                })
            except Exception as exc:  # noqa: BLE001
                errors.append(f"player response: {exc}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: console.append(f"{msg.type}: {msg.text}"))

        embed_url = (
            f"https://www.youtube-nocookie.com/embed/{video_id}"
            f"?autoplay=1&mute=0&playsinline=1&enablejsapi=1&controls=1&rel=0&origin={ORIGIN}"
        )
        row: dict[str, object] = {"video_id": video_id, "embed_url": embed_url}
        try:
            response = page.goto(
                embed_url,
                wait_until="domcontentloaded",
                timeout=90000,
                referer=f"{ORIGIN}/karaoke/",
            )
            row["http_status"] = response.status if response else None
            page.wait_for_timeout(8000)

            for selector in ["button.ytp-large-play-button", ".ytp-play-button"]:
                try:
                    locator = page.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        locator.first.click(timeout=3000)
                        break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"click {selector}: {exc}")

            page.wait_for_timeout(15000)
            row["title"] = page.title()
            row["body_text"] = page.locator("body").inner_text(timeout=5000)[:6000]
            row["video_state"] = page.evaluate(
                """
                () => {
                  const v = document.querySelector('video');
                  return v ? {
                    currentTime: v.currentTime,
                    duration: v.duration,
                    paused: v.paused,
                    muted: v.muted,
                    volume: v.volume,
                    readyState: v.readyState,
                    networkState: v.networkState,
                    error: v.error ? {code: v.error.code, message: v.error.message} : null,
                    src: v.currentSrc || v.src || null,
                  } : null;
                }
                """
            )
            row["yt_initial_player_response"] = page.evaluate(
                """
                () => {
                  const p = window.ytInitialPlayerResponse || window.ytplayer?.config?.args?.raw_player_response;
                  if (!p) return null;
                  const r = typeof p === 'string' ? JSON.parse(p) : p;
                  return {
                    playability: r.playabilityStatus,
                    video_details: r.videoDetails,
                    caption_tracks: r.captions?.playerCaptionsTracklistRenderer?.captionTracks || [],
                    streaming_data: {
                      expiresInSeconds: r.streamingData?.expiresInSeconds,
                      format_count: r.streamingData?.formats?.length || 0,
                      adaptive_format_count: r.streamingData?.adaptiveFormats?.length || 0,
                    },
                  };
                }
                """
            )
            screenshot = OUT / f"{key}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            row["screenshot"] = screenshot.name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"navigation: {type(exc).__name__}: {exc}")

        row["media"] = [media_info(url) for url in media_urls]
        row["player_responses"] = player_responses
        row["errors"] = errors
        row["console_tail"] = console[-100:]
        result[key] = row
        page.close()

    context.close()
    browser.close()

(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
