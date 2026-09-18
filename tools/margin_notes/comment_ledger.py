"""Durable tracker for margin_notes review comments.

The margin_notes Artifact's shared database has no public API a standalone
script can query directly -- reading it requires the Artifact tool's own
read_db action from inside a Claude Code session. The workflow this script
supports is therefore: (1) inside a session, export the comments collection
via `Artifact action:read_db db_op:list collection:comments` and save it as
comments_export_<date>.json (see that file for the exact shape); (2) run this
script to diff the export against comment_ledger.json and report which
comments are new since the last triage pass; (3) after triaging, add/update
entries in comment_ledger.json by hand (or have the session do it) and, for
anything actually resolved, write status:"resolved" back to the live
database via `Artifact action:write_db db_op:batch` -- this script does not
write to the Artifact itself, only reads local files.

Usage:
    python comment_ledger.py diff <export.json>   # what's new since the ledger
    python comment_ledger.py report                # ledger status breakdown
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER_PATH = HERE / "comment_ledger.json"


def load_ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def load_export(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def diff(export_path: Path) -> None:
    ledger = load_ledger()
    known_ids = {e["id"] for e in ledger["entries"]}
    export = load_export(export_path)

    new_comments = [c for c in export["comments"] if c["id"] not in known_ids]
    if not new_comments:
        print(f"No new comments since the ledger was last updated ({ledger['updated_at']}).")
        return

    print(f"{len(new_comments)} comment(s) not yet in the ledger:\n")
    for c in new_comments:
        print(f"  [{c['id']}] block={c['block_id']}")
        print(f"    {c['comment']}\n")


def report() -> None:
    ledger = load_ledger()
    by_status: dict[str, list[dict]] = {}
    for e in ledger["entries"]:
        by_status.setdefault(e["status"], []).append(e)

    total = len(ledger["entries"])
    print(f"comment_ledger.json -- {total} tracked comments, updated {ledger['updated_at']}\n")
    for status, label in ledger["status_legend"].items():
        entries = by_status.get(status, [])
        print(f"{status} ({len(entries)}): {label}")
        for e in entries:
            commit = f" [{e['commit']}]" if e.get("commit") else ""
            print(f"    [{e['id']}] {e['block_id']}{commit}")
        print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    cmd = sys.argv[1]
    if cmd == "diff":
        if len(sys.argv) != 3:
            print("usage: comment_ledger.py diff <export.json>")
            raise SystemExit(1)
        diff(Path(sys.argv[2]))
    elif cmd == "report":
        report()
    else:
        print(__doc__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
