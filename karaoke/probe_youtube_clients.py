from __future__ import annotations

import json
import subprocess
from pathlib import Path

VIDEOS = {
    "heart-crack": "qNfdEAzXImE",
    "down-deeper-hq": "BXuuCuuZtxM",
    "da-ara": "iWvB7L3Q5hY",
}

CLIENTS = [
    "web_embedded",
    "tv",
    "tv_downgraded",
    "tv_simply",
    "visionos",
    "web_safari",
    "mweb",
    "android_vr",
]

OUT = Path("karaoke/youtube-client-output")
OUT.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", (exc.stderr or "") + "\nTIMEOUT")


results: dict[str, object] = {}
for key, video_id in VIDEOS.items():
    url = f"https://www.youtube.com/watch?v={video_id}"
    attempts = []
    for client in CLIENTS:
        proc = run([
            "yt-dlp",
            "--no-warnings",
            "--skip-download",
            "--dump-single-json",
            "--add-header", "Referer:https://www.reddit.com/",
            "--extractor-args", f"youtube:player_client={client}",
            url,
        ])
        row: dict[str, object] = {
            "client": client,
            "returncode": proc.returncode,
            "stderr": proc.stderr[-3000:],
        }
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout)
                row.update({
                    "title": data.get("title"),
                    "duration": data.get("duration"),
                    "format_count": len(data.get("formats") or []),
                    "subtitle_languages": sorted((data.get("subtitles") or {}).keys()),
                    "automatic_caption_languages": sorted((data.get("automatic_captions") or {}).keys()),
                    "audio_formats": [
                        {
                            "format_id": f.get("format_id"),
                            "ext": f.get("ext"),
                            "acodec": f.get("acodec"),
                            "vcodec": f.get("vcodec"),
                            "protocol": f.get("protocol"),
                            "url_host": (f.get("url") or "").split("/")[2] if str(f.get("url") or "").startswith("http") else None,
                        }
                        for f in (data.get("formats") or [])
                        if f.get("acodec") not in (None, "none")
                    ][:20],
                })
            except json.JSONDecodeError as exc:
                row["parse_error"] = str(exc)
        attempts.append(row)
    results[key] = {"video_id": video_id, "attempts": attempts}

(OUT / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
