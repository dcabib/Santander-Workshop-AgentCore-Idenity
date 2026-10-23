"""Mutações do catálogo exclusivamente como custom resources CloudFormation."""

import json
import os
import time
import urllib.request

import boto3
from botocore.exceptions import ClientError

from .contracts import digest

STABLE = {"DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED", "DEPRECATED"}


class Provider:
    def __init__(self, client, sleep=time.sleep, polls=100):
        self.client, self.sleep, self.polls = client, sleep, polls
        self.physical_id = None

    def wait(self, registry, record=None, states=None, absent=False):
        args = {"registryId": registry}
        method = self.client.get_registry
        if record:
            args["recordId"] = record
            method = self.client.get_registry_record
        for _ in range(self.polls):
            try:
                value = method(**args)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
                if absent:
                    return {}
            else:
                if not absent and value["status"] in (states or STABLE):
                    return value
                if value["status"].endswith("FAILED"):
                    raise RuntimeError("REGISTRY_RESOURCE_FAILED")
            self.sleep(3)
        raise TimeoutError("REGISTRY_NOT_STABLE")

    def handle(self, event):
        props = event["ResourceProperties"]
        kind = props["Kind"]
        if kind not in {"Registry", "Record", "Submission", "Approval"}:
            raise ValueError("INVALID_KIND")
        physical = event.get("PhysicalResourceId", "")
        if event["RequestType"] == "Delete":
            # Remover Submission/Approval não desfaz uma decisão. O registro tem seu próprio Delete.
            if kind not in {"Registry", "Record"} or not physical.startswith("arn:"):
                return physical or "deleted", {}
            parts = physical.split("/")
            registry, record = (parts[-3], parts[-1]) if kind == "Record" else (parts[-1], None)
            try:
                if record:
                    self.client.delete_registry_record(registryId=registry, recordId=record)
                else:
                    self.client.delete_registry(registryId=registry)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
            self.wait(registry, record, absent=True)
            return physical, {}
        if event["RequestType"] not in {"Create", "Update"}:
            raise ValueError("INVALID_REQUEST")
        token = digest(
            [
                event["StackId"],
                event["LogicalResourceId"],
                {k: v for k, v in props.items() if k != "ServiceToken"},
            ]
        )
        if kind == "Registry":
            if props.get("RecoveryArn"):
                # Reconciliação pelo próprio IaC após cancelamento de Create pelo CFN.
                arn = props["RecoveryArn"]
                current = self.wait(arn.split("/")[-1], states={"READY"})
                if current["registryArn"] != arn or not current["name"].startswith(
                    "workshop-personas-"
                ):
                    raise ValueError("RECOVERY_RESOURCE_MISMATCH")
                self.physical_id = arn
                return arn, {"Id": arn.split("/")[-1], "Arn": arn}
            result = self.client.create_registry(
                name="workshop-personas-" + token[:12],
                discoveryConfiguration={"authorizerType": "AWS_IAM"},
                approvalConfiguration={"autoApprovalRules": []},
                clientToken=token,
            )
            self.physical_id = result["registryArn"]
            registry = self.physical_id.split("/")[-1]
            self.wait(registry, states={"READY"})
            return self.physical_id, {"Id": registry, "Arn": self.physical_id}
        registry = props["RegistryId"]
        if kind == "Record":
            package = json.loads(props["Package"])
            # Versionamento imutável nesta bancada: alteração do bundle exige nova versão.
            result = self.client.create_registry_record(
                registryId=registry, clientToken=token, **package
            )
            self.physical_id = result["recordArn"]
            record = self.physical_id.split("/")[-1]
            self.wait(registry, record)
            return self.physical_id, {"Id": record, "Digest": digest(package)}
        record = props["RecordId"]
        current = self.wait(registry, record)
        args = {"registryId": registry, "recordId": record}
        if kind == "Submission":
            if current["status"] == "DRAFT":
                self.client.submit_registry_record_for_approval(**args)
                self.wait(registry, record, {"PENDING_APPROVAL"})
            elif current["status"] not in {"PENDING_APPROVAL", "APPROVED", "REJECTED"}:
                raise ValueError("CANNOT_SUBMIT")
        else:
            # O aprovador confirma exatamente os campos que compõem o bundle revisado.
            package = {
                k: current[k]
                for k in ("name", "recordType", "recordVersion", "description", "descriptors")
            }
            if digest(package) != props["ReviewedDigest"]:
                raise ValueError("REVIEW_CHANGED")
            decision = props["Decision"]
            if decision not in {"APPROVED", "REJECTED"}:
                raise ValueError("INVALID_DECISION")
            if current["status"] != decision:
                if current["status"] != "PENDING_APPROVAL":
                    raise ValueError("EXPECTED_PENDING_APPROVAL")
                self.client.update_registry_record_status(
                    **args,
                    status=decision,
                    statusReason="Bundle revisado no change set CloudFormation",
                )
                self.wait(registry, record, {decision})
        return f"{kind}-{record}", {"Status": self.wait(registry, record)["status"]}


def handler(event, context):
    p = Provider(boto3.client("agent-registry-control"))
    physical = event.get("PhysicalResourceId", "failed-" + event["LogicalResourceId"])
    status, data, reason = "SUCCESS", {}, "Concluído"
    try:
        if event["ResourceProperties"]["Kind"] not in os.environ["RESOURCE_KINDS"].split(","):
            raise ValueError("WRONG_PROVIDER")
        physical, data = p.handle(event)
    except Exception as exc:
        physical = p.physical_id or physical
        status = "FAILED"
        # Somente código/tipo; nunca evento, credenciais ou URL de resposta.
        code = exc.response["Error"]["Code"] if isinstance(exc, ClientError) else str(exc)
        reason = f"{type(exc).__name__}: {code}"[:500]
        print(json.dumps({"error": reason, "logical_id": event["LogicalResourceId"]}))
    body = json.dumps(
        {
            "Status": status,
            "Reason": reason,
            "PhysicalResourceId": physical,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "NoEcho": False,
            "Data": data,
        }
    ).encode()
    request = urllib.request.Request(
        event["ResponseURL"],
        data=body,
        method="PUT",
        headers={"Content-Type": "", "Content-Length": str(len(body))},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()
