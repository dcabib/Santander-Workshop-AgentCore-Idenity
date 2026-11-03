"""Pipeline CloudFormation da jornada; nenhum recurso criado fora dos templates."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from santander_demo.aws_workshop.client import stack_name
from santander_demo.aws_workshop.config import DOMAINS, check_accounts, load, session, stack_outputs

ROOT = Path(__file__).resolve().parents[1]
PHASES = ("bootstrap", "identity", "gateway", "backend", "bindings", "agent", "policy-draft")


def outputs(config, domain, phase):
    return stack_outputs(session(config, domain), stack_name(config, domain, phase))


def prepare(config, domain, phase):
    values = {}
    if phase == "bootstrap":
        return values
    values["Project"] = stack_name(config, domain, "aws")
    if phase in {"identity", "gateway", "backend", "agent", "agent-riscos", "agent-fraude", "policy-draft"}:
        values["ArtifactBucket"] = outputs(config, domain, "bootstrap")["ArtifactBucket"]
    if phase in {"gateway", "backend", "bindings", "agent", "agent-riscos", "agent-fraude", "federation-bindings"}:
        identity = outputs(config, "platform", "identity")
        values.update({k: identity[k] for k in ["Issuer", "SupervisorClientId", "RiscosClientId"]})
        if phase in {"backend", "bindings"}:
            values.update({f"User{x}Oid": identity[f"User{x}Oid"] for x in "ABCD"})
    if phase == "gateway":
        values["EngineName"] = values["Project"].replace("-", "_")
        from botocore.exceptions import ClientError

        try:
            values["KnownGatewayArn"] = outputs(config, domain, "gateway")["GatewayArn"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ValidationError" or "does not exist" not in str(exc):
                raise
            values["KnownGatewayArn"] = ""
    if phase in {"backend", "bindings"}:
        gateway = outputs(config, domain, "gateway")
        values["GatewayArn"] = gateway["GatewayArn"]
    if phase == "backend":
        values["RuntimeName"] = values.pop("Project").replace("-", "_")
        values["GatewayRoleArn"] = gateway["GatewayRoleArn"]
        values["LifecycleStage"] = config.get("lifecycle_stage", "baseline")
    if phase == "bindings":
        values.pop("Project")
        values.pop("UserDOid")
        values.update({k: gateway[k] for k in ["GatewayId", "PolicyEngineId", "GatewayRoleName"]})
        backend = outputs(config, domain, "backend")
        values.update({k: backend[k] for k in ["RuntimeUrl", "RuntimeArn"]})
    if phase == "agent":
        values["RuntimeName"] = values.pop("Project").replace("-", "_") + "_agent"
        values["GatewayUrl"] = outputs(config, domain, "gateway")["GatewayUrl"]
        values["ModelId"] = config["model_id"]
    if phase in {"agent-riscos", "agent-fraude"}:
        values["RuntimeName"] = values.pop("Project").replace("-", "_") + "_" + phase.replace("-", "_")
        values["GatewayUrl"] = outputs(config, "platform", "gateway")["GatewayUrl"]
        values["ModelId"] = config["model_id"]
    if phase == "federation-bindings":
        if domain != "platform":
            raise ValueError("FEDERATION_BELONGS_TO_PLATFORM")
        values.pop("Project")
        gateway = outputs(config, "platform", "gateway")
        values.update({k: gateway[k] for k in ["GatewayId", "GatewayArn", "PolicyEngineId"]})
        identity = outputs(config, "platform", "identity")
        values.update({f"User{x}Oid": identity[f"User{x}Oid"] for x in "ABC"})
        for label, target_domain in [
            ("Retail", "retail-banking"), ("Transaction", "transaction-banking"),
            ("Lending", "lending-wealth"),
        ]:
            values[label + "Url"] = outputs(config, target_domain, "gateway")["GatewayUrl"]
    if phase == "observer":
        values = {
            "Project": config["project"],
            "RunnerArn": outputs(config, "platform", "runner")["RoleArn"],
            "ControlArns": ",".join(sorted({
                value + suffix
                for phase_name in ["gateway", "backend"]
                for key, value in outputs(config, domain, phase_name).items()
                if key.endswith("Arn")
                for suffix in ["", "/*"]
            })),
        }
    if phase == "policy-draft":
        gateway = outputs(config, domain, "gateway")
        values.update({k: gateway[k] for k in ["GatewayArn", "PolicyEngineId", "PolicyEngineArn"]})
        values["RawText"] = (
            "Permit only the configured Cognito subject "
            + outputs(config, "platform", "identity")["UserCOid"]
            + " to call riscos___consultar_risco for cliente_id C001 "
            "with max_registros between 1 and 10. All other access must be denied."
        )
    if phase == "rag-agent":
        from santander_demo.rag.deployment import outputs as rag_outputs

        rag = json.loads((ROOT / config["integrations"]["rag"]["config"]).read_text())
        aws = session(config)
        access = rag_outputs(aws, rag, "access")
        data = rag_outputs(aws, rag, "data")
        values = {
            "ArtifactBucket": outputs(config, "platform", "bootstrap")["ArtifactBucket"],
            "Issuer": f"https://cognito-idp.{rag['region']}.amazonaws.com/{rag['user_pool_id']}",
            "LoginClientId": rag["login_client_id"],
            "RuntimeName": config["project"].replace("-", "_") + "_rag",
            "GatewayUrl": access["GatewayUrl"], "SourceBucket": data["SourceBucket"],
            "KnowledgeBaseId": data["KnowledgeBaseId"], "ModelArn": rag["model_arn"],
            "RagConfig": json.dumps(rag),
        }
    return values


def recover_failed_create(config, domain, phase):
    """Recuperação explícita de stack novo cujo rollback já removeu os recursos."""
    descriptions = {
        "backend": "Workshop AWS - MCP Runtime, source ACLs and native AgentCore Memory",
        "bindings": "Workshop AWS - MCP JWT propagation and explicit per-person Cedar",
        "policy-draft": "Santander - geração assistida de rascunho Cedar, sem publicação",
    }
    if phase not in descriptions:
        raise ValueError("RECOVERY_IS_SCOPED_TO_NEW_BACKEND_BINDINGS_OR_POLICY_DRAFT")
    check_accounts(config, domains=tuple(dict.fromkeys(["platform", domain])))
    cloudformation = session(config, domain).client("cloudformation")
    name = stack_name(config, domain, phase)
    stack = cloudformation.describe_stacks(StackName=name)["Stacks"][0]
    if stack["StackStatus"] != "ROLLBACK_COMPLETE":
        raise ValueError("RECOVERY_REQUIRES_COMPLETED_CREATE_ROLLBACK")
    document = cloudformation.get_template(StackName=name)["TemplateBody"]
    if isinstance(document, str):
        document = json.loads(document)
    if document.get("Description") != descriptions[phase]:
        raise ValueError("RECOVERY_TEMPLATE_OWNERSHIP_MISMATCH")
    resources = [
        resource for page in cloudformation.get_paginator("list_stack_resources").paginate(StackName=name)
        for resource in page["StackResourceSummaries"]
    ]
    def removed_or_failed(resource):
        if resource["ResourceStatus"] in {"DELETE_COMPLETE", "CREATE_FAILED"}:
            return True
        # A API não tem DeletePolicyGeneration. Só aceitamos o marcador de
        # Create que falhou, nunca um rascunho gerado ou outro recurso retido.
        return (
            phase == "policy-draft"
            and resource.get("LogicalResourceId") == "Draft"
            and resource.get("ResourceType") == "Custom::AgentCorePolicyDraft"
            and resource["ResourceStatus"] == "DELETE_SKIPPED"
            and re.fullmatch(r"failed-[0-9a-f]{12}", resource.get("PhysicalResourceId", "")) is not None
        )

    if not all(removed_or_failed(resource) for resource in resources):
        raise ValueError("RECOVERY_BLOCKED_BY_REMAINING_RESOURCES")
    # Operação do pipeline, somente após --recover-failed-create explícito.
    # Log groups gerados pelo serviço são preservados para investigação.
    cloudformation.delete_stack(StackName=name)
    cloudformation.get_waiter("stack_delete_complete").wait(StackName=name)


def deploy(config, domain, phase, execute):
    if phase == "identity" and domain != "platform":
        raise ValueError("A identidade compartilhada pertence à conta de plataforma")
    check_accounts(config, domains=tuple(dict.fromkeys(["platform", domain])))
    params = prepare(config, domain, phase)
    path = ROOT / "build" / f"workshop-{domain}-{phase}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(params, indent=2) + "\n")
    path.chmod(0o600)
    profile = config["accounts"][domain].get("profile")
    subprocess.run([
        sys.executable, str(ROOT / "scripts/banking_deploy.py"), phase,
        "--scenario", "workshop",
        *(["--profile", profile] if profile else []),
        "--account", config["accounts"][domain]["id"],
        "--region", config["region"],
        "--stack", stack_name(config, domain, phase), "--parameters", str(path),
        *(["--execute"] if execute else []),
    ], cwd=ROOT, check=True)
    if execute and phase == "gateway" and not params["KnownGatewayArn"]:
        # A primeira criação fornece o ARN gerado pelo serviço. O segundo
        # change set fixa a trust policy nesse ARN antes de criar o backend.
        deploy(config, domain, phase, execute)


def main():
    sys.path.insert(0, str(ROOT))
    from infra.workshop.generate import generate

    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=[
        *PHASES, "rag-agent", "observer", "federation-bindings", "agent-riscos", "agent-fraude", "all",
    ])
    parser.add_argument("--config", default="config/aws.workshop.json")
    parser.add_argument("--domain", choices=DOMAINS, default="platform")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--lifecycle-stage", choices=[
        "baseline", "updated", "revoked", "deleted", "reingested",
    ])
    parser.add_argument("--recover-failed-create", action="store_true",
                        help="Recuperação aprovada de backend/bindings/policy-draft novos em ROLLBACK_COMPLETE")
    args = parser.parse_args()
    if args.phase == "all" and not args.execute:
        parser.error("Para revisar change sets, selecione uma fase; all requer --execute")
    config = load(args.config)
    if args.lifecycle_stage:
        if args.phase != "backend" or args.domain != "platform":
            parser.error("O ciclo da aula 15 pertence somente ao backend da plataforma")
        config["lifecycle_stage"] = args.lifecycle_stage
    generate()
    if args.recover_failed_create:
        if not args.execute or args.phase not in {"backend", "bindings", "policy-draft"}:
            parser.error("Recuperação requer backend, bindings ou policy-draft com --execute")
        recover_failed_create(config, args.domain, args.phase)
    phases = PHASES if args.phase == "all" else [args.phase]
    for phase in phases:
        if args.phase == "all" and args.domain != "platform" and phase in {
            "identity", "agent", "policy-draft",
        }:
            continue
        deploy(config, args.domain, phase, args.execute)


if __name__ == "__main__":
    main()
