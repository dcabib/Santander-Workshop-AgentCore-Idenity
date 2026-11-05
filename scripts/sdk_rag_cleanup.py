"""Células de verificação e limpeza dos recursos RAG registrados."""

from scripts.aws_notebook_lessons import code, step

KEYS = {
    "rag.bucket", "rag.bucket_ready", "rag.objects", "rag.knowledge_role", "rag.knowledge_base",
    "rag.data_source", "rag.ingestion", "rag.gateway_permission", "rag.target",
    "rag.policy.analista", "rag.policy.auditor", "rag.artifact", "rag.runtime_role", "rag.runtime", "rag.logs",
}


def precheck():
    return code("""
    bedrock = aws.client("bedrock-agent") if any(key.startswith("rag.") for key in state.data["resources"]) else None
    from santander_demo.notebook_contracts import managed_source_configuration, native_knowledge_connector
    def rag_digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    for key, suffix in (("rag.knowledge_role", "-rag-knowledge"), ("rag.runtime_role", "-rag-runtime")):
        entry = state.get(key)
        if entry:
            assert entry["name"] == NAME_PREFIX + suffix
            current = iam.get_role(RoleName=entry["name"])["Role"]
            assert current["Arn"] == entry["arn"] and not current.get("PermissionsBoundary")
            owned({tag["Key"]: tag["Value"] for tag in current["Tags"]})
            assert rag_digest(current["AssumeRolePolicyDocument"]) == entry["trust_sha256"]
            attached = iam.list_attached_role_policies(RoleName=entry["name"])
            assert not attached["AttachedPolicies"] and not attached.get("IsTruncated")
            inline = iam.list_role_policies(RoleName=entry["name"])
            assert set(inline["PolicyNames"]) <= {entry["policy_name"]} and not inline.get("IsTruncated")
            if entry["policy_name"] in inline["PolicyNames"]:
                policy = iam.get_role_policy(RoleName=entry["name"], PolicyName=entry["policy_name"])["PolicyDocument"]
                assert rag_digest(policy) == entry["policy_sha256"], "RAG_ROLE_CHANGED"
    entry = state.get("rag.runtime")
    if entry:
        assert entry["name"] == NAME_PREFIX.replace("-", "_") + "_rag"
        current = control.get_agent_runtime(agentRuntimeId=entry["id"])
        assert current["agentRuntimeArn"] == entry["arn"] and current["roleArn"] == entry["role_arn"]
        fields = ("agentRuntimeArtifact", "roleArn", "networkConfiguration", "protocolConfiguration",
                  "authorizerConfiguration", "requestHeaderConfiguration", "environmentVariables", "lifecycleConfiguration")
        assert rag_digest({key: current[key] for key in fields}) == entry["configuration_sha256"], "RAG_RUNTIME_CHANGED"
        owned(control.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
        # O processo pode falhar antes da célula final registrar seu grupo.
        # Consultamos somente o nome derivado do ID do Runtime conferido.
        log_name = "/aws/bedrock-agentcore/runtimes/" + entry["id"] + "-DEFAULT"
        page = logs.describe_log_groups(logGroupNamePrefix=log_name)
        matches = [group for group in page["logGroups"] if group["logGroupName"] == log_name]
        if matches:
            state.record("rag.logs", {"name": log_name, "runtime_id": entry["id"]}, lesson="16")
    entry = state.get("rag.logs")
    if entry:
        assert entry["runtime_id"].startswith(NAME_PREFIX.replace("-", "_") + "_rag-")
        assert entry["name"] == "/aws/bedrock-agentcore/runtimes/" + entry["runtime_id"] + "-DEFAULT"
    entry = state.get("rag.knowledge_base")
    if entry:
        assert entry["arn"] == f"arn:{PARTITION}:bedrock:{REGION}:{ACCOUNT_ID}:knowledge-base/{entry['id']}"
        current = bedrock.get_knowledge_base(knowledgeBaseId=entry["id"])["knowledgeBase"]
        assert current["knowledgeBaseArn"] == entry["arn"] and current["name"] == NAME_PREFIX.replace("-", "_") + "_rag"
        assert current["roleArn"] == entry["role_arn"]
        assert rag_digest(current["knowledgeBaseConfiguration"]) == entry["configuration_sha256"]
        page = bedrock.list_data_sources(knowledgeBaseId=entry["id"])
        source = state.get("rag.data_source")
        assert not page.get("nextToken")
        # A exclusão pode concluir depois de um timeout do kernel. Uma fonte
        # registrada ausente é aceitável; uma fonte desconhecida continua bloqueando.
        assert {item["dataSourceId"] for item in page["dataSourceSummaries"]} <= ({source["id"]} if source else set())
    entry = state.get("rag.data_source")
    if entry:
        assert entry["knowledge_base_id"] == state.require("rag.knowledge_base", lesson="16")["id"]
        try:
            current = bedrock.get_data_source(
                knowledgeBaseId=entry["knowledge_base_id"], dataSourceId=entry["id"])["dataSource"]
        except bedrock.exceptions.ResourceNotFoundException:
            current = None
        if current is not None:
            assert current["name"] == "synthetic-acl-corpus" and current["dataDeletionPolicy"] == "DELETE"
            assert rag_digest(managed_source_configuration(current["dataSourceConfiguration"])) == entry["configuration_sha256"]
            assert rag_digest(current["vectorIngestionConfiguration"]) == entry["ingestion_sha256"]
            page = bedrock.list_ingestion_jobs(knowledgeBaseId=entry["knowledge_base_id"], dataSourceId=entry["id"])
            ingestion = state.get("rag.ingestion")
            assert not page.get("nextToken")
            assert {item["ingestionJobId"] for item in page["ingestionJobSummaries"]} == ({ingestion["id"]} if ingestion else set())
            assert all(item["status"] in {"COMPLETE", "FAILED", "STOPPED"} for item in page["ingestionJobSummaries"]), (
                "INGESTION_STILL_RUNNING"
            )
    entry = state.get("rag.target")
    if entry:
        assert entry["gateway_id"] == state.require("gateway.instance", lesson="01")["id"]
        assert entry["knowledge_base_id"] == state.require("rag.knowledge_base", lesson="16")["id"]
        current = control.get_gateway_target(gatewayIdentifier=entry["gateway_id"], targetId=entry["id"])
        assert current["name"] == "rag"
        assert rag_digest(native_knowledge_connector(current["targetConfiguration"])) == entry["configuration_sha256"]
        assert current["credentialProviderConfigurations"] == [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    entry = state.get("rag.gateway_permission")
    if entry:
        assert entry["role_name"] == state.require("gateway.role", lesson="01")["name"]
        assert entry["name"] == "Lesson16NativeKnowledgeBase"
        current = iam.get_role_policy(RoleName=entry["role_name"], PolicyName=entry["name"])["PolicyDocument"]
        assert rag_digest(current) == entry["document_sha256"]
    entry = state.get("rag.bucket")
    if entry:
        name = NAME_PREFIX + "-rag-" + ACCOUNT_ID + "-" + REGION
        assert entry["name"] == name and entry["arn"] == f"arn:{PARTITION}:s3:::{name}"
        s3.head_bucket(Bucket=name, ExpectedBucketOwner=ACCOUNT_ID)
        page = s3.list_objects_v2(Bucket=name, ExpectedBucketOwner=ACCOUNT_ID)
        assert not page.get("IsTruncated")
        registered = state.get("rag.objects")
        hashes = registered["hashes"] if registered else {}
        assert {item["Key"] for item in page.get("Contents", [])} == set(hashes), "UNREGISTERED_RAG_OBJECTS"
        if registered:
            assert registered["bucket"] == name
        for key, expected in hashes.items():
            remote = s3.get_object(Bucket=name, Key=key, ExpectedBucketOwner=ACCOUNT_ID)
            assert hashlib.sha256(remote["Body"].read()).hexdigest() == expected, "RAG_CORPUS_CHANGED"
    entry = state.get("rag.artifact")
    if entry:
        assert entry["bucket"] == state.require("runtime.bucket", lesson="03")["name"]
        assert entry["key"] == "rag/" + entry["sha256"] + ".zip"
        remote = s3.get_object(Bucket=entry["bucket"], Key=entry["key"], ExpectedBucketOwner=ACCOUNT_ID)
        assert hashlib.sha256(remote["Body"].read()).hexdigest() == entry["sha256"]
    """).source


