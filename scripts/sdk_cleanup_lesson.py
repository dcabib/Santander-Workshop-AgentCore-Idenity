"""Limpeza explícita e restrita aos recursos registrados pela jornada SDK."""

from textwrap import indent

from scripts.aws_notebook_lessons import md, step
from scripts.sdk_rag_cleanup import cleanup as rag_cleanup
from scripts.sdk_rag_cleanup import precheck as rag_precheck


def cleanup():
    return [
        md("""
        ### Execute apenas ao encerrar as aulas

        As células seguintes **excluem os recursos criados nas aulas 01–09 e 15–16** e seus
        dados sintéticos. Os logs também serão removidos. O segredo é agendado
        para exclusão com recuperação por sete dias.
        Assets de geração de políticas são temporários no serviço e expiram
        após sete dias; o SDK não oferece DeletePolicyGeneration.

        Esta limpeza não descobre recursos por prefixo para apagá-los. Ela usa
        os IDs registrados, confere tags ou a identidade completa da função
        (ARN, descrição, hash do código e role) e rejeita dependências
        não contempladas. Recursos do VS Code, do evento e de implantações
        anteriores não entram no registro e não serão removidos.

        Leia os IDs da próxima célula antes de executar as exclusões. O arquivo
        de estado só esquece um recurso depois de confirmar sua remoção.
        """),
        *step(
            "Conferir a execução e suas dependências",
            "Interrompemos antes da primeira exclusão se outra aula tiver "
            "adicionado recursos que ainda dependem deste Gateway. Isso evita "
            "uma limpeza parcial silenciosa enquanto a jornada é ampliada.",
            """
            import time
            import hashlib
            from botocore.exceptions import ClientError

            control = aws.client("bedrock-agentcore-control")
            cognito = aws.client("cognito-idp")
            iam = aws.client("iam")
            lambdas = aws.client("lambda")
            logs = aws.client("logs")
            secrets = aws.client("secretsmanager")
            s3 = aws.client("s3")
            supported = {
                "identity.pool", "identity.client", "identity.other_client", "identity.demo_credentials",
                "identity.user.analista", "identity.user.auditor",
                "identity.password_ready.analista", "identity.password_ready.auditor",
                "gateway.tool_logs", "gateway.lambda_role", "gateway.tool_lambda",
                "gateway.role", "gateway.instance", "gateway.lambda_target",
                "gateway.runtime_target", "gateway.runtime_permission",
                "runtime.bucket", "runtime.bucket_ready", "runtime.artifact",
                "runtime.role", "runtime.instance", "runtime.logs",
                "policy.engine", "policy.customer", "policy.gateway_role_permission",
                "policy.draft", "policy.generation", "policy.workload",
                "registry.instance", "registry.record.mcp",
                "registry.role.developer", "registry.role.publisher",
                "registry.role.approver", "registry.role.consumer",
                "memory.instance", "memory.source_table",
                "memory.identity_pool", "memory.identity_mapping",
                "memory.source_item.canonical", "memory.source_item.analista", "memory.source_item.auditor",
                "memory.role.analista", "memory.role.auditor",
                "memory.event.analista", "memory.event_request.analista",
                "rag.bucket", "rag.bucket_ready", "rag.objects", "rag.knowledge_role", "rag.knowledge_base",
                "rag.data_source", "rag.ingestion", "rag.gateway_permission", "rag.target",
                "rag.policy.analista", "rag.policy.auditor", "rag.artifact", "rag.runtime_role", "rag.runtime", "rag.logs",
            }
            unknown = set(state.data["resources"]) - supported
            if unknown:
                raise RuntimeError("CLEANUP_DEPENDENCIES_NOT_SUPPORTED: " + ", ".join(sorted(unknown)))

            def owned(tags):
                if not all(tags.get(key) == value for key, value in TAGS.items()):
                    raise RuntimeError("CLEANUP_OWNERSHIP_MISMATCH")

            def wait_deleted(read, not_found, timeout=300):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        response = read()
                    except not_found:
                        return
                    if response.get("status") in {"FAILED", "DELETE_FAILED", "DELETE_UNSUCCESSFUL"}:
                        raise RuntimeError("CLEANUP_DELETE_FAILED")
                    time.sleep(5)
                raise TimeoutError("CLEANUP_DELETE_TIMEOUT")

            # Valide a propriedade de todos os recursos ANTES da primeira mutação.
            entry = state.get("memory.identity_pool")
            if entry:
                federation = aws.client("cognito-identity")
                current = federation.describe_identity_pool(IdentityPoolId=entry["id"])
                assert all(current.get(key) == value for key, value in entry["config"].items()), "IDENTITY_POOL_CHANGED"
                assert entry["config"]["IdentityPoolName"] == NAME_PREFIX.replace("-", "_") + "_memory"
                assert not current["AllowUnauthenticatedIdentities"] and not current["AllowClassicFlow"]
                assert not any(current.get(key) for key in (
                    "SupportedLoginProviders", "DeveloperProviderName", "OpenIdConnectProviderARNs", "SamlProviderARNs",
                )), "UNEXPECTED_FEDERATION_PROVIDER"
                owned(current["IdentityPoolTags"])
                mapping = state.get("memory.identity_mapping")
                if mapping:
                    assert mapping["pool_id"] == entry["id"]
                current_mapping = federation.get_identity_pool_roles(IdentityPoolId=entry["id"])
                assert {key: current_mapping.get(key, {}) for key in ("Roles", "RoleMappings")} == (
                    mapping["document"] if mapping else {"Roles": {}, "RoleMappings": {}}
                ), "IDENTITY_MAPPING_CHANGED"
            for person in ("analista", "auditor"):
                entry = state.get("memory.role." + person)
                if entry:
                    assert entry["name"] == NAME_PREFIX + "-memory-" + person
                    assert entry["policy_name"] == "Lesson15ActorAndSource"
                    role = iam.get_role(RoleName=entry["name"])["Role"]
                    assert role["Arn"] == entry["arn"] and not role.get("PermissionsBoundary")
                    owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
                    expected_trust = {
                        "Version": "2012-10-17", "Statement": [{
                            "Effect": "Allow", "Principal": {"Federated": "cognito-identity.amazonaws.com"},
                            "Action": "sts:AssumeRoleWithWebIdentity",
                            "Condition": {
                                "StringEquals": {"cognito-identity.amazonaws.com:aud": entry.get("identity_pool_id")},
                                "ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "authenticated"},
                            },
                        }],
                    }
                    # Estados anteriores à federação continuam removíveis após conferir a trust original.
                    if "trusted_principal" in entry:
                        expected_trust = {"Version": "2012-10-17", "Statement": [{
                            "Effect": "Allow", "Principal": {"AWS": entry["trusted_principal"]},
                            "Action": "sts:AssumeRole",
                        }]}
                    assert role["AssumeRolePolicyDocument"] == expected_trust
                    attached = iam.list_attached_role_policies(RoleName=entry["name"])
                    assert not attached["AttachedPolicies"] and not attached.get("IsTruncated")
                    inline = iam.list_role_policies(RoleName=entry["name"])
                    assert set(inline["PolicyNames"]) <= {entry["policy_name"]} and not inline.get("IsTruncated")
                    if entry["policy_name"] in inline["PolicyNames"]:
                        document = iam.get_role_policy(
                            RoleName=entry["name"], PolicyName=entry["policy_name"],
                        )["PolicyDocument"]
                        assert hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() == (
                            entry["policy_sha256"]
                        ), "MEMORY_ROLE_CHANGED"
            entry = state.get("memory.instance")
            if entry:
                memory_api = aws.client("bedrock-agentcore")
                memory = control.get_memory(memoryId=entry["id"])["memory"]
                assert memory["arn"] == entry["arn"] and memory["name"] == NAME_PREFIX.replace("-", "_") + "_memory"
                assert memory["eventExpiryDuration"] == 7 and not memory.get("strategies")
                assert not memory.get("memoryExecutionRoleArn") and not memory.get("encryptionKeyArn")
                owned(control.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
                event_entry = state.get("memory.event.analista")
                request_entry = state.get("memory.event_request.analista")
                if event_entry:
                    assert request_entry and event_entry["memory_id"] == entry["id"]
                    for field in ("actor_id", "session_id", "payload_sha256"):
                        assert event_entry[field] == request_entry[field]
                expected_actor = request_entry["actor_id"] if request_entry else None
                actors = memory_api.list_actors(memoryId=entry["id"], maxResults=100)
                assert not actors.get("nextToken")
                assert {actor["actorId"] for actor in actors["actorSummaries"]} <= ({expected_actor} if expected_actor else set())
                if request_entry:
                    assert request_entry["memory_id"] == entry["id"]
                    sessions = memory_api.list_sessions(memoryId=entry["id"], actorId=expected_actor, maxResults=100)
                    assert not sessions.get("nextToken")
                    assert {session["sessionId"] for session in sessions["sessionSummaries"]} <= {request_entry["session_id"]}
                    events = memory_api.list_events(
                        memoryId=entry["id"], actorId=expected_actor, sessionId=request_entry["session_id"],
                        includePayloads=True, maxResults=100,
                    )
                    assert not events.get("nextToken")
                    assert {event["eventId"] for event in events["events"]} == ({event_entry["id"]} if event_entry else set()), (
                        "UNREGISTERED_MEMORY_EVENTS"
                    )
                    for event in events["events"]:
                        assert hashlib.sha256(json.dumps(event["payload"], sort_keys=True).encode()).hexdigest() == (
                            event_entry["payload_sha256"]
                        ), "MEMORY_EVENT_CHANGED"
            entry = state.get("memory.source_table")
            if entry:
                dynamodb = aws.client("dynamodb")
                assert entry["name"] == NAME_PREFIX + "-memory-source"
                table = dynamodb.describe_table(TableName=entry["name"])["Table"]
                assert table["TableArn"] == entry["arn"] and not table.get("DeletionProtectionEnabled")
                if "table_id" in entry:
                    assert entry["table_id"] and table["TableId"] == entry["table_id"], "SOURCE_TABLE_REPLACED"
                else:
                    # Limpeza de tabelas antigas criadas com tags; não adota uma tabela pelo nome.
                    tags = dynamodb.list_tags_of_resource(ResourceArn=entry["arn"])
                    assert not tags.get("NextToken")
                    owned({tag["Key"]: tag["Value"] for tag in tags["Tags"]})
                expected_items = {}
                for name in ("canonical", "analista", "auditor"):
                    item = state.get("memory.source_item." + name)
                    if item:
                        assert item["table_name"] == entry["name"]
                        expected_items[json.dumps(item["key"], sort_keys=True)] = item["item_sha256"]
                scanned = dynamodb.scan(TableName=entry["name"], ConsistentRead=True)
                assert not scanned.get("LastEvaluatedKey"), "SOURCE_TABLE_UNEXPECTED_VOLUME"
                actual_items = {
                    json.dumps({field: item[field] for field in ("PK", "SK")}, sort_keys=True):
                    hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
                    for item in scanned["Items"]
                }
                assert actual_items == expected_items, "UNREGISTERED_OR_CHANGED_SOURCE_ITEMS"
            for persona in ("developer", "publisher", "approver", "consumer"):
                entry = state.get("registry.role." + persona)
                if entry:
                    official_name = {
                        "publisher": "publisher_persona", "approver": "admin_persona",
                        "consumer": "consumer_persona",
                    }.get(persona)
                    assert entry["name"] in {official_name, NAME_PREFIX + "-registry-" + persona}
                    assert entry["policy_name"] == "Lesson07Persona"
                    role = iam.get_role(RoleName=entry["name"])["Role"]
                    assert role["Arn"] == entry["arn"]
                    owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
                    assert role["AssumeRolePolicyDocument"] == {
                        "Version": "2012-10-17", "Statement": [{
                            "Effect": "Allow", "Principal": {"AWS": entry["trusted_principal"]},
                            "Action": "sts:AssumeRole",
                        }],
                    }
                    assert not role.get("PermissionsBoundary")
                    attached = iam.list_attached_role_policies(RoleName=entry["name"])
                    assert not attached["AttachedPolicies"] and not attached.get("IsTruncated")
                    inline = iam.list_role_policies(RoleName=entry["name"])
                    assert set(inline["PolicyNames"]) <= {entry["policy_name"]} and not inline.get("IsTruncated")
                    if entry["policy_name"] in inline["PolicyNames"]:
                        document = iam.get_role_policy(
                            RoleName=entry["name"], PolicyName=entry["policy_name"],
                        )["PolicyDocument"]
                        assert hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() == (
                            entry["policy_sha256"]
                        ), "PERSONA_POLICY_CHANGED"
            entry = state.get("registry.instance")
            if entry:
                registry_control = aws.client("agent-registry-control")
                catalog = registry_control.get_registry(registryId=entry["id"])
                assert catalog["registryArn"] == entry["arn"]
                assert catalog["name"] == entry["name"] == NAME_PREFIX + "-registry"
                assert catalog["discoveryConfiguration"] == {"authorizerType": "AWS_IAM"}
                assert not catalog.get("approvalConfiguration", {}).get("autoApprovalRules", [])
                assert catalog.get("autoDetection", {}).get("status", "INACTIVE") == "INACTIVE"
                owned(registry_control.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
                records = registry_control.list_registry_records(registryId=entry["id"])
                record_entry = state.get("registry.record.mcp")
                expected_records = {record_entry["id"]} if record_entry else set()
                assert {record["recordId"] for record in records["registryRecords"]} == expected_records, (
                    "REGISTRY_RECORD_CLEANUP_REQUIRED"
                )
                assert not records.get("nextToken"), (
                    "REGISTRY_RECORD_CLEANUP_REQUIRED"
                )
            record_entry = state.get("registry.record.mcp")
            if record_entry:
                parent = state.require("registry.instance", lesson="06")
                assert record_entry["registry_id"] == parent["id"]
                assert record_entry["registry_arn"] == parent["arn"]
                assert record_entry["name"] == NAME_PREFIX + "-workload-mcp"
                assert record_entry["arn"] == parent["arn"] + "/record/" + record_entry["id"]
                record = registry_control.get_registry_record(
                    registryId=parent["id"], recordId=record_entry["id"],
                )
                assert record["recordArn"] == record_entry["arn"] and record["registryArn"] == parent["arn"]
                assert record["name"] == record_entry["name"] and record["recordType"] == "MCP"
                package = {key: record[key] for key in (
                    "name", "recordType", "recordVersion", "description", "descriptors",
                )}
                assert hashlib.sha256(json.dumps(package, sort_keys=True).encode()).hexdigest() == (
                    record_entry["package_sha256"]
                ), "REGISTRY_RECORD_CHANGED"
            entry = state.get("identity.pool")
            if entry:
                pool = cognito.describe_user_pool(UserPoolId=entry["id"])["UserPool"]
                owned(pool["UserPoolTags"])
                assert pool["Arn"] == entry["arn"]
                for key in (
                    "identity.client", "identity.other_client", "identity.user.analista", "identity.user.auditor",
                    "identity.password_ready.analista", "identity.password_ready.auditor",
                ):
                    child = state.get(key)
                    if child:
                        assert child["pool_id"] == entry["id"], "IDENTITY_DEPENDENCY_MISMATCH"
            entry = state.get("gateway.instance")
            if entry:
                owned(control.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
                gateway = control.get_gateway(gatewayIdentifier=entry["id"])
                assert gateway["gatewayArn"] == entry["arn"]
                engine = state.get("policy.engine")
                if gateway.get("policyEngineConfiguration"):
                    assert engine and gateway["policyEngineConfiguration"] == {
                        "arn": engine["arn"], "mode": "ENFORCE",
                    }, "UNREGISTERED_GATEWAY_POLICY_ENGINE"
                expected_targets = {
                    child["id"] for child in (
                        state.get("gateway.lambda_target"), state.get("gateway.runtime_target"), state.get("rag.target"),
                    ) if child
                }
                actual_targets = set()
                page = control.list_gateway_targets(gatewayIdentifier=entry["id"])
                while True:
                    actual_targets.update(item["targetId"] for item in page.get("items", []))
                    if not page.get("nextToken"):
                        break
                    page = control.list_gateway_targets(
                        gatewayIdentifier=entry["id"], nextToken=page["nextToken"],
                    )
                assert actual_targets == expected_targets, "UNREGISTERED_GATEWAY_TARGETS"
            entry = state.get("gateway.runtime_target")
            if entry:
                from urllib.parse import quote
                parent = state.require("gateway.instance", lesson="01")
                runtime_entry = state.require("runtime.instance", lesson="03")
                assert entry["gateway_id"] == parent["id"] and entry["runtime_arn"] == runtime_entry["arn"]
                endpoint = (
                    f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
                    + quote(runtime_entry["arn"], safe="") + "/invocations?qualifier=DEFAULT"
                )
                assert entry["endpoint"] == endpoint and entry["name"] == "workload"
                target = control.get_gateway_target(gatewayIdentifier=parent["id"], targetId=entry["id"])
                assert target["name"] == entry["name"]
                assert target["targetConfiguration"] == {"mcp": {"mcpServer": {"endpoint": endpoint}}}
                assert target["credentialProviderConfigurations"] == [{
                    "credentialProviderType": "GATEWAY_IAM_ROLE",
                    "credentialProvider": {"iamCredentialProvider": {"service": "bedrock-agentcore", "region": REGION}},
                }]
            entry = state.get("policy.engine")
            if any(state.get(key) for key in (
                "policy.customer", "policy.draft", "policy.generation", "policy.workload",
                "rag.policy.analista", "rag.policy.auditor",
            )):
                assert entry, "POLICY_ENGINE_STATE_REQUIRED"
            if entry:
                engine = control.get_policy_engine(policyEngineId=entry["id"])
                assert engine["policyEngineArn"] == entry["arn"]
                assert engine["name"] == NAME_PREFIX.replace("-", "_") + "_policy"
                owned(control.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
                children = [
                    child for child in (
                        state.get("policy.customer"), state.get("policy.draft"), state.get("policy.workload"),
                        state.get("rag.policy.analista"), state.get("rag.policy.auditor"),
                    )
                    if child
                ]
                expected_policies = {child["id"] for child in children}
                actual_policies = set()
                page = control.list_policies(policyEngineId=entry["id"])
                while True:
                    actual_policies.update(item["policyId"] for item in page["policies"])
                    if not page.get("nextToken"):
                        break
                    page = control.list_policies(
                        policyEngineId=entry["id"], nextToken=page["nextToken"],
                    )
                assert actual_policies == expected_policies, "UNREGISTERED_ENGINE_POLICIES"
                for child in children:
                    assert child["engine_id"] == entry["id"]
                    current = control.get_policy(
                        policyEngineId=entry["id"], policyId=child["id"],
                    )
                    assert current["policyArn"] == child["arn"]
                    assert hashlib.sha256(
                        current["definition"]["cedar"]["statement"].encode(),
                    ).hexdigest() == child["statement_sha256"], "POLICY_DEFINITION_CHANGED"
                generation = state.get("policy.generation")
                if generation:
                    assert generation["engine_id"] == entry["id"]
                    page = control.list_policy_generations(policyEngineId=entry["id"])
                    while True:
                        for item in page["policyGenerations"]:
                            assert item["policyGenerationId"] == generation["id"], (
                                "UNREGISTERED_POLICY_GENERATION"
                            )
                            assert item["policyGenerationArn"] == generation["arn"]
                            assert item["resource"] == {"arn": generation["gateway_arn"]}
                        if not page.get("nextToken"):
                            break
                        page = control.list_policy_generations(
                            policyEngineId=entry["id"], nextToken=page["nextToken"],
                        )
            permission = state.get("policy.gateway_role_permission")
            if permission:
                role = state.require("gateway.role", lesson="01")
                assert permission["role_name"] == role["name"]
                assert permission["name"] == "Lesson04AuthorizePolicy"
                for key, field in (("policy.engine", "engine_arn"), ("gateway.instance", "gateway_arn")):
                    parent = state.get(key)
                    if parent:
                        assert permission[field] == parent["arn"]
                document = iam.get_role_policy(
                    RoleName=permission["role_name"], PolicyName=permission["name"],
                )["PolicyDocument"]
                assert hashlib.sha256(
                    json.dumps(document, sort_keys=True).encode(),
                ).hexdigest() == permission["document_sha256"], "POLICY_IAM_DOCUMENT_CHANGED"
            runtime_permission = state.get("gateway.runtime_permission")
            if runtime_permission:
                role = state.require("gateway.role", lesson="01")
                assert runtime_permission["role_name"] == role["name"]
                assert runtime_permission["name"] == "Lesson09InvokeRuntime"
                runtime_entry = state.get("runtime.instance")
                if runtime_entry:
                    assert runtime_permission["runtime_arn"] == runtime_entry["arn"]
                document = iam.get_role_policy(
                    RoleName=role["name"], PolicyName=runtime_permission["name"],
                )["PolicyDocument"]
                assert hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() == (
                    runtime_permission["document_sha256"]
                ), "RUNTIME_PERMISSION_CHANGED"
            entry = state.get("gateway.tool_lambda")
            if entry:
                function = lambdas.get_function(FunctionName=entry["arn"])
                configuration = function["Configuration"]
                marker = "santander-agentcore:" + state.data["run_id"] + ":lesson01:customer-risk"
                expected_name = NAME_PREFIX + "-customer-risk"
                expected_arn = f"arn:{PARTITION}:lambda:{REGION}:{ACCOUNT_ID}:function:{expected_name}"
                assert entry["ownership_marker"] == marker
                assert entry["name"] == expected_name and entry["arn"] == expected_arn
                assert configuration["FunctionName"] == expected_name
                assert configuration["FunctionArn"] == expected_arn
                assert configuration["Description"] == marker
                assert configuration["CodeSha256"] == entry["code_hash"]
                assert configuration["Role"] == entry["role_arn"]
                assert entry["role_arn"] == state.require("gateway.lambda_role", lesson="01")["arn"]
            entry = state.get("runtime.instance")
            if entry:
                current = control.get_agent_runtime(agentRuntimeId=entry["id"])
                assert current["agentRuntimeArn"] == entry["arn"]
                assert current["roleArn"] == entry["role_arn"]
                owned(control.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
                artifact = state.require("runtime.artifact", lesson="03")
                assert current["agentRuntimeArtifact"]["codeConfiguration"]["code"]["s3"] == {
                    "bucket": artifact["bucket"], "prefix": artifact["key"],
                }
            entry = state.get("runtime.logs")
            if entry:
                assert entry["runtime_id"].startswith(NAME_PREFIX.replace("-", "_") + "_mcp-")
                assert entry["name"] == "/aws/bedrock-agentcore/runtimes/" + entry["runtime_id"] + "-DEFAULT"
                if state.get("runtime.instance"):
                    assert entry["runtime_id"] == state.get("runtime.instance")["id"]
            entry = state.get("runtime.bucket")
            if entry:
                bucket_name = NAME_PREFIX + "-" + ACCOUNT_ID + "-" + REGION
                assert entry == {
                    "name": bucket_name, "arn": f"arn:{PARTITION}:s3:::{bucket_name}", "lesson": "03",
                }
                s3.head_bucket(Bucket=bucket_name, ExpectedBucketOwner=ACCOUNT_ID)
                expected_keys = set()
                ready = state.get("runtime.bucket_ready")
                if ready:
                    assert ready == {"name": bucket_name, "marker": "workshop-owner.json", "lesson": "03"}
                    expected_keys.add(ready["marker"])
                    remote_marker = s3.get_object(
                        Bucket=bucket_name, Key=ready["marker"], ExpectedBucketOwner=ACCOUNT_ID,
                    )
                    assert json.loads(remote_marker["Body"].read()) == {
                        "run_id": state.data["run_id"], "account": ACCOUNT_ID, "region": REGION,
                    }
                artifact = state.get("runtime.artifact")
                if artifact:
                    import hashlib
                    assert artifact["bucket"] == bucket_name and ready
                    assert artifact["key"] == "runtime/" + artifact["sha256"] + ".zip"
                    expected_keys.add(artifact["key"])
                    uploaded = s3.get_object(
                        Bucket=bucket_name, Key=artifact["key"], ExpectedBucketOwner=ACCOUNT_ID,
                    )
                    assert hashlib.sha256(uploaded["Body"].read()).hexdigest() == artifact["sha256"]
                actual_keys = set()
                rag_artifact = state.get("rag.artifact")
                if rag_artifact:
                    assert rag_artifact["bucket"] == bucket_name
                    expected_keys.add(rag_artifact["key"])
                page = s3.list_objects_v2(Bucket=bucket_name, ExpectedBucketOwner=ACCOUNT_ID)
                while True:
                    actual_keys.update(item["Key"] for item in page.get("Contents", []))
                    if not page.get("IsTruncated"):
                        break
                    page = s3.list_objects_v2(
                        Bucket=bucket_name, ExpectedBucketOwner=ACCOUNT_ID,
                        ContinuationToken=page["NextContinuationToken"],
                    )
                assert actual_keys == expected_keys, "UNREGISTERED_RUNTIME_BUCKET_OBJECTS"
            for key in ("gateway.role", "gateway.lambda_role", "runtime.role"):
                entry = state.get(key)
                if entry:
                    role = iam.get_role(RoleName=entry["name"])["Role"]
                    owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
                    assert role["Arn"] == entry["arn"]
                    attached = iam.list_attached_role_policies(RoleName=entry["name"])
                    assert not attached["AttachedPolicies"] and not attached.get("IsTruncated")
                    expected = {
                        "gateway.role": {"Lesson01InvokeLambda"},
                        "gateway.lambda_role": {"Lesson01Logs"},
                        "runtime.role": {"Lesson03Runtime"},
                    }[key]
                    if key == "gateway.role" and permission:
                        expected.add(permission["name"])
                    if key == "gateway.role" and runtime_permission:
                        expected.add(runtime_permission["name"])
                    if key == "gateway.role" and state.get("rag.gateway_permission"):
                        expected.add("Lesson16NativeKnowledgeBase")
                    inline = iam.list_role_policies(RoleName=entry["name"])
                    assert not inline.get("IsTruncated")
                    assert set(inline["PolicyNames"]) <= expected
            entry = state.get("gateway.tool_logs")
            if entry:
                owned(logs.list_tags_for_resource(resourceArn=entry["arn"])["tags"])
            entry = state.get("identity.demo_credentials")
            if entry:
                metadata = secrets.describe_secret(SecretId=entry["arn"])
                owned({tag["Key"]: tag["Value"] for tag in metadata["Tags"]})
            print({
                "account": ACCOUNT_ID, "region": REGION, "execution": state.data["run_id"],
                "resources_to_remove": state.data["resources"],
            })
            """ + "\n" + indent(rag_precheck(), " " * 12),
        ),
        *rag_cleanup(),
        *step(
            "Remover eventos, Memory, visões da fonte e suas roles",
            "A conferência anterior recusou actors, sessões, eventos ou itens "
            "desconhecidos. Excluímos o evento registrado, Memory e a tabela "
            "dedicada, depois somente as duas roles didáticas da aula 15.",
            """
            entry = state.get("memory.event.analista")
            if entry:
                args = {
                    "memoryId": entry["memory_id"], "actorId": entry["actor_id"],
                    "sessionId": entry["session_id"], "eventId": entry["id"],
                }
                memory_api.delete_event(**args)
                wait_deleted(
                    lambda: memory_api.get_event(**args),
                    memory_api.exceptions.ResourceNotFoundException,
                )
                state.forget("memory.event.analista", expected=entry)
            entry = state.get("memory.instance")
            if entry:
                control.delete_memory(
                    memoryId=entry["id"], clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":delete-memory")),
                )
                wait_deleted(
                    lambda: control.get_memory(memoryId=entry["id"])["memory"],
                    control.exceptions.ResourceNotFoundException,
                )
                state.forget("memory.instance", expected=entry)
                request_entry = state.get("memory.event_request.analista")
                if request_entry:
                    state.forget("memory.event_request.analista", expected=request_entry)
            entry = state.get("memory.source_table")
            if entry:
                dynamodb.delete_table(TableName=entry["name"])
                wait_deleted(
                    lambda: dynamodb.describe_table(TableName=entry["name"]),
                    dynamodb.exceptions.ResourceNotFoundException,
                )
                for name in ("canonical", "analista", "auditor"):
                    key = "memory.source_item." + name
                    item = state.get(key)
                    if item:
                        state.forget(key, expected=item)
                state.forget("memory.source_table", expected=entry)
            entry = state.get("memory.identity_pool")
            if entry:
                federation.delete_identity_pool(IdentityPoolId=entry["id"])
                wait_deleted(
                    lambda: federation.describe_identity_pool(IdentityPoolId=entry["id"]),
                    federation.exceptions.ResourceNotFoundException,
                )
                mapping = state.get("memory.identity_mapping")
                if mapping:
                    state.forget("memory.identity_mapping", expected=mapping)
                state.forget("memory.identity_pool", expected=entry)
            for person in ("analista", "auditor"):
                key = "memory.role." + person
                entry = state.get(key)
                if entry:
                    inline = iam.list_role_policies(RoleName=entry["name"])
                    assert set(inline["PolicyNames"]) <= {entry["policy_name"]} and not inline.get("IsTruncated")
                    if entry["policy_name"] in inline["PolicyNames"]:
                        iam.delete_role_policy(RoleName=entry["name"], PolicyName=entry["policy_name"])
                    iam.delete_role(RoleName=entry["name"])
                    wait_deleted(lambda: iam.get_role(RoleName=entry["name"]), iam.exceptions.NoSuchEntityException)
                    state.forget(key, expected=entry)
            print({"memory_and_source_cleanup": "COMPLETE"})
            """,
        ),
        *step(
            "Remover o registro MCP revisado",
            "DeleteRegistryRecord remove somente o ARN e o conteúdo "
            "conferidos acima. A remoção do registro precede as personas "
            "e o catálogo; registros desconhecidos impedem esta limpeza.",
            """
            entry = state.get("registry.record.mcp")
            if entry:
                args = {"registryId": entry["registry_id"], "recordId": entry["id"]}
                registry_control.delete_registry_record(**args)
                wait_deleted(
                    lambda: registry_control.get_registry_record(**args),
                    registry_control.exceptions.ResourceNotFoundException,
                )
                state.forget("registry.record.mcp", expected=entry)
                print({"deleted": "registry.record.mcp"})
            """,
        ),
        *step(
            "Remover as roles das personas",
            "As trust policies, tags e documentos IAM já foram conferidos. "
            "Excluímos somente a policy inline e a role registradas para cada "
            "persona; não alteramos policies ou roles do participante.",
            """
            for persona in ("developer", "publisher", "approver", "consumer"):
                key = "registry.role." + persona
                entry = state.get(key)
                if entry:
                    inline = iam.list_role_policies(RoleName=entry["name"])
                    assert set(inline["PolicyNames"]) <= {entry["policy_name"]} and not inline.get("IsTruncated")
                    if entry["policy_name"] in inline["PolicyNames"]:
                        iam.delete_role_policy(RoleName=entry["name"], PolicyName=entry["policy_name"])
                    iam.delete_role(RoleName=entry["name"])
                    wait_deleted(
                        lambda: iam.get_role(RoleName=entry["name"]), iam.exceptions.NoSuchEntityException,
                    )
                    state.forget(key, expected=entry)
                    print({"deleted": key})
            """,
        ),
        *step(
            "Excluir o Registry vazio desta execução",
            "ListRegistryRecords precisa confirmar que o catálogo não contém "
            "registros antes de DeleteRegistry. Um registro desconhecido exige "
            "revisar suas dependências; a célula não o exclui automaticamente.",
            """
            entry = state.get("registry.instance")
            if entry:
                records = registry_control.list_registry_records(registryId=entry["id"])
                assert not records["registryRecords"] and not records.get("nextToken"), (
                    "REGISTRY_RECORD_CLEANUP_REQUIRED"
                )
                registry_control.delete_registry(registryId=entry["id"])
                wait_deleted(
                    lambda: registry_control.get_registry(registryId=entry["id"]),
                    registry_control.exceptions.ResourceNotFoundException,
                )
                state.forget("registry.instance", expected=entry)
                print({"deleted": "registry.instance"})
            """,
        ),
        *step(
            "Remover o target Runtime antes do servidor MCP",
            "O Gateway deve deixar de referenciar o Runtime antes da exclusão "
            "do servidor. Excluímos somente o target da aula 09 conferido acima.",
            """
            entry = state.get("gateway.runtime_target")
            if entry:
                args = {"gatewayIdentifier": entry["gateway_id"], "targetId": entry["id"]}
                control.delete_gateway_target(**args)
                wait_deleted(
                    lambda: control.get_gateway_target(**args),
                    control.exceptions.ResourceNotFoundException,
                )
                state.forget("gateway.runtime_target", expected=entry)
                print({"deleted": "gateway.runtime_target"})
            """,
        ),
        *step(
            "Excluir o Runtime antes de remover o código",
            "O Runtime precisa parar de usar sua role e seu artefato antes "
            "de excluí-los. Somente o Runtime registrado pela aula é removido.",
            """
            entry = state.get("runtime.instance")
            if entry:
                control.delete_agent_runtime(agentRuntimeId=entry["id"])
                wait_deleted(
                    lambda: control.get_agent_runtime(agentRuntimeId=entry["id"]),
                    control.exceptions.ResourceNotFoundException,
                )
                state.forget("runtime.instance", expected=entry)
                print({"deleted_runtime": entry["id"]})
            """,
        ),
        *step(
            "Excluir o target e depois o Gateway",
            "DeleteGatewayTarget remove a associação com a ferramenta. "
            "Depois de confirmar que ela desapareceu, DeleteGateway remove "
            "o endpoint. As roles só serão removidas na etapa seguinte.",
            """
            entry = state.get("gateway.lambda_target")
            if entry:
                parent = state.require("gateway.instance", lesson="01")
                assert entry["gateway_id"] == parent["id"]
                target = control.get_gateway_target(
                    gatewayIdentifier=parent["id"], targetId=entry["id"],
                )
                assert target["targetConfiguration"]["mcp"]["lambda"]["lambdaArn"] == (
                    state.require("gateway.tool_lambda", lesson="01")["arn"]
                )
                control.delete_gateway_target(gatewayIdentifier=parent["id"], targetId=entry["id"])
                wait_deleted(
                    lambda: control.get_gateway_target(
                        gatewayIdentifier=parent["id"], targetId=entry["id"],
                    ), control.exceptions.ResourceNotFoundException,
                )
                state.forget("gateway.lambda_target", expected=entry)
                print({"deleted": "gateway.lambda_target"})
            entry = state.get("gateway.instance")
            if entry:
                remaining = control.list_gateway_targets(gatewayIdentifier=entry["id"])
                assert not remaining.get("items") and not remaining.get("nextToken"), "TARGETS_REMAIN"
                control.delete_gateway(gatewayIdentifier=entry["id"])
                wait_deleted(
                    lambda: control.get_gateway(gatewayIdentifier=entry["id"]),
                    control.exceptions.ResourceNotFoundException,
                )
                state.forget("gateway.instance", expected=entry)
                print({"deleted": "gateway.instance"})
            """,
        ),
        *step(
            "Excluir as políticas e depois o engine",
            "Depois da exclusão do Gateway, removemos as políticas registradas "
            "e aguardamos sua remoção antes de excluir o engine. Um engine "
            "com políticas desconhecidas foi recusado na conferência inicial.",
            """
            assert state.get("gateway.instance") is None, "GATEWAY_STILL_EXISTS"
            for policy_key in ("policy.workload", "policy.draft", "policy.customer"):
                entry = state.get(policy_key)
                if entry:
                    control.delete_policy(policyEngineId=entry["engine_id"], policyId=entry["id"])
                    wait_deleted(
                        lambda: control.get_policy(
                            policyEngineId=entry["engine_id"], policyId=entry["id"],
                        ), control.exceptions.ResourceNotFoundException,
                    )
                    state.forget(policy_key, expected=entry)
                    print({"deleted": policy_key})
            entry = state.get("policy.engine")
            if entry:
                remaining = control.list_policies(policyEngineId=entry["id"])
                assert not remaining["policies"] and not remaining.get("nextToken")
                control.delete_policy_engine(policyEngineId=entry["id"])
                wait_deleted(
                    lambda: control.get_policy_engine(policyEngineId=entry["id"]),
                    control.exceptions.ResourceNotFoundException,
                )
                state.forget("policy.engine", expected=entry)
                print({"deleted": "policy.engine"})
                generation = state.get("policy.generation")
                if generation:
                    assert generation["engine_id"] == entry["id"]
                    state.forget("policy.generation", expected=generation)
                    print({"generation_assets": "TEMPORARY_SERVICE_ASSETS_EXPIRE_AFTER_7_DAYS"})
            """,
        ),
        *step(
            "Excluir a função, suas roles e os logs",
            "Sem o Gateway, podemos remover a função e as policies específicas "
            "desta aula. Não desanexamos policies desconhecidas nem removemos "
            "roles compartilhadas para contornar um conflito.",
            """
            entry = state.get("gateway.tool_lambda")
            if entry:
                lambdas.delete_function(FunctionName=entry["arn"])
                wait_deleted(
                    lambda: lambdas.get_function(FunctionName=entry["arn"]),
                    lambdas.exceptions.ResourceNotFoundException,
                )
                state.forget("gateway.tool_lambda", expected=entry)
                print({"deleted": "gateway.tool_lambda"})
            for key, policy_name in (
                ("gateway.role", "Lesson01InvokeLambda"),
                ("gateway.lambda_role", "Lesson01Logs"),
                ("runtime.role", "Lesson03Runtime"),
            ):
                entry = state.get(key)
                if entry:
                    permissions = [
                        (permission_key, state.get(permission_key))
                        for permission_key in ("policy.gateway_role_permission", "gateway.runtime_permission")
                        if key == "gateway.role" and state.get(permission_key)
                    ]
                    expected = {policy_name}
                    expected.update(permission["name"] for _, permission in permissions)
                    names = iam.list_role_policies(RoleName=entry["name"])["PolicyNames"]
                    assert set(names) <= expected
                    for inline_name in sorted(expected & set(names)):
                        iam.delete_role_policy(RoleName=entry["name"], PolicyName=inline_name)
                    for permission_key, permission in permissions:
                        remaining = iam.list_role_policies(RoleName=entry["name"])
                        assert permission["name"] not in remaining["PolicyNames"]
                        assert not remaining.get("IsTruncated")
                        state.forget(permission_key, expected=permission)
                    iam.delete_role(RoleName=entry["name"])
                    wait_deleted(
                        lambda: iam.get_role(RoleName=entry["name"]), iam.exceptions.NoSuchEntityException,
                    )
                    state.forget(key, expected=entry)
                    print({"deleted": key})
            for log_key in ("gateway.tool_logs", "runtime.logs"):
                entry = state.get(log_key)
                if not entry:
                    continue
                logs.delete_log_group(logGroupName=entry["name"])
                deadline = time.monotonic() + 60
                while True:
                    remaining = [
                        group["logGroupName"]
                        for page in logs.get_paginator("describe_log_groups").paginate(
                            logGroupNamePrefix=entry["name"],
                        )
                        for group in page["logGroups"]
                        if group["logGroupName"] == entry["name"]
                    ]
                    if not remaining:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("LOG_GROUP_DELETE_TIMEOUT")
                    time.sleep(5)
                state.forget(log_key, expected=entry)
                print({"deleted": log_key})
            """,
        ),
        *step(
            "Remover somente os objetos registrados e o bucket do Runtime",
            "A conferência inicial recusou objetos desconhecidos. Excluímos "
            "o ZIP e o marcador pelos nomes registrados e confirmamos que o "
            "bucket ficou vazio. Não há exclusão recursiva por prefixo ou "
            "remoção de versões de outros objetos.",
            """
            bucket = state.get("runtime.bucket")
            if bucket:
                assert state.get("runtime.instance") is None, "RUNTIME_STILL_EXISTS"
                artifact = state.get("runtime.artifact")
                ready = state.get("runtime.bucket_ready")
                keys = [artifact["key"]] if artifact else []
                if ready:
                    keys.append(ready["marker"])
                for key in keys:
                    s3.delete_object(Bucket=bucket["name"], Key=key, ExpectedBucketOwner=ACCOUNT_ID)
                    try:
                        s3.head_object(Bucket=bucket["name"], Key=key, ExpectedBucketOwner=ACCOUNT_ID)
                    except ClientError as error:
                        assert error.response["Error"]["Code"] in {"404", "NoSuchKey"}
                    else:
                        raise RuntimeError("ARTIFACT_DELETE_NOT_CONFIRMED")
                remaining = s3.list_objects_v2(Bucket=bucket["name"], ExpectedBucketOwner=ACCOUNT_ID)
                assert not remaining.get("Contents") and not remaining.get("IsTruncated")
                s3.delete_bucket(Bucket=bucket["name"], ExpectedBucketOwner=ACCOUNT_ID)
                try:
                    s3.head_bucket(Bucket=bucket["name"], ExpectedBucketOwner=ACCOUNT_ID)
                except ClientError as error:
                    assert error.response["Error"]["Code"] in {"404", "NoSuchBucket"}
                else:
                    raise RuntimeError("BUCKET_DELETE_NOT_CONFIRMED")
                for key, entry in (
                    ("runtime.artifact", artifact), ("runtime.bucket_ready", ready), ("runtime.bucket", bucket),
                ):
                    if entry:
                        state.forget(key, expected=entry)
                print({"deleted_runtime_bucket": bucket["name"]})
            """,
        ),
        *step(
            "Excluir o pool e agendar a remoção do segredo",
            "A exclusão do User Pool remove também seus clientes e usuários. "
            "Secrets Manager mantém uma janela de recuperação de sete dias. "
            "O nome desse segredo continua reservado durante essa janela. "
            "Aguardamos a confirmação em DescribeSecret, porque essa leitura "
            "pode levar alguns segundos para refletir o agendamento.",
            """
            entry = state.get("identity.pool")
            if entry:
                cognito.delete_user_pool(UserPoolId=entry["id"])
                wait_deleted(
                    lambda: cognito.describe_user_pool(UserPoolId=entry["id"]),
                    cognito.exceptions.ResourceNotFoundException,
                )
                for key in (
                    "identity.client", "identity.other_client", "identity.user.analista", "identity.user.auditor",
                    "identity.password_ready.analista", "identity.password_ready.auditor",
                ):
                    child = state.get(key)
                    if child:
                        assert child["pool_id"] == entry["id"]
                        state.forget(key, expected=child)
                state.forget("identity.pool", expected=entry)
                print({"deleted": "identity.pool, clients and synthetic users"})
            entry = state.get("identity.demo_credentials")
            if entry:
                metadata = secrets.describe_secret(SecretId=entry["arn"])
                if "DeletedDate" not in metadata:
                    secrets.delete_secret(SecretId=entry["arn"], RecoveryWindowInDays=7)
                deadline = time.monotonic() + 60
                while not metadata.get("DeletedDate"):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("SECRET_DELETION_CONFIRMATION_TIMEOUT")
                    time.sleep(2)
                    metadata = secrets.describe_secret(SecretId=entry["arn"])
                state.forget("identity.demo_credentials", expected=entry)
                print({"secret": "SCHEDULED_FOR_DELETION", "recovery_window_days": 7})
            assert not state.data["resources"], state.data["resources"]
            state.complete_cleanup()
            print({"cleanup": "COMPLETE", "execution": state.data["run_id"]})
            print({"next_execution": "Abra a aula 00 para obter novos nomes nesta conta."})
            """,
        ),
    ]
