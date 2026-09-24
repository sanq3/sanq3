from __future__ import annotations

import json
import subprocess
from pathlib import Path

VIDEOS = {
    "heart-crack": "qNfdEAzXImE",
    "halo-error": "BEzKZ12Heto",
    "show-it": "yaXhmBfxGJY",
    "down-deeper-hq": "BXuuCuuZtxM",
    "down-deeper-v2": "_9b8AoJWFWc",
    "run-it-up": "LPMqZqDPQaM",
    "da-ara": "iWvB7L3Q5hY",
}

OUT = Path("karaoke/probe-output")
OUT.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


results: dict[str, object] = {}
for key, video_id in VIDEOS.items():
    url = f"https://www.youtube.com/watch?v={video_id}"
    item: dict[str, object] = {"video_id": video_id, "url": url}

    # Metadata and subtitle inventory. Try a small set of official player clients;
    # no cookies, credentials, or user data are used.
    clients = ["web", "android", "ios"]
    metadata = None
    errors: list[dict[str, object]] = []
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
                item["metadata_client"] = client
                break
            except json.JSONDecodeError as exc:
                errors.append({"client": client, "error": f"invalid JSON: {exc}", "stderr": proc.stderr[-2000:]})
        else:
            errors.append({"client": client, "returncode": proc.returncode, "stderr": proc.stderr[-4000:]})

    if metadata is not None:
        item.update({
            "title": metadata.get("title"),
            "duration": metadata.get("duration"),
            "channel": metadata.get("channel"),
            "availability": metadata.get("availability"),
            "live_status": metadata.get("live_status"),
            "subtitles": sorted((metadata.get("subtitles") or {}).keys()),
            "automatic_captions": sorted((metadata.get("automatic_captions") or {}).keys()),
            "webpage_url": metadata.get("webpage_url"),
        })
    item["errors"] = errors
    results[key] = item

(OUT / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
