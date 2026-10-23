"""Reconcilia Create cancelado pelo CFN; somente stacks vazios em ROLLBACK_COMPLETE."""

import argparse
import json
import subprocess
import sys

import boto3

from santander_demo.registry_workflow.contracts import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--prefix", default="registry-personas")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name="us-east-1")
    cf = session.client("cloudformation")
    name = args.prefix + "-foundation"
    stack = cf.describe_stacks(StackName=name)["Stacks"][0]
    if stack["StackStatus"] != "ROLLBACK_COMPLETE" or stack.get("EnableTerminationProtection"):
        raise ValueError("RECOVERY_REQUIRES_UNPROTECTED_ROLLED_BACK_STACK")
    resources = cf.list_stack_resources(StackName=stack["StackId"])["StackResourceSummaries"]
    if any(r["ResourceStatus"] != "DELETE_COMPLETE" for r in resources):
        raise ValueError("STACK_HAS_REMAINING_RESOURCES")
    # Nome derivado do mesmo token usado no Create original; não adota catálogos alheios.
    template = cf.get_template(StackName=stack["StackId"])["TemplateBody"]
    if isinstance(template, str):
        template = json.loads(template)
    props = template["Resources"]["Registry"]["Properties"]
    if props != {"ServiceToken": {"Fn::GetAtt": ["RegistryProvider", "Arn"]}, "Kind": "Registry"}:
        raise ValueError("UNEXPECTED_ORIGINAL_TEMPLATE")
    token = digest([stack["StackId"], "Registry", {"Kind": "Registry"}])
    expected = "workshop-personas-" + token[:12]
    client = session.client("agent-registry-control")
    found, params = [], {}
    while True:
        page = client.list_registries(**params)
        found.extend(r for r in page.get("registries", []) if r["name"] == expected)
        if not page.get("nextToken"):
            break
        params["nextToken"] = page["nextToken"]
    if len(found) != 1 or found[0]["status"] != "READY":
        raise ValueError("EXPECTED_ONE_READY_REGISTRY")
    print(
        json.dumps(
            {
                "mode": "IAC_RECOVERY" if args.execute else "READ_ONLY_PLAN",
                "stack": name,
                "registry": found[0]["registryArn"],
                "action": "replace_empty_stack_and_reconcile_registry",
            }
        )
    )
    if args.execute:
        cf.delete_stack(StackName=stack["StackId"])
        cf.get_waiter("stack_delete_complete").wait(StackName=stack["StackId"])
        subprocess.run(
            [
                sys.executable,
                "scripts/registry_deploy.py",
                "foundation",
                "--profile",
                args.profile,
                "--prefix",
                args.prefix,
                "--recover-registry",
                found[0]["registryArn"],
                "--execute",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
