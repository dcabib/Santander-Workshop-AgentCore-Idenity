"""Publica capacidades da aula 14 em fases CloudFormation com revisão por digest."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from santander_demo.aws_workshop.catalog import origin_bundle
from santander_demo.aws_workshop.client import stack_name
from santander_demo.aws_workshop.config import check_accounts, load, session, stack_outputs
from santander_demo.registry_workflow.contracts import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from infra.registry_workflow.generate import main as generate

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["publish", "submit", "approve"])
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--review", help="JSON com digests e decisões conferidos")
    args = parser.parse_args()
    config = load(args.config)
    check_accounts(config, domains=("platform", "retail-banking"))
    registry_path = ROOT / config["integrations"]["registry"]["config"]
    registry = json.loads(registry_path.read_text())
    aws = session(config)
    if registry["account"] != config["accounts"]["platform"]["id"]:
        raise ValueError("CATALOG_ACCOUNT_MISMATCH")
    prefix = registry["prefix"] + "-origin-"
    params = {"RegistryId": registry["RegistryId"]}
    labels = ("Riscos", "Fraude")
    if args.phase == "publish":
        origin = session(config, "retail-banking")
        package = origin_bundle(
            stack_outputs(aws, stack_name(config, "platform", "identity")),
            stack_outputs(aws, stack_name(config, "platform", "gateway"))["GatewayUrl"],
            {
                label: stack_outputs(
                    origin, stack_name(config, "retail-banking", "agent-" + label.lower()),
                )["RuntimeArn"]
                for label in labels
            },
        )
        params["PublisherProviderArn"] = registry["PublisherProviderArn"]
        params.update({label + "Package": json.dumps(package[label]) for label in labels})
        (ROOT / "build/workshop-origin-bundle.json").write_text(json.dumps(package, indent=2) + "\n")
        (ROOT / "build/workshop-origin-review-candidate.json").write_text(json.dumps({
            **{label + "Digest": digest(package[label]) for label in labels},
            **{label + "Decision": "APPROVED" for label in labels},
        }, indent=2) + "\n")
    else:
        records = stack_outputs(aws, prefix + "publish")
        params.update({label + "RecordId": records[label + "RecordId"] for label in labels})
        actor = "Approver" if args.phase == "approve" else "Publisher"
        params[actor + "ProviderArn"] = registry[actor + "ProviderArn"]
        if args.phase == "approve":
            if not args.review:
                parser.error("Revise build/workshop-origin-bundle.json e forneça --review")
            review = json.loads(Path(args.review).read_text())
            if set(review) != {label + suffix for label in labels for suffix in ["Digest", "Decision"]}:
                parser.error("Campos de revisão inválidos")
            if any(review[label + "Digest"] != records[label + "Digest"] for label in labels):
                parser.error("REVIEW_CHANGED")
            if any(review[label + "Decision"] not in {"APPROVED", "REJECTED"} for label in labels):
                parser.error("INVALID_DECISION")
            params.update(review)
    generate()
    path = ROOT / f"build/workshop-origin-{args.phase}-parameters.json"
    path.write_text(json.dumps(params, indent=2) + "\n")
    account = config["accounts"]["platform"]
    subprocess.run([
        sys.executable, str(ROOT / "scripts/banking_deploy.py"), "origin-" + args.phase,
        "--scenario", "registry_workflow",
        *(["--profile", account["profile"]] if account.get("profile") else []),
        "--region", config["region"], "--account", account["id"],
        "--stack", prefix + args.phase, "--parameters", str(path),
        *(["--execute"] if args.execute else []),
    ], cwd=ROOT, check=True)
    if args.execute:
        registry.update(stack_outputs(aws, prefix + "publish"))
        registry_path.write_text(json.dumps(registry, indent=2) + "\n")
        registry_path.chmod(0o600)


if __name__ == "__main__":
    main()
