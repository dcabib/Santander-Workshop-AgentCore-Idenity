"""Leituras e invocações; nenhum create/update/delete fora do provider IaC."""

import json
import time
import uuid

import boto3
import httpx
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

from .contracts import validate_agent

DISCOVERY_ACTIONS = [
    "agent-registry:SearchDiscoverableRegistryRecords",
    "agent-registry:ListDiscoverableRegistryRecords",
    "agent-registry:GetDiscoverableRegistryRecord",
]


class RegistryLab:
    def __init__(self, config):
        self.config = config
        self.operator = boto3.Session(profile_name=config["profile"], region_name=config["region"])

    def persona(self, name, discovery_only=False):
        if name not in {"Developer", "Publisher", "Approver", "Consumer"}:
            raise ValueError("UNKNOWN_PERSONA")
        args = {
            "RoleArn": self.config[name + "RoleArn"],
            "RoleSessionName": "registry-workshop-" + name.lower(),
        }
        if discovery_only:
            if name != "Consumer":
                raise ValueError("CONSUMER_REQUIRED")
            arn = self.config["RegistryArn"]
            args["Policy"] = json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": DISCOVERY_ACTIONS,
                            "Resource": [arn, arn + "/record/*"],
                        }
                    ],
                }
            )
        credentials = self.operator.client("sts").assume_role(**args)["Credentials"]
        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=self.config["region"],
        )

    def states(self):
        client = self.persona("Approver").client("agent-registry-control")
        return {
            name: client.get_registry_record(
                registryId=self.config["RegistryId"], recordId=self.config[name + "RecordId"]
            )["status"]
            for name in ("Mcp", "Agent")
        }

    def discover(self, session=None):
        client = (session or self.persona("Consumer")).client("agent-registry")
        args, ids = {"registryId": self.config["RegistryId"], "maxResults": 50}, []
        while True:
            page = client.list_discoverable_registry_records(**args)
            ids.extend(r["recordId"] for r in page.get("registryRecords", []))
            if not page.get("nextToken"):
                break
            args["nextToken"] = page["nextToken"]
        records = []
        for index in range(0, len(ids), 10):
            response = client.batch_get_discoverable_registry_record(
                entries=[
                    {
                        "registryId": self.config["RegistryId"],
                        "recordIds": ids[index : index + 10],
                    }
                ]
            )
            if response.get("errors"):
                raise PermissionError("DISCOVERY_PARTIAL_FAILURE")
            records.extend(response.get("registryRecords", []))
        return records

    def invoke(self, record, session=None):
        arn = validate_agent(
            record,
            gateway_url=self.config["GatewayUrl"],
            runtime_arn=self.config["RuntimeArn"],
            version="1.0.0",
        )
        response = (
            (session or self.persona("Consumer"))
            .client("bedrock-agentcore")
            .invoke_agent_runtime(
                agentRuntimeArn=arn,
                runtimeSessionId=str(uuid.uuid4()),
                contentType="application/json",
                accept="application/json",
                payload=json.dumps({"customer_id": "C001"}).encode(),
            )
        )
        raw = b"".join(response["response"].iter_chunks())
        return json.loads(raw)

    def iam_matrix(self):
        """Simulação de políticas IAM, não tentativa de executar escritas proibidas."""
        actions = [
            "agent-registry:CreateRegistryRecord",
            "agent-registry:UpdateRegistryRecordStatus",
            "agent-registry:ListDiscoverableRegistryRecords",
            "bedrock-agentcore:InvokeAgentRuntime",
        ]
        expected = {
            "Developer": [False, False, False, True],
            "Publisher": [True, False, False, False],
            "Approver": [False, True, False, False],
            "Consumer": [False, False, True, True],
        }
        resources = [
            self.config["RegistryArn"],
            self.config["RegistryArn"] + "/record/" + self.config["AgentRecordId"],
            self.config["RegistryArn"],
            self.config["RuntimeArn"],
        ]
        rows = []
        for name, allowed in expected.items():
            for action, arn, want in zip(actions, resources, allowed, strict=True):
                result = self.operator.client("iam").simulate_principal_policy(
                    PolicySourceArn=self.config[name + "RoleArn"],
                    ActionNames=[action],
                    ResourceArns=[arn],
                )["EvaluationResults"][0]["EvalDecision"]
                assert (result == "allowed") == want, (name, action, result)
                rows.append({"persona": name, "action": action, "decision": result})
        return rows

    def acceptance(self, polls=40):
        self.anonymous_checks()
        assert self.states() == {"Mcp": "APPROVED", "Agent": "APPROVED"}
        records = []
        for _ in range(polls):
            records = self.discover()
            if {r["recordId"] for r in records} >= {
                self.config["McpRecordId"],
                self.config["AgentRecordId"],
            }:
                break
            time.sleep(3)
        else:
            raise TimeoutError("DISCOVERY_NOT_INDEXED")
        agent = next(r for r in records if r["recordId"] == self.config["AgentRecordId"])
        result = self.invoke(agent)
        assert result["result"] == {"customer_id": "C001", "risk": "baixo"}, result
        limited = self.persona("Consumer", discovery_only=True)
        assert any(r["recordId"] == agent["recordId"] for r in self.discover(limited))
        try:
            self.invoke(agent, limited)
        except ClientError as exc:
            assert exc.response["Error"]["Code"] == "AccessDeniedException"
        else:
            raise AssertionError("DISCOVERY_ONLY_SESSION_INVOKED")
        matrix = self.iam_matrix()
        return {
            "mode": "AWS_LIVE",
            "status": "PASS",
            "approved_records": len(records),
            "discovery_without_invocation": "DENIED_AS_EXPECTED",
            "anonymous_runtime_and_gateway": "DENIED_AS_EXPECTED",
            "iam_checks": len(matrix),
            "result": result,
        }

    def anonymous_checks(self):
        client = boto3.client(
            "bedrock-agentcore", region_name=self.config["region"],
            config=Config(signature_version=UNSIGNED),
        )
        try:
            client.invoke_agent_runtime(
                agentRuntimeArn=self.config["RuntimeArn"], runtimeSessionId=str(uuid.uuid4()),
                contentType="application/json", payload=b'{"customer_id":"C001"}',
            )
        except ClientError as exc:
            assert exc.response["ResponseMetadata"]["HTTPStatusCode"] in {401, 403}
        else:
            raise AssertionError("ANONYMOUS_RUNTIME_ALLOWED")
        response = httpx.post(self.config["GatewayUrl"], json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        }, timeout=30, follow_redirects=False)
        assert response.status_code in {401, 403}, ("ANONYMOUS_GATEWAY", response.status_code)
