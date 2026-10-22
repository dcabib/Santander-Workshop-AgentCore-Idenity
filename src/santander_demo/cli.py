import argparse
import json
from pathlib import Path

from santander_demo.local import Workshop
from santander_demo.policy import PolicyContract, render


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "matrix", "cedar", "preflight"])
    parser.add_argument("--config", default="config/local.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    lab = Workshop()
    if args.command == "demo":
        result = {u: lab.analyze(lab.idp.token(u)) for u in ("riscos", "ambos")}
    elif args.command == "matrix":
        result = {"mode": "LOCAL_SIMULATION", "tests": lab.policy_matrix()}
    elif args.command == "cedar":
        print(render(PolicyContract()))
        return
    else:
        from santander_demo.cloud import CloudWorkshop
        from santander_demo.config import Environment

        result = CloudWorkshop(Environment.load(args.config)).preflight()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")
    else:
        print(text)
