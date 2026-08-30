"""PAPER-S6/S18 follow-up: bounded, rate-limited acquisition of a screening batch
from the docx-corpus remote candidate pool, per the answered HITL
(f24d8e0e-bdf4-47df-81b8-f0392fca954b, 2026-08-30): "Approve a bounded
acquisition of metadata-listed candidates, subject to per-file rights/
privacy/exposure adjudication and no redistribution."

Scope, deliberately bounded: 500 documents (not the full 18,680-record
pool), stratified by the pool's own `type` field toward equation-likelier
categories (technical/reports/reference over policies), sampled with a
fixed seed for reproducibility. This is a SCREENING acquisition only -- no
file this script downloads enters product-linked development or the
primary benchmark without the full S6 rights/privacy/exposure/independent-
gold/Word-receipt pipeline. Excludes the 90 IDs already sampled and
reviewed (raw/docx-corpus/sample_90.json, 0/90 had OMML).

Rate-limited to be polite to the remote host (docxcorp.us): sequential
requests, 1 request/second, a real User-Agent identifying this as a
research screening pull, a short per-request timeout, and a single retry
on transient failure. Never redistributes fetched content; every fetched
file stays under local E: storage per this project's storage-boundary
convention.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_CANDIDATES_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\filtered_candidates.json")
_SAMPLE90_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\sample_90.json")
_OUT_DIR = Path(r"E:\MeridianData\ooxml-graph-paper\raw\docx-corpus\batch-500-v1")
_MANIFEST_PATH = Path(r"E:\MeridianData\ooxml-graph-paper\manifests\docxcorpus-batch-500-v1.json")

_SEED = 20260830
_BATCH_SIZE = 500
_TYPE_QUOTAS = {"technical": 200, "reports": 125, "reference": 100, "policies": 75}
_REQUEST_DELAY_SECONDS = 1.0
_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "ooxml-graph-paper-research-screening/1.0 (bounded academic screening pull; contact: local research use only)"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _select_batch() -> list[dict[str, Any]]:
    candidates = json.loads(_CANDIDATES_PATH.read_text(encoding="utf-8"))
    already = {r["id"] for r in json.loads(_SAMPLE90_PATH.read_text(encoding="utf-8"))}
    remaining = [r for r in candidates if r["id"] not in already]

    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in remaining:
        by_type.setdefault(r.get("type", "unknown"), []).append(r)

    rng = random.Random(_SEED)
    batch: list[dict[str, Any]] = []
    for type_name, quota in _TYPE_QUOTAS.items():
        pool = by_type.get(type_name, [])
        rng.shuffle(pool)
        batch.extend(pool[:quota])

    assert len(batch) == sum(min(len(by_type.get(t, [])), q) for t, q in _TYPE_QUOTAS.items())
    return batch


def _fetch_one(record: dict[str, Any]) -> dict[str, Any]:
    url = record["url"]
    dest = _OUT_DIR / f"{record['id']}.docx"
    entry: dict[str, Any] = {
        "id": record["id"],
        "url": url,
        "type": record.get("type"),
        "topic": record.get("topic"),
        "requested_at": None,
        "http_status": None,
        "sha256": None,
        "byte_size": None,
        "local_path": None,
        "error": None,
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

    batch = _select_batch()
    print(f"Selected {len(batch)} candidates (quota: {_TYPE_QUOTAS}), seed={_SEED}", flush=True)

    results: list[dict[str, Any]] = []
    ok = 0
    for i, record in enumerate(batch, 1):
        entry = _fetch_one(record)
        results.append(entry)
        if entry["local_path"]:
            ok += 1
        if i % 25 == 0 or i == len(batch):
            print(f"  [{i}/{len(batch)}] ok={ok} last={entry['id'][:12]} status={entry['http_status']} err={entry['error']}", flush=True)
        time.sleep(_REQUEST_DELAY_SECONDS)

    manifest = {
        "schema": "docxcorpus-batch-500-v1",
        "hitl_authorization": "f24d8e0e-bdf4-47df-81b8-f0392fca954b (answered 2026-08-30, Adam): bounded acquisition, screening only, no redistribution, per-file rights/privacy/exposure adjudication required before any product-linked use",
        "seed": _SEED,
        "batch_size_requested": _BATCH_SIZE,
        "type_quotas": _TYPE_QUOTAS,
        "excluded_already_sampled_count": 90,
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
