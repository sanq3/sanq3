from __future__ import annotations

import json
import subprocess
from pathlib import Path

QUERIES = {
    "heart-crack": "Heart Crack LIMU99 오늘의 한요일은 여자다",
    "halo-error": "Halo Error 이루하 오늘의 한요일은 여자다",
    "show-it": "Show It 월평 A팀 오늘의 한요일은 여자다",
    "down-deeper": "Down Deeper 6월 월말평가 B팀 오늘의 한요일은 여자다",
    "run-it-up": "Run It Up 5월 월평 D팀 오늘의 한요일은 여자다",
    "da-ara": "다 알아 박소애 오늘의 한요일은 여자다",
}

KNOWN = {
    "heart-crack-a": "https://www.bilibili.com/video/BV19rDTBNEHs/",
    "heart-crack-b": "https://www.bilibili.com/video/BV1ZEMJ6gEf9/",
    "down-deeper": "https://www.bilibili.com/video/BV1yUMJ6SEFk/",
}

OUT = Path("karaoke/bilibili-output")
OUT.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", (exc.stderr or "") + "\nTIMEOUT")


result: dict[str, object] = {"searches": {}, "known": {}}

for key, query in QUERIES.items():
    proc = run([
        "yt-dlp",
        "--no-warnings",
        "--flat-playlist",
        "--playlist-end", "20",
        "--dump-json",
        f"bilisearch20:{query}",
    ])
    rows: list[dict[str, object]] = []
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            "id": data.get("id"),
            "title": data.get("title"),
            "url": data.get("url") or data.get("webpage_url"),
            "duration": data.get("duration"),
            "uploader": data.get("uploader"),
        })
    result["searches"][key] = {
        "query": query,
        "returncode": proc.returncode,
        "stderr": proc.stderr[-4000:],
        "results": rows,
    }

for key, url in KNOWN.items():
    proc = run([
        "yt-dlp",
        "--no-warnings",
        "--skip-download",
        "--dump-single-json",
        url,
    ])
    row: dict[str, object] = {
        "url": url,
        "returncode": proc.returncode,
        "stderr": proc.stderr[-4000:],
    }
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            row.update({
                "id": data.get("id"),
                "title": data.get("title"),
                "duration": data.get("duration"),
                "uploader": data.get("uploader"),
                "formats": [
                    {
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "acodec": f.get("acodec"),
                        "vcodec": f.get("vcodec"),
                        "abr": f.get("abr"),
                        "height": f.get("height"),
                    }
                    for f in (data.get("formats") or [])
                ],
            })
        except json.JSONDecodeError as exc:
            row["parse_error"] = str(exc)
    result["known"][key] = row

(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
