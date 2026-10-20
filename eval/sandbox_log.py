"""`make evidence`: run the sandbox evidence end to end and keep the console output.

Runs, in order, the no-model evaluations (`python -m eval.run_all`, which writes results/RESULTS.md
and results/results.json), the seeded demo (`python -m sim.demo`, which writes results/demo/) and the
audit-chain verifier on the demo's log (`python -m agent.audit verify results/demo/audit.jsonl`), and
writes everything they print, with each command's exit code, to results/logs/sandbox-run.log.

The log is written by this script only; never edit it by hand. Everything in it is simulated: a
fictional company, a mocked WeBank feed, simulated unit listings and scripted owners.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "results" / "logs" / "sandbox-run.log"

STEPS: list[tuple[str, list[str]]] = [
    ("make eval: the no-model evaluations", [sys.executable, "-m", "eval.run_all"]),
    ("make demo: the six demo moments, seeded", [sys.executable, "-m", "sim.demo"]),
    (
        "audit chain of the demo run",
        [sys.executable, "-m", "agent.audit", "verify", "results/demo/audit.jsonl"],
    ),
]


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return out.stdout.strip()


def _local(text: str) -> str:
    """Paths relative to the repo root, so the log carries no machine-specific directories."""
    return text.replace(str(ROOT) + "/", "").replace(str(ROOT), ".")


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    lines = [
        "# Waypoint sandbox run log (simulated; written by eval/sandbox_log.py, never by hand)",
        f"started:  {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"commit:   {_git('rev-parse', 'HEAD')}{' (with uncommitted changes)' if dirty else ''}",
        f"python:   {platform.python_version()} on {platform.system()} {platform.machine()}",
        "",
    ]
    failed = 0
    for title, cmd in STEPS:
        shown = " ".join(["python", *cmd[1:]])
        print(f"== {title}: {shown}", flush=True)
        t0 = time.time()
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        took = time.time() - t0
        failed += res.returncode != 0
        lines += [
            "=" * 100,
            f"== {title}",
            f"$ {shown}",
            "=" * 100,
            _local(res.stdout).rstrip(),
        ]
        if res.stderr.strip():
            lines += ["-- stderr --", _local(res.stderr).rstrip()]
        lines += [f"-- exit code {res.returncode} in {took:.0f} s", ""]
        print(f"   exit {res.returncode} in {took:.0f} s", flush=True)
    lines.append(f"finished: {datetime.now(UTC).isoformat(timespec='seconds')}; {failed} step(s) failed")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {LOG.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