def cleanup():
    return [
        *step(
        "Remover o agente RAG e o conector",
        "Após conferir toda a execução, removemos o Runtime, target, "
        "permits e concessão IAM de retrieval. DeleteDataSource usa a política "
        "DELETE registrada na criação; só depois excluímos a base, roles, "
        "corpus e artefato. Não removemos buckets por descoberta de prefixo.",
        """
        entry = state.get("rag.runtime")
        if entry:
            control.delete_agent_runtime(agentRuntimeId=entry["id"])
            wait_deleted(lambda: control.get_agent_runtime(agentRuntimeId=entry["id"]),
                         control.exceptions.ResourceNotFoundException)
            state.forget("rag.runtime", expected=entry)
        entry = state.get("rag.target")
        if entry:
            control.delete_gateway_target(gatewayIdentifier=entry["gateway_id"], targetId=entry["id"])
            wait_deleted(lambda: control.get_gateway_target(gatewayIdentifier=entry["gateway_id"], targetId=entry["id"]),
                         control.exceptions.ResourceNotFoundException)
            state.forget("rag.target", expected=entry)
        for key in ("rag.policy.analista", "rag.policy.auditor"):
            entry = state.get(key)
            if entry:
                control.delete_policy(policyEngineId=entry["engine_id"], policyId=entry["id"])
                wait_deleted(lambda: control.get_policy(policyEngineId=entry["engine_id"], policyId=entry["id"]),
                             control.exceptions.ResourceNotFoundException)
                state.forget(key, expected=entry)
        entry = state.get("rag.gateway_permission")
        if entry:
            iam.delete_role_policy(RoleName=entry["role_name"], PolicyName=entry["name"])
            wait_deleted(lambda: iam.get_role_policy(RoleName=entry["role_name"], PolicyName=entry["name"]),
                         iam.exceptions.NoSuchEntityException)
            state.forget("rag.gateway_permission", expected=entry)
        """,
        ),
        *step(
        "Excluir a fonte gerenciada e aguardar a confirmação",
        "DeleteDataSource usa a política DELETE registrada na criação. "
        "A exclusão MANAGED pode exceder cinco minutos; esta célula aguarda "
        "até quatorze minutos. Se a fonte estiver DELETING, acompanha a operação "
        "existente. Se já desapareceu, retira somente seu ID registrado. "
        "Uma fonte desconhecida na base impede a limpeza na verificação inicial.",
        """
        entry = state.get("rag.data_source")
        if entry:
            try:
                current = bedrock.get_data_source(
                    knowledgeBaseId=entry["knowledge_base_id"], dataSourceId=entry["id"])["dataSource"]
            except bedrock.exceptions.ResourceNotFoundException:
                current = None
            if current is not None:
                if current["status"] != "DELETING":
                    assert current["status"] == "AVAILABLE", ("DATA_SOURCE_DELETE_NOT_READY", current["status"])
                    bedrock.delete_data_source(knowledgeBaseId=entry["knowledge_base_id"], dataSourceId=entry["id"])
                wait_deleted(lambda: bedrock.get_data_source(
                    knowledgeBaseId=entry["knowledge_base_id"], dataSourceId=entry["id"])["dataSource"],
                    bedrock.exceptions.ResourceNotFoundException, timeout=840)
            state.forget("rag.data_source", expected=entry)
        entry = state.get("rag.ingestion")
        if entry:
            assert not state.get("rag.data_source")
            state.forget("rag.ingestion", expected=entry)
        print({"rag_data_source_cleanup": "CONFIRMED"})
        """,
        ),
        *step(
        "Remover a base RAG, roles, corpus e artefato",
        "A fonte já foi confirmada como ausente. Excluímos a base e os "
        "recursos restantes pelos IDs e hashes conferidos no início da aula.",
        """
        entry = state.get("rag.knowledge_base")
        if entry:
            bedrock.delete_knowledge_base(knowledgeBaseId=entry["id"])
            wait_deleted(lambda: bedrock.get_knowledge_base(knowledgeBaseId=entry["id"])["knowledgeBase"],
                         bedrock.exceptions.ResourceNotFoundException)
            state.forget("rag.knowledge_base", expected=entry)
        for key in ("rag.runtime_role", "rag.knowledge_role"):
            entry = state.get(key)
            if entry:
                names = iam.list_role_policies(RoleName=entry["name"])["PolicyNames"]
                if entry["policy_name"] in names:
                    iam.delete_role_policy(RoleName=entry["name"], PolicyName=entry["policy_name"])
                iam.delete_role(RoleName=entry["name"])
                wait_deleted(lambda: iam.get_role(RoleName=entry["name"]), iam.exceptions.NoSuchEntityException)
                state.forget(key, expected=entry)
        entry = state.get("rag.bucket")
        if entry:
            registered = state.get("rag.objects")
            for key in registered["hashes"] if registered else []:
                s3.delete_object(Bucket=entry["name"], Key=key, ExpectedBucketOwner=ACCOUNT_ID)
            assert not s3.list_objects_v2(Bucket=entry["name"], ExpectedBucketOwner=ACCOUNT_ID).get("Contents")
            s3.delete_bucket(Bucket=entry["name"], ExpectedBucketOwner=ACCOUNT_ID)
            s3.get_waiter("bucket_not_exists").wait(Bucket=entry["name"], ExpectedBucketOwner=ACCOUNT_ID)
            for key in ("rag.objects", "rag.bucket_ready", "rag.bucket"):
                if state.get(key):
                    state.forget(key, expected=state.get(key))
        entry = state.get("rag.artifact")
        if entry:
            s3.delete_object(Bucket=entry["bucket"], Key=entry["key"], ExpectedBucketOwner=ACCOUNT_ID)
            try:
                s3.get_object(Bucket=entry["bucket"], Key=entry["key"], ExpectedBucketOwner=ACCOUNT_ID)
            except s3.exceptions.NoSuchKey:
                state.forget("rag.artifact", expected=entry)
            else:
                raise AssertionError("RAG_ARTIFACT_STILL_PRESENT")
        entry = state.get("rag.logs")
        if entry:
            logs.delete_log_group(logGroupName=entry["name"])
            page = logs.describe_log_groups(logGroupNamePrefix=entry["name"])
            assert not any(group["logGroupName"] == entry["name"] for group in page["logGroups"])
            state.forget("rag.logs", expected=entry)
        print({"rag_cleanup": "CONFIRMED"})
        """,
        ),
    ]
