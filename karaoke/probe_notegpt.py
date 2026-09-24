from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

SOURCE = "https://www.youtube.com/watch?v=qNfdEAzXImE"
PAGE_URL = "https://notegpt.io/youtube-to-transcript"
OUT = Path("karaoke/notegpt-output")
OUT.mkdir(parents=True, exist_ok=True)


def scrub_headers(headers: dict[str, str]) -> dict[str, str]:
    allowed = {"content-type", "content-length", "location", "retry-after"}
    return {k.lower(): v for k, v in headers.items() if k.lower() in allowed}


result: dict[str, object] = {
    "page_url": PAGE_URL,
    "source": SOURCE,
    "responses": [],
    "errors": [],
    "snapshots": [],
}

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-dev-shm-usage", "--no-sandbox"],
    )
    context = browser.new_context(
        locale="en-US",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 1100},
        accept_downloads=True,
    )
    page = context.new_page()

    def on_response(response):
        url = response.url
        if not any(token in url.lower() for token in ("transcript", "youtube", "task", "subtitle", "summary", "video")):
            return
        item: dict[str, object] = {
            "url": url,
            "host": urlparse(url).netloc,
            "status": response.status,
            "headers": scrub_headers(response.headers),
        }
        content_type = response.headers.get("content-type", "")
        if any(token in content_type for token in ("json", "text")):
            try:
                item["body"] = response.text()[:200000]
            except Exception as exc:  # noqa: BLE001
                item["body_error"] = str(exc)
        result["responses"].append(item)

    page.on("response", on_response)
    page.on("pageerror", lambda exc: result["errors"].append(str(exc)))
    page.on("console", lambda msg: result["errors"].append(f"console {msg.type}: {msg.text}") if msg.type == "error" else None)

    try:
        response = page.goto(PAGE_URL, wait_until="networkidle", timeout=120000)
        result["http_status"] = response.status if response else None
        result["title"] = page.title()

        inputs = page.locator("input")
        result["inputs"] = [
            {
                "type": inputs.nth(i).get_attribute("type"),
                "placeholder": inputs.nth(i).get_attribute("placeholder"),
                "name": inputs.nth(i).get_attribute("name"),
            }
            for i in range(min(inputs.count(), 30))
        ]
        buttons = page.get_by_role("button")
        result["buttons"] = [buttons.nth(i).inner_text()[:300] for i in range(min(buttons.count(), 50))]

        target_input = page.locator("input[placeholder*='YouTube'], input[placeholder*='youtube'], input[placeholder*='Paste']").first
        if not target_input.count():
            # Fall back to the widest visible text input.
            candidates = page.locator("input[type='text'], input:not([type])")
            for i in range(candidates.count()):
                if candidates.nth(i).is_visible():
                    target_input = candidates.nth(i)
                    break
        if not target_input.count():
            raise RuntimeError("No visible transcript URL input found")

        target_input.fill(SOURCE)
        page.wait_for_timeout(1000)

        clicked = False
        for name in ("Generate Transcript", "Generate", "Transcribe"):
            locator = page.get_by_role("button", name=name, exact=False)
            if locator.count() and locator.first.is_visible():
                locator.first.click(timeout=10000)
                result["clicked_button"] = locator.first.inner_text()
                clicked = True
                break
        if not clicked:
            raise RuntimeError("Generate button not found")

        # Wait up to 8 minutes for a transcript or an explicit error.
        deadline = time.time() + 480
        last_text = ""
        while time.time() < deadline:
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=10000)
            if body_text != last_text:
                result["snapshots"].append({
                    "elapsed": round(480 - max(deadline - time.time(), 0), 1),
                    "text": body_text[-30000:],
                })
                last_text = body_text
            lowered = body_text.lower()
            source_markers = ("oh oh oh", "그렇게 보지 마", "heart crack")
            if any(marker.lower() in lowered for marker in source_markers):
                result["completed"] = True
                result["final_text"] = body_text[-100000:]
                break
            if any(marker in lowered for marker in ("failed", "error", "try again", "sign in", "captcha", "verify")):
                result["possible_error_text"] = body_text[-30000:]
                # Do not stop immediately; transient error banners may appear.

        screenshot = OUT / "final.png"
        page.screenshot(path=str(screenshot), full_page=True)
        result["screenshot"] = screenshot.name
        (OUT / "final.html").write_text(page.content(), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        try:
            page.screenshot(path=str(OUT / "error.png"), full_page=True)
        except Exception:
            pass
    finally:
        context.close()
        browser.close()

(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
