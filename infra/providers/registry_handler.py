"""CloudFormation custom resources: Registry, publicação e decisão de aprovação.

Registry ainda não consta da especificação CloudFormation 267.0.0. Este provider
possui Create/Update/Delete, IDs determinísticos, retries idempotentes e espera
limitada. Não é uma ferramenta para mutações avulsas em notebooks.
"""

import hashlib
import json
import os
import time
import urllib.request

import boto3
from botocore.exceptions import ClientError


def stable_token(event):
    props = {k: v for k, v in event["ResourceProperties"].items() if k != "ServiceToken"}
    payload = [event["StackId"], event["LogicalResourceId"], props]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class Provider:
    def __init__(self, client, sleep=time.sleep, max_polls=90):
        self.client, self.sleep, self.max_polls = client, sleep, max_polls
        self.physical_id = None

    def wait(self, method, args, states, absent=False):
        for _ in range(self.max_polls):
            try:
                result = getattr(self.client, method)(**args)
            except ClientError as exc:
                if exc.response["Error"]["Code"] == "ResourceNotFoundException":
                    if absent:
                        return {}
                    self.sleep(2)
                    continue
                raise
            state = result.get("status")
            if not absent and state in states:
                return result
            if state and state.endswith("_FAILED"):
                raise RuntimeError(f"RESOURCE_{state}")
            self.sleep(2)
        raise TimeoutError("RESOURCE_NOT_STABLE")

    def delete(self, kind, physical):
        if physical.startswith("failed-") or kind == "Approval":
            return
        if kind == "Registry":
            args, op, getter = (
                {"registryId": physical.split("/")[-1]},
                "delete_registry",
                "get_registry",
            )
        else:
            parts = physical.split("/")
            args = {"registryId": parts[-3], "recordId": parts[-1]}
            op, getter = "delete_registry_record", "get_registry_record"
        try:
            getattr(self.client, op)(**args)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            return
        self.wait(getter, args, set(), absent=True)

    def handle(self, event):
        p, token = event["ResourceProperties"], stable_token(event)
        kind = p["Kind"]
        if kind not in {"Registry", "Record", "Approval"}:
            raise ValueError("UNKNOWN_KIND")
        if event["RequestType"] == "Delete":
            self.delete(kind, event["PhysicalResourceId"])
            return event["PhysicalResourceId"], {}
        if event["RequestType"] not in {"Create", "Update"}:
            raise ValueError("UNKNOWN_REQUEST")
        if kind == "Registry":
            # Mudanças no catálogo substituem o recurso e preservam o anterior para rollback.
            response = self.client.create_registry(
                name=f"{p['Name']}-{token[:10]}",
                description="Catálogo sintético Santander; governado pelo CloudFormation",
                authorizerType="AWS_IAM",
                approvalConfiguration={"autoApproval": False},
                clientToken=token,
            )
            physical = response["registryArn"]
            self.physical_id = physical
            args = {"registryId": physical.split("/")[-1]}
            self.wait("get_registry", args, {"READY"})
            return physical, {"Arn": physical, "Id": args["registryId"]}
        if kind == "Record":
            response = self.client.create_registry_record(
                registryId=p["RegistryId"],
                name=f"{p['Name']}-{token[:10]}",
                description=p["Description"],
                descriptorType="MCP",
                descriptors=p["Descriptors"],
                recordVersion=p["Version"],
                clientToken=token,
            )
            physical = response["recordArn"]
            self.physical_id = physical
            args = {"registryId": p["RegistryId"], "recordId": physical.split("/")[-1]}
            current = self.wait(
                "get_registry_record",
                args,
                {
                    "DRAFT",
                    "PENDING_APPROVAL",
                    "APPROVED",
                    "REJECTED",
                },
            )
            desired = p.get("Submit", "false") == "true"
            if desired and current["status"] == "DRAFT":
                self.client.submit_registry_record_for_approval(**args)
                self.wait("get_registry_record", args, {"PENDING_APPROVAL"})
            return physical, {"Arn": physical, "Id": args["recordId"]}
        args = {"registryId": p["RegistryId"], "recordId": p["RecordId"]}
        desired = p["Decision"]
        if desired not in {"APPROVED", "REJECTED"}:
            raise ValueError("INVALID_DECISION")
        current = self.wait(
            "get_registry_record",
            args,
            {
                "DRAFT",
                "PENDING_APPROVAL",
                "APPROVED",
                "REJECTED",
            },
        )
        if current["status"] != desired:
            if current["status"] != "PENDING_APPROVAL":
                raise ValueError("NEW_RECORD_VERSION_REQUIRED")
            self.client.update_registry_record_status(
                **args, status=desired, statusReason="Decisão revisada no change set IaC"
            )
            self.wait("get_registry_record", args, {desired})
        # Delete da decisão não reverte uma aprovação. Delete do registro remove a capacidade.
        return f"approval-{p['RecordId']}-{desired}", {"Status": desired}


def handler(event, context):
    physical = event.get("PhysicalResourceId", "failed-" + stable_token(event)[:16])
    status, data, reason = "SUCCESS", {}, "Concluído"
    provider = Provider(boto3.client("bedrock-agentcore-control"))
    try:
        # Funções distintas têm roles distintas; rejeitar roteamento à função errada.
        if event["ResourceProperties"]["Kind"] != os.environ["RESOURCE_KIND"]:
            raise ValueError("WRONG_PROVIDER")
        physical, data = provider.handle(event)
    except Exception as exc:
        # Devolver o ARN criado também na falha permite o Delete no rollback CFN.
        physical = provider.physical_id or physical
        status, reason = "FAILED", type(exc).__name__ + ": consultar logs sanitizados"
        print(
            json.dumps({"error_type": type(exc).__name__, "logical_id": event["LogicalResourceId"]})
        )
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
    # Nunca logar evento inteiro: ResponseURL é uma URL assinada.
    with urllib.request.urlopen(request, timeout=20):
        pass
