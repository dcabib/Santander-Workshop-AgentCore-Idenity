"""Fixture declarada por CloudFormation; nenhuma carga manual fora do pipeline."""

import json
from urllib.request import Request, urlopen

import boto3

from .lifecycle import revision, stage

DATA = {
    "riscos": [{"cliente_id": "C001", "rating": "B", "score": 720}],
    "fraude": [{"cliente_id": "C001", "indicios": ["dispositivo_novo"], "revisao": "manual"}],
    "k2": [{"documento": "limite-operacional", "conteudo": "Consultas limitadas a dez registros."}],
}
GRANTS = {"a": ["riscos", "k2"], "b": ["fraude", "k2"], "c": ["riscos", "fraude", "k2"], "d": []}


def provision(event, table):
    if event["RequestType"] == "Delete":
        return {}  # CloudFormation controla o ciclo de vida da tabela.
    props = event["ResourceProperties"]
    current = stage(props.get("LifecycleStage", "baseline"))
    grants = json.loads(props["GrantsJson"]) if "GrantsJson" in props else GRANTS
    with table.batch_writer() as batch:
        for name, rows in DATA.items():
            if name == "k2":
                if current == "deleted":
                    batch.delete_item(Key={"pk": "DATA", "sk": name})
                    continue
                rows = [{**row, "revision": revision(current)} for row in rows]
            batch.put_item(Item={"pk": "DATA", "sk": name, "content": json.dumps(rows)})
        for label, subject in props["Users"].items():
            for name in DATA:
                batch.put_item(Item={
                    "pk": "ACL#" + subject, "sk": name,
                    "allowed": name in grants[label] and not (
                        current == "revoked" and label == "c" and name == "k2"
                    ),
                })
    return {"SourceKind": "AWS_SIMULATED_DATABRICKS", "LifecycleStage": current}


def handler(event, context):
    response = {
        "StackId": event["StackId"], "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "PhysicalResourceId": event.get("PhysicalResourceId", event["LogicalResourceId"]),
        "Status": "SUCCESS", "Data": {},
    }
    try:
        response["Data"] = provision(
            event, boto3.resource("dynamodb").Table(event["ResourceProperties"]["Table"]),
        )
    except Exception as exc:
        response.update(Status="FAILED", Reason="Source provisioning failed: " + type(exc).__name__)
    body = json.dumps(response).encode()
    with urlopen(Request(
        event["ResponseURL"], data=body, method="PUT", headers={"Content-Type": ""},
    ), timeout=30) as remote:
        remote.read()
