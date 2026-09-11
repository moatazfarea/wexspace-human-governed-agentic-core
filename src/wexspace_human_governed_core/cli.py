from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import GovernedRuntime
from .strands_runtime import invoke_live_bedrock


def _json_arg(value: str):
    return json.loads(value)


def main() -> None:
    p = argparse.ArgumentParser(prog="wexspace-core")
    p.add_argument("--state-dir", default=".wexspace-state")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create")
    c.add_argument("work_id")
    c.add_argument("objective")
    c.add_argument("inputs", type=_json_arg)

    r = sub.add_parser("run")
    r.add_argument("work_id")
    r.add_argument("--stop-after", type=int)

    live = sub.add_parser("run-live")
    live.add_argument("work_id")
    live.add_argument("prompt")

    s = sub.add_parser("status")
    s.add_argument("work_id")

    review = sub.add_parser("review")
    review.add_argument("work_id")
    review.add_argument("reviewer")
    g = review.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    review.add_argument("--note", default="")

    ex = sub.add_parser("export")
    ex.add_argument("work_id")
    ex.add_argument("out_dir")

    args = p.parse_args()
    rt = GovernedRuntime(Path(args.state_dir))
    if args.cmd == "create":
        rt.create_work(args.work_id, args.objective, args.inputs)
        print(json.dumps(rt.status(args.work_id), indent=2, sort_keys=True))
    elif args.cmd == "run":
        print(json.dumps(rt.run_deterministic(args.work_id, args.stop_after), indent=2, sort_keys=True))
    elif args.cmd == "run-live":
        print(invoke_live_bedrock(Path(args.state_dir), args.work_id, args.prompt))
    elif args.cmd == "status":
        print(json.dumps(rt.status(args.work_id), indent=2, sort_keys=True))
    elif args.cmd == "review":
        rt.repo.review(args.work_id, args.reviewer, args.approve, args.note)
        print(json.dumps(rt.status(args.work_id), indent=2, sort_keys=True))
    elif args.cmd == "export":
        paths = rt.export_review_package(args.work_id, Path(args.out_dir))
        print("\n".join(map(str, paths)))
