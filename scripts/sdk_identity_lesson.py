"""Identidade da pessoa e da aplicação, sem simular Microsoft OBO."""

from scripts.aws_notebook_lessons import md, step


def identity():
    return [
        md("""
        ### Pessoa, aplicação e autorização

        Na aula 01 criamos a identidade e a primeira aplicação. Agora criaremos
        **outro app client Cognito** e autenticaremos a mesma pessoa nas duas
        aplicações. O `sub` deve permanecer igual, enquanto `aud` muda.

        O Gateway aceita apenas a audiência configurada na aula 01. Um token
        pode ter assinatura válida e identificar uma pessoa conhecida, mas ainda
        ser recusado por ter sido emitido para outra aplicação.

        **Pré-requisito:** concluir a aula 01 nesta conta/região. Esta aula usa
        Cognito e o Gateway na AWS; não exige outro provedor de identidade.
        Usa `CreateUserPoolClient`, `DescribeUserPoolClient`, leitura do segredo,
        `InitiateAuth` e consultas ao Gateway. Não amplia permissões IAM.
        """),
        *step(
            "Ler os recursos criados na aula 01",
            "Primeiro conferimos as dependências. Esta célula não cria recursos "
            "nem procura outputs de implantação. O issuer é reconstruído a "
            "partir do pool que criamos.",
            """
            import httpx
            import jwt

            cognito = aws.client("cognito-idp")
            secrets = aws.client("secretsmanager")
            control = aws.client("bedrock-agentcore-control")
            pool_entry = state.require("identity.pool", lesson="01")
            client_entry = state.require("identity.client", lesson="01")
            gateway_entry = state.require("gateway.instance", lesson="01")
            target_entry = state.require("gateway.lambda_target", lesson="01")
            secret_entry = state.require("identity.demo_credentials", lesson="01")
            pool = cognito.describe_user_pool(UserPoolId=pool_entry["id"])["UserPool"]
            assert all(pool["UserPoolTags"].get(key) == value for key, value in TAGS.items())
            assert pool["Arn"] == pool_entry["arn"]
            POOL_ID = pool["Id"]
            CLIENT_ID = client_entry["id"]
            assert client_entry["pool_id"] == POOL_ID
            ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
            gateway_response = control.get_gateway(gatewayIdentifier=gateway_entry["id"])
            assert gateway_response["status"] == "READY"
            assert gateway_response["gatewayArn"] == gateway_entry["arn"]
            assert gateway_response["authorizerType"] == "CUSTOM_JWT"
            assert gateway_response["authorizerConfiguration"] == {"customJWTAuthorizer": {
                "discoveryUrl": ISSUER + "/.well-known/openid-configuration",
                "allowedAudience": [CLIENT_ID],
            }}
            target = control.get_gateway_target(
                gatewayIdentifier=gateway_entry["id"], targetId=target_entry["id"],
            )
            assert target["status"] == "READY"
            GATEWAY_URL = gateway_response["gatewayUrl"]
            from santander_demo.aws_endpoints import gateway_region
            assert gateway_region(GATEWAY_URL) == REGION
            print({"pool_id": POOL_ID, "gateway_id": gateway_entry["id"], "allowed_audience": CLIENT_ID})
            """,
        ),
        *step(
            "Criar uma segunda aplicação no mesmo pool",
            "Este novo app client representa outra aplicação. Não vamos "
            "adicionar sua audiência ao Gateway: a negativa será parte do "
            "exercício. No Entra ID, registre também as aplicações e os recursos "
            "apropriados; não copie os identificadores Cognito.",
            """
            other_client_entry = state.get("identity.other_client")
            if other_client_entry is None:
                created = cognito.create_user_pool_client(
                    UserPoolId=POOL_ID, ClientName=NAME_PREFIX + "-other-app",
                    GenerateSecret=False,
                    ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
                    PreventUserExistenceErrors="ENABLED", EnableTokenRevocation=True,
                    IdTokenValidity=15, AccessTokenValidity=15, RefreshTokenValidity=1,
                    TokenValidityUnits={
                        "IdToken": "minutes", "AccessToken": "minutes", "RefreshToken": "days",
                    },
                )["UserPoolClient"]
                other_client_entry = state.record(
                    "identity.other_client", {"id": created["ClientId"], "pool_id": POOL_ID}, lesson="02",
                )
            assert other_client_entry["pool_id"] == POOL_ID
            other_app = cognito.describe_user_pool_client(
                UserPoolId=POOL_ID, ClientId=other_client_entry["id"],
            )["UserPoolClient"]
            assert other_app["ClientName"] == NAME_PREFIX + "-other-app"
            assert "ClientSecret" not in other_app
            OTHER_CLIENT_ID = other_app["ClientId"]
            assert OTHER_CLIENT_ID != CLIENT_ID
            print({"new_app_client_id": OTHER_CLIENT_ID, "gateway_configuration_changed": False})
            """,
        ),
        *step(
            "Autenticar e verificar os tokens das duas aplicações",
            "InitiateAuth autentica a pessoa. A validação criptográfica usa "
            "JWKS, issuer e a audiência esperada para cada aplicação. O registro "
            "do sub retornado na criação permite conferir que recebemos a "
            "identidade esperada. Exibimos apenas claims selecionadas.",
            """
            jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json")
            credentials = json.loads(
                secrets.get_secret_value(SecretId=secret_entry["arn"])["SecretString"]
            )
            tokens = {}
            verified_claims = {}
            try:
                for app_name, app_id in (("notebook", CLIENT_ID), ("other_app", OTHER_CLIENT_ID)):
                    result = cognito.initiate_auth(
                        ClientId=app_id, AuthFlow="USER_PASSWORD_AUTH",
                        AuthParameters={"USERNAME": "analista", "PASSWORD": credentials["analista"]},
                    )
                    token = result["AuthenticationResult"]["IdToken"]
                    claims = jwt.decode(
                        token, jwks.get_signing_key_from_jwt(token).key,
                        algorithms=["RS256"], issuer=ISSUER, audience=app_id,
                        options={"require": ["exp", "iat", "iss", "sub", "aud", "token_use"]},
                    )
                    assert claims["token_use"] == "id"
                    assert claims["sub"] == state.require("identity.user.analista", lesson="01")["sub"]
                    tokens[app_name] = token
                    verified_claims[app_name] = claims
                    print({
                        "application": app_name, "subject": claims["sub"],
                        "audience": claims["aud"], "issuer": claims["iss"],
                    })
                assert verified_claims["notebook"]["sub"] == verified_claims["other_app"]["sub"]
                assert verified_claims["notebook"]["aud"] != verified_claims["other_app"]["aud"]
            finally:
                del credentials
            del token, result
            """,
        ),
        *step(
            "Demonstrar que uma assinatura válida não basta",
            "O token da segunda aplicação foi validado na célula anterior, "
            "mas o Gateway precisa recusá-lo por audiência. Também alteraremos "
            "o payload desse token para a audiência permitida, sem assiná-lo "
            "novamente: o Gateway deve recusar a assinatura inválida. "
            "Nesses dois casos, o Gateway retorna HTTP 403 e o erro MCP "
            "insufficient_scope (-32002). Conferimos ambos e o Request ID; "
            "um erro de rede ou outro erro HTTP não comprova autorização.",
            """
            import base64

            initialize = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "santander-identity", "version": "1"},
                },
            }
            header, payload, signature = tokens["other_app"].split(".")
            modified_claims = dict(verified_claims["other_app"], aud=CLIENT_ID)
            encoded = base64.urlsafe_b64encode(
                json.dumps(modified_claims, separators=(",", ":")).encode(),
            ).rstrip(b"=").decode()
            tampered_token = header + "." + encoded + "." + signature
            for case, rejected_token in (
                ("valid_signature_wrong_audience", tokens["other_app"]),
                ("allowed_audience_invalid_signature", tampered_token),
            ):
                response = httpx.post(
                    GATEWAY_URL, json=initialize, timeout=30, follow_redirects=False,
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Authorization": "Bearer " + rejected_token,
                    },
                )
                assert response.status_code == 403, f"{case}: HTTP {response.status_code}"
                denial = response.json()
                assert "result" not in denial, "UNEXPECTED_MCP_RESULT"
                error = denial.get("error", {})
                assert error.get("code") == -32002, "EXPECTED_MCP_AUTHORIZATION_DENIAL"
                assert error.get("message", "").startswith("insufficient_scope"), (
                    "EXPECTED_INSUFFICIENT_SCOPE"
                )
                request_id = response.headers.get("x-amzn-requestid")
                assert request_id, "AUTH_DENY_WITHOUT_AWS_REQUEST_ID"
                print({
                    "case": case, "status": "DENY", "http_status": response.status_code,
                    "mcp_error_code": error["code"], "request_id": request_id,
                })
            del tampered_token, rejected_token, header, payload, signature, encoded
            """,
        ),
        *step(
            "Confirmar a chamada com a audiência permitida",
            "Usamos o token da aplicação aceita para chamar a ferramenta na "
            "AWS. A comparação só está completa quando as negativas e o caso "
            "positivo funcionam com o mesmo Gateway.",
            """
            from datetime import timedelta
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async with httpx.AsyncClient(
                headers={"Authorization": "Bearer " + tokens["notebook"]},
                timeout=httpx.Timeout(90, connect=15), follow_redirects=False,
            ) as http:
                async with streamable_http_client(
                    GATEWAY_URL, http_client=http, terminate_on_close=False,
                ) as (read, write, _):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=90),
                    ) as mcp:
                        await mcp.initialize()
                        result = await mcp.call_tool(
                            target_entry["name"] + "___customer_risk",
                            arguments={"customer_id": "cliente-001"},
                        )
                        assert not result.isError
                        data = result.structuredContent
                        if data is None:
                            text = [item.text for item in result.content if item.type == "text"]
                            assert len(text) == 1
                            data = json.loads(text[0])
                        assert data["execution"] == "AWS_LAMBDA" and data["synthetic"] is True
                        assert data["customer_id"] == "cliente-001" and data["risk"] == "low"
                        assert data["lambda_request_id"]
                        print({"case": "allowed_audience", "status": "PASS", "result": data})
            del tokens
            """,
        ),
        md("""
        ### Relação com Microsoft Entra ID

        | Conceito | Cognito desta aula | Entra ID |
        |---|---|---|
        | Emissor | Issuer do User Pool | Issuer do tenant e versão de endpoint |
        | Pessoa | `sub` no pool | `sub` é específico do contexto; `oid` com `tid` identifica o objeto no tenant |
        | Aplicação/recurso | App client é a audiência deste ID token | A audiência de um access token identifica a API; claims de aplicação dependem do fluxo |
        | Chaves de assinatura | JWKS do issuer | JWKS publicado pelo issuer do tenant |
        | Autorização | Ainda limitada à audiência; Cedar nas próximas aulas | Scopes, app roles, consentimentos e regras do recurso |

        OBO da Microsoft é uma **troca de token** feita por uma aplicação
        intermediária para obter um access token destinado a outra API, com os
        consentimentos e credenciais exigidos pelo Entra ID. Não fizemos essa
        troca aqui. Repassar um JWT Cognito ou fazer dois logins não implementa
        Microsoft OBO.

        Também não criamos ainda a identidade de um agente no Runtime.
        Identidade da pessoa, identidade da aplicação e identidade do workload
        são distintas. A aula de Runtime mostrará o workload executando na AWS.

        **Aceite:** mesma pessoa com audiências diferentes, duas negativas
        HTTP 403 com erro MCP de autorização e uma invocação Lambda permitida.
        Na aula 01, ausência de token e JWT malformado retornaram HTTP 401.
        A limpeza 99 exclui o pool
        dedicado, incluindo os dois clientes.
        """),
    ]
