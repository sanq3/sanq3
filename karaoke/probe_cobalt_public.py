from __future__ import annotations

import json
from urllib.parse import urlparse

import requests

# Opt-in public API instances listed by cobalt.directory for YouTube support.
# Root metadata is checked first. Authentication/Turnstile is never bypassed.
CANDIDATES = [
    "https://bergung-api.hoffnungfuerdiezukunft.net",
    "https://cobalt-alpha.wolfy.love",
    "https://lime.clxxped.lol",
    "https://nuko-c.meowing.de",
    "https://cobalt-api.lamps-dev.dev",
    "https://kitty.tame.gg",
    "https://grapefruit.clxxped.lol",
    "https://subito-c.meowing.de",
    "https://api.qwkuns.me",
    "https://api-cobalt.eversiege.network",
    "https://apicobalt.mgytr.top",
    "https://melon.clxxped.lol",
]

SOURCES = {
    "youtube-heart-crack": "https://www.youtube.com/watch?v=qNfdEAzXImE",
    "bilibili-heart-crack": "https://www.bilibili.com/video/BV1TnQ6BXEU6/",
}

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "sanq3-korean-lyrics-study/1.2 (+https://github.com/sanq3/sanq3)",
}


def inspect_target(target: str) -> dict[str, object]:
    parsed = urlparse(target)
    info: dict[str, object] = {
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path": parsed.path,
    }
    try:
        with requests.get(
            target,
            headers={"User-Agent": HEADERS["User-Agent"]},
            stream=True,
            timeout=60,
        ) as media:
            info["status"] = media.status_code
            info["headers"] = {
                "content_type": media.headers.get("content-type"),
                "content_length": media.headers.get("content-length"),
                "estimated_content_length": media.headers.get("estimated-content-length"),
                "accept_ranges": media.headers.get("accept-ranges"),
            }
            info["first_chunk_bytes"] = len(next(media.iter_content(65536), b""))
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


result: dict[str, object] = {"instances": {}, "post_attempts": 0}
post_attempts = 0

for api in CANDIDATES:
    row: dict[str, object] = {"api": api, "source_results": {}}
    try:
        info = requests.get(
            api,
            headers={"User-Agent": HEADERS["User-Agent"]},
            timeout=15,
        )
        row["info_status"] = info.status_code
        info_payload = (
            info.json()
            if "json" in info.headers.get("content-type", "")
            else {"raw": info.text[:2000]}
        )
        row["info"] = info_payload
        cobalt = info_payload.get("cobalt", {}) if isinstance(info_payload, dict) else {}
        services = cobalt.get("services") or []
        protected = bool(cobalt.get("turnstileSitekey"))
        row["protected"] = protected
        row["services"] = services

        # Only use instances that openly advertise the requested service and
        # do not expose an auth challenge. Limit total POSTs to keep load tiny.
        if protected or post_attempts >= 6:
            result["instances"][api] = row
            continue

        for source_key, source_url in SOURCES.items():
            service = "bilibili" if "bilibili" in source_key else "youtube"
            if service not in services or post_attempts >= 6:
                continue
            post_attempts += 1
            source_row: dict[str, object] = {"source_url": source_url}
            try:
                response = requests.post(
                    api,
                    headers=HEADERS,
                    json={
                        "url": source_url,
                        "downloadMode": "audio",
                        "audioFormat": "wav",
                        "audioBitrate": "128",
                        "filenameStyle": "basic",
                        "disableMetadata": True,
                        "localProcessing": "disabled",
                    },
                    timeout=120,
                )
                source_row["http_status"] = response.status_code
                source_row["rate_limit"] = {
                    "limit": response.headers.get("ratelimit-limit"),
                    "remaining": response.headers.get("ratelimit-remaining"),
                    "reset": response.headers.get("ratelimit-reset"),
                }
                payload = (
                    response.json()
                    if "json" in response.headers.get("content-type", "")
                    else {"raw": response.text[:4000]}
                )
                source_row["payload"] = payload
                target = payload.get("url") if isinstance(payload, dict) else None
                if target:
                    source_row["target"] = inspect_target(target)
            except Exception as exc:  # noqa: BLE001 - diagnostics only
                source_row["error"] = f"{type(exc).__name__}: {exc}"
            row["source_results"][source_key] = source_row
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        row["error"] = f"{type(exc).__name__}: {exc}"
    result["instances"][api] = row

result["post_attempts"] = post_attempts
with open("karaoke/cobalt-public-probe.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
