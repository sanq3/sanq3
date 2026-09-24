from __future__ import annotations

import json
from urllib.parse import urlparse

import requests

INSTANCES = [
    "https://api-cobalt.eversiege.network",
    "https://nuko-c.meowing.de",
]
SOURCE = "https://www.youtube.com/watch?v=qNfdEAzXImE"
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "sanq3-korean-lyrics-study/1.0 (+https://github.com/sanq3/sanq3)",
}

result: dict[str, object] = {}
for api in INSTANCES:
    row: dict[str, object] = {"api": api}
    try:
        info = requests.get(api, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=20)
        row["info_status"] = info.status_code
        row["info"] = info.json() if "json" in info.headers.get("content-type", "") else info.text[:2000]

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
    result[api] = row

with open("karaoke/cobalt-public-probe.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
