"""Deploy dos notebooks 10/11: artefato por hash e CloudFormation."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "template",
    )
    parser.add_argument(
        "--scenario", choices=["banking", "federation", "journey", "rag", "registry_workflow"], default="banking"
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--stack", required=True)
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    params = json.loads(Path(args.parameters).read_text())
    if not isinstance(params, dict) or not all(isinstance(v, str) for v in params.values()):
        parser.error("Os parâmetros devem ser um objeto JSON de strings")
    if any("REPLACE" in v for v in params.values()):
        parser.error("Preencha os identificadores do sandbox")
    if any("secret" in k.lower() and not k.endswith("Arn") for k in params):
        parser.error("Aceita apenas ARN de segredo, nunca o valor")
    directory = ROOT / "infra" / args.scenario / "templates"
    if args.template not in {p.stem for p in directory.glob("*.json")}:
        parser.error("Template não pertence ao cenário selecionado")
    template = directory / f"{args.template}.json"
    definitions = json.loads(template.read_text()).get("Parameters", {})
    unknown = set(params) - set(definitions)
    missing = (
        {key for key, value in definitions.items() if "Default" not in value}
        - set(params)
        - {"ArtifactKey"}
    )
    if unknown or missing:
        parser.error(f"Parâmetros desconhecidos={sorted(unknown)}, ausentes={sorted(missing)}")
    aws = ["aws", "--profile", args.profile, "--region", args.region]
    caller = json.loads(subprocess.check_output(aws + ["sts", "get-caller-identity"]))
    if caller["Account"] != args.account:
        parser.error("Perfil aponta para outra conta")
    if "ArtifactKey" in definitions:
        manifest = json.loads((ROOT / "build/banking-artifacts.json").read_text())
        artifact = ROOT / manifest["file"]
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["sha256"]:
            parser.error("Artefato alterado; repita o build local")
        subprocess.run(
            aws
            + [
                "s3",
                "cp",
                str(artifact),
                f"s3://{params['ArtifactBucket']}/{manifest['key']}",
                "--only-show-errors",
            ],
            check=True,
        )
        params["ArtifactKey"] = manifest["key"]
    target = ROOT / "build" / f"{args.scenario}-{args.template}-parameters.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        json.dumps([{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()])
    )
    subprocess.run(
        aws
        + [
            "cloudformation",
            "deploy",
            "--template-file",
            str(template),
            "--stack-name",
            args.stack,
            "--parameter-overrides",
            "file://" + str(target),
            "--capabilities",
            "CAPABILITY_NAMED_IAM" if args.scenario == "journey" else "CAPABILITY_IAM",
            "--no-fail-on-empty-changeset",
            *([] if args.execute else ["--no-execute-changeset"]),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
