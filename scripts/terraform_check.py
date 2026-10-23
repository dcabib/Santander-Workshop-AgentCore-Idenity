"""Smoke test de cloud: somente autenticação e invocações, sem provisionamento."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from terraform_deploy import load_config, outputs, preflight

from santander_demo.terraform_lab.client import verify_cloud


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/local.terraform.json")
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    settings = load_config(args.config)
    preflight(settings)
    deployed = outputs(settings)
    path = Path("evidence/terraform-agentcore-live.json")
    path.parent.mkdir(exist_ok=True)
    # Uma tentativa nova não pode deixar o PASS antigo parecer o resultado atual.
    started = {"status": "RUNNING", "mode": "AWS_LIVE", "started_at": datetime.now(UTC).isoformat()}
    path.write_text(json.dumps(started, indent=2) + "\n")
    try:
        report = asyncio.run(verify_cloud(
            deployed, profile=settings["profile"], include_llm=args.llm
        ))
    except Exception as exc:
        path.write_text(json.dumps({
            **started, "status": "FAIL", "error_type": type(exc).__name__,
        }, indent=2) + "\n")
        raise
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
