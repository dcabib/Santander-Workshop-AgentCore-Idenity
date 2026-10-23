"""Remoção de um stack do workshop pelo CloudFormation; padrão somente leitura."""

import argparse
import json
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIRS = {
    "workshop": ROOT / "infra/templates",
    "banking": ROOT / "infra/banking/templates",
    "federation": ROOT / "infra/federation/templates",
    "journey": ROOT / "infra/journey/templates",
    "rag": ROOT / "infra/rag/templates",
    "registry_workflow": ROOT / "infra/registry_workflow/templates",
}
STABLE_STATES = {
    "CREATE_COMPLETE",
    "UPDATE_COMPLETE",
    "UPDATE_ROLLBACK_COMPLETE",
    "ROLLBACK_COMPLETE",
}


def load_template(scenario, name):
    directory = TEMPLATE_DIRS[scenario]
    if name not in {path.stem for path in directory.glob("*.json")}:
        raise ValueError("Template não pertence ao cenário selecionado")
    return json.loads((directory / f"{name}.json").read_text())


def plan_cleanup(session, *, account, region, stack_name, template):
    """Confere conta, ARN e template, sem ler valores de parâmetros/segredos na saída."""
    if session.client("sts").get_caller_identity()["Account"] != account:
        raise ValueError("A conta do perfil não corresponde à conta solicitada")
    client = session.client("cloudformation")
    stack = client.describe_stacks(StackName=stack_name)["Stacks"][0]
    arn = stack["StackId"]
    parts = arn.split(":", 5)
    if (
        len(parts) != 6
        or parts[0] != "arn"
        or parts[2] != "cloudformation"
        or parts[3] != region
        or parts[4] != account
        or stack["StackName"] != stack_name
        or not parts[5].startswith(f"stack/{stack_name}/")
    ):
        raise ValueError("Stack, região ou conta divergem do alvo solicitado")
    deployed = client.get_template(StackName=arn, TemplateStage="Original")["TemplateBody"]
    if isinstance(deployed, str):
        deployed = json.loads(deployed)
    if deployed != template:
        raise ValueError(
            "Template implantado difere da fonte local; confira a versão IaC antes de remover"
        )
    blockers = []
    if stack.get("EnableTerminationProtection"):
        blockers.append("TERMINATION_PROTECTION_ENABLED")
    if stack["StackStatus"] not in STABLE_STATES:
        blockers.append("STACK_NOT_IN_STABLE_STATE")
    retained = {
        logical_id: {"type": resource["Type"], "policy": resource["DeletionPolicy"]}
        for logical_id, resource in template["Resources"].items()
        if resource.get("DeletionPolicy") in {"Retain", "RetainExceptOnCreate", "Snapshot"}
    }
    return {
        "mode": "READ_ONLY_PLAN",
        "account": account,
        "region": region,
        "stack_name": stack_name,
        "stack_id": arn,
        "stack_status": stack["StackStatus"],
        "template_matches": True,
        "blockers": blockers,
        "retention_declared_in_template": retained,
        "external_resources": "NOT_MANAGED_BY_THIS_STACK",
        "dependency_order": "REVIEW_SCENARIO_RUNBOOK",
    }


def execute_cleanup(session, plan, confirmation):
    """Única mutação: exclusão pelo ARN exato do stack; respeita Retain e proteções."""
    if confirmation != plan["stack_id"]:
        raise ValueError("Confirme o ARN exato exibido no plano com --confirm-stack-id")
    if plan["blockers"]:
        raise ValueError("Remoção bloqueada: " + ", ".join(plan["blockers"]))
    client = session.client("cloudformation")
    client.delete_stack(StackName=plan["stack_id"])
    client.get_waiter("stack_delete_complete").wait(
        StackName=plan["stack_id"], WaiterConfig={"Delay": 5, "MaxAttempts": 120}
    )
    return {
        "cloud_cleanup": "STACK_DELETE_COMPLETE",
        "stack_id": plan["stack_id"],
        "retained_resources": plan["retention_declared_in_template"],
        "external_resources": "UNCHANGED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(TEMPLATE_DIRS), required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--stack", required=True, help="Nome exato do stack do laboratório")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-stack-id", help="ARN do stack exibido pelo plano revisado")
    args = parser.parse_args()
    if args.execute and not args.confirm_stack_id:
        parser.error("--execute requer --confirm-stack-id com o ARN do plano revisado")
    template = load_template(args.scenario, args.template)
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    plan = plan_cleanup(
        session,
        account=args.account,
        region=args.region,
        stack_name=args.stack,
        template=template,
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if args.execute:
        print(json.dumps(execute_cleanup(session, plan, args.confirm_stack_id), indent=2))


if __name__ == "__main__":
    main()
