"""Pipeline do runner AWS: fonte privada, CloudFormation e execução CodeBuild."""

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from santander_demo.aws_workshop.client import stack_name
from santander_demo.aws_workshop.config import (
    DOMAINS,
    _identifiers_only,
    check_accounts,
    load,
    session,
    stack_outputs,
)
from santander_demo.aws_workshop.manifest import (
    account_plan,
    assert_account_plan,
    check_selection,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def outputs(config, phase):
    return stack_outputs(session(config), stack_name(config, "platform", phase))


def integration_configs(config):
    values = {}
    for integration in config["integrations"].values():
        path = integration["config"]
        if Path(path).is_absolute() or ".." in Path(path).parts or not path.startswith("config/aws."):
            raise ValueError("INTEGRATION_CONFIG_MUST_BE_PROJECT_AWS_FILE")
        value = json.loads((ROOT / path).read_text())
        _identifiers_only(value)
        value["profile"] = None
        values[path] = value
    return values


def package(config):
    """Whitelist explícita; não inclui credenciais, state, ambiente Python ou evidências."""
    config = json.loads(json.dumps(config))
    for domain, account in config["accounts"].items():
        account["profile"] = None
        if domain != "platform":
            account["role_arn"] = (
                f"arn:aws:iam::{account['id']}:role/{config['project']}-observer"
            )
    files = {}
    for directory, suffixes in [
        ("src", {".py"}), ("scripts", {".py", ".sh"}), ("infra", {".py", ".tf", ".json"}),
        ("notebooks", {".ipynb"}), ("tests", {".py"}), ("docs", {".md", ".svg"}),
    ]:
        for path in (ROOT / directory).rglob("*"):
            if (
                path.is_file() and path.suffix in suffixes
                and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(ROOT).parts)
                and not path.name.endswith((".tfstate", ".tfstate.backup", ".tfvars.json"))
            ):
                files[str(path.relative_to(ROOT))] = path.read_bytes()
    for name in ["pyproject.toml", "uv.lock", "README.md"]:
        files[name] = (ROOT / name).read_bytes()
    for name, value in {
        "config/aws.workshop.json": config, **integration_configs(config),
    }.items():
        files[name] = (json.dumps(value, indent=2) + "\n").encode()
    tf = config["integrations"]["terraform"]["outputs"]
    tf_outputs = json.loads((ROOT / tf).read_text())
    _identifiers_only(tf_outputs)
    files[tf] = json.dumps(tf_outputs).encode()
    destination = ROOT / "build/workshop-source.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return destination, hashlib.sha256(destination.read_bytes()).hexdigest()


def parameters(config, key, labs):
    envs = [outputs(config, phase) for phase in ["identity", "gateway", "backend", "agent"]]
    integrations = integration_configs(config)
    registry = integrations[config["integrations"]["registry"]["config"]]
    rag = integrations[config["integrations"]["rag"]["config"]]
    aws = session(config)
    for phase in ["identity", "data", "access"]:
        envs.append(stack_outputs(aws, f"{rag['project']}-rag-{phase}"))
    envs.append(registry)
    tf = json.loads((ROOT / config["integrations"]["terraform"]["outputs"]).read_text())
    envs.append(tf)
    # Fases opcionais: erros diferentes de ausência real continuam bloqueantes.
    from botocore.exceptions import ClientError

    for phase in ["rag-agent", "policy-draft"]:
        try:
            envs.append(outputs(config, phase))
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ValidationError" or "does not exist" not in str(exc):
                raise
    arns = {
        value for env in envs for name, value in env.items()
        if (
            isinstance(value, str) and value.startswith("arn:")
            and value.split(":")[2] == "bedrock-agentcore"
            and "secret" not in name.lower()
        )
    }
    arns |= {value + "/*" for value in arns if ":bedrock-agentcore:" in value}
    arns.add(f"arn:aws:bedrock-agentcore:{config['region']}:{config['accounts']['platform']['id']}:token-vault/default")
    knowledge_arns = {
        value + suffix for env in envs for value in env.values()
        if isinstance(value, str) and value.startswith("arn:aws:bedrock:")
        and ":knowledge-base/" in value for suffix in ["", "/*"]
    }
    source_arns = {
        "arn:aws:s3:::" + env["SourceBucket"] + "/" + suffix
        for env in envs if "SourceBucket" in env for suffix in ["documents/*", "acl/*"]
    }
    log_arns = {
        f"arn:aws:logs:{config['region']}:{config['accounts']['platform']['id']}:log-group:{value}:*"
        for env in envs for name, value in env.items()
        if name.endswith("LogGroup") and isinstance(value, str)
    }
    for arn in arns:
        if ":runtime/" in arn and not arn.endswith("/*"):
            runtime_id = arn.split(":runtime/", 1)[1]
            log_arns.add(
                f"arn:aws:logs:{config['region']}:{config['accounts']['platform']['id']}:"
                f"log-group:/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT:*"
            )
    personas = [
        value for key, value in registry.items()
        if key.endswith("RoleArn") and isinstance(value, str)
    ]
    secrets = [
        value for env in envs for key, value in env.items()
        if "secret" in key.lower() and isinstance(value, str) and value.startswith("arn:")
    ]
    return {
        "Project": config["project"], "SourceKey": key,
        "GatewayRoleArn": outputs(config, "gateway")["GatewayRoleArn"],
        "ArtifactBucket": outputs(config, "bootstrap")["ArtifactBucket"],
        "Labs": " ".join(labs), "ControlArns": ",".join(sorted(arns)),
        "KnowledgeArns": ",".join(sorted(knowledge_arns)),
        "SourceArns": ",".join(sorted(source_arns)),
        "LogArns": ",".join(sorted(log_arns)),
        "SecretArns": ",".join(sorted(set(secrets))),
        "ObserverArns": ",".join(
            f"arn:aws:iam::{config['accounts'][d]['id']}:role/{config['project']}-observer"
            for d in DOMAINS if d != "platform"
        ),
        "PersonaArns": ",".join(sorted(personas)),
        "TerraformPoolArn": f"arn:aws:cognito-idp:{config['region']}:{tf['account_id']}:userpool/{tf['user_pool_id']}",
    }


