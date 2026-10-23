"""Ensaio real do lab 16. Não cria nem modifica recursos; requer IaC implantado."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import boto3

from santander_demo.rag import client, cognito
from santander_demo.rag.contract import QUESTION
from santander_demo.rag.deployment import outputs, preflight
from santander_demo.rag.transport import authorization_probe, correlate

ROOT = Path(__file__).resolve().parents[1]


async def run(config):
    admin = boto3.Session(profile_name=config["profile"], region_name=config["region"])
    environment = preflight(config, admin)
    identity_environment = outputs(admin, config, "identity")
    caller = client.caller_session(config, environment)
    boundary = await authorization_probe(config, environment, caller)
    identity_api = caller.client("bedrock-agentcore")
    model = caller.client("bedrock-runtime")
    rows, started = [], int(time.time() * 1000)
    for label in "abcd":
        token = cognito.login(admin, config, identity_environment, label)
        # Identity pode identificar D; só a Policy decide se ele acessa a tool.
        wat = identity_api.get_workload_access_token_for_jwt(
            workloadName=environment["WorkloadName"],
            userToken=token,
        )
        issued = bool(wat.get("workloadAccessToken"))
        del wat
        row = await client.ask(config, environment, token, QUESTION, model)
        row["user_bound_workload_token_issued"] = issued
        if label != "d":
            row.update(await client.coverage_probe(config, environment, token))
        rows.append(row)
        print(
            f"{label.upper()}: {row['outcome']}; "
            f"documentos={row['document_ids']}; cobertura={row.get('coverage_document_ids', [])}",
            file=sys.stderr,
            flush=True,
        )
        if label == "a":
            rows.append(
                await client.probe_identity_spoof(
                    config,
                    environment,
                    token,
                    config["users"]["c"]["email"],
                )
            )
        del token
    correlate(admin, environment, rows, started)
    return {
        "mode": "AWS_LIVE",
        "authorization_boundary": boundary,
        "started_ms": started,
        "acceptance": client.acceptance(rows),
        "cases": client.sanitized_evidence(rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/local.rag.json")
    parser.add_argument("--correlate-only", action="store_true")
    args = parser.parse_args()
    config = client.load_config(args.config)
    destination = ROOT / "evidence/rag-live.json"
    if args.correlate_only:
        report = json.loads(destination.read_text())
        session = boto3.Session(profile_name=config["profile"], region_name=config["region"])
        environment = outputs(session, config, "access")
        correlate(session, environment, report["cases"], report["started_ms"])
        report["acceptance"] = client.acceptance(report["cases"])
    else:
        report = asyncio.run(run(config))
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["acceptance"]["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
