from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests

# Public-source probe only: no cookies, credentials, or account data.
VIDEOS = {
    "heart-crack": "qNfdEAzXImE",
    "halo-error": "BEzKZ12Heto",
    "show-it": "yaXhmBfxGJY",
    "down-deeper-hq": "BXuuCuuZtxM",
    "down-deeper-v2": "_9b8AoJWFWc",
    "run-it-up": "LPMqZqDPQaM",
    "da-ara": "iWvB7L3Q5hY",
}

PIPED_APIS = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.reallyaweso.me",
    "https://pipedapi.privacy.com.de",
    "https://pipedapi.r4fo.com",
    "https://pipedapi.leptons.xyz",
]

INVIDIOUS_APIS = [
    "https://yewtu.be",
    "https://inv.nadeko.net",
    "https://invidious.private.coffee",
    "https://invidious.privacyredirect.com",
    "https://invidious.nerdvpn.de",
]

OUT = Path("karaoke/probe-output")
OUT.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def safe_get_json(url: str) -> tuple[dict | list | None, str | None]:
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 karaoke-source-probe/1.0"},
        )
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        return None, f"{type(exc).__name__}: {exc}"


results: dict[str, object] = {}
for key, video_id in VIDEOS.items():
    url = f"https://www.youtube.com/watch?v={video_id}"
    item: dict[str, object] = {"video_id": video_id, "url": url}

    # First try yt-dlp without authentication.
    clients = ["web", "android", "ios"]
    metadata = None
    yt_errors: list[dict[str, object]] = []
    for client in clients:
        proc = run([
            "yt-dlp",
            "--no-warnings",
            "--skip-download",
            "--dump-single-json",
            "--extractor-args",
            f"youtube:player_client={client}",
            url,
        ])
        if proc.returncode == 0:
            try:
                metadata = json.loads(proc.stdout)
                item["metadata_source"] = f"yt-dlp:{client}"
                break
            except json.JSONDecodeError as exc:
                yt_errors.append({"client": client, "error": f"invalid JSON: {exc}", "stderr": proc.stderr[-2000:]})
        else:
            yt_errors.append({"client": client, "returncode": proc.returncode, "stderr": proc.stderr[-2000:]})

    if metadata is not None:
        item.update({
            "title": metadata.get("title"),
            "duration": metadata.get("duration"),
            "channel": metadata.get("channel"),
            "availability": metadata.get("availability"),
            "subtitles": sorted((metadata.get("subtitles") or {}).keys()),
            "automatic_captions": sorted((metadata.get("automatic_captions") or {}).keys()),
        })
    item["yt_dlp_errors"] = yt_errors

    # Public Piped APIs can provide metadata and stream inventory without cookies.
    piped_attempts: list[dict[str, object]] = []
    for base in PIPED_APIS:
        data, error = safe_get_json(f"{base}/streams/{video_id}")
        attempt: dict[str, object] = {"host": urlparse(base).netloc}
        if isinstance(data, dict):
            audio_streams = data.get("audioStreams") or []
            subtitles = data.get("subtitles") or []
            attempt.update({
                "ok": True,
                "title": data.get("title"),
                "duration": data.get("duration"),
                "audio_stream_count": len(audio_streams),
                "subtitle_count": len(subtitles),
                "audio_mime_types": sorted({str(s.get("mimeType")) for s in audio_streams if s.get("mimeType")}),
            })
            piped_attempts.append(attempt)
            if not item.get("title"):
                item.update({
                    "metadata_source": f"piped:{urlparse(base).netloc}",
                    "title": data.get("title"),
                    "duration": data.get("duration"),
                    "channel": data.get("uploader"),
                    "subtitles": [s.get("code") or s.get("name") for s in subtitles],
                })
            break
        attempt.update({"ok": False, "error": error})
        piped_attempts.append(attempt)
    item["piped_attempts"] = piped_attempts

    # Invidious is a second independent public-source fallback.
    invidious_attempts: list[dict[str, object]] = []
    for base in INVIDIOUS_APIS:
        data, error = safe_get_json(f"{base}/api/v1/videos/{video_id}")
        attempt = {"host": urlparse(base).netloc}
        if isinstance(data, dict):
            adaptive = data.get("adaptiveFormats") or []
            captions = data.get("captions") or []
            attempt.update({
                "ok": True,
                "title": data.get("title"),
                "duration": data.get("lengthSeconds"),
                "adaptive_format_count": len(adaptive),
                "caption_count": len(captions),
            })
            invidious_attempts.append(attempt)
            if not item.get("title"):
                item.update({
                    "metadata_source": f"invidious:{urlparse(base).netloc}",
                    "title": data.get("title"),
                    "duration": data.get("lengthSeconds"),
                    "channel": data.get("author"),
                    "subtitles": [c.get("label") or c.get("languageCode") for c in captions],
                })
            break
        attempt.update({"ok": False, "error": error})
        invidious_attempts.append(attempt)
    item["invidious_attempts"] = invidious_attempts

    results[key] = item

(OUT / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
