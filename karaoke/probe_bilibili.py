from __future__ import annotations

import json
import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

QUERIES = {
    "heart-crack": "Heart Crack LIMU99 오늘의 한요일은 여자다",
    "halo-error": "Halo Error 이루하 오늘의 한요일은 여자다",
    "show-it": "Show It 월평 A팀 오늘의 한요일은 여자다",
    "down-deeper": "Down Deeper 6월 월말평가 B팀 오늘의 한요일은 여자다",
    "run-it-up": "Run It Up 5월 월평 D팀 오늘의 한요일은 여자다",
    "da-ara": "다 알아 박소애 오늘의 한요일은 여자다",
}

KNOWN = {
    "heart-crack-a": "BV19rDTBNEHs",
    "heart-crack-b": "BV1ZEMJ6gEf9",
    "down-deeper": "BV1yUMJ6SEFk",
}

OUT = Path("karaoke/bilibili-output")
OUT.mkdir(parents=True, exist_ok=True)

BUVID3 = f"{uuid.uuid4()}infoc"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json,text/plain,*/*",
    "Cookie": f"buvid3={BUVID3}; CURRENT_FNVAL=4048; b_lsid={uuid.uuid4().hex[:16].upper()}",
}


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", (exc.stderr or "") + "\nTIMEOUT")


def api_get(path: str, params: dict[str, object]) -> tuple[dict | None, str | None]:
    try:
        response = requests.get(
            f"https://api.bilibili.com{path}",
            params=params,
            headers=HEADERS,
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            return None, f"API code {payload.get('code')}: {payload.get('message')}"
        return payload.get("data"), None
    except Exception as exc:  # noqa: BLE001 - diagnostic probe
        return None, f"{type(exc).__name__}: {exc}"


def resolve_aid(aid: str) -> dict[str, object]:
    data, error = api_get("/x/web-interface/view", {"aid": aid})
    if not isinstance(data, dict):
        return {"aid": aid, "error": error}
    pages = data.get("pages") or []
    first = pages[0] if pages else {}
    return {
        "aid": data.get("aid"),
        "bvid": data.get("bvid"),
        "title": data.get("title"),
        "duration": data.get("duration"),
        "owner_mid": (data.get("owner") or {}).get("mid"),
        "owner_name": (data.get("owner") or {}).get("name"),
        "cid": first.get("cid"),
        "description": data.get("desc"),
    }


def resolve_bvid(bvid: str) -> dict[str, object]:
    data, error = api_get("/x/web-interface/view", {"bvid": bvid})
    if not isinstance(data, dict):
        return {"bvid": bvid, "error": error}
    pages = data.get("pages") or []
    first = pages[0] if pages else {}
    row: dict[str, object] = {
        "aid": data.get("aid"),
        "bvid": data.get("bvid"),
        "title": data.get("title"),
        "duration": data.get("duration"),
        "owner_mid": (data.get("owner") or {}).get("mid"),
        "owner_name": (data.get("owner") or {}).get("name"),
        "cid": first.get("cid"),
        "description": data.get("desc"),
    }
    cid = first.get("cid")
    if cid:
        play, play_error = api_get(
            "/x/player/playurl",
            {
                "bvid": bvid,
                "cid": cid,
                "qn": 64,
                "fnver": 0,
                "fnval": 4048,
                "fourk": 0,
            },
        )
        if isinstance(play, dict):
            dash = play.get("dash") or {}
            durl = play.get("durl") or []
            row["playurl"] = {
                "quality": play.get("quality"),
                "format": play.get("format"),
                "timelength": play.get("timelength"),
                "audio": [
                    {
                        "id": a.get("id"),
                        "base_url_host": urlparse(a.get("baseUrl") or a.get("base_url") or "").netloc,
                        "bandwidth": a.get("bandwidth"),
                        "codecs": a.get("codecs"),
                        "mime_type": a.get("mimeType") or a.get("mime_type"),
                        "has_url": bool(a.get("baseUrl") or a.get("base_url")),
                    }
                    for a in (dash.get("audio") or [])
                ],
                "durl": [
                    {
                        "length": d.get("length"),
                        "size": d.get("size"),
                        "host": urlparse(d.get("url") or "").netloc,
                        "has_url": bool(d.get("url")),
                    }
                    for d in durl
                ],
            }
        else:
            row["playurl_error"] = play_error
    return row


result: dict[str, object] = {"searches": {}, "known": {}, "buvid3": BUVID3}

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
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw_id = str(data.get("id") or "")
        if not raw_id or raw_id in seen:
            continue
        seen.add(raw_id)
        if raw_id.isdigit():
            rows.append(resolve_aid(raw_id))
        else:
            match = re.search(r"BV[0-9A-Za-z]+", raw_id)
            rows.append(resolve_bvid(match.group(0)) if match else {"id": raw_id})
    result["searches"][key] = {
        "query": query,
        "returncode": proc.returncode,
        "stderr": proc.stderr[-4000:],
        "results": rows,
    }

for key, bvid in KNOWN.items():
    result["known"][key] = resolve_bvid(bvid)

(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
