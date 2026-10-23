"""Publicação e ingestão exclusivamente como recurso CloudFormation."""

import hashlib
import json
import time
import urllib.request

import boto3

from santander_demo.rag.corpus import corpus_digest, objects


def provision(event, s3, bedrock, *, sleep=time.sleep, monotonic=time.monotonic):
    props = event["ResourceProperties"]
    physical = event.get("PhysicalResourceId", "rag-corpus-" + props["KnowledgeBaseId"])
    if event["RequestType"] == "Delete":
        # Fonte e KB são retidas; não apagamos documentos nem desabilitamos proteções.
        return physical, {"Retained": True}
    if props["CorpusDigest"] != corpus_digest(props["Users"]):
        raise ValueError("CORPUS_DIGEST_MISMATCH")
    for key, content in objects(props["Bucket"], props["Users"]).items():
        s3.put_object(
            Bucket=props["Bucket"],
            Key=key,
            Body=content,
            ContentType="application/json"
            if key.endswith(".json")
            else "text/plain; charset=utf-8",
            ServerSideEncryption="AES256",
        )
    args = {"knowledgeBaseId": props["KnowledgeBaseId"], "dataSourceId": props["DataSourceId"]}
    deadline = monotonic() + 720
    while bedrock.get_data_source(**args)["dataSource"]["status"] != "AVAILABLE":
        if monotonic() >= deadline:
            raise TimeoutError("DATA_SOURCE_NOT_AVAILABLE")
        sleep(10)
    token = hashlib.sha256(event["RequestId"].encode()).hexdigest()
    job = bedrock.start_ingestion_job(**args, clientToken=token)["ingestionJob"]
    while True:
        current = bedrock.get_ingestion_job(**args, ingestionJobId=job["ingestionJobId"])[
            "ingestionJob"
        ]
        if current["status"] == "COMPLETE":
            if current.get("statistics", {}).get("numberOfDocumentsFailed", 0):
                raise RuntimeError("INGESTION_HAS_FAILED_DOCUMENTS")
            return physical, {"IngestionJobId": job["ingestionJobId"]}
        if current["status"] in {"FAILED", "STOPPED"}:
            raise RuntimeError("INGESTION_" + current["status"])
        if monotonic() >= deadline:
            raise TimeoutError("INGESTION_DEADLINE_EXCEEDED")
        sleep(10)


def handler(event, context):
    physical = event.get("PhysicalResourceId", "rag-corpus-" + event["LogicalResourceId"])
    status, data, reason = "SUCCESS", {}, "Concluído"
    try:
        physical, data = provision(event, boto3.client("s3"), boto3.client("bedrock-agent"))
    except Exception as exc:
        status, reason = "FAILED", type(exc).__name__ + ": revisar ingestão pelo pipeline IaC"
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
    with urllib.request.urlopen(request, timeout=20):
        pass
