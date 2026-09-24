from __future__ import annotations

import json
from urllib.parse import urlparse

import requests

DIRECTORY = "https://cobalt.directory/api/working?type=api"
SOURCE = "https://www.youtube.com/watch?v=qNfdEAzXImE"
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "sanq3-korean-lyrics-study/1.1 (+https://github.com/sanq3/sanq3)",
}

result: dict[str, object] = {"directory": DIRECTORY, "instances": {}}
try:
    directory = requests.get(DIRECTORY, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=30)
    directory.raise_for_status()
    candidates = directory.json().get("data", {}).get("youtube", [])
except Exception as exc:  # noqa: BLE001
    result["directory_error"] = f"{type(exc).__name__}: {exc}"
    candidates = []

# Root GETs are harmless. POST only to the first three opt-in instances that
# explicitly advertise YouTube support and do not expose Turnstile.
post_attempts = 0
for api in candidates:
    row: dict[str, object] = {"api": api}
    try:
        info = requests.get(api, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
        row["info_status"] = info.status_code
        info_payload = info.json() if "json" in info.headers.get("content-type", "") else {"raw": info.text[:2000]}
        row["info"] = info_payload
        cobalt = info_payload.get("cobalt", {}) if isinstance(info_payload, dict) else {}
        protected = bool(cobalt.get("turnstileSitekey"))
        row["protected"] = protected
        row["advertises_youtube"] = "youtube" in (cobalt.get("services") or [])

        if protected or not row["advertises_youtube"] or post_attempts >= 3:
            result["instances"][api] = row
            continue

        post_attempts += 1
        response = requests.post(
            api,
            headers=HEADERS,
            json={
                "url": SOURCE,
                "downloadMode": "audio",
                "audioFormat": "wav",
                "audioBitrate": "128",
                "filenameStyle": "basic",
                "disableMetadata": True,
                "localProcessing": "disabled",
            },
            timeout=120,
        )
        row["post_status"] = response.status_code
        row["rate_limit"] = {
            "limit": response.headers.get("ratelimit-limit"),
            "remaining": response.headers.get("ratelimit-remaining"),
            "reset": response.headers.get("ratelimit-reset"),
        }
        payload = response.json() if "json" in response.headers.get("content-type", "") else {"raw": response.text[:4000]}
        row["payload"] = payload
        target = payload.get("url") if isinstance(payload, dict) else None
        if target:
            parsed = urlparse(target)
            row["target"] = {"scheme": parsed.scheme, "host": parsed.netloc, "path": parsed.path}
            with requests.get(target, headers={"User-Agent": HEADERS["User-Agent"]}, stream=True, timeout=60) as media:
                row["media_status"] = media.status_code
                row["media_headers"] = {
                    "content_type": media.headers.get("content-type"),
                    "content_length": media.headers.get("content-length"),
                    "estimated_content_length": media.headers.get("estimated-content-length"),
                }
                row["first_chunk_bytes"] = len(next(media.iter_content(65536), b""))
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    result["instances"][api] = row

result["post_attempts"] = post_attempts
with open("karaoke/cobalt-public-probe.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
