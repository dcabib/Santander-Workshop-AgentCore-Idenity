"""Único wrapper de IaC da trilha Terraform: plan, apply e destroy via provider."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra/terraform_agentcore"
BUILD = ROOT / "build/terraform-agentcore"


def load_config(path):
    config = json.loads(Path(path).read_text())
    required = {"profile", "region", "expected_account_id", "project_name"}
    if not required <= config.keys() or any(not config[key] for key in required):
        raise ValueError(f"Configuração precisa de: {sorted(required)}")
    return config


def environment(config):
    env = dict(os.environ)
    # Um AWS_ACCESS_KEY_ID ambiente não pode sobrepor silenciosamente o perfil escolhido.
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                "AWS_SECURITY_TOKEN", "AWS_DEFAULT_PROFILE"):
        env.pop(key, None)
    env.update({
        "AWS_PROFILE": config["profile"],
        "AWS_REGION": config["region"],
        "AWS_DEFAULT_REGION": config["region"],
        "AWS_EC2_METADATA_DISABLED": "true",
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=[
        "preflight", "init", "validate", "plan", "apply", "outputs",
        "plan-destroy", "destroy", "drift",
    ])
    parser.add_argument("--config", default=str(ROOT / "config/local.terraform.json"))
    args = parser.parse_args()
    os.umask(0o077)  # State, planos e inputs podem conter segredos.
    config = load_config(args.config)
    BUILD.mkdir(parents=True, exist_ok=True)
    if args.command == "init":
        terraform(config, "init", "-input=false", "-no-color")
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
