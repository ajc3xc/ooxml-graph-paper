"""Structural checks a LaTeX compiler itself won't catch. Run after every build.
Exits non-zero on any finding so a build script (build.ps1) fails loudly rather
than silently leaving a broken/incomplete manuscript in place."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEX = (HERE / "main.tex").read_text(encoding="utf-8")
BIB = (HERE / "refs.bib").read_text(encoding="utf-8")

problems: list[str] = []

# Every \cite{...} key must exist in refs.bib, and vice versa isn't required
# (an unused bib entry is harmless), but a dangling cite is a real bug.
bib_keys = set(re.findall(r"@\w+\{([^,]+),", BIB))
cite_keys: set[str] = set()
for m in re.finditer(r"\\cite[tp]?\*?(?:\[[^\]]*\])?\{([^}]+)\}", TEX):
    cite_keys.update(k.strip() for k in m.group(1).split(","))
dangling = cite_keys - bib_keys
if dangling:
    problems.append(f"cite keys with no matching refs.bib entry: {sorted(dangling)}")

# Every \label{...} referenced by \ref/\Cref must exist.
labels = set(re.findall(r"\\label\{([^}]+)\}", TEX))
refs: set[str] = set()
for m in re.finditer(r"\\(?:ref|Cref|autoref)\{([^}]+)\}", TEX):
    refs.add(m.group(1))
dangling_refs = refs - labels
if dangling_refs:
    problems.append(f"\\ref to a \\label that doesn't exist: {sorted(dangling_refs)}")

# Flag remaining TODO/PENDING markers so they're never silently missed before
# a real submission -- this is a preliminary draft and is EXPECTED to have
# some right now; the check exists so they can't be forgotten later.
todos = re.findall(r"\\todo\{([^}]*)\}", TEX)
pendings = re.findall(r"\\pending\{([^}]*)\}", TEX)
if todos:
    print(f"NOTE: {len(todos)} \\todo{{}} marker(s) still present (expected pre-submission):")
    for t in todos:
        print(f"  - {t}")
if pendings:
    print(f"NOTE: {len(pendings)} \\pending{{}} marker(s) still present (expected until re-run lands):")
    for p in pendings:
        print(f"  - {p}")

if problems:
    print("PREFLIGHT FAILED:")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)

print("Preflight OK (structural checks only -- does not check writing quality; see paper-review-toolkit).")
