"""Reconcilia KB/bucket retidos de um CREATE revertido usando IMPORT do CloudFormation.

Não chama APIs de criação, alteração ou exclusão de S3/Bedrock diretamente.
O modo padrão apenas produz o plano. Depois do import, reaplique a fase data.
"""

import argparse
import copy
import json
from pathlib import Path
from uuid import uuid4

import boto3

from infra.rag.generate import data

ROOT = Path(__file__).resolve().parents[1]


def plan(session, stack_id):
    cfn = session.client("cloudformation")
    stack = cfn.describe_stacks(StackName=stack_id)["Stacks"][0]
    account = session.client("sts").get_caller_identity()["Account"]
    if stack["StackId"] != stack_id or stack_id.split(":")[4] != account:
        raise ValueError("STACK_ACCOUNT_MISMATCH")
    if stack["StackStatus"] != "ROLLBACK_COMPLETE" or stack.get("EnableTerminationProtection"):
        raise ValueError("ONLY_UNPROTECTED_ROLLBACK_COMPLETE_SUPPORTED")
    deployed = cfn.get_template(StackName=stack_id)["TemplateBody"]
    deployed = json.loads(deployed) if isinstance(deployed, str) else deployed
    if deployed.get("Description") != data()["Description"]:
        raise ValueError("NOT_THIS_PROJECT_DATA_TEMPLATE")
    resources = cfn.list_stack_resources(StackName=stack_id)["StackResourceSummaries"]
    retained = {
        r["LogicalResourceId"]: r for r in resources if r["ResourceStatus"] == "DELETE_SKIPPED"
    }
    if "DataSource" in retained and not retained["DataSource"].get("PhysicalResourceId"):
        del retained["DataSource"]  # Falha antes da criação; não há recurso para importar.
    if set(retained) != {"KnowledgeBase", "SourceBucket"}:
        raise ValueError("UNEXPECTED_RETAINED_RESOURCES")
    kb_id = retained["KnowledgeBase"]["PhysicalResourceId"]
    kb = session.client("bedrock-agent").get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]
    sources = session.client("bedrock-agent").list_data_sources(knowledgeBaseId=kb_id)
    if sources.get("dataSourceSummaries") or sources.get("nextToken"):
        raise ValueError("EXISTING_DATA_SOURCES_REQUIRE_SEPARATE_REVIEW")
    if kb["knowledgeBaseConfiguration"]["type"] != "MANAGED":
        raise ValueError("NOT_A_MANAGED_KB")
    parameters = {p["ParameterKey"]: p["ParameterValue"] for p in stack.get("Parameters", [])}
    if kb["name"] != parameters["Project"]:
        raise ValueError("KB_PROJECT_MISMATCH")
    # As propriedades continuam as mesmas que criaram os recursos. O import
    # apenas os reassocia ao stack; a atualização seguinte restaura dependências.
    bucket_resource = copy.deepcopy(deployed["Resources"]["SourceBucket"])
    kb_resource = copy.deepcopy(deployed["Resources"]["KnowledgeBase"])
    kb_resource["Properties"]["Name"] = kb["name"]
    kb_resource["Properties"]["RoleArn"] = kb["roleArn"]
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Reassociate retained RAG resources before applying the corrected data template",
        "Resources": {"SourceBucket": bucket_resource, "KnowledgeBase": kb_resource},
    }
    imports = [
        {
            "ResourceType": "AWS::S3::Bucket",
            "LogicalResourceId": "SourceBucket",
            "ResourceIdentifier": {"BucketName": retained["SourceBucket"]["PhysicalResourceId"]},
        },
        {
            "ResourceType": "AWS::Bedrock::KnowledgeBase",
            "LogicalResourceId": "KnowledgeBase",
            "ResourceIdentifier": {"KnowledgeBaseId": kb_id},
        },
    ]
    cfn.get_template_summary(TemplateBody=json.dumps(template))
    return {
        "stack_id": stack_id,
        "stack_name": stack["StackName"],
        "template": template,
        "imports": imports,
    }


def execute(session, proposal, confirmation):
    if confirmation != proposal["stack_id"]:
        raise ValueError("EXACT_STACK_ARN_CONFIRMATION_REQUIRED")
    cfn = session.client("cloudformation")
    cfn.delete_stack(StackName=proposal["stack_id"])
    cfn.get_waiter("stack_delete_complete").wait(
        StackName=proposal["stack_id"], WaiterConfig={"Delay": 5, "MaxAttempts": 120}
    )
    change = cfn.create_change_set(
        StackName=proposal["stack_name"],
        ChangeSetName="recover-" + uuid4().hex[:12],
        ChangeSetType="IMPORT",
        TemplateBody=json.dumps(proposal["template"]),
        ResourcesToImport=proposal["imports"],
    )
    cfn.get_waiter("change_set_create_complete").wait(
        ChangeSetName=change["Id"], WaiterConfig={"Delay": 5, "MaxAttempts": 120}
    )
    details = cfn.describe_change_set(ChangeSetName=change["Id"])
    if {x["ResourceChange"]["Action"] for x in details["Changes"]} != {"Import"}:
        raise ValueError("UNEXPECTED_CHANGESET_ACTION")
    cfn.execute_change_set(ChangeSetName=change["Id"])
    cfn.get_waiter("stack_import_complete").wait(
        StackName=change["StackId"], WaiterConfig={"Delay": 5, "MaxAttempts": 180}
    )
    return {"recovery": "IMPORT_COMPLETE", "stack_id": change["StackId"], "next_phase": "data"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--stack-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-stack-id")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    proposal = plan(session, args.stack_id)
    destination = ROOT / "build/rag-recovery.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(proposal, indent=2) + "\n")
    print(
        json.dumps(
            {"mode": "READ_ONLY_PLAN", "manifest": str(destination), "imports": proposal["imports"]}
        )
    )
    if args.execute:
        print(json.dumps(execute(session, proposal, args.confirm_stack_id)))


if __name__ == "__main__":
    main()
