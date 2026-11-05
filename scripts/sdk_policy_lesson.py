"""Policy: engine, Cedar e decisões reais no Gateway, criados pelo notebook."""

from scripts.aws_notebook_lessons import md, step


def policy():
    return [
        md("""
        ### Autenticar a pessoa e autorizar a operação

        `JWT Cognito → Gateway → decisão Cedar → Lambda, somente se permitido`

        Na aula 01, o Gateway aceitou a audiência do notebook. Agora criaremos
        um **Policy Engine** e uma política que permite ao **analista** consultar
        somente **cliente-001**. O auditor e consultas a outro cliente serão
        negados. Os dados continuam sintéticos.

        **Pré-requisito:** aula 01 concluída nesta conta/região. Uma conta basta.
        Usaremos as APIs de Policy, `UpdateGateway` e uma policy IAM adicional
        na role do Gateway que a aula 01 criou. Não alteramos a role do
        participante. O schema da ferramenta vem do target já registrado.

        `ENFORCE` faz o Gateway aplicar a decisão. `LOG_ONLY` somente observa
        e não demonstra bloqueio. Sem um `permit` aplicável, Cedar nega por
        padrão. A associação do engine passa a restringir também as chamadas
        feitas nas aulas anteriores.
        """),
        *step(
            "Conferir pool, Gateway, target e role",
            "As dependências são lidas pelos IDs retornados na aula 01. "
            "Conferimos a propriedade dos recursos e o authorizer antes "
            "de configurar a autorização. Uma configuração inesperada "
            "interrompe a célula.",
            """
            import hashlib
            import time
            import httpx
            import jwt

            control = aws.client("bedrock-agentcore-control")
            iam = aws.client("iam")
            cognito = aws.client("cognito-idp")
            secrets = aws.client("secretsmanager")
            pool_entry = state.require("identity.pool", lesson="01")
            client_entry = state.require("identity.client", lesson="01")
            gateway_entry = state.require("gateway.instance", lesson="01")
            target_entry = state.require("gateway.lambda_target", lesson="01")
            role_entry = state.require("gateway.role", lesson="01")
            secret_entry = state.require("identity.demo_credentials", lesson="01")
            analyst_entry = state.require("identity.user.analista", lesson="01")
            auditor_entry = state.require("identity.user.auditor", lesson="01")

            def owned(tags):
                assert all(tags.get(key) == value for key, value in TAGS.items()), (
                    "POLICY_RESOURCE_OWNERSHIP_MISMATCH"
                )

            def wait_ready(read, ready):
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    current = read()
                    if current["status"] == ready:
                        return current
                    if current["status"] in {
                        "FAILED", "CREATE_FAILED", "UPDATE_FAILED", "UPDATE_UNSUCCESSFUL",
                        "DELETE_FAILED", "DELETING",
                    }:
                        raise RuntimeError(
                            "POLICY_RESOURCE_FAILED: " + str(current.get("statusReasons", []))
                        )
                    time.sleep(5)
                raise TimeoutError("POLICY_RESOURCE_NOT_READY")

            pool = cognito.describe_user_pool(UserPoolId=pool_entry["id"])["UserPool"]
            owned(pool["UserPoolTags"])
            assert pool["Arn"] == pool_entry["arn"]
            POOL_ID = pool_entry["id"]
            CLIENT_ID = client_entry["id"]
            for entry in (client_entry, analyst_entry, auditor_entry):
                assert entry["pool_id"] == POOL_ID
            ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
            gateway = control.get_gateway(gatewayIdentifier=gateway_entry["id"])
            owned(control.list_tags_for_resource(resourceArn=gateway_entry["arn"])["tags"])
            assert gateway["gatewayArn"] == gateway_entry["arn"]
            assert gateway["name"] == NAME_PREFIX + "-gateway"
            assert gateway["status"] == "READY"
            assert gateway["roleArn"] == role_entry["arn"]
            assert gateway["authorizerType"] == "CUSTOM_JWT"
            assert gateway["authorizerConfiguration"] == {"customJWTAuthorizer": {
                "discoveryUrl": ISSUER + "/.well-known/openid-configuration",
                "allowedAudience": [CLIENT_ID],
            }}
            role = iam.get_role(RoleName=role_entry["name"])["Role"]
            owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
            assert role["Arn"] == role_entry["arn"]
            assert target_entry["gateway_id"] == gateway_entry["id"]
            target = control.get_gateway_target(
                gatewayIdentifier=gateway_entry["id"], targetId=target_entry["id"],
            )
            assert target["status"] == "READY"
            assert target["targetConfiguration"]["mcp"]["lambda"]["lambdaArn"] == (
                state.require("gateway.tool_lambda", lesson="01")["arn"]
            )
            TOOL_NAME = target_entry["name"] + "___customer_risk"
            GATEWAY_URL = gateway["gatewayUrl"]
            from santander_demo.aws_endpoints import gateway_region
            assert gateway_region(GATEWAY_URL) == REGION
            print({"gateway_id": gateway_entry["id"], "tool": TOOL_NAME, "region": REGION})
            """,
        ),
        *step(
            "Criar o Policy Engine",
            "O engine reúne as políticas que o Gateway consultará. Criamos "
            "um engine exclusivo desta execução, registramos seus IDs e "
            "aguardamos ACTIVE. Nenhuma permissão de negócio foi concedida ainda.",
            """
            ENGINE_NAME = NAME_PREFIX.replace("-", "_") + "_policy"
            engine_entry = state.get("policy.engine")
            if engine_entry is None:
                created = control.create_policy_engine(
                    name=ENGINE_NAME,
                    description="Workshop Santander: pessoa, ferramenta e cliente sintético",
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":policy-engine")),
                    tags=TAGS,
                )
                engine_entry = state.record(
                    "policy.engine",
                    {"id": created["policyEngineId"], "arn": created["policyEngineArn"]},
                    lesson="04",
                )
            engine = wait_ready(
                lambda: control.get_policy_engine(policyEngineId=engine_entry["id"]), "ACTIVE",
            )
            assert engine["policyEngineArn"] == engine_entry["arn"]
            assert engine["name"] == ENGINE_NAME
            owned(control.list_tags_for_resource(resourceArn=engine_entry["arn"])["tags"])
            print({"policy_engine_id": engine_entry["id"], "status": engine["status"]})
            """,
        ),
        *step(
            "Permitir que a role do Gateway consulte este engine",
            "IAM autoriza a comunicação entre serviços. Esta policy concede "
            "GetPolicyEngine e as operações de autorização somente ao engine "
            "e ao Gateway exibidos. A permissão de invocar a Lambda da aula "
            "01 permanece separada. Exibimos o documento antes de aplicá-lo.",
            """
            POLICY_IAM_NAME = "Lesson04AuthorizePolicy"
            policy_iam = {"Version": "2012-10-17", "Statement": [
                {
                    "Effect": "Allow", "Action": ["bedrock-agentcore:GetPolicyEngine"],
                    "Resource": engine_entry["arn"],
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "bedrock-agentcore:AuthorizeAction",
                        "bedrock-agentcore:PartiallyAuthorizeActions",
                    ],
                    "Resource": [engine_entry["arn"], gateway_entry["arn"]],
                },
            ]}
            print(json.dumps(policy_iam, indent=2))
            try:
                previous = iam.get_role_policy(
                    RoleName=role_entry["name"], PolicyName=POLICY_IAM_NAME,
                )["PolicyDocument"]
            except iam.exceptions.NoSuchEntityException:
                previous = None
            assert previous is None or previous == policy_iam, "POLICY_IAM_DOCUMENT_CHANGED"
            if previous is None:
                iam.put_role_policy(
                    RoleName=role_entry["name"], PolicyName=POLICY_IAM_NAME,
                    PolicyDocument=json.dumps(policy_iam),
                )
            state.record("policy.gateway_role_permission", {
                "role_name": role_entry["name"], "name": POLICY_IAM_NAME,
                "engine_arn": engine_entry["arn"], "gateway_arn": gateway_entry["arn"],
                "document_sha256": hashlib.sha256(
                    json.dumps(policy_iam, sort_keys=True).encode(),
                ).hexdigest(),
            }, lesson="04")
            if previous is None:
                # IAM propaga a nova permissão antes da associação ao Gateway.
                time.sleep(10)
            """,
        ),
        *step(
            "Associar o engine ao Gateway em ENFORCE",
            "O Gateway passa a pedir uma decisão antes de invocar a ferramenta. "
            "Até criarmos o permit, a negação padrão é esperada. Preservamos "
            "authorizer, protocolo e demais configurações retornadas por "
            "GetGateway; não reconstruímos o endpoint nem trocamos sua role.",
            """
            desired_engine = {"arn": engine_entry["arn"], "mode": "ENFORCE"}
            current = control.get_gateway(gatewayIdentifier=gateway_entry["id"])
            existing_engine = current.get("policyEngineConfiguration")
            assert existing_engine is None or existing_engine == desired_engine, (
                "UNEXPECTED_GATEWAY_POLICY_ENGINE"
            )
            if existing_engine is None:
                preserved_fields = (
                    "name", "description", "roleArn", "protocolType", "protocolConfiguration",
                    "authorizerType", "authorizerConfiguration", "kmsKeyArn",
                    "customTransformConfiguration", "interceptorConfigurations",
                    "exceptionLevel", "wafConfiguration",
                )
                update = {key: current[key] for key in preserved_fields if key in current}
                update.update(
                    gatewayIdentifier=gateway_entry["id"],
                    policyEngineConfiguration=desired_engine,
                )
                control.update_gateway(**update)
            current = wait_ready(
                lambda: control.get_gateway(gatewayIdentifier=gateway_entry["id"]), "READY",
            )
            assert current["policyEngineConfiguration"] == desired_engine
            assert current["authorizerConfiguration"] == gateway["authorizerConfiguration"]
            assert current["authorizerType"] == "CUSTOM_JWT"
            assert current["roleArn"] == role_entry["arn"]
            print({"gateway_id": gateway_entry["id"], "policy_engine": desired_engine})
            """,
        ),
        *step(
            "Escrever e ler a regra Cedar",
            "Principal é o sub verificado da pessoa; action é o nome MCP "
            "completo; resource é o ARN deste Gateway. O bloco when confere "
            "issuer, tipo de token, audiência e customer_id. A Lambda não "
            "recebe a chamada quando esta decisão é negativa.",
            '''
            CEDAR = f"""permit(
                principal == AgentCore::OAuthUser::{json.dumps(analyst_entry["sub"])},
                action == AgentCore::Action::{json.dumps(TOOL_NAME)},
                resource == AgentCore::Gateway::{json.dumps(gateway_entry["arn"])}
            ) when {{
                principal.hasTag("iss") &&
                principal.getTag("iss") == {json.dumps(ISSUER)} &&
                principal.hasTag("token_use") &&
                principal.getTag("token_use") == "id" &&
                principal.hasTag("aud") &&
                principal.getTag("aud") == {json.dumps(CLIENT_ID)} &&
                context.input.customer_id == "cliente-001"
            }};"""
            print(CEDAR)
            print({
                "allowed_person": "analista",
                "allowed_customer": "cliente-001",
                "all_other_requests": "IMPLICIT_DENY",
            })
            ''',
        ),
        *step(
            "Criar a política com validação estrita",
            "CreatePolicy valida a regra contra o schema disponível no "
            "engine. FAIL_ON_ANY_FINDINGS impede ignorar problemas de "
            "validação. ACTIVE e ENFORCE são conferidos antes do teste. "
            "Uma política diferente da registrada interrompe a retomada.",
            """
            statement_sha256 = hashlib.sha256(CEDAR.encode()).hexdigest()
            policy_entry = state.get("policy.customer")
            if policy_entry is None:
                created = control.create_policy(
                    policyEngineId=engine_entry["id"], name="AllowAnalystCustomer001",
                    description="Somente analista, audiencia do notebook e cliente-001",
                    definition={"cedar": {"statement": CEDAR}},
                    validationMode="FAIL_ON_ANY_FINDINGS", enforcementMode="ACTIVE",
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":customer-policy")),
                )
                policy_entry = state.record("policy.customer", {
                    "id": created["policyId"], "arn": created["policyArn"],
                    "engine_id": engine_entry["id"], "statement_sha256": statement_sha256,
                }, lesson="04")
            assert policy_entry["engine_id"] == engine_entry["id"]
            assert policy_entry["statement_sha256"] == statement_sha256
            created_policy = wait_ready(
                lambda: control.get_policy(
                    policyEngineId=engine_entry["id"], policyId=policy_entry["id"],
                ), "ACTIVE",
            )
            assert created_policy["policyArn"] == policy_entry["arn"]
            assert created_policy["definition"] == {"cedar": {"statement": CEDAR}}
            assert created_policy["enforcementMode"] == "ACTIVE"
            print({
                "policy_id": policy_entry["id"], "status": created_policy["status"],
                "enforcement_mode": created_policy["enforcementMode"],
            })
            """,
        ),
        *step(
            "Autenticar analista e auditor",
            "Ambas as pessoas recebem tokens válidos da mesma aplicação. "
            "Assim, a negativa do auditor testará a política de negócio, "
            "e não uma falha de login ou audiência. Tokens e senhas "
            "permanecem na memória e não são exibidos.",
            """
            jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json")
            credentials = json.loads(
                secrets.get_secret_value(SecretId=secret_entry["arn"])["SecretString"],
            )
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
                    print({"person": person, "subject_verified": True, "audience": CLIENT_ID})
            finally:
                del credentials
            del authentication, token
            """,
        ),
        *step(
            "Invocar a ferramenta e comparar as decisões",
            "Enviamos a mesma operação MCP em três casos. O permitido deve "
            "retornar dados sintéticos e Request ID da Lambda. As negativas "
            "precisam vir do mecanismo de Policy do Gateway, com Request ID "
            "AWS; um timeout ou uma falha de autenticação não conta como "
            "negação Cedar.",
            """
            def mcp_message(response, request_id):
                if response.headers.get("content-type", "").startswith("text/event-stream"):
                    messages = [
                        json.loads(line[5:].strip()) for line in response.text.splitlines()
                        if line.startswith("data:") and line[5:].strip()
                    ]
                    matches = [message for message in messages if message.get("id") == request_id]
                    assert len(matches) == 1, "MCP_RESPONSE_ID_MISMATCH"
                    return matches[0]
                message = response.json()
                assert message.get("id") == request_id, "MCP_RESPONSE_ID_MISMATCH"
                return message

            cases = [
                ("analyst_allowed_customer", "analista", "cliente-001", "ALLOW"),
                ("analyst_other_customer", "analista", "cliente-002", "DENY"),
                ("auditor_same_customer", "auditor", "cliente-001", "DENY"),
            ]
            for case, person, customer_id, expected in cases:
                with httpx.Client(
                    timeout=90, follow_redirects=False,
                    headers={
                        "Authorization": "Bearer " + tokens[person],
                        "Accept": "application/json, text/event-stream",
                    },
                ) as http:
                    initialize = http.post(GATEWAY_URL, json={
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26", "capabilities": {},
                            "clientInfo": {"name": "santander-policy", "version": "1"},
                        },
                    })
                    initialize.raise_for_status()
                    assert "result" in mcp_message(initialize, 1), "MCP_INITIALIZE_FAILED"
                    headers = {"MCP-Protocol-Version": "2025-03-26"}
                    if initialize.headers.get("mcp-session-id"):
                        headers["Mcp-Session-Id"] = initialize.headers["mcp-session-id"]
                    response = http.post(GATEWAY_URL, headers=headers, json={
                        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": TOOL_NAME, "arguments": {"customer_id": customer_id}},
                    })
                    aws_request_id = response.headers.get("x-amzn-requestid")
                    assert aws_request_id, "GATEWAY_RESPONSE_WITHOUT_AWS_REQUEST_ID"
                    message = mcp_message(response, 2)
                    if expected == "ALLOW":
                        response.raise_for_status()
                        assert "error" not in message and not message["result"].get("isError")
                        result = message["result"]
                        data = result.get("structuredContent")
                        if data is None:
                            text = [item["text"] for item in result["content"] if item["type"] == "text"]
                            assert len(text) == 1
                            data = json.loads(text[0])
                        assert data["execution"] == "AWS_LAMBDA" and data["synthetic"] is True
                        assert data["customer_id"] == customer_id and data["risk"] == "low"
                        assert data["lambda_request_id"]
                        print({
                            "case": case, "status": "ALLOW", "request_id": aws_request_id,
                            "lambda_request_id": data["lambda_request_id"],
                        })
                    else:
                        # A resposta precisa identificar a decisão de Policy.
                        # Outros erros não são convertidos em um teste aprovado.
                        error = message.get("error", {})
                        result = message.get("result", {})
                        assert bool(error) != bool(result.get("isError")), "EXPECTED_MCP_ERROR"
                        if error:
                            assert "result" not in message
                            denial_message = error.get("message", "").lower()
                        else:
                            assert result["isError"] is True
                            denial_message = " ".join(
                                item["text"] for item in result.get("content", [])
                                if item.get("type") == "text"
                            ).lower()
                        assert response.status_code in {200, 403}, (
                            "UNEXPECTED_DENIAL_HTTP_STATUS", response.status_code,
                        )
                        assert "policy" in denial_message and any(
                            word in denial_message for word in ("denied", "not allowed", "unauthorized", "deny")
                        ), "EXPECTED_POLICY_DENIAL: " + json.dumps(error)
                        print({
                            "case": case, "status": "DENY", "http_status": response.status_code,
                            "mcp_error_code": error.get("code"), "request_id": aws_request_id,
                        })
            del tokens
            """,
        ),
        md("""
        ### Interpretar o resultado

        | Pessoa | Parâmetro | Resultado esperado |
        |---|---|---|
        | analista | cliente-001 | Permitido, com resultado da Lambda |
        | analista | cliente-002 | Negado pela condição de entrada |
        | auditor | cliente-001 | Negado por não ser o principal permitido |

        O teste positivo comprova execução da ferramenta. As negativas
        comprovam a decisão de Policy no Gateway. Esta aula não implementa
        uma ACL na fonte nem prova sua aplicação; essa camada aparece nas
        aulas de dados.

        **Entra ID:** o desenho também exige assinatura, issuer, audiência
        e claims verificadas antes da política. Adapte os identificadores
        e a modelagem de pessoas/aplicações às claims do token emitido pelo
        tenant. Os valores Cognito desta regra não podem ser copiados
        literalmente para Entra ID.

        **Aceite:** engine e política ACTIVE, Gateway ENFORCE, um ALLOW e
        dois DENY com evidências AWS. A aula 99 remove Gateway, políticas,
        engine e permissões específicas ao encerrar a jornada.
        """),
    ]
