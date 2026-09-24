from __future__ import annotations

import json
import time
from urllib.parse import urlparse

import requests

VIDEOS = {
    "heart-crack": "https://www.youtube.com/watch?v=qNfdEAzXImE",
    "halo-error": "https://www.youtube.com/watch?v=BEzKZ12Heto",
    "show-it": "https://www.youtube.com/watch?v=yaXhmBfxGJY",
    "down-deeper-hq": "https://www.youtube.com/watch?v=BXuuCuuZtxM",
    "down-deeper-v2": "https://www.youtube.com/watch?v=_9b8AoJWFWc",
    "run-it-up": "https://www.youtube.com/watch?v=LPMqZqDPQaM",
    "da-ara": "https://www.youtube.com/watch?v=iWvB7L3Q5hY",
}

API = "http://127.0.0.1:9000"


def wait_ready() -> dict:
    last = None
    for _ in range(120):
        try:
            response = requests.get(API, timeout=2)
            last = {"status": response.status_code, "text": response.text[:2000]}
            if response.ok:
                return response.json()
        except Exception as exc:  # noqa: BLE001
            last = {"error": f"{type(exc).__name__}: {exc}"}
        time.sleep(1)
    raise RuntimeError(f"cobalt did not become ready: {last}")


result: dict[str, object] = {"instance": wait_ready(), "videos": {}}
for key, source_url in VIDEOS.items():
    row: dict[str, object] = {"source_url": source_url}
    try:
        response = requests.post(
            API,
            json={
                "url": source_url,
                "downloadMode": "audio",
                "audioFormat": "wav",
                "audioBitrate": "128",
                "filenameStyle": "basic",
                "disableMetadata": True,
                "localProcessing": "disabled",
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=120,
        )
        row["http_status"] = response.status_code
        row["headers"] = {
            "content_type": response.headers.get("content-type"),
            "rate_limit": response.headers.get("ratelimit-limit"),
            "rate_remaining": response.headers.get("ratelimit-remaining"),
        }
        payload = response.json()
        row["payload"] = payload
        target = payload.get("url") if isinstance(payload, dict) else None
        if target:
            parsed = urlparse(target)
            row["target"] = {
                "scheme": parsed.scheme,
                "host": parsed.netloc,
                "path": parsed.path,
                "query_keys": sorted({part.partition("=")[0] for part in parsed.query.split("&") if part}),
            }
            # Validate that the returned resource is readable, but do not retain media.
            with requests.get(target, stream=True, timeout=60) as media:
                row["media_status"] = media.status_code
                row["media_headers"] = {
                    "content_type": media.headers.get("content-type"),
                    "content_length": media.headers.get("content-length"),
                    "estimated_content_length": media.headers.get("estimated-content-length"),
                    "accept_ranges": media.headers.get("accept-ranges"),
                }
                first = next(media.iter_content(65536), b"")
                row["first_chunk_bytes"] = len(first)
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    result["videos"][key] = row

print(json.dumps(result, ensure_ascii=False, indent=2))
with open("karaoke/cobalt-probe.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
