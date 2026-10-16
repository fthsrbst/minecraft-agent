"""CLI: run an evaluation plan, or write its report.

    uv run --env-file ../.env python -m agent_core.evaluation run ../plugins/<game> PLAN.json \\
        [--out runs/eval/<plan id>] [--phase learning|test|all] [--tasks N]
    uv run python -m agent_core.evaluation report runs/eval/<plan id>
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agent_core.evaluation.plan import PlanError, load_plan
from agent_core.evaluation.report import build_report
from agent_core.evaluation.runner import run_plan
from agent_core.plugins import ManifestError, PluginError


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent_core.evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("plugin_dir", type=Path)
    run.add_argument("plan", type=Path)
    run.add_argument("--out", type=Path)
    run.add_argument("--phase", choices=["learning", "test", "all"], default="all")
    run.add_argument("--tasks", type=int, help="only the first N tasks (pilot runs)")
    report = sub.add_parser("report")
    report.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        text = build_report(args.out)
        (args.out / "report.md").write_text(text, encoding="utf-8")
        print(text)
        return 0
    try:
        plan = load_plan(args.plan)
        out = args.out or Path("runs/eval") / plan.id
        phases = ("learning", "test") if args.phase == "all" else (args.phase,)
        asyncio.run(run_plan(plan, args.plugin_dir, out, phases=phases, tasks_limit=args.tasks))
    except (PlanError, ManifestError, PluginError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"results in {out}; write the report with: python -m agent_core.evaluation report {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
