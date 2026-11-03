"""Mostra as contas exigidas antes do workshop; não implanta nem executa aulas."""

import argparse
import json

from santander_demo.aws_workshop.config import load
from santander_demo.aws_workshop.manifest import LABS, account_plan, check_selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--labs", nargs="+", choices=LABS)
    parser.add_argument("--runner", action="store_true",
                        help="Incluir as contas exigidas pela seleção implantada no runner")
    parser.add_argument("--check-aws", action="store_true",
                        help="Também consultar STS e dependências das aulas, somente leitura")
    args = parser.parse_args()
    config = load(args.config)
    report = account_plan(config, args.labs, runner=args.runner)
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    if report["status"] == "BLOCKED":
        raise SystemExit("Pré-requisitos ausentes; consulte docs/contas-e-elegibilidade.md.")
    if args.check_aws:
        check_selection(config, args.labs, runner=args.runner)
        print(json.dumps({
            "validation": "AWS_PREFLIGHT", "status": "PASS",
            "note": "Contas e dependências consultadas; aulas ainda não executadas.",
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
