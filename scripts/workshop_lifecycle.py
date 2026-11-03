"""Uma transição IaC da aula 15 e seu teste em CodeBuild; falhas interrompem a sequência."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from santander_demo.aws_workshop.backend import session_id
from santander_demo.aws_workshop.config import load
from santander_demo.aws_workshop.lifecycle import STAGES

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--memory-session", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    session_id(args.memory_session)
    config = load(args.config)
    rag = json.loads((ROOT / config["integrations"]["rag"]["config"]).read_text())
    commands = [
        [
            sys.executable, "scripts/workshop_deploy.py", "backend",
            "--config", args.config, "--lifecycle-stage", args.stage, "--execute",
        ],
        [
            sys.executable, "scripts/rag_deploy.py", "data",
            "--project", rag["project"],
            *(["--profile", rag["profile"]] if rag.get("profile") else []),
            "--region", rag["region"], "--lifecycle-stage", args.stage, "--execute",
        ],
        [
            sys.executable, "scripts/workshop_runner.py", "run",
            "--config", args.config, "--execute", "--labs", "15",
            "--lifecycle-stage", args.stage, "--memory-session", args.memory_session,
        ],
    ]
    if not args.execute:
        print(json.dumps({"stage": args.stage, "commands": commands}, indent=2))
        return
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
