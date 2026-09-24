from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode

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

BASES = [
    "https://www.youtube.com/api/timedtext",
    "https://video.google.com/timedtext",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.youtube.com/",
}

OUT = Path("karaoke/youtube-timedtext-output")
OUT.mkdir(parents=True, exist_ok=True)


def get(url: str, params: dict[str, str]) -> dict[str, object]:
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        return {
            "url": response.url,
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "length": len(response.content),
            "text": response.text[:20000],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


result: dict[str, object] = {}
for key, video_id in VIDEOS.items():
    row: dict[str, object] = {"video_id": video_id, "attempts": []}
    for base in BASES:
        row["attempts"].append({
            "kind": "list",
            "base": base,
            **get(base, {"type": "list", "v": video_id}),
        })
        for lang in ("ko", "en", "ja"):
            for kind in (None, "asr"):
                params = {"v": video_id, "lang": lang, "fmt": "json3"}
                if kind:
                    params["kind"] = kind
                row["attempts"].append({
                    "kind": f"caption-{lang}-{kind or 'manual'}",
                    "base": base,
                    **get(base, params),
                })
    result[key] = row

(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
