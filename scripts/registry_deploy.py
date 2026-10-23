"""Pipeline IaC do Registry: cada fase é um stack revisável e independente."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from santander_demo.registry_workflow.contracts import bundle, digest

ROOT = Path(__file__).resolve().parents[1]


def outputs(session, stack):
    return {
        v["OutputKey"]: v["OutputValue"]
        for v in session.client("cloudformation")
        .describe_stacks(StackName=stack)["Stacks"][0]
        .get("Outputs", [])
    }


def operator_arn(session, caller):
    if ":assumed-role/" in caller["Arn"]:
        return session.client("iam").get_role(RoleName=caller["Arn"].split("/")[-2])["Role"]["Arn"]
    return caller["Arn"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=["bootstrap", "foundation", "publish", "submit", "approve"])
    p.add_argument("--profile", default="default")
    p.add_argument("--region", choices=["us-east-1"], default="us-east-1")
    p.add_argument("--prefix", default="registry-personas")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--recover-registry", default="", help="Uso pelo wrapper de recuperação do IaC")
    p.add_argument(
        "--review", help="JSON com digests conferidos e decisões; obrigatório em approve"
    )
    args = p.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    caller = session.client("sts").get_caller_identity()
    prefix = args.prefix
    if not prefix.replace("-", "").isalnum() or not prefix[0].isalpha() or len(prefix) > 40:
        p.error("Prefixo deve começar com letra e conter letras, números e hífens (até 40)")
    params = {}
    if args.phase == "foundation":
        recovered = args.recover_registry
        if not recovered:
            try:
                existing = session.client("cloudformation").describe_stacks(StackName=prefix + "-foundation")["Stacks"][0]
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ValidationError" or "does not exist" not in str(exc):
                    raise
            else:
                recovered = next((v["ParameterValue"] for v in existing.get("Parameters", [])
                                  if v["ParameterKey"] == "RecoveryRegistryArn"), "")
        params = {
            "RecoveryRegistryArn": recovered,
            "ArtifactBucket": outputs(session, prefix + "-bootstrap")["ArtifactBucket"],
            "OperatorArn": operator_arn(session, caller),
            "Project": prefix,
            "RuntimeName": prefix.replace("-", "_"),
        }
    if args.phase in {"publish", "submit", "approve"}:
        infra = outputs(session, prefix + "-foundation")
        params = {"RegistryId": infra["RegistryId"]}
        if args.phase == "publish":
            package = bundle(infra["GatewayUrl"], infra["RuntimeArn"])
            params.update(
                PublisherProviderArn=infra["PublisherProviderArn"],
                McpPackage=json.dumps(package["MCP"]),
                AgentPackage=json.dumps(package["AGENT"]),
            )
            path = ROOT / "build/registry-review-candidate.json"
            path.write_text(
                json.dumps(
                    {
                        "McpDigest": digest(package["MCP"]),
                        "AgentDigest": digest(package["AGENT"]),
                        "McpDecision": "APPROVED",
                        "AgentDecision": "APPROVED",
                    },
                    indent=2,
                )
                + "\n"
            )
            (ROOT / "build/registry-bundle.json").write_text(json.dumps(package, indent=2) + "\n")
            print("Bundle e candidato a decisão em build/registry-*.json; revise antes de aprovar.")
        else:
            records = outputs(session, prefix + "-publish")
            params.update({k: records[k] for k in ("McpRecordId", "AgentRecordId")})
            actor = "Approver" if args.phase == "approve" else "Publisher"
            params[actor + "ProviderArn"] = infra[actor + "ProviderArn"]
            if args.phase == "approve":
                if not args.review:
                    p.error(
                        "Leia build/registry-bundle.json e passe --review com os digests e decisões revisados"
                    )
                review = json.loads(Path(args.review).read_text())
                if set(review) != {"McpDigest", "AgentDigest", "McpDecision", "AgentDecision"}:
                    p.error("Campos inválidos no arquivo de revisão")
                if any(review[k] != records[k] for k in ("McpDigest", "AgentDigest")):
                    p.error("A revisão não corresponde à publicação")
                params.update(review)
    target = ROOT / "build" / ("registry-" + args.phase + ".json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(params, indent=2) + "\n")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/banking_deploy.py"),
            args.phase,
            "--scenario",
            "registry_workflow",
            "--profile",
            args.profile,
            "--region",
            args.region,
            "--account",
            caller["Account"],
            "--stack",
            prefix + "-" + args.phase,
            "--parameters",
            str(target),
            *(["--execute"] if args.execute else []),
        ],
        check=True,
        cwd=ROOT,
    )
    if args.execute and args.phase != "bootstrap":
        config = {
            "profile": args.profile,
            "region": args.region,
            "prefix": prefix,
            "account": caller["Account"],
            **outputs(session, prefix + "-foundation"),
        }
        if args.phase in {"publish", "submit", "approve"}:
            config.update(outputs(session, prefix + "-publish"))
        (ROOT / "config/local.registry.json").write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
