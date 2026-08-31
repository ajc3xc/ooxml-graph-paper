"""PAPER-S6 follow-up round 3: same topic-stratified acquisition pattern as
round 2, excluding everything fetched in the 90-sample, round 1 (batch-500),
and round 2 (batch-2, 3133 docs). Round 2 found 16 organic-OMML hits across 4
distinct topics (technology, environment, finance, government) out of 3133
documents (~0.51%), against zero hits in the other 4 topics (education,
general, nonprofit, legal_judicial) at n=400 each -- real, informative
signal, not noise. This round adds another 400/topic (or the remaining pool,
whichever is smaller) to both push the raw organic-unit count further past
the >=24 gate and get more evidence on whether the zero-hit topics are
genuinely at ~0% or merely unlucky at n=400.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_CANDIDATES_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\filtered_candidates.json")
_SAMPLE90_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\sample_90.json")
_BATCH500_MANIFEST_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\manifests\docxcorpus-batch-500-v1.json")
_BATCH2_MANIFEST_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\manifests\docxcorpus-batch-2-v1.json")
_OUT_DIR = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\batch-3-v1")
_MANIFEST_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\manifests\docxcorpus-batch-3-v1.json")

_SEED = 20260831001
_TOPIC_QUOTA = 400
_REQUEST_DELAY_SECONDS = 1.0
_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "ooxml-graph-paper-research-screening/1.0 (bounded academic screening pull; contact: local research use only)"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _select_batch() -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates = json.loads(_CANDIDATES_PATH.read_text(encoding="utf-8"))
    already = {r["id"] for r in json.loads(_SAMPLE90_PATH.read_text(encoding="utf-8"))}
    already |= {e["id"] for e in json.loads(_BATCH500_MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]}
    already |= {e["id"] for e in json.loads(_BATCH2_MANIFEST_PATH.read_text(encoding="utf-8"))["entries"]}
    remaining = [r for r in candidates if r["id"] not in already]

    by_topic: dict[str, list[dict[str, Any]]] = {}
    for r in remaining:
        by_topic.setdefault(r.get("topic", "unknown"), []).append(r)

    rng = random.Random(_SEED)
    batch: list[dict[str, Any]] = []
    quotas_applied: dict[str, int] = {}
    for topic_name, pool in sorted(by_topic.items()):
        rng.shuffle(pool)
        take = min(len(pool), _TOPIC_QUOTA)
        batch.extend(pool[:take])
        quotas_applied[topic_name] = take

    return batch, quotas_applied


def _fetch_one(record: dict[str, Any]) -> dict[str, Any]:
    url = record["url"]
    dest = _OUT_DIR / f"{record['id']}.docx"
    entry: dict[str, Any] = {
        "id": record["id"], "url": url, "type": record.get("type"), "topic": record.get("topic"),
        "requested_at": None, "http_status": None, "sha256": None, "byte_size": None,
        "local_path": None, "error": None,
    }
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    for attempt in range(2):
        entry["requested_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                entry["http_status"] = resp.status
                data = resp.read()
            if entry["http_status"] == 200 and data:
                dest.write_bytes(data)
                entry["sha256"] = _sha256_bytes(data)
                entry["byte_size"] = len(data)
                entry["local_path"] = str(dest)
            else:
                entry["error"] = f"unexpected status {entry['http_status']} or empty body"
            return entry
        except urllib.error.HTTPError as exc:
            entry["http_status"] = exc.code
            entry["error"] = f"HTTPError: {exc.code} {exc.reason}"
            if exc.code in (429, 503) and attempt == 0:
                time.sleep(5.0)
                continue
            return entry
        except (urllib.error.URLError, TimeoutError) as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                time.sleep(2.0)
                continue
            return entry
    return entry


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    batch, quotas_applied = _select_batch()
    print(f"Selected {len(batch)} candidates (per-topic quotas: {quotas_applied}), seed={_SEED}", flush=True)

    results: list[dict[str, Any]] = []
    ok = 0
    for i, record in enumerate(batch, 1):
        entry = _fetch_one(record)
        results.append(entry)
        if entry["local_path"]:
            ok += 1
        if i % 100 == 0 or i == len(batch):
            print(f"  [{i}/{len(batch)}] ok={ok} last={entry['id'][:12]} status={entry['http_status']} err={entry['error']}", flush=True)
        time.sleep(_REQUEST_DELAY_SECONDS)

    manifest = {
        "schema": "docxcorpus-batch-3-v1",
        "authorization": "same explicit user authorization as round 2 (2026-08-31): 'pursue much more acquisition'. Round 2 found 16 hits/3133 docs across 4 topics, informing this round's continuation.",
        "seed": _SEED,
        "topic_quota_per_topic": _TOPIC_QUOTA,
        "topic_quotas_applied": quotas_applied,
        "requested_count": len(batch),
        "successful_downloads": ok,
        "failed_downloads": len(batch) - ok,
        "entries": results,
    }
    _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. {ok}/{len(batch)} downloaded successfully.")
    print(f"Manifest: {_MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
