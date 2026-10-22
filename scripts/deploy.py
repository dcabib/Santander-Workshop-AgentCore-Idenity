"""Pipeline IaC: identidade alvo → upload de artefato → change set → execução explícita.

Sem create/update/delete de recursos AgentCore fora do CloudFormation.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "template",
        choices=["bootstrap", "hub", "registry", "fraud-runtime", "origin", "policy-draft"],
    )
    p.add_argument("--profile", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--stack", required=True)
    p.add_argument("--parameters", required=True, help="JSON Parameters CloudFormation")
    p.add_argument("--execute", action="store_true", help="Executa o change set; padrão só prepara")
    args = p.parse_args()
    params = json.loads(Path(args.parameters).read_text())
    if not isinstance(params, dict) or not all(isinstance(v, str) for v in params.values()):
        p.error("Parâmetros devem ser um objeto de strings")
    if any("secret" in k.lower() and not k.endswith("Arn") for k in params):
        p.error("Segredos devem ser referências ARN, nunca valores")
    if any("REPLACE" in v for v in params.values()):
        p.error("Substitua os placeholders antes de preparar o deploy")
    declared = json.loads((ROOT / "infra/templates" / (args.template + ".json")).read_text())[
        "Parameters"
    ]
    if set(params) - set(declared):
        p.error("Arquivo contém parâmetros desconhecidos pelo template")
    automatic = {"LambdaKey", "RuntimeKey", "ProviderKey"}
    missing = {k for k, v in declared.items() if "Default" not in v} - set(params) - automatic
    if missing:
        p.error("Parâmetros obrigatórios ausentes: " + ", ".join(sorted(missing)))
    base = ["aws", "--profile", args.profile, "--region", args.region]
    caller = json.loads(subprocess.check_output(base + ["sts", "get-caller-identity"]))
    if caller["Account"] != args.account:
        p.error("A conta do perfil não corresponde a --account")
    if (
        args.template != "bootstrap"
        and args.template != "origin"
        or params.get("EnableRuntime") == "true"
    ):
        manifest = json.loads((ROOT / "build/artifacts.json").read_text())
        archive = ROOT / manifest["file"]
        if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
            p.error("Artefato mudou; execute novamente build_artifacts.py")
        bucket = params["ArtifactBucket"]
        # Publicação de artefato endereçado por hash, parte do pipeline IaC.
        subprocess.run(
            base
            + ["s3", "cp", str(archive), f"s3://{bucket}/{manifest['key']}", "--only-show-errors"],
            check=True,
        )
        key_name = {
            "hub": "LambdaKey",
            "registry": "ProviderKey",
            "policy-draft": "ProviderKey",
            "fraud-runtime": "RuntimeKey",
            "origin": "RuntimeKey",
        }[args.template]
        params[key_name] = manifest["key"]
    parameter_file = ROOT / "build" / f"{args.template}-parameters.json"
    parameter_file.parent.mkdir(exist_ok=True)
    parameter_file.write_text(
        json.dumps([{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()])
    )
    command = base + [
        "cloudformation",
        "deploy",
        "--template-file",
        str(ROOT / "infra/templates" / (args.template + ".json")),
        "--stack-name",
        args.stack,
        "--parameter-overrides",
        "file://" + str(parameter_file),
        "--capabilities",
        "CAPABILITY_NAMED_IAM",
        "--no-fail-on-empty-changeset",
    ]
    if not args.execute:
        command.append("--no-execute-changeset")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
