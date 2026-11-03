"""Pipeline IaC do lab 16: bootstrap -> identity -> data -> access, uma fase por execução."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infra.rag.generate import generate  # noqa: E402
from santander_demo.rag.client import validate_config  # noqa: E402
from santander_demo.rag.deployment import outputs, prepare_phase  # noqa: E402


def configuration(session, project, profile, region):
    caller = session.client("sts").get_caller_identity()
    arn = caller["Arn"]
    if ":assumed-role/" in arn:
        name = arn.split(":assumed-role/", 1)[1].split("/")[0]
        arn = session.client("iam").get_role(RoleName=name)["Role"]["Arn"]
    config = {
        "project": project,
        "profile": profile,
        "account_id": caller["Account"],
        "region": region,
        "caller_principal_arn": arn,
        "auth_provider": "cognito",
        "model_arn": f"arn:aws:bedrock:{region}::foundation-model/amazon.nova-lite-v1:0",
    }
    identity = outputs(session, config, "identity")
    config.update(
        user_pool_id=identity["UserPoolId"],
        login_client_id=identity["LoginClientId"],
        users={
            x.lower(): {"oid": identity[f"User{x}Oid"], "email": identity[f"User{x}Email"]}
            for x in "ABCD"
        },
    )
    return validate_config(config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["bootstrap", "identity", "data", "access", "config"])
    parser.add_argument("--project", default="santander-rag")
    parser.add_argument("--profile", help="Omitir para usar a role do ambiente AWS")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--lifecycle-stage", choices=[
        "baseline", "updated", "revoked", "deleted", "reingested",
    ])
    args = parser.parse_args()
    if args.lifecycle_stage and args.phase != "data":
        parser.error("--lifecycle-stage aplica-se somente à fase data")
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    generate()
    if args.phase in {"bootstrap", "identity"}:
        params = {}
        if args.phase == "identity":
            params = {
                "Project": args.project,
                "ArtifactBucket": outputs(session, {"project": args.project}, "bootstrap")[
                    "ArtifactBucket"
                ],
            }
        path = ROOT / "config" / f"aws.rag-{args.phase}.json"
        path.write_text(json.dumps(params, indent=2) + "\n")
        path.chmod(0o600)
        command = [
            sys.executable,
            str(ROOT / "scripts/banking_deploy.py"),
            args.phase,
            "--scenario",
            "rag",
            *(["--profile", args.profile] if args.profile else []),
            "--account",
            account,
            "--region",
            args.region,
            "--stack",
            f"{args.project}-rag-{args.phase}",
            "--parameters",
            str(path),
        ]
    else:
        config = configuration(session, args.project, args.profile, args.region)
        if args.lifecycle_stage:
            config["lifecycle_stage"] = args.lifecycle_stage
        path = ROOT / "config/aws.rag.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        path.chmod(0o600)
        if args.phase == "config":
            print(json.dumps({"configuration": str(path), "identifiers_only": True}))
            return
        command = prepare_phase(ROOT, config, session, args.phase)["args"]
    if args.execute:
        command.append("--execute")
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
