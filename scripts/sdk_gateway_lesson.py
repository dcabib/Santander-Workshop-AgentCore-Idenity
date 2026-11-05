"""Aula Gateway: cada mutação AWS permanece visível na célula correspondente."""

from scripts.aws_notebook_lessons import md, step


def gateway():
    return [
        md("""
        ### O caminho da requisição

        `Pessoa → JWT Cognito → AgentCore Gateway → role IAM → Lambda`

        Vamos construir esse caminho agora, em **uma conta AWS**. A Lambda
        representa uma ferramenta de consulta a dados **sintéticos**. O Gateway
        transforma seu schema em uma ferramenta MCP. Não há servidor MCP no
        computador do participante.

        Esta aula permite a ferramenta aos usuários criados pelo administrador
        deste pool. Na aula de Policy adicionaremos decisões por pessoa e
        parâmetros com Cedar. Autenticação e autorização são etapas diferentes.

        **Permissões usadas:** Cognito para administrar o pool/clientes/usuários;
        Secrets Manager para guardar as senhas sintéticas; IAM para criar e
        passar as duas roles; Lambda e CloudWatch Logs; APIs de controle do
        AgentCore Gateway. A role do participante já precisa dessas permissões.
        `AccessDenied` é um bloqueio a examinar com o responsável pela conta.

        Os IDs são salvos após cada criação. Ao repetir uma célula, o notebook
        confere o recurso registrado. Se uma criação foi interrompida antes de
        salvar seu ID, investigue o recurso pelo nome exibido; não adote recursos
        de outra execução nem apague recursos do ambiente para liberar um nome.
        """),
        *step(
            "Preparar os clientes e uma espera com limite",
            "Os clientes abaixo chamam os serviços AWS. A função de espera "
            "consulta o estado retornado pela API, interrompe em falha e tem "
            "prazo máximo. Ela não cria recursos.",
            """
            import time
            from botocore.exceptions import ClientError

            cognito = aws.client("cognito-idp")
            secrets = aws.client("secretsmanager")
            iam = aws.client("iam")
            logs = aws.client("logs")
            lambdas = aws.client("lambda")
            control = aws.client("bedrock-agentcore-control")
            tag_list = [{"Key": key, "Value": value} for key, value in TAGS.items()]

            def require_owned(actual_tags):
                if not all(actual_tags.get(key) == value for key, value in TAGS.items()):
                    raise RuntimeError("RESOURCE_OWNERSHIP_MISMATCH")

            def wait_status(read, field, ready, *, seconds=300):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    response = read()
                    status = response[field]
                    if status == ready:
                        return response
                    if status in {"FAILED", "Failed", "CREATE_FAILED", "UPDATE_FAILED", "DELETING"}:
                        raise RuntimeError(
                            f"RESOURCE_FAILED: {status}; "
                            + str(response.get("statusReasons", response.get("StateReason", "")))
                        )
                    time.sleep(5)
                raise TimeoutError(f"RESOURCE_NOT_READY: expected {ready}, last status {status}")

            print({"resource_prefix": NAME_PREFIX, "region": REGION})
            """,
        ),
        *step(
            "Criar o User Pool do Cognito",
            "O pool é o emissor de identidade. Somente o administrador pode "
            "cadastrar usuários neste exercício; não habilitamos inscrição "
            "pública. No Entra ID, o tenant e suas configurações de identidade "
            "cumprem um papel semelhante, mas são administrados por outras APIs.",
            """
            pool_entry = state.get("identity.pool")
            if pool_entry is None:
                created = cognito.create_user_pool(
                    PoolName=NAME_PREFIX + "-people",
                    AdminCreateUserConfig={"AllowAdminCreateUserOnly": True},
                    Policies={"PasswordPolicy": {
                        "MinimumLength": 20, "RequireUppercase": True,
                        "RequireLowercase": True, "RequireNumbers": True,
                        "RequireSymbols": True,
                    }},
                    UserPoolTags=TAGS,
                )["UserPool"]
                pool_entry = state.record(
                    "identity.pool", {"id": created["Id"], "arn": created["Arn"]}, lesson="01",
                )
            pool = cognito.describe_user_pool(UserPoolId=pool_entry["id"])["UserPool"]
            require_owned(pool["UserPoolTags"])
            assert pool["Name"] == NAME_PREFIX + "-people"
            assert pool["Arn"] == pool_entry["arn"]
            assert pool["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"]
            POOL_ID = pool["Id"]
            ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
            print({"user_pool_id": POOL_ID, "issuer": ISSUER})
            """,
        ),
        *step(
            "Criar o cliente que representa o notebook",
            "O app client identifica a aplicação. Para tornar a primeira "
            "autenticação reproduzível, usaremos InitiateAuth com o fluxo "
            "USER_PASSWORD_AUTH e usuários sintéticos. O cadastro continua "
            "restrito ao administrador por IAM. Uma aplicação para usuários reais "
            "normalmente usaria o fluxo de login apropriado, como Authorization "
            "Code com PKCE. Esta célula não implementa Microsoft OBO.",
            """
            app_entry = state.get("identity.client")
            if app_entry is None:
                created = cognito.create_user_pool_client(
                    UserPoolId=POOL_ID, ClientName=NAME_PREFIX + "-notebook",
                    GenerateSecret=False,
                    ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
                    PreventUserExistenceErrors="ENABLED", EnableTokenRevocation=True,
                    IdTokenValidity=15, AccessTokenValidity=15, RefreshTokenValidity=1,
                    TokenValidityUnits={
                        "IdToken": "minutes", "AccessToken": "minutes", "RefreshToken": "days",
                    },
                )["UserPoolClient"]
                app_entry = state.record(
                    "identity.client", {"id": created["ClientId"], "pool_id": POOL_ID}, lesson="01",
                )
            assert app_entry["pool_id"] == POOL_ID
            app = cognito.describe_user_pool_client(
                UserPoolId=POOL_ID, ClientId=app_entry["id"],
            )["UserPoolClient"]
            assert app["ClientName"] == NAME_PREFIX + "-notebook"
            assert "ClientSecret" not in app
            CLIENT_ID = app["ClientId"]
            # Migração de um cliente criado pela primeira revisão desta aula.
            # Atualizamos somente os fluxos explícitos; não criamos outro cliente.
            expected_flows = {"ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"}
            actual_flows = set(app["ExplicitAuthFlows"])
            if actual_flows != expected_flows:
                assert actual_flows == {
                    "ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH",
                }, "UNEXPECTED_APP_CLIENT_AUTH_FLOWS"
                cognito.update_user_pool_client(
                    UserPoolId=POOL_ID, ClientId=CLIENT_ID,
                    ExplicitAuthFlows=sorted(expected_flows),
                    PreventUserExistenceErrors=app["PreventUserExistenceErrors"],
                    EnableTokenRevocation=app["EnableTokenRevocation"],
                    IdTokenValidity=app["IdTokenValidity"],
                    AccessTokenValidity=app["AccessTokenValidity"],
                    RefreshTokenValidity=app["RefreshTokenValidity"],
                    TokenValidityUnits=app["TokenValidityUnits"],
                )
                app = cognito.describe_user_pool_client(
                    UserPoolId=POOL_ID, ClientId=CLIENT_ID,
                )["UserPoolClient"]
            assert set(app["ExplicitAuthFlows"]) == expected_flows
            print({"app_client_id": CLIENT_ID, "id_token_audience": CLIENT_ID})
            """,
        ),
        *step(
            "Guardar senhas sintéticas no Secrets Manager",
            "A senha não vai para o Git, para o arquivo de IDs ou para a saída "
            "do notebook. O Secrets Manager permite retomar o exercício em "
            "outro kernel. A permissão de leitura desse segredo deve ficar "
            "com os participantes autorizados desta execução.",
            """
            secret_entry = state.get("identity.demo_credentials")
            if secret_entry is None:
                passwords = {
                    username: secrets.get_random_password(
                        PasswordLength=32, RequireEachIncludedType=True,
                    )["RandomPassword"]
                    for username in ("analista", "auditor")
                }
                created = secrets.create_secret(
                    Name=NAME_PREFIX + "-demo-credentials",
                    Description="Senhas de usuarios sinteticos desta execucao do workshop",
                    SecretString=json.dumps(passwords), Tags=tag_list,
                )
                secret_entry = state.record(
                    "identity.demo_credentials", {"arn": created["ARN"]}, lesson="01",
                )
                del passwords
            secret_metadata = secrets.describe_secret(SecretId=secret_entry["arn"])
            require_owned({tag["Key"]: tag["Value"] for tag in secret_metadata["Tags"]})
            assert secret_metadata["Name"] == NAME_PREFIX + "-demo-credentials"
            print({"credentials": "AWS_SECRETS_MANAGER", "values_printed": False})
            """,
        ),
        *step(
            "Cadastrar as duas pessoas do exercício",
            "Criamos analista e auditor no pool desta execução. A senha "
            "permanente só é definida durante o primeiro cadastro. As próximas "
            "aulas usarão essas duas identidades para comparar decisões. "
            "AdminCreateUser retorna o sub da pessoa; salvamos esse identificador "
            "antes de configurar a senha. Não precisamos listar usuários nem "
            "consultar AdminGetUser. Um conflito de nome sem registro interrompe "
            "a célula para investigação, sem adotar um usuário desconhecido.",
            """
            passwords = json.loads(
                secrets.get_secret_value(SecretId=secret_entry["arn"])["SecretString"]
            )
            try:
                for username in ("analista", "auditor"):
                    key = "identity.user." + username
                    person_entry = state.get(key)
                    if person_entry is None:
                        person = cognito.admin_create_user(
                            UserPoolId=POOL_ID, Username=username, MessageAction="SUPPRESS",
                            TemporaryPassword=passwords[username],
                        )["User"]
                        attributes = {item["Name"]: item["Value"] for item in person["Attributes"]}
                        person_entry = state.record(
                            key, {"username": username, "sub": attributes["sub"], "pool_id": POOL_ID},
                            lesson="01",
                        )
                    assert person_entry["pool_id"] == POOL_ID
                    assert person_entry["username"] == username
                    password_key = "identity.password_ready." + username
                    if state.get(password_key) is None:
                        cognito.admin_set_user_password(
                            UserPoolId=POOL_ID, Username=username,
                            Password=passwords[username], Permanent=True,
                        )
                        state.record(
                            password_key, {"username": username, "pool_id": POOL_ID}, lesson="01",
                        )
                print({"users_created": ["analista", "auditor"], "pool_id": POOL_ID})
            finally:
                del passwords
            """,
        ),
        *step(
            "Definir o código da ferramenta que executará no Lambda",
            "A função recebe os argumentos do schema MCP e retorna uma consulta "
            "sintética. O código abaixo será empacotado e enviado ao Lambda. "
            "Ainda não estamos executando a ferramenta no kernel. Observe que "
            "ela não recebe nem registra a senha ou o token da pessoa.",
            '''
            TOOL_SOURCE = """def handler(event, context):
                customer_id = event.get("customer_id")
                synthetic = {
                    "cliente-001": {"segment": "retail", "risk": "low"},
                    "cliente-002": {"segment": "retail", "risk": "medium"},
                }
                if customer_id not in synthetic:
                    raise ValueError("SYNTHETIC_CUSTOMER_NOT_FOUND")
                return {
                    "customer_id": customer_id,
                    **synthetic[customer_id],
                    "synthetic": True,
                    "execution": "AWS_LAMBDA",
                    "lambda_request_id": context.aws_request_id,
                }
            """
            from IPython.display import Code
            display(Code(TOOL_SOURCE, language="python"), include=["text/html", "text/plain"])
            FUNCTION_NAME = NAME_PREFIX + "-customer-risk"
            FUNCTION_ARN = f"arn:{PARTITION}:lambda:{REGION}:{ACCOUNT_ID}:function:{FUNCTION_NAME}"
            FUNCTION_MARKER = "santander-agentcore:" + state.data["run_id"] + ":lesson01:customer-risk"
            LOG_GROUP = "/aws/lambda/" + FUNCTION_NAME
            LOG_ARN = f"arn:{PARTITION}:logs:{REGION}:{ACCOUNT_ID}:log-group:{LOG_GROUP}"
            ''',
        ),
        *step(
            "Criar o grupo de logs e a role da função",
            "O CloudWatch recebe os logs da ferramenta. A role permite escrever "
            "somente neste grupo e é assumida pelo serviço Lambda. Criamos uma "
            "role com o prefixo desta execução; nenhuma role do ambiente de "
            "VS Code é alterada.",
            """
            log_entry = state.get("gateway.tool_logs")
            if log_entry is None:
                logs.create_log_group(logGroupName=LOG_GROUP, tags=TAGS)
                log_entry = state.record(
                    "gateway.tool_logs", {"name": LOG_GROUP, "arn": LOG_ARN}, lesson="01",
                )
            assert log_entry["name"] == LOG_GROUP
            require_owned(logs.list_tags_for_resource(resourceArn=LOG_ARN)["tags"])
            logs.put_retention_policy(logGroupName=LOG_GROUP, retentionInDays=7)

            LAMBDA_ROLE_NAME = NAME_PREFIX + "-lambda"
            lambda_trust = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }]}
            lambda_role_entry = state.get("gateway.lambda_role")
            if lambda_role_entry is None:
                created = iam.create_role(
                    RoleName=LAMBDA_ROLE_NAME,
                    AssumeRolePolicyDocument=json.dumps(lambda_trust), Tags=tag_list,
                )["Role"]
                lambda_role_entry = state.record(
                    "gateway.lambda_role", {"name": created["RoleName"], "arn": created["Arn"]},
                    lesson="01",
                )
            role = iam.get_role(RoleName=lambda_role_entry["name"])["Role"]
            require_owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
            assert role["Arn"] == lambda_role_entry["arn"]
            assert role["AssumeRolePolicyDocument"] == lambda_trust
            log_policy = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": LOG_ARN + ":*",
            }]}
            try:
                existing_policy = iam.get_role_policy(
                    RoleName=role["RoleName"], PolicyName="Lesson01Logs",
                )["PolicyDocument"]
            except iam.exceptions.NoSuchEntityException:
                existing_policy = None
            if existing_policy is None:
                iam.put_role_policy(
                    RoleName=role["RoleName"], PolicyName="Lesson01Logs",
                    PolicyDocument=json.dumps(log_policy),
                )
            else:
                assert existing_policy == log_policy, "LAMBDA_ROLE_POLICY_CHANGED"
            print({"lambda_role_arn": role["Arn"], "log_group": LOG_GROUP})
            """,
        ),
        *step(
            "Empacotar o código e criar a função Lambda",
            "CreateFunction envia o ZIP e associa a role IAM. GetFunction consulta "
            "a API até a função ficar ativa. Registramos ARN, hash do código, "
            "role e um marcador na descrição para conferir a propriedade e "
            "recusar alterações inesperadas na retomada e na limpeza. Esta "
            "função não depende de tags Lambda. Uma nova role pode levar alguns "
            "segundos para propagar: a repetição abaixo é limitada e trata "
            "somente essa resposta específica da AWS; outros erros interrompem.",
            """
            import base64
            import hashlib
            import io
            import zipfile

            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
                entry = zipfile.ZipInfo("lambda_function.py", date_time=(2026, 1, 1, 0, 0, 0))
                package.writestr(entry, TOOL_SOURCE.encode())
            artifact = archive.getvalue()
            code_hash = base64.b64encode(hashlib.sha256(artifact).digest()).decode()
            function_entry = state.get("gateway.tool_lambda")
            if function_entry is None:
                for attempt in range(12):
                    try:
                        created = lambdas.create_function(
                            FunctionName=FUNCTION_NAME, Runtime="python3.12",
                            Description=FUNCTION_MARKER,
                            Role=lambda_role_entry["arn"], Handler="lambda_function.handler",
                            Code={"ZipFile": artifact}, Timeout=15, MemorySize=128,
                        )
                        break
                    except ClientError as error:
                        details = error.response["Error"]
                        if (
                            details["Code"] != "InvalidParameterValueException"
                            or "cannot be assumed by Lambda" not in details["Message"]
                            or attempt == 11
                        ):
                            raise
                        time.sleep(5)
                function_entry = state.record(
                    "gateway.tool_lambda",
                    {
                        "arn": created["FunctionArn"], "name": FUNCTION_NAME, "code_hash": code_hash,
                        "role_arn": lambda_role_entry["arn"], "ownership_marker": FUNCTION_MARKER,
                    },
                    lesson="01",
                )
            wait_status(
                lambda: lambdas.get_function(FunctionName=function_entry["arn"])["Configuration"],
                "State", "Active",
            )
            function = lambdas.get_function(FunctionName=function_entry["arn"])
            assert function_entry["ownership_marker"] == FUNCTION_MARKER
            assert function_entry["role_arn"] == lambda_role_entry["arn"]
            assert function_entry["code_hash"] == code_hash
            assert function["Configuration"]["Description"] == FUNCTION_MARKER
            assert function["Configuration"]["FunctionArn"] == FUNCTION_ARN
            assert function["Configuration"]["Role"] == lambda_role_entry["arn"]
            assert function["Configuration"]["CodeSha256"] == code_hash
            print({"lambda": FUNCTION_ARN, "state": function["Configuration"]["State"]})
            """,
        ),
        *step(
            "Criar a role que o Gateway usará no target",
            "A pessoa entra com JWT. No salto Gateway → Lambda, a AWS usa a "
            "role de execução do Gateway. Essa role pode invocar somente a "
            "função desta aula. A trust policy limita conta e serviço; depois "
            "da criação do Gateway, vamos restringi-la ao ARN exato retornado.",
            """
            GATEWAY_ROLE_NAME = NAME_PREFIX + "-gateway"
            gateway_entry = state.get("gateway.instance")
            source_arn = (
                gateway_entry["arn"] if gateway_entry else
                f"arn:{PARTITION}:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:gateway/*"
            )
            gateway_trust = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Action": "sts:AssumeRole",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": ACCOUNT_ID},
                    "ArnLike": {"aws:SourceArn": source_arn},
                },
            }]}
            gateway_role_entry = state.get("gateway.role")
            if gateway_role_entry is None:
                created = iam.create_role(
                    RoleName=GATEWAY_ROLE_NAME,
                    AssumeRolePolicyDocument=json.dumps(gateway_trust), Tags=tag_list,
                )["Role"]
                gateway_role_entry = state.record(
                    "gateway.role", {"name": created["RoleName"], "arn": created["Arn"]}, lesson="01",
                )
            role = iam.get_role(RoleName=gateway_role_entry["name"])["Role"]
            require_owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
            assert role["Arn"] == gateway_role_entry["arn"]
            # Restringir o ARN abaixo é uma etapa posterior; não ampliamos trust na repetição.
            actual_trust = role["AssumeRolePolicyDocument"]
            initial_trust = json.loads(json.dumps(gateway_trust))
            initial_trust["Statement"][0]["Condition"]["ArnLike"]["aws:SourceArn"] = (
                f"arn:{PARTITION}:bedrock-agentcore:{REGION}:{ACCOUNT_ID}:gateway/*"
            )
            assert actual_trust in [gateway_trust, initial_trust]
            invoke_policy = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": FUNCTION_ARN,
            }]}
            try:
                existing_policy = iam.get_role_policy(
                    RoleName=role["RoleName"], PolicyName="Lesson01InvokeLambda",
                )["PolicyDocument"]
            except iam.exceptions.NoSuchEntityException:
                existing_policy = None
            if existing_policy is None:
                iam.put_role_policy(
                    RoleName=role["RoleName"], PolicyName="Lesson01InvokeLambda",
                    PolicyDocument=json.dumps(invoke_policy),
                )
            else:
                assert existing_policy == invoke_policy, "GATEWAY_ROLE_POLICY_CHANGED"
            print({"gateway_role_arn": role["Arn"], "allowed_target": FUNCTION_ARN})
            """,
        ),
        *step(
            "Criar o AgentCore Gateway com authorizer JWT",
            "Esta é a chamada que cria o Gateway. Discovery URL aponta para "
            "o documento OIDC do Cognito; allowedAudience limita a aplicação "
            "aceita. Usaremos o ID token do app client. No Entra ID a ideia "
            "de issuer, JWKS e audiência é semelhante, mas os valores e claims "
            "vêm do tenant e do registro da aplicação.",
            """
            gateway_entry = state.get("gateway.instance")
            jwt_authorizer = {"customJWTAuthorizer": {
                "discoveryUrl": ISSUER + "/.well-known/openid-configuration",
                "allowedAudience": [CLIENT_ID],
            }}
            if gateway_entry is None:
                created = control.create_gateway(
                    name=NAME_PREFIX + "-gateway",
                    description="Gateway criado passo a passo no notebook Santander",
                    roleArn=gateway_role_entry["arn"],
                    protocolType="MCP", authorizerType="CUSTOM_JWT",
                    authorizerConfiguration=jwt_authorizer, tags=TAGS,
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + "-gateway-create")),
                )
                gateway_entry = state.record(
                    "gateway.instance",
                    {"id": created["gatewayId"], "arn": created["gatewayArn"]}, lesson="01",
                )
            gateway_response = wait_status(
                lambda: control.get_gateway(gatewayIdentifier=gateway_entry["id"]),
                "status", "READY",
            )
            require_owned(control.list_tags_for_resource(resourceArn=gateway_entry["arn"])["tags"])
            assert gateway_response["gatewayArn"] == gateway_entry["arn"]
            assert gateway_response["roleArn"] == gateway_role_entry["arn"]
            assert gateway_response["authorizerType"] == "CUSTOM_JWT"
            assert gateway_response["authorizerConfiguration"] == jwt_authorizer
            GATEWAY_ID = gateway_entry["id"]
            GATEWAY_URL = gateway_response["gatewayUrl"]
            print({"gateway_id": GATEWAY_ID, "url": GATEWAY_URL, "status": "READY"})
            """,
        ),
        *step(
            "Restringir a trust policy ao Gateway criado",
            "Agora conhecemos o ARN do Gateway. A role aceitará AssumeRole "
            "somente quando o serviço apresentar esse ARN e esta conta de "
            "origem. A célula também confere a política gravada.",
            """
            gateway_trust["Statement"][0]["Condition"]["ArnLike"]["aws:SourceArn"] = gateway_entry["arn"]
            current_role = iam.get_role(RoleName=gateway_role_entry["name"])["Role"]
            if current_role["AssumeRolePolicyDocument"] != gateway_trust:
                assert current_role["AssumeRolePolicyDocument"] == initial_trust
                iam.update_assume_role_policy(
                    RoleName=gateway_role_entry["name"],
                    PolicyDocument=json.dumps(gateway_trust),
                )
            updated_role = iam.get_role(RoleName=gateway_role_entry["name"])["Role"]
            assert updated_role["AssumeRolePolicyDocument"] == gateway_trust
            print({"trusted_gateway": gateway_entry["arn"], "source_account": ACCOUNT_ID})
            """,
        ),
        *step(
            "Confirmar que o Gateway rejeita chamadas sem identidade válida",
            "Antes de adicionar o target, enviamos initialize MCP sem token "
            "e com um token inválido. Exigimos HTTP 401 e o identificador da "
            "resposta AWS. Uma falha de DNS, timeout ou erro 500 não comprova "
            "que o authorizer funciona.",
            """
            import httpx
            from santander_demo.aws_endpoints import gateway_region

            assert gateway_region(GATEWAY_URL) == REGION
            initialize = {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "santander-workshop", "version": "1"},
                },
            }
            for label, auth_header in [("anonymous", {}), ("invalid_jwt", {"Authorization": "Bearer invalid"})]:
                response = httpx.post(
                    GATEWAY_URL, json=initialize, timeout=30, follow_redirects=False,
                    headers={"Accept": "application/json, text/event-stream", **auth_header},
                )
                assert response.status_code == 401, f"{label}: HTTP {response.status_code}"
                request_id = response.headers.get("x-amzn-requestid")
                assert request_id, "AUTH_DENY_WITHOUT_AWS_REQUEST_ID"
                print({"case": label, "http_status": 401, "request_id": request_id})
            """,
        ),
        *step(
            "Publicar o schema da ferramenta como target Lambda",
            "O schema descreve nome, argumentos e tipos que um cliente MCP "
            "consegue descobrir. GATEWAY_IAM_ROLE determina como o Gateway "
            "invoca a Lambda. Não criamos uma Function URL pública. "
            "Compare o ARN e o schema retornados por GetGatewayTarget. "
            "Após uma mudança IAM, o serviço pode demorar a assumir a role. "
            "A repetição limitada abaixo mantém os mesmos parâmetros, confere "
            "a trust policy e não amplia permissões. Se o erro persistir, para.",
            """
            tool_schema = [{
                "name": "customer_risk",
                "description": "Consulta risco sintetico de cliente para o workshop",
                "inputSchema": {
                    "type": "object",
                    "properties": {"customer_id": {
                        "type": "string", "description": "cliente-001 ou cliente-002",
                    }},
                    "required": ["customer_id"],
                },
            }]
            target_configuration = {"mcp": {"lambda": {
                "lambdaArn": FUNCTION_ARN, "toolSchema": {"inlinePayload": tool_schema},
            }}}
            target_entry = state.get("gateway.lambda_target")
            if target_entry is None:
                for attempt in range(12):
                    try:
                        created = control.create_gateway_target(
                            gatewayIdentifier=GATEWAY_ID, name="customer",
                            description="Ferramenta Lambda sintetica criada na aula 01",
                            targetConfiguration=target_configuration,
                            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
                            clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + "-lambda-target-create")),
                        )
                        break
                    except ClientError as error:
                        details = error.response["Error"]
                        if (
                            details["Code"] != "ValidationException"
                            or "Gateway service is not authorized to perform AssumeRole" not in details["Message"]
                            or attempt == 11
                        ):
                            raise
                        current_role = iam.get_role(RoleName=gateway_role_entry["name"])["Role"]
                        assert current_role["AssumeRolePolicyDocument"] == gateway_trust
                        print({"waiting_for_iam": True, "attempt": attempt + 1, "retry_in_seconds": 5})
                        time.sleep(5)
                target_entry = state.record(
                    "gateway.lambda_target",
                    {"id": created["targetId"], "gateway_id": GATEWAY_ID, "name": "customer"},
                    lesson="01",
                )
            assert target_entry["gateway_id"] == GATEWAY_ID
            target = wait_status(
                lambda: control.get_gateway_target(
                    gatewayIdentifier=GATEWAY_ID, targetId=target_entry["id"],
                ), "status", "READY",
            )
            assert target["targetConfiguration"] == target_configuration
            assert target["credentialProviderConfigurations"] == [
                {"credentialProviderType": "GATEWAY_IAM_ROLE"},
            ]
            print({"target_id": target_entry["id"], "status": target["status"], "lambda": FUNCTION_ARN})
            """,
        ),
        *step(
            "Autenticar a pessoa e validar seu ID token",
            "Cognito emite o token. A validação usa as chaves públicas do issuer "
            "e confere assinatura, expiração, issuer e audiência. Exibimos "
            "somente claims selecionadas. O Gateway fará a própria validação "
            "ao receber o token na próxima célula.",
            """
            import jwt

            passwords = json.loads(
                secrets.get_secret_value(SecretId=secret_entry["arn"])["SecretString"]
            )
            try:
                authentication = cognito.initiate_auth(
                    ClientId=CLIENT_ID, AuthFlow="USER_PASSWORD_AUTH",
                    AuthParameters={"USERNAME": "analista", "PASSWORD": passwords["analista"]},
                )["AuthenticationResult"]
                token = authentication["IdToken"]
                del authentication
            finally:
                del passwords
            jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json")
            claims = jwt.decode(
                token, jwks.get_signing_key_from_jwt(token).key, algorithms=["RS256"],
                issuer=ISSUER, audience=CLIENT_ID,
                options={"require": ["exp", "iat", "iss", "sub", "aud", "token_use"]},
            )
            assert claims["token_use"] == "id"
            assert claims["sub"] == state.require("identity.user.analista", lesson="01")["sub"]
            print({"username": claims["cognito:username"], "audience": claims["aud"], "verified": True})
            """,
        ),
        *step(
            "Descobrir e invocar a ferramenta pela interface MCP",
            "O cliente envia tools/list e tools/call ao endpoint AWS. O "
            "resultado precisa conter uma evidência de execução Lambda e o "
            "resultado sintético esperado. Não basta verificar que o recurso "
            "foi criado. O token fica somente na memória do kernel.",
            """
            from datetime import timedelta
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async with httpx.AsyncClient(
                headers={"Authorization": "Bearer " + token},
                timeout=httpx.Timeout(90, connect=15), follow_redirects=False,
            ) as http:
                async with streamable_http_client(
                    GATEWAY_URL, http_client=http, terminate_on_close=False,
                ) as (read, write, _):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=90),
                    ) as mcp:
                        await mcp.initialize()
                        discovered = await mcp.list_tools()
                        names = [tool.name for tool in discovered.tools]
                        tool_name = target_entry["name"] + "___customer_risk"
                        assert tool_name in names, names
                        print({"discovered_tools": names})
                        result = await mcp.call_tool(
                            tool_name, arguments={"customer_id": "cliente-001"},
                        )
                        assert not result.isError, "GATEWAY_TOOL_INVOCATION_FAILED"
                        payload = result.structuredContent
                        if payload is None:
                            text = [item.text for item in result.content if item.type == "text"]
                            assert len(text) == 1
                            payload = json.loads(text[0])
                        assert payload["execution"] == "AWS_LAMBDA"
                        assert payload["customer_id"] == "cliente-001"
                        assert payload["risk"] == "low" and payload["synthetic"] is True
                        assert payload["lambda_request_id"]
                        print({"case": "authenticated_tool", "status": "PASS", "result": payload})
            del token
            """,
        ),
        md("""
        ### O que foi criado e o que observar no console

        Abra Cognito e confira o pool e o cliente exibidos. Em AgentCore Gateway,
        examine o authorizer, o target e seu schema. Em Lambda, confira o código
        e a role; em IAM, compare a trust policy com a permissão de invocação.
        O grupo de logs foi criado com retenção de sete dias.

        **Aceite desta aula:** Gateway e target READY; chamadas anônima e com
        JWT inválido retornam 401; o usuário autenticado descobre e invoca a
        ferramenta, recebendo o Request ID da Lambda na AWS.

        Esses recursos são utilizados pelas próximas aulas. A remoção deve
        ocorrer ao encerrar a jornada. A aula
        [99 — Limpeza SDK](99_cleanup_sdk.ipynb) mostra as chamadas de exclusão
        e verifica a propriedade de cada recurso. Ela só limpa as aulas já
        convertidas e recusa registros de dependências ainda não contempladas.
        """),
    ]