def deploy(config, labs, execute):
    from infra.workshop.generate import generate

    assert_account_plan(account_plan(config, labs, runner=True))
    check_accounts(config, domains=DOMAINS)
    generate()
    archive, digest = package(config)
    key = "source/" + digest + ".zip"
    params = parameters(config, key, labs)
    path = ROOT / "build/workshop-runner-parameters.json"
    path.write_text(json.dumps(params, indent=2) + "\n")
    # Fonte imutável por hash é um artefato do pipeline IaC, como o ZIP dos runtimes.
    session(config).client("s3").upload_file(str(archive), params["ArtifactBucket"], key)
    account = config["accounts"]["platform"]
    subprocess.run([
        sys.executable, str(ROOT / "scripts/banking_deploy.py"), "runner",
        "--scenario", "workshop",
        *(["--profile", account["profile"]] if account.get("profile") else []),
        "--region", config["region"], "--account", account["id"],
        "--stack", stack_name(config, "platform", "runner"), "--parameters", str(path),
        *(["--execute"] if execute else []),
    ], cwd=ROOT, check=True)
    print(json.dumps({"source_sha256": digest, "source_key": key, "labs": labs or "all"}))


def preflight_run(config, codebuild, project_name, labs):
    """Confere a seleção efetiva, inclusive WORKSHOP_LABS salvo no projeto AWS."""
    if not labs:
        projects = codebuild.batch_get_projects(names=[project_name])["projects"]
        if len(projects) != 1:
            raise ValueError("WORKSHOP_RUNNER_PROJECT_NOT_FOUND")
        environment = {
            item["name"]: item["value"]
            for item in projects[0]["environment"]["environmentVariables"]
        }
        labs = environment.get("WORKSHOP_LABS", "").split()
    check_selection(config, labs, runner=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["deploy", "run", "status", "fetch"])
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--labs", nargs="*", default=[])
    parser.add_argument("--build-id")
    parser.add_argument("--lifecycle-stage", choices=[
        "baseline", "updated", "revoked", "deleted", "reingested",
    ])
    parser.add_argument("--memory-session")
    args = parser.parse_args()
    if any(lab not in {f"{i:02d}" for i in range(17)} for lab in args.labs):
        parser.error("Aulas válidas: 00 a 16")
    if args.lifecycle_stage or args.memory_session:
        from santander_demo.aws_workshop.backend import session_id

        if args.action != "run" or args.labs != ["15"] or not all([
            args.lifecycle_stage, args.memory_session,
        ]):
            parser.error("Ciclo de vida requer run --labs 15 --lifecycle-stage e --memory-session")
        session_id(args.memory_session)
    config = load(args.config)
    check_accounts(config)
    if args.action == "deploy":
        deploy(config, args.labs, args.execute)
        return
    env = outputs(config, "runner")
    aws = session(config)
    codebuild = aws.client("codebuild")
    if args.action == "run":
        if not args.execute:
            parser.error("run requer --execute para iniciar a execução AWS")
        preflight_run(config, codebuild, env["ProjectName"], args.labs)
        overrides = []
        if args.labs:
            overrides.append({"name": "WORKSHOP_LABS", "value": " ".join(args.labs), "type": "PLAINTEXT"})
        if args.lifecycle_stage:
            overrides.extend([
                {"name": "WORKSHOP_LIFECYCLE_STAGE", "value": args.lifecycle_stage, "type": "PLAINTEXT"},
                {"name": "WORKSHOP_MEMORY_SESSION", "value": args.memory_session, "type": "PLAINTEXT"},
            ])
        result = codebuild.start_build(
            projectName=env["ProjectName"], environmentVariablesOverride=overrides,
        )["build"]
    else:
        if not args.build_id or not args.build_id.startswith(env["ProjectName"] + ":"):
            parser.error("Forneça --build-id pertencente ao runner deste projeto")
        result, = codebuild.batch_get_builds(ids=[args.build_id])["builds"]
    record = {key: result.get(key) for key in ["id", "arn", "buildStatus", "currentPhase", "logs", "artifacts", "phases"]}
    path = ROOT / "evidence/workshop-build.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    if args.action == "fetch":
        location = result.get("artifacts", {}).get("location", "")
        if not location.startswith("arn:aws:s3:::"):
            raise ValueError("BUILD_ARTIFACTS_NOT_AVAILABLE")
        bucket, key = location.removeprefix("arn:aws:s3:::").split("/", 1)
        if bucket != outputs(config, "bootstrap")["ArtifactBucket"] or not key.startswith("evidence/"):
            raise ValueError("UNEXPECTED_BUILD_ARTIFACT_LOCATION")
        target = ROOT / "evidence" / result["id"].split(":")[1]
        target.mkdir(exist_ok=True)
        archive = target / "notebooks.zip"
        aws.client("s3").download_file(bucket, key, str(archive))
        with zipfile.ZipFile(archive) as zipped:
            if any(Path(name).is_absolute() or ".." in Path(name).parts for name in zipped.namelist()):
                raise ValueError("UNSAFE_EVIDENCE_ARCHIVE_PATH")
            zipped.extractall(target)
        record["downloaded"] = str(target)
    print(json.dumps(record, indent=2, default=str))


if __name__ == "__main__":
    main()
