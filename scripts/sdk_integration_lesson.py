"""Gateway JWT e Policy diante de um target Runtime MCP autenticado por IAM."""

from scripts.aws_notebook_lessons import md, step


def integration():
    return [
        md("""
        ### Integrar os serviços que construímos

        `Pessoa → JWT Cognito → Gateway + Cedar → IAM/SigV4 → Runtime MCP → STS`

        **Pré-requisitos:** aulas 01, 03 e 04. Nesta aula, adicionamos ao Gateway
        o Runtime MCP já criado, concedemos à role do Gateway a invocação
        desse Runtime e criamos um permit Cedar específico para o analista.
        As chamadas de configuração aparecem abaixo; Terraform e CloudFormation
        não participam da execução.

        O Gateway autentica a pessoa. A assinatura SigV4 identifica o Gateway
        no salto ao Runtime; o código MCP consulta STS com a role do workload.
        Não encaminhamos o JWT ao servidor nem apresentamos essa integração
        como OBO. As personas IAM das aulas anteriores continuam podendo
        invocar diretamente o Runtime conforme suas permissões.

        No Entra ID, a entrada JWT exige issuer, audiência e claims compatíveis,
        além da configuração do aplicativo. A identidade IAM entre serviços
        AWS continua distinta do token da pessoa.
        """),
        *step(
            "Conferir Gateway, Runtime, Policy e identidades",
            "Consultamos os IDs das aulas anteriores e conferimos tags, "
            "authorizers, roles e ENFORCE antes de acrescentar a integração.",
            """
            import hashlib
            import time
            from urllib.parse import quote
            import httpx
            import jwt

            control = aws.client("bedrock-agentcore-control")
            iam = aws.client("iam")
            cognito = aws.client("cognito-idp")
            secrets = aws.client("secretsmanager")
            gateway_entry = state.require("gateway.instance", lesson="01")
            role_entry = state.require("gateway.role", lesson="01")
            runtime_entry = state.require("runtime.instance", lesson="03")
            engine_entry = state.require("policy.engine", lesson="04")
            pool_entry = state.require("identity.pool", lesson="01")
            client_entry = state.require("identity.client", lesson="01")
            analyst_entry = state.require("identity.user.analista", lesson="01")
            auditor_entry = state.require("identity.user.auditor", lesson="01")
            secret_entry = state.require("identity.demo_credentials", lesson="01")
            for entry in (client_entry, analyst_entry, auditor_entry):
                assert entry["pool_id"] == pool_entry["id"]
            CLIENT_ID = client_entry["id"]
            ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_entry['id']}"

            def owned(tags):
                assert all(tags.get(key) == value for key, value in TAGS.items()), "OWNERSHIP_MISMATCH"

            def wait_ready(read, ready):
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    response = read()
                    if response["status"] == ready:
                        return response
                    if response["status"] in {"FAILED", "CREATE_FAILED", "UPDATE_FAILED", "UPDATE_UNSUCCESSFUL"}:
                        raise RuntimeError("INTEGRATION_FAILED: " + str(response.get("statusReasons", [])))
                    time.sleep(5)
                raise TimeoutError("INTEGRATION_NOT_READY")

            gateway = control.get_gateway(gatewayIdentifier=gateway_entry["id"])
            assert gateway["status"] == "READY" and gateway["gatewayArn"] == gateway_entry["arn"]
            assert gateway["roleArn"] == role_entry["arn"]
            assert gateway["authorizerType"] == "CUSTOM_JWT"
            assert gateway["authorizerConfiguration"] == {"customJWTAuthorizer": {
                "discoveryUrl": ISSUER + "/.well-known/openid-configuration", "allowedAudience": [CLIENT_ID],
            }}
            assert gateway["policyEngineConfiguration"] == {"arn": engine_entry["arn"], "mode": "ENFORCE"}
            owned(control.list_tags_for_resource(resourceArn=gateway_entry["arn"])["tags"])
            runtime = control.get_agent_runtime(agentRuntimeId=runtime_entry["id"])
            assert runtime["status"] == "READY" and runtime["agentRuntimeArn"] == runtime_entry["arn"]
            assert runtime["roleArn"] == runtime_entry["role_arn"]
            assert runtime["protocolConfiguration"] == {"serverProtocol": "MCP"}
            assert not runtime.get("authorizerConfiguration"), "IAM_RUNTIME_REQUIRED"
            owned(control.list_tags_for_resource(resourceArn=runtime_entry["arn"])["tags"])
            engine = control.get_policy_engine(policyEngineId=engine_entry["id"])
            assert engine["status"] == "ACTIVE" and engine["policyEngineArn"] == engine_entry["arn"]
            owned(control.list_tags_for_resource(resourceArn=engine_entry["arn"])["tags"])
            pool = cognito.describe_user_pool(UserPoolId=pool_entry["id"])["UserPool"]
            assert pool["Arn"] == pool_entry["arn"]
            owned(pool["UserPoolTags"])
            role = iam.get_role(RoleName=role_entry["name"])["Role"]
            assert role["Arn"] == role_entry["arn"]
            owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
            from santander_demo.aws_endpoints import gateway_region
            GATEWAY_URL = gateway["gatewayUrl"]
            assert gateway_region(GATEWAY_URL) == REGION
            RUNTIME_URL = (
                f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
                + quote(runtime_entry["arn"], safe="") + "/invocations?qualifier=DEFAULT"
            )
            print({"gateway": gateway_entry["id"], "runtime": runtime_entry["id"], "policy": "ENFORCE"})
            """,
        ),
        *step(
            "Permitir que o Gateway invoque somente este Runtime",
            "Aplicamos uma policy inline à role criada na aula 01. O documento "
            "autoriza InvokeAgentRuntime nos ARNs deste Runtime e de seu endpoint "
            "DEFAULT. Não altera a role do participante nem concede acesso "
            "a outros Runtimes.",
            """
            PERMISSION_NAME = "Lesson09InvokeRuntime"
            document = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
                "Resource": [runtime_entry["arn"], runtime_entry["arn"] + "/runtime-endpoint/DEFAULT"],
            }]}
            print(json.dumps(document, indent=2))
            try:
                previous = iam.get_role_policy(
                    RoleName=role_entry["name"], PolicyName=PERMISSION_NAME,
                )["PolicyDocument"]
            except iam.exceptions.NoSuchEntityException:
                previous = None
            assert previous is None or previous == document, "RUNTIME_PERMISSION_CHANGED"
            if previous is None:
                iam.put_role_policy(
                    RoleName=role_entry["name"], PolicyName=PERMISSION_NAME,
                    PolicyDocument=json.dumps(document),
                )
            state.record("gateway.runtime_permission", {
                "role_name": role_entry["name"], "name": PERMISSION_NAME,
                "runtime_arn": runtime_entry["arn"],
                "document_sha256": hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
            }, lesson="09")
            if previous is None:
                time.sleep(10)
            """,
        ),
        *step(
            "Criar o target MCP com autenticação IAM",
            "CreateGatewayTarget recebe o endpoint do Runtime. "
            "GATEWAY_IAM_ROLE e iamCredentialProvider indicam ao Gateway "
            "como assinar a chamada para bedrock-agentcore na região. "
            "O serviço descobre as ferramentas e precisa retornar READY.",
            """
            TARGET_CONFIGURATION = {"mcp": {"mcpServer": {"endpoint": RUNTIME_URL}}}
            TARGET_CREDENTIALS = [{
                "credentialProviderType": "GATEWAY_IAM_ROLE",
                "credentialProvider": {"iamCredentialProvider": {"service": "bedrock-agentcore", "region": REGION}},
            }]
            print(json.dumps({
                "targetConfiguration": TARGET_CONFIGURATION,
                "credentialProviderConfigurations": TARGET_CREDENTIALS,
            }, indent=2))
            target_entry = state.get("gateway.runtime_target")
            if target_entry is None:
                created = control.create_gateway_target(
                    gatewayIdentifier=gateway_entry["id"], name="workload",
                    description="Runtime MCP criado na aula 03; salto autenticado por IAM",
                    targetConfiguration=TARGET_CONFIGURATION,
                    credentialProviderConfigurations=TARGET_CREDENTIALS,
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":runtime-target")),
                )
                target_entry = state.record("gateway.runtime_target", {
                    "id": created["targetId"], "gateway_id": gateway_entry["id"],
                    "name": "workload", "runtime_arn": runtime_entry["arn"],
                    "endpoint": RUNTIME_URL,
                }, lesson="09")
            assert target_entry["gateway_id"] == gateway_entry["id"]
            assert target_entry["runtime_arn"] == runtime_entry["arn"] and target_entry["endpoint"] == RUNTIME_URL
            target = wait_ready(lambda: control.get_gateway_target(
                gatewayIdentifier=gateway_entry["id"], targetId=target_entry["id"],
            ), "READY")
            assert target["name"] == target_entry["name"] == "workload"
            assert target["targetConfiguration"] == TARGET_CONFIGURATION
            assert target["credentialProviderConfigurations"] == TARGET_CREDENTIALS
            TOOL_NAME = "workload___workload_identity"
            print({"target": target_entry["id"], "status": target["status"],
                   "request_id": target["ResponseMetadata"]["RequestId"]})
            """,
        ),
        *step(
            "Autorizar o analista a usar a nova ferramenta",
            "Esta regra Cedar é adicional à da aula 04 e vale somente para "
            "workload_identity neste Gateway. A validação continua estrita, "
            "com a política ACTIVE e o engine em ENFORCE.",
            '''
            CEDAR = f"""permit(
                principal == AgentCore::OAuthUser::{json.dumps(analyst_entry["sub"])},
                action == AgentCore::Action::{json.dumps(TOOL_NAME)},
                resource == AgentCore::Gateway::{json.dumps(gateway_entry["arn"])}
            ) when {{
                principal.hasTag("iss") &&
                principal.getTag("iss") == {json.dumps(ISSUER)} &&
                principal.hasTag("aud") &&
                principal.getTag("aud") == {json.dumps(CLIENT_ID)} &&
                principal.hasTag("token_use") &&
                principal.getTag("token_use") == "id"
            }};"""
            print(CEDAR)
            statement_hash = hashlib.sha256(CEDAR.encode()).hexdigest()
            policy_entry = state.get("policy.workload")
            if policy_entry is None:
                created = control.create_policy(
                    policyEngineId=engine_entry["id"], name="AllowAnalystWorkloadIdentity",
                    description="Analista autenticado consulta a identidade do workload",
                    definition={"cedar": {"statement": CEDAR}},
                    validationMode="FAIL_ON_ANY_FINDINGS", enforcementMode="ACTIVE",
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":workload-policy")),
                )
                policy_entry = state.record("policy.workload", {
                    "id": created["policyId"], "arn": created["policyArn"],
                    "engine_id": engine_entry["id"], "statement_sha256": statement_hash,
                }, lesson="09")
            assert policy_entry["engine_id"] == engine_entry["id"] and policy_entry["statement_sha256"] == statement_hash
            policy = wait_ready(lambda: control.get_policy(
                policyEngineId=engine_entry["id"], policyId=policy_entry["id"],
            ), "ACTIVE")
            assert policy["policyArn"] == policy_entry["arn"]
            assert policy["definition"] == {"cedar": {"statement": CEDAR}}
            assert policy["enforcementMode"] == "ACTIVE"
            print({"policy": policy_entry["id"], "status": "ACTIVE",
                   "request_id": policy["ResponseMetadata"]["RequestId"]})
            ''',
        ),
        *step(
            "Autenticar as pessoas e chamar o Runtime pelo Gateway",
            "Analista e auditor usam tokens Cognito válidos. O permitido deve "
            "retornar a identidade do workload na AWS. A negativa do auditor "
            "precisa ser uma decisão Policy do Gateway, não uma falha de login, "
            "rede ou invocação do backend.",
            """
            jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json")
            credentials = json.loads(secrets.get_secret_value(SecretId=secret_entry["arn"])["SecretString"])
            tokens = {}
            try:
                for person, expected in (("analista", analyst_entry), ("auditor", auditor_entry)):
                    authentication = cognito.initiate_auth(
                        ClientId=CLIENT_ID, AuthFlow="USER_PASSWORD_AUTH",
                        AuthParameters={"USERNAME": person, "PASSWORD": credentials[person]},
                    )["AuthenticationResult"]
                    token = authentication["IdToken"]
                    claims = jwt.decode(
                        token, jwks.get_signing_key_from_jwt(token).key,
                        algorithms=["RS256"], issuer=ISSUER, audience=CLIENT_ID,
                        options={"require": ["exp", "iat", "iss", "sub", "aud", "token_use"]},
                    )
                    assert claims["token_use"] == "id" and claims["sub"] == expected["sub"]
                    tokens[person] = token
            finally:
                del credentials
            del authentication, token

            request = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                       "params": {"name": TOOL_NAME, "arguments": {}}}
            for person in ("analista", "auditor"):
                response = httpx.post(
                    GATEWAY_URL, json=request, timeout=120, follow_redirects=False,
                    headers={"Authorization": "Bearer " + tokens[person],
                             "Accept": "application/json, text/event-stream"},
                )
                request_id = response.headers.get("x-amzn-requestid")
                assert request_id and response.status_code == 200
                if response.headers.get("content-type", "").startswith("text/event-stream"):
                    messages = []
                    for block in response.text.replace("\\r\\n", "\\n").split("\\n\\n"):
                        lines = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
                        if lines:
                            messages.append(json.loads("\\n".join(lines)))
                    matched = [message for message in messages if message.get("id") == 9]
                    assert len(matched) == 1
                    message = matched[0]
                else:
                    message = response.json()
                assert message.get("id") == 9
                if person == "auditor":
                    error = message.get("error", {})
                    assert error.get("code") == -32002
                    assert "policy" in error.get("message", "").lower(), "EXPECTED_POLICY_DENIAL"
                    print({"person": person, "gateway_runtime": "DENY", "request_id": request_id})
                else:
                    assert "error" not in message
                    result = message["result"]
                    assert not result.get("isError"), "GATEWAY_RUNTIME_TOOL_FAILED"
                    data = result.get("structuredContent")
                    if data is None:
                        texts = [item["text"] for item in result["content"] if item["type"] == "text"]
                        assert len(texts) == 1
                        data = json.loads(texts[0])
                    assert data["execution"] == "AWS_AGENTCORE_RUNTIME"
                    assert data["account"] == ACCOUNT_ID and data["run_id"] == state.data["run_id"]
                    assert (":assumed-role/" + NAME_PREFIX + "-runtime/") in data["principal"]
                    assert data["sts_request_id"]
                    print({"person": person, "gateway_runtime": "ALLOW",
                           "request_id": request_id, "result": data})
            """,
        ),
        md("""
        ### Fronteiras demonstradas

        Cognito autentica a pessoa; Cedar decide se ela pode chamar a ferramenta;
        IAM autoriza o Gateway no Runtime; a role do Runtime identifica o
        código que consulta STS. O retorno da ferramenta não é um token humano
        e não comprova delegação Microsoft OBO.

        A limpeza 99 remove o target antes do Runtime, exclui a política
        adicional e remove a permissão IAM ao encerrar a role do Gateway.
        A role e os recursos do editor não fazem parte dessa limpeza.
        """),
    ]
