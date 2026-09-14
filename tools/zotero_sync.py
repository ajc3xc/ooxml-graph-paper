#!/usr/bin/env python3
"""
Generalized Zotero <-> LaTeX bibliography sync, against Zotero's LOCAL HTTP
API (the desktop app must be running on this machine -- there is no headless/
remote path, see the "no bypass" note in `ensure_write_authorized` below).
Not hardcoded to one paper: every path/name is a CLI argument.

Two surfaces of the local API, confirmed empirically against Zotero 10.0.1:
  * ``/api/...``          -- read: full Web-API-compatible item/collection
    reads, including ``format=bibtex`` export. Unauthenticated (any local
    process can read the library).
  * ``/api/local/...``    -- write: requires an interactive human "Allow"
    click in the running Zotero app the FIRST time (``/local/authorize``,
    Zotero-Server-ID header from a prior GET's response header). The
    resulting key is then remembered per-profile (not scoped to the
    requesting app), so a key obtained once by any tool keeps working for
    any other local tool afterward -- this script tries the existing
    ZOTERO_LOCAL_API_KEY from .env first and only triggers a fresh popup if
    that key no longer works.

Requires: pip install httpx python-dotenv
Reads ZOTERO_LOCAL_API_KEY from a local .env -- checked in this repo root
first, falling back to the dnabert-error-correction project's .env where a
key from an earlier Zotero setup already lives. Never printed, logged, or
passed on the command line.

Usage:
    python zotero_sync.py list-collections
    python zotero_sync.py ensure-collection --name "OOXML-Graph Paper"
    python zotero_sync.py check --tex ../paper/main.tex --bib ../paper/refs.bib
    python zotero_sync.py sync --collection "OOXML-Graph Paper" --bib ../paper/refs.bib
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
FALLBACK_ENV_PATH = Path(r"C:\Users\13144\Documents\dnabert-error-correction\.env")

BASE = "http://127.0.0.1:23119/api"
LOCAL_USER = "0"
APP_NAME = "ooxml-graph-paper/zotero_sync.py"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv(REPO_ROOT / ".env")
load_dotenv(FALLBACK_ENV_PATH)


def get_server_id(client: httpx.Client) -> str:
    """A HEAD request does NOT return this header -- must be a real GET."""
    resp = client.get(f"{BASE}/users/{LOCAL_USER}/items", params={"limit": 1})
    server_id = resp.headers.get("Zotero-Server-ID")
    if not server_id:
        sys.exit("No Zotero-Server-ID header -- is the Zotero desktop app running "
                  "with the local API enabled (Settings > Advanced)?")
    return server_id


def request_fresh_authorization(client: httpx.Client, server_id: str) -> str:
    """POST /local/authorize -- pops an Allow/Always Allow dialog in the
    running Zotero app EVERY time it's called, by design (this is the
    bootstrap step, not a silent validity check -- never call this just to
    "probe" an existing key). There is no way to script past that click;
    this blocks (long timeout) until the human answers it."""
    print("Requesting Zotero authorization -- check the desktop app for an "
          "Allow/Always Allow dialog and click it now.", file=sys.stderr)
    resp = client.post(
        f"{BASE}/local/authorize",
        headers={"Zotero-Server-ID": server_id},
        json={"appName": APP_NAME},
        timeout=120.0,  # human has to click; give real time
    )
    resp.raise_for_status()
    key = resp.json()["key"]
    print("Authorized. Add this to your .env so future runs skip the popup:\n"
          "  ZOTERO_LOCAL_API_KEY=<the key just granted -- not printed here>",
          file=sys.stderr)
    return key


def write_with_auth(client: httpx.Client, server_id: str, method: str, url: str, **kw) -> httpx.Response:
    """Try the existing ZOTERO_LOCAL_API_KEY from .env directly on a real
    write call first (authorizations persist per-profile, not per-app, so a
    key obtained by any prior local tool should still work with no popup).
    Only on an actual auth failure (401/403) does this fall through to
    /local/authorize."""
    existing = os.environ.get("ZOTERO_LOCAL_API_KEY")
    if existing:
        resp = client.request(method, url, headers={"Zotero-Server-ID": server_id,
                                                      "Zotero-API-Key": existing}, **kw)
        if resp.status_code not in (401, 403):
            return resp

    key = request_fresh_authorization(client, server_id)
    return client.request(method, url, headers={"Zotero-Server-ID": server_id,
                                                  "Zotero-API-Key": key}, **kw)


def list_collections(client: httpx.Client) -> list[dict]:
    resp = client.get(f"{BASE}/users/{LOCAL_USER}/collections", params={"format": "json"})
    resp.raise_for_status()
    return resp.json()


def find_collection(client: httpx.Client, name: str) -> dict | None:
    for c in list_collections(client):
        if c.get("data", {}).get("name") == name:
            return c
    return None


def create_collection(client: httpx.Client, name: str, server_id: str) -> dict:
    resp = write_with_auth(client, server_id, "POST", f"{BASE}/users/{LOCAL_USER}/collections",
                            json=[{"name": name}])
    resp.raise_for_status()
    body = resp.json()
    # Web-API-shaped response: {"successful": {"0": {...item...}}, ...}
    successful = body.get("successful", {})
    if not successful:
        sys.exit(f"Collection creation did not report success: {json.dumps(body)}")
    return next(iter(successful.values()))


CITE_RE = re.compile(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear)\{([^}]*)\}")


def scan_tex_cite_keys(tex_path: Path) -> set[str]:
    text = tex_path.read_text(encoding="utf-8")
    keys: set[str] = set()
    for m in CITE_RE.finditer(text):
        for k in m.group(1).split(","):
            k = k.strip()
            if k:
                keys.add(k)
    return keys


def scan_bib_keys(bib_path: Path) -> set[str]:
    if not bib_path.exists():
        return set()
    text = bib_path.read_text(encoding="utf-8")
    return set(re.findall(r"@\w+\{([^,\s]+),", text))


def cmd_list_collections(args: argparse.Namespace) -> None:
    with httpx.Client(timeout=10.0) as client:
        for c in list_collections(client):
            print(c["data"]["key"], c["data"]["name"])


def cmd_ensure_collection(args: argparse.Namespace) -> None:
    with httpx.Client(timeout=10.0) as client:
        existing = find_collection(client, args.name)
        if existing:
            print(f"Already exists: {existing['data']['key']} {args.name}")
            return
        server_id = get_server_id(client)
        created = create_collection(client, args.name, server_id)
        print(f"Created: {created['data']['key']} {args.name}")


def cmd_check(args: argparse.Namespace) -> None:
    tex_keys = scan_tex_cite_keys(Path(args.tex))
    bib_keys = scan_bib_keys(Path(args.bib))
    missing = sorted(tex_keys - bib_keys)
    unused = sorted(bib_keys - tex_keys)
    print(f"{len(tex_keys)} cite key(s) in {args.tex}, {len(bib_keys)} entr{'y' if len(bib_keys)==1 else 'ies'} in {args.bib}")
    if missing:
        print(f"MISSING from bib ({len(missing)}): {', '.join(missing)}")
    if unused:
        print(f"Unused in tex ({len(unused)}): {', '.join(unused)}")
    if not missing and not unused:
        print("Consistent: every cited key has a bib entry, no unused entries.")
    sys.exit(1 if missing else 0)


BIBTEX_KEY_HINT_RE = re.compile(r"bibtex-key:\s*([^\s,}]+)")
BIB_ENTRY_HEADER_RE = re.compile(r"^(@\w+\{)([^,\s]+)(,)", re.MULTILINE)
BIB_NOTE_FIELD_RE = re.compile(r"\n\tnote = \{([^}]*)\},")


def remap_citekeys(bibtex: str) -> str:
    """Rewrite each entry's auto-generated Zotero citekey to the stable key
    recorded in its own ``note = {...bibtex-key: X...}`` field (written by
    this project's item-seeding step), so existing \\cite{} calls in a .tex
    file keep working after a Zotero re-sync instead of silently breaking.
    Entries with no hint keep their Zotero-generated key unchanged. The
    ``bibtex-key: X`` marker itself is internal plumbing, not something a
    reader should see, so it's stripped out of the emitted note/extra text
    (any other real note content on its own line is kept)."""
    entries = re.split(r"(?=^@\w+\{)", bibtex, flags=re.MULTILINE)
    out = []
    for entry in entries:
        m = BIBTEX_KEY_HINT_RE.search(entry)
        if m:
            stable_key = m.group(1)
            entry = BIB_ENTRY_HEADER_RE.sub(rf"\g<1>{stable_key}\g<3>", entry, count=1)
            entry = strip_bibtex_key_hint(entry)
        out.append(entry)
    return "".join(out)


def strip_bibtex_key_hint(entry: str) -> str:
    """Remove the ``bibtex-key: X`` marker from a note/extra field, along
    with the field entirely if nothing else was in it."""
    m = BIB_NOTE_FIELD_RE.search(entry)
    if not m:
        return entry
    remaining_lines = [
        line for line in m.group(1).splitlines()
        if not line.strip().lower().startswith("bibtex-key:")
    ]
    remaining = "\n".join(remaining_lines).strip()
    replacement = f"\n\tnote = {{{remaining}}}," if remaining else ""
    return entry[: m.start()] + replacement + entry[m.end():]


def cmd_sync(args: argparse.Namespace) -> None:
    with httpx.Client(timeout=10.0) as client:
        coll = find_collection(client, args.collection)
        if not coll:
            sys.exit(f"No Zotero collection named {args.collection!r} -- run "
                      f"ensure-collection first.")
        key = coll["data"]["key"]
        resp = client.get(f"{BASE}/users/{LOCAL_USER}/collections/{key}/items",
                           params={"format": "bibtex"})
        resp.raise_for_status()
        text = remap_citekeys(resp.text)
        Path(args.bib).write_text(text, encoding="utf-8")
        n = text.count("@")
        print(f"Wrote {n} entr{'y' if n==1 else 'ies'} from {args.collection!r} to {args.bib}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-collections").set_defaults(func=cmd_list_collections)

    p = sub.add_parser("ensure-collection", help="Create a Zotero collection if it doesn't exist")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_ensure_collection)

    p = sub.add_parser("check", help="Report cite{}-keys missing from / unused in the .bib")
    p.add_argument("--tex", required=True)
    p.add_argument("--bib", required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("sync", help="Overwrite a .bib file with a Zotero collection's export")
    p.add_argument("--collection", required=True)
    p.add_argument("--bib", required=True)
    p.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
