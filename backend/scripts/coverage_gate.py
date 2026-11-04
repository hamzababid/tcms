"""Coverage gate (docs/08 §4): ≥ 85% lines on */service.py, */rules.py, reporting/*; ≥ 95% branches on */rules.py.

Reads coverage.json (`pytest --cov=tcms --cov-branch --cov-report=json`). Modules that do not exist yet
are not gated; the gate reports which files it checked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LINE_MIN, BRANCH_MIN = 85.0, 95.0


def main(path: str = "coverage.json") -> int:
    files: dict[str, dict] = json.loads(Path(path).read_text())["files"]
    gated = {
        f: d
        for f, d in files.items()
        if f.endswith(("/service.py", "/rules.py"))
        or ("/reporting/" in f and not f.endswith(("/models.py", "/__init__.py")))
    }
    if not gated:
        print("coverage gate: no service/rules/reporting modules yet - nothing to gate")
        return 0
    failures = []
    covered = sum(d["summary"]["covered_lines"] for d in gated.values())
    statements = sum(d["summary"]["num_statements"] for d in gated.values())
    line_pct = 100.0 * covered / statements if statements else 100.0
    if line_pct < LINE_MIN:
        failures.append(f"line coverage {line_pct:.1f}% < {LINE_MIN}% on service/rules/reporting")
    for f, d in gated.items():
        if f.endswith("/rules.py") and d["summary"].get("num_branches"):
            pct = 100.0 * d["summary"]["covered_branches"] / d["summary"]["num_branches"]
            if pct < BRANCH_MIN:
                failures.append(f"branch coverage {pct:.1f}% < {BRANCH_MIN}% in {f}")
    print(f"coverage gate: {len(gated)} files, {line_pct:.1f}% lines")
    for msg in failures:
        print("FAIL", msg)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
