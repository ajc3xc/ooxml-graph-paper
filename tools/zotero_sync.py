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
    python zotero_sync.py push --collection "OOXML-Graph Paper" --bib ../paper/refs.bib
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


BIB_ENTRY_BODY_RE = re.compile(r"@(\w+)\{([^,\s]+),\s*\n(.*?)\n\}", re.DOTALL)
BIB_FIELD_LINE_RE = re.compile(r"^\s*(\w+)\s*=\s*\{(.*)\},?\s*$", re.MULTILINE)

# BibTeX entry type -> Zotero itemType, matched to what's already in the
# "OOXML-Graph Paper" collection (confirmed by inspecting its live items):
# @article -> journalArticle, @inproceedings -> conferencePaper,
# @techreport -> report, @misc -> preprint (this file's @misc entries are all
# arXiv preprints). Anything else falls back to "document" rather than guessing.
_ENTRY_TYPE_TO_ITEM_TYPE = {
    "article": "journalArticle",
    "inproceedings": "conferencePaper",
    "techreport": "report",
    "misc": "preprint",
    "book": "book",
    "incollection": "bookSection",
}


def strip_bib_braces(s: str) -> str:
    """Drop BibTeX capitalization-protection braces (``{SWE}-bench`` ->
    ``SWE-bench``) -- Zotero fields are plain text, not BibTeX source."""
    return s.replace("{", "").replace("}", "")


def parse_bib_entries(text: str) -> list[dict]:
    """Parse ``@type{citekey, field = {value}, ...}`` entries.

    Assumes each field is one physical line (true of every entry this repo's
    refs.bib has ever contained) -- a value spanning multiple lines, or
    containing a literal unescaped ``}``, will not parse correctly.
    """
    entries = []
    for entry_type, citekey, body in BIB_ENTRY_BODY_RE.findall(text):
        fields = {m.group(1).lower(): m.group(2) for m in BIB_FIELD_LINE_RE.finditer(body)}
        entries.append({"type": entry_type.lower(), "citekey": citekey, "fields": fields})
    return entries


def parse_creators(author_field: str) -> list[dict]:
    """``"Last, First and Org Name and Last2, First2"`` -> Zotero creators.

    A ``"Last, First"`` pair becomes a person creator; anything with no comma
    (a bare organization name, e.g. ``"Ecma International"``) becomes a
    single-field ``name`` creator, matching Zotero's own convention (seen on
    the existing ``ecma376`` item in the collection).
    """
    creators = []
    for person in author_field.split(" and "):
        person = person.strip()
        if not person:
            continue
        if "," in person:
            last, _, first = person.partition(",")
            creators.append({"creatorType": "author", "firstName": first.strip(), "lastName": last.strip()})
        else:
            creators.append({"creatorType": "author", "name": person})
    return creators


def build_item_data(entry: dict, collection_key: str) -> dict | None:
    """Build a Zotero item-creation payload from one parsed bib entry.

    Field mapping matches what's already live in the collection: journal ->
    publicationTitle, number -> issue, note -> the first line(s) of extra,
    with a trailing ``bibtex-key: <citekey>`` line always appended so
    remap_citekeys (the read-path counterpart) can restore this exact citekey
    on a future ``sync`` pull instead of Zotero's auto-generated one.
    Returns ``None`` if the entry has no title (nothing usable to create).
    """
    f = entry["fields"]
    citekey = entry["citekey"]
    item_type = _ENTRY_TYPE_TO_ITEM_TYPE.get(entry["type"], "document")
    title = strip_bib_braces(f.get("title", "")).strip()
    if not title:
        return None
    data: dict = {
        "itemType": item_type,
        "title": title,
        "creators": parse_creators(f.get("author", "")),
        "date": f.get("year", ""),
        "collections": [collection_key],
    }
    if f.get("doi"):
        data["DOI"] = f["doi"]
    if f.get("url"):
        data["url"] = f["url"]
    if item_type == "journalArticle":
        if f.get("journal"):
            data["publicationTitle"] = f["journal"]
        if f.get("volume"):
            data["volume"] = f["volume"]
        if f.get("number"):
            data["issue"] = f["number"]
    if f.get("pages"):
        data["pages"] = f["pages"].replace("--", "-")
    if item_type == "conferencePaper" and f.get("booktitle"):
        data["proceedingsTitle"] = strip_bib_braces(f["booktitle"])
    if item_type == "report" and f.get("institution"):
        data["institution"] = strip_bib_braces(f["institution"])
    note_lines = [strip_bib_braces(f["note"])] if f.get("note") else []
    note_lines.append(f"bibtex-key: {citekey}")
    data["extra"] = "\n".join(note_lines)
    return data


def fetch_collection_items(client: httpx.Client, key: str) -> list[dict]:
    resp = client.get(f"{BASE}/users/{LOCAL_USER}/collections/{key}/items",
                       params={"format": "json", "limit": 100})
    resp.raise_for_status()
    return resp.json()


def cmd_push(args: argparse.Namespace) -> None:
    with httpx.Client(timeout=10.0) as client:
        coll = find_collection(client, args.collection)
        if not coll:
            sys.exit(f"No Zotero collection named {args.collection!r} -- run "
                      f"ensure-collection first.")
        key = coll["data"]["key"]
        existing_items = fetch_collection_items(client, key)
        existing_dois = {
            d["DOI"].strip().lower()
            for it in existing_items
            if (d := it["data"]).get("DOI")
        }
        existing_keys = set()
        for it in existing_items:
            m = BIBTEX_KEY_HINT_RE.search(it["data"].get("extra") or "")
            if m:
                existing_keys.add(m.group(1))

        entries = parse_bib_entries(Path(args.bib).read_text(encoding="utf-8"))

        to_create = []
        skipped = []
        for entry in entries:
            citekey = entry["citekey"]
            doi = entry["fields"].get("doi", "").strip().lower()
            if citekey in existing_keys or (doi and doi in existing_dois):
                skipped.append(citekey)
                continue
            data = build_item_data(entry, key)
            if data is None:
                skipped.append(f"{citekey} (no title -- not pushed)")
                continue
            to_create.append((citekey, data))

        if not to_create:
            print(f"Nothing to push -- all {len(entries)} bib entr"
                  f"{'y' if len(entries) == 1 else 'ies'} already present in {args.collection!r}.")
            return

        server_id = get_server_id(client)
        resp = write_with_auth(client, server_id, "POST", f"{BASE}/users/{LOCAL_USER}/items",
                                json=[d for _, d in to_create])
        resp.raise_for_status()
        body = resp.json()
        successful = body.get("successful", {})
        failed = body.get("failed", {})
        for idx, (citekey, _) in enumerate(to_create):
            si = str(idx)
            if si in successful:
                print(f"Created: {successful[si]['data']['key']} {citekey}")
            elif si in failed:
                print(f"FAILED: {citekey} -- {failed[si]}")
        if skipped:
            print(f"Skipped (already present): {', '.join(skipped)}")


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

    p = sub.add_parser("push", help="Create Zotero items for .bib entries not already in the collection")
    p.add_argument("--collection", required=True)
    p.add_argument("--bib", required=True)
    p.set_defaults(func=cmd_push)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
