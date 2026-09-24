from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

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

OUT = Path("karaoke/public-transcript-api-output")
OUT.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    }
)


def get(url: str, *, headers: dict[str, str] | None = None, timeout: int = 45) -> dict[str, Any]:
    try:
        response = SESSION.get(url, headers=headers or {}, timeout=timeout, allow_redirects=True)
        body = response.text
        parsed: Any
        try:
            parsed = response.json()
        except Exception:
            parsed = body
        return {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "url": response.url,
            "body": parsed if not isinstance(parsed, str) else parsed[:100_000],
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    results: dict[str, Any] = {}

    demo_key_result = get("https://youtube2text.org/api/demo-key")
    demo_key = None
    body = demo_key_result.get("body")
    if isinstance(body, dict):
        demo_key = body.get("apiKey")

    for name, video_id in VIDEOS.items():
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        encoded_url = quote(youtube_url, safe="")
        item: dict[str, Any] = {}

        item["freetranscriptapi_id"] = get(
            f"https://api.freetranscriptapi.com/v1/transcript?video_url={video_id}"
        )
        item["freetranscriptapi_url"] = get(
            f"https://api.freetranscriptapi.com/v1/transcript?video_url={encoded_url}"
        )
        item["tubetext"] = get(
            f"https://tubetext.vercel.app/youtube/transcript-with-timestamps?video_id={video_id}"
        )
        item["youtube_transcript_ai"] = get(
            f"https://youtube-transcript.ai/transcript/{video_id}.txt?lang=ko"
        )
        item["transcriptapi_io"] = get(
            f"https://api.transcriptapi.io/transcript?video_id={video_id}"
        )
        item["vcyon"] = get(
            f"https://vcyon.com/v1/youtube/transcript?videoId={video_id}"
        )
        if demo_key:
            item["youtube2text"] = get(
                f"https://youtube2text.org/api/transcribe?url={encoded_url}&maxChars=100000",
                headers={"x-api-key": demo_key},
                timeout=90,
            )
        else:
            item["youtube2text"] = {"demo_key_error": demo_key_result}

        results[name] = item
        (OUT / f"{name}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        time.sleep(1)

    summary = {
        "generated_at_epoch": int(time.time()),
        "demo_key": bool(demo_key),
        "videos": VIDEOS,
        "results": results,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
