from __future__ import annotations

import json
import time
from pathlib import Path

import requests

VIDEOS = {
    "heart-crack": "qNfdEAzXImE",
    "halo-error": "BEzKZ12Heto",
    "show-it": "yaXhmBfxGJY",
    "down-deeper-hq": "BXuuCuuZtxM",
    "down-deeper-v2": "_9b8AoJWFWc",
    "run-it-up": "LPMqZqDPQaM",
    "da-ara": "iWvB7L3Q5hY",
}

API = "https://notegpt.io/api/v2/video-transcript-v2"
OUT = Path("karaoke/notegpt-transcripts")
OUT.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "sanq3-korean-lyrics-study/1.0 (+https://github.com/sanq3/sanq3)",
    "Referer": "https://notegpt.io/youtube-to-transcript",
}

summary: dict[str, object] = {}
for index, (key, video_id) in enumerate(VIDEOS.items()):
    row: dict[str, object] = {"video_id": video_id}
    try:
        response = requests.get(
            API,
            params={"platform": "youtube", "video_id": video_id},
            headers=HEADERS,
            timeout=120,
        )
        row["http_status"] = response.status_code
        row["content_type"] = response.headers.get("content-type")
        payload = response.json()
        row["code"] = payload.get("code")
        row["message"] = payload.get("message")
        data = payload.get("data") or {}
        row["video_info"] = data.get("videoInfo")
        row["language_code"] = data.get("language_code")
        transcripts = data.get("transcripts") or {}
        row["transcript_keys"] = sorted(transcripts)
        row["segment_counts"] = {
            lang: {
                name: len(items) if isinstance(items, list) else None
                for name, items in body.items()
            }
            for lang, body in transcripts.items()
            if isinstance(body, dict)
        }
        (OUT / f"{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    summary[key] = row
    if index + 1 < len(VIDEOS):
        time.sleep(2)

(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
