"""Único wrapper de IaC da trilha Terraform: plan, apply e destroy via provider."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra/terraform_agentcore"
BUILD = ROOT / "build/terraform-agentcore"


def load_config(path):
    config = json.loads(Path(path).read_text())
    required = {"region", "expected_account_id", "project_name"}
    if not required <= config.keys() or any(not config[key] for key in required):
        raise ValueError(f"Configuração precisa de: {sorted(required)}")
    config.setdefault("profile", None)
    return config


def environment(config):
    env = dict(os.environ)
    # Um AWS_ACCESS_KEY_ID ambiente não pode sobrepor silenciosamente o perfil escolhido.
    if config.get("profile"):
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                    "AWS_SECURITY_TOKEN", "AWS_DEFAULT_PROFILE"):
            env.pop(key, None)
        env["AWS_PROFILE"] = config["profile"]
        env["AWS_EC2_METADATA_DISABLED"] = "true"
    else:
        env.pop("AWS_PROFILE", None)
        env.pop("AWS_DEFAULT_PROFILE", None)
    env.update({
        "AWS_REGION": config["region"],
        "AWS_DEFAULT_REGION": config["region"],
        "TF_IN_AUTOMATION": "1",
        "TF_INPUT": "0",
    })
    return env


def preflight(config):
    session = boto3.Session(profile_name=config["profile"], region_name=config["region"])
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != config["expected_account_id"]:
        raise RuntimeError("WRONG_AWS_ACCOUNT: a conta autenticada difere da configuração")
    return {
        "account_id": identity["Account"],
        "region": config["region"],
        "profile": config["profile"],
        "principal_arn": identity["Arn"],
    }


def terraform(config, *args, capture=False, success_codes=(0,)):
    result = subprocess.run(
        ["terraform", f"-chdir={INFRA}", *args],
        cwd=ROOT, env=environment(config), text=True,
        capture_output=capture, check=False,
    )
    if result.returncode not in success_codes:
        # Outputs podem conter segredos de state: não imprimir stderr/stdout capturados.
        raise RuntimeError(f"Terraform {args[0]} falhou (exit={result.returncode})")
    return result


def input_files(config):
    paths = list(INFRA.glob("*.tf")) + [INFRA / ".terraform.lock.hcl"]
    paths += [BUILD / "runtime.zip", BUILD / "lambda.zip"]
    return {
        "config": config,
        "files": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)
        },
    }


def tfvars(config):
    # Leitura do state, não import por CLI. Um ID de import precisa ser conhecido
    # no plan; o Runtime só fornece esse ID depois de ser criado pelo serviço.
    state = terraform(config, "state", "list", capture=True, success_codes=(0, 1))
    if state.returncode == 1 and "No state file was found" not in state.stderr:
        raise RuntimeError("STATE_INSPECTION_FAILED")
    values = {
        "aws_region": config["region"],
        "expected_account_id": config["expected_account_id"],
        "project_name": config["project_name"],
        "runtime_zip": str(BUILD / "runtime.zip"),
        "lambda_zip": str(BUILD / "lambda.zip"),
        "model_id": config.get("model_id", "amazon.nova-lite-v1:0"),
        "manage_runtime_logs": "aws_bedrockagentcore_agent_runtime.agent" in state.stdout.splitlines(),
    }
    path = BUILD / "inputs.tfvars.json"
    path.write_text(json.dumps(values, indent=2) + "\n")
    return path


def outputs(config):
    return json.loads(terraform(config, "output", "-json", "workshop", capture=True).stdout)


def check_state_target(config):
    """Evita reutilizar o state de uma turma para substituir outra implantação."""
    existing = json.loads(terraform(config, "output", "-json", capture=True).stdout)
    if "workshop" not in existing:
        return
    value = existing["workshop"]["value"]
    expected = {
        "account_id": config["expected_account_id"],
        "region": config["region"],
        "project_name": config["project_name"],
    }
    if any(value.get(key) != target for key, target in expected.items()):
        raise RuntimeError("STATE_TARGET_MISMATCH: use um checkout/state separado para outra turma")


def state_matches(config, state):
    value = state.get("outputs", {}).get("workshop", {}).get("value", {})
    expected = {
        "account_id": config["expected_account_id"],
        "region": config["region"], "project_name": config["project_name"],
    }
    if any(value.get(key) != target for key, target in expected.items()):
        raise RuntimeError("STATE_TARGET_MISMATCH")


def backend_configuration(config):
    """Bucket pertence ao bootstrap IaC, é privado, criptografado e versionado."""
    from santander_demo.aws_workshop.config import stack_outputs

    backend = config.get("backend", {})
    stack, key = backend.get("stack", ""), backend.get("key", "")
    if (
        not re.fullmatch(r"[a-z][a-z0-9-]+-core-bootstrap", stack)
        or key != f"terraform/state/{config['project_name']}.tfstate"
    ):
        raise ValueError("AWS_STATE_BACKEND_REQUIRED")
    aws = boto3.Session(profile_name=config.get("profile"), region_name=config["region"])
    bucket = stack_outputs(aws, stack)["ArtifactBucket"]
    s3 = aws.client("s3")
    request = {"Bucket": bucket, "ExpectedBucketOwner": config["expected_account_id"]}
    encryption = s3.get_bucket_encryption(**request)["ServerSideEncryptionConfiguration"]["Rules"]
    if not any(rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") in {
        "AES256", "aws:kms",
    } for rule in encryption):
        raise ValueError("STATE_BUCKET_ENCRYPTION_REQUIRED")
    if s3.get_bucket_versioning(**request).get("Status") != "Enabled":
        raise ValueError("STATE_BUCKET_VERSIONING_REQUIRED")
    if not all(s3.get_public_access_block(**request)["PublicAccessBlockConfiguration"].values()):
        raise ValueError("STATE_BUCKET_MUST_BE_PRIVATE")
    return {"bucket": bucket, "key": key, "region": config["region"],
            "encrypt": True, "use_lockfile": True,
            "allowed_account_ids": [config["expected_account_id"]]}


def init_backend(config, *, migrate=False):
    """Migração de state pelo próprio Terraform, sem import ou escrita S3 avulsa."""
    from botocore.exceptions import ClientError

    preflight(config)
    backend = backend_configuration(config)
    if migrate:
        metadata = INFRA / ".terraform/terraform.tfstate"
        if metadata.exists():
            previous = json.loads(metadata.read_text()).get("backend", {})
            if previous.get("type") == "s3":
                raise ValueError("STATE_ALREADY_USES_S3")
        source = INFRA / "terraform.tfstate"
        state = json.loads(source.read_text())
        state_matches(config, state)
        aws = boto3.Session(profile_name=config.get("profile"), region_name=config["region"])
        try:
            aws.client("s3").head_object(
                Bucket=backend["bucket"], Key=backend["key"],
                ExpectedBucketOwner=config["expected_account_id"],
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            raise ValueError("REMOTE_STATE_EXISTS_REFUSE_OVERWRITE")
        backup = BUILD / "state-before-s3.tfstate"
        if not backup.exists():
            backup.write_bytes(source.read_bytes())
            backup.chmod(0o600)
    path = BUILD / "backend.json"
    path.write_text(json.dumps(backend, indent=2) + "\n")
    path.chmod(0o600)
    terraform(config, "init", "-input=false", "-no-color", f"-backend-config={path}",
              *(["-migrate-state", "-force-copy"] if migrate else []))
    if migrate:
        state_matches(config, json.loads(terraform(config, "state", "pull", capture=True).stdout))
        print(json.dumps({"state_backend": "AWS_S3", "migrated": True, "locking": "S3_LOCKFILE"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=[
        "preflight", "init", "migrate-state", "validate", "plan", "apply", "outputs",
        "plan-destroy", "destroy", "drift",
    ])
    parser.add_argument("--config", default=str(ROOT / "config/aws.terraform.json"))
    args = parser.parse_args()
    os.umask(0o077)  # State, planos e inputs podem conter segredos.
    config = load_config(args.config)
    BUILD.mkdir(parents=True, exist_ok=True)
    if args.command in {"init", "migrate-state"}:
        init_backend(config, migrate=args.command == "migrate-state")
        return
    if args.command == "validate":
        terraform(config, "fmt", "-check", "-recursive")
        terraform(config, "validate", "-no-color")
        return
    print(json.dumps({"preflight": preflight(config)}, ensure_ascii=False), flush=True)
    if args.command == "preflight":
        return
    if args.command == "outputs":
        print(json.dumps(outputs(config), ensure_ascii=False, indent=2))
        return
    check_state_target(config)
    destroy = args.command in {"plan-destroy", "destroy"}
    plan = BUILD / ("destroy.tfplan" if destroy else "deploy.tfplan")
    receipt = plan.with_suffix(".receipt.json")
    if args.command in {"plan", "plan-destroy", "drift"}:
        command = ["plan", "-input=false", "-no-color", f"-var-file={tfvars(config)}"]
        if destroy:
            command.append("-destroy")
        if args.command == "drift":
            result = terraform(config, *command, "-detailed-exitcode", success_codes=(0, 2))
            print(json.dumps({"drift": "NONE" if result.returncode == 0 else "CHANGES"}))
            if result.returncode == 2:
                raise SystemExit(2)
            return
        terraform(config, *command, f"-out={plan}")
        receipt.write_text(json.dumps({
            "inputs": input_files(config),
            "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
        }, indent=2) + "\n")
        return
    # Aplicar somente o plano já produzido/revisável, na mesma conta/configuração.
    recorded = json.loads(receipt.read_text())
    if (
        recorded["inputs"] != input_files(config)
        or recorded["plan_sha256"] != hashlib.sha256(plan.read_bytes()).hexdigest()
    ):
        raise RuntimeError("PLAN_INPUTS_CHANGED: gere e revise um novo plano")
    terraform(config, "apply", "-input=false", "-no-color", str(plan))
    if not destroy:
        result = outputs(config)
        (BUILD / "outputs.json").write_text(json.dumps(result, indent=2) + "\n")
        if not result["runtime_logs_managed"]:
            print("Runtime criado. Execute plan e apply novamente para gerenciar os logs via import declarativo.")


if __name__ == "__main__":
    main()
