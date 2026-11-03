"""Limpeza explícita e restrita aos recursos registrados pela jornada SDK."""

from scripts.aws_notebook_lessons import md, step


def cleanup():
    return [
        md("""
        ### Execute apenas ao encerrar as aulas

        As células seguintes **excluem os recursos criados nas aulas 01–03** e seus
        dados sintéticos. Os logs também serão removidos. O segredo é agendado
        para exclusão com recuperação por sete dias.

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
                "runtime.bucket", "runtime.bucket_ready", "runtime.artifact",
                "runtime.role", "runtime.instance", "runtime.logs",
            }
            unknown = set(state.data["resources"]) - supported
            if unknown:
                raise RuntimeError("CLEANUP_DEPENDENCIES_NOT_SUPPORTED: " + ", ".join(sorted(unknown)))

            def owned(tags):
                if not all(tags.get(key) == value for key, value in TAGS.items()):
                    raise RuntimeError("CLEANUP_OWNERSHIP_MISMATCH")

            def wait_deleted(read, not_found):
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    try:
                        response = read()
                    except not_found:
                        return
                    if response.get("status") in {"FAILED", "DELETE_FAILED"}:
                        raise RuntimeError("CLEANUP_DELETE_FAILED")
                    time.sleep(5)
                raise TimeoutError("CLEANUP_DELETE_TIMEOUT")

            # Valide a propriedade de todos os recursos ANTES da primeira mutação.
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
                assert control.get_gateway(gatewayIdentifier=entry["id"])["gatewayArn"] == entry["arn"]
                target_entry = state.get("gateway.lambda_target")
                expected_targets = {target_entry["id"]} if target_entry else set()
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
                        "gateway.role": "Lesson01InvokeLambda",
                        "gateway.lambda_role": "Lesson01Logs",
                        "runtime.role": "Lesson03Runtime",
                    }[key]
                    inline = iam.list_role_policies(RoleName=entry["name"])
                    assert not inline.get("IsTruncated")
                    assert set(inline["PolicyNames"]) <= {expected}
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
                    names = iam.list_role_policies(RoleName=entry["name"])["PolicyNames"]
                    assert set(names) <= {policy_name}
                    if policy_name in names:
                        iam.delete_role_policy(RoleName=entry["name"], PolicyName=policy_name)
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
            "O nome desse segredo continua reservado durante essa janela.",
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
                metadata = secrets.describe_secret(SecretId=entry["arn"])
                assert metadata.get("DeletedDate"), "SECRET_DELETION_NOT_SCHEDULED"
                state.forget("identity.demo_credentials", expected=entry)
                print({"secret": "SCHEDULED_FOR_DELETION", "recovery_window_days": 7})
            assert not state.data["resources"], state.data["resources"]
            print({"cleanup": "COMPLETE", "execution": state.data["run_id"]})
            """,
        ),
    ]
