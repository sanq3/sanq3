from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

VIDEOS = {
    "heart-crack-a": "BV1ZEMJ6gEf9",
    "heart-crack-b": "BV1TnQ6BXEU6",
    "halo-error": "BV1JoDGB8EbS",
    "show-it": "BV1BZXVBvECS",
    "down-deeper-hq": "BV1yUMJ6SEFk",
    "down-deeper-v2": "BV11rVj6xEau",
    "run-it-up": "BV1kMDgBsEcF",
}

OUT = Path("karaoke/bilibili-embed-output")
OUT.mkdir(parents=True, exist_ok=True)


def media_info(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return {
        "host": parsed.netloc,
        "path": parsed.path,
        "mime": (query.get("mime") or [None])[0],
        "deadline": (query.get("deadline") or [None])[0],
        "platform": (query.get("platform") or [None])[0],
        "qn": (query.get("qn") or [None])[0],
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
        locale="zh-CN",
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        viewport={"width": 430, "height": 932},
        extra_http_headers={
            "Referer": "https://www.bilibili.com/",
        },
    )

    for key, bvid in VIDEOS.items():
        page = context.new_page()
        media_urls: list[str] = []
        api_payloads: list[dict[str, object]] = []
        console: list[str] = []
        errors: list[str] = []

        def on_request(request):
            url = request.url
            if any(token in url for token in (".m4s", ".mp4", "upos-sz", "bilivideo", "videoplayback")):
                if url not in media_urls:
                    media_urls.append(url)

        def on_response(response):
            url = response.url
            if any(token in url for token in ("playurl", "player/wbi", "x/player")):
                try:
                    payload = response.json()
                    api_payloads.append({
                        "url": url,
                        "status": response.status,
                        "payload": payload,
                    })
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"api parse {url}: {exc}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", lambda msg: console.append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        url = (
            "https://player.bilibili.com/player.html"
            f"?bvid={bvid}&page=1&high_quality=1&autoplay=1&danmaku=0&as_wide=1"
        )
        row: dict[str, object] = {"bvid": bvid, "embed_url": url}
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
            row["http_status"] = response.status if response else None
            page.wait_for_timeout(10000)

            # Try visible play controls and the video surface.
            for selector in [
                "video",
                ".bpx-player-ctrl-play",
                ".bilibili-player-video-btn-start",
                ".bpx-player-video-area",
            ]:
                try:
                    locator = page.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        locator.first.click(timeout=3000, force=True)
                        break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"click {selector}: {exc}")

            page.wait_for_timeout(18000)
            row["title"] = page.title()
            row["body_text"] = page.locator("body").inner_text(timeout=5000)[:8000]
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
            screenshot = OUT / f"{key}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            row["screenshot"] = screenshot.name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"navigation: {type(exc).__name__}: {exc}")

        row["media"] = [media_info(url) for url in media_urls]
        row["api_payloads"] = api_payloads[-20:]
        row["console_tail"] = console[-100:]
        row["errors"] = errors
        result[key] = row
        page.close()

    context.close()
    browser.close()

(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
