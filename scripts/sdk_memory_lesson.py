"""Memory por actor IAM e referências sujeitas à autorização atual na fonte."""

from scripts.aws_notebook_lessons import md, step


def memory():
    return [
        md("""
        ### Uma lembrança não restaura acesso revogado

        `Cognito User Pool → Identity Pool → sessão IAM por pessoa → Memory: referência`

        `Referência → DynamoDB: visão autorizada atual → conteúdo, se disponível`

        **Pré-requisito:** aula 01. Uma conta basta. Criamos AgentCore Memory,
        uma fonte sintética DynamoDB, um Cognito Identity Pool e duas roles
        didáticas nesta aula. Não precisamos de `sts:AssumeRole` na sessão
        do editor: Cognito emite as credenciais após validar o login.
        Os recursos são criados pelas chamadas SDK abaixo.

        Usamos **memória de curto prazo**: eventos por actor e sessão, com
        expiração de sete dias. Não configuramos estratégias de extração ou
        afirmamos ter testado memória semântica de longo prazo.

        A fonte modela concessões como linhas de uma visão por pessoa. IAM
        restringe `GetItem` ao partition key dessa pessoa. Revogar uma concessão
        remove sua linha materializada; o documento canônico permanece.
        Este é um modelo sintético de autorização, não Databricks ou Unity
        Catalog reais. Memory guarda somente o ID da referência, sem copiar
        o conteúdo financeiro para o evento.
        """),
        *step(
            "Autenticar as pessoas e definir actors estáveis",
            "Verificamos assinatura, issuer, audiência e sub dos tokens Cognito. "
            "O actor é um hash de issuer e sub. A role didática de cada pessoa "
            "receberá esse actor fixo na condição IAM; trocar actorId na chamada "
            "não deve conceder acesso a outra pessoa.",
            """
            import hashlib
            import time
            from datetime import UTC, datetime
            import jwt
            from botocore.exceptions import ClientError

            control = aws.client("bedrock-agentcore-control")
            memory_api = aws.client("bedrock-agentcore")
            dynamodb = aws.client("dynamodb")
            iam = aws.client("iam")
            cognito = aws.client("cognito-idp")
            federation = aws.client("cognito-identity")
            secrets = aws.client("secretsmanager")
            pool_entry = state.require("identity.pool", lesson="01")
            client_entry = state.require("identity.client", lesson="01")
            secret_entry = state.require("identity.demo_credentials", lesson="01")
            people = {name: state.require("identity.user." + name, lesson="01") for name in ("analista", "auditor")}
            assert client_entry["pool_id"] == pool_entry["id"]
            assert all(entry["pool_id"] == pool_entry["id"] for entry in people.values())
            ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_entry['id']}"
            jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json")
            credentials = json.loads(secrets.get_secret_value(SecretId=secret_entry["arn"])["SecretString"])
            actors = {}
            login_tokens = {}
            try:
                for person, expected in people.items():
                    authentication = cognito.initiate_auth(
                        ClientId=client_entry["id"], AuthFlow="USER_PASSWORD_AUTH",
                        AuthParameters={"USERNAME": person, "PASSWORD": credentials[person]},
                    )["AuthenticationResult"]
                    token = authentication["IdToken"]
                    claims = jwt.decode(
                        token, jwks.get_signing_key_from_jwt(token).key,
                        algorithms=["RS256"], issuer=ISSUER, audience=client_entry["id"],
                        options={"require": ["exp", "iat", "iss", "sub", "aud", "token_use"]},
                    )
                    assert claims["token_use"] == "id" and claims["sub"] == expected["sub"]
                    login_tokens[person] = token
                    actors[person] = "actor_" + hashlib.sha256(
                        (claims["iss"] + "\\0" + claims["sub"]).encode(),
                    ).hexdigest()
            finally:
                del credentials
            del authentication, token, claims
            def owned(tags):
                assert all(tags.get(key) == value for key, value in TAGS.items()), "OWNERSHIP_MISMATCH"

            print({"actors": actors, "memory_kind": "SHORT_TERM_EVENTS"})
            """,
        ),
        *step(
            "Criar o Identity Pool para logins autenticados",
            "CreateIdentityPool aceita somente o User Pool e o app client da aula 01. "
            "Desabilitamos identidades anônimas e o fluxo clássico. O serviço "
            "validará o token e escolherá a role por regras de sub; o cliente "
            "não escolhe livremente uma role. Entra ID também pode federar com "
            "Identity Pools, usando o provedor e as claims correspondentes.",
            """
            PROVIDER = f"cognito-idp.{REGION}.amazonaws.com/{pool_entry['id']}"
            POOL_CONFIG = {
                "IdentityPoolName": NAME_PREFIX.replace("-", "_") + "_memory",
                "AllowUnauthenticatedIdentities": False, "AllowClassicFlow": False,
                "CognitoIdentityProviders": [{
                    "ProviderName": PROVIDER, "ClientId": client_entry["id"],
                    "ServerSideTokenCheck": True,
                }],
            }
            identity_pool = state.get("memory.identity_pool")
            if identity_pool is None:
                created = federation.create_identity_pool(**POOL_CONFIG, IdentityPoolTags=TAGS)
                identity_pool = state.record("memory.identity_pool", {
                    "id": created["IdentityPoolId"], "config": POOL_CONFIG,
                }, lesson="15")
            assert identity_pool["config"] == POOL_CONFIG
            current = federation.describe_identity_pool(IdentityPoolId=identity_pool["id"])
            assert all(current.get(key) == value for key, value in POOL_CONFIG.items()), "IDENTITY_POOL_CHANGED"
            assert not any(current.get(key) for key in (
                "SupportedLoginProviders", "DeveloperProviderName", "OpenIdConnectProviderARNs", "SamlProviderARNs",
            )), "UNEXPECTED_FEDERATION_PROVIDER"
            owned(current["IdentityPoolTags"])
            TRUST = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"Federated": "cognito-identity.amazonaws.com"},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {"cognito-identity.amazonaws.com:aud": identity_pool["id"]},
                    "ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "authenticated"},
                },
            }]}
            print({"identity_pool_id": identity_pool["id"], "trust": TRUST})
            """,
        ),
        *step(
            "Criar Memory e aguardar ACTIVE",
            "CreateMemory cria o recurso com eventos de sete dias. Não "
            "selecionamos memoryStrategies nesta aula. Conferimos nome, "
            "ARN, configuração e tags antes de reutilizar um Memory registrado.",
            """
            MEMORY_NAME = NAME_PREFIX.replace("-", "_") + "_memory"
            memory_entry = state.get("memory.instance")
            if memory_entry is None:
                created = control.create_memory(
                    name=MEMORY_NAME, eventExpiryDuration=7, memoryStrategies=[],
                    description="Workshop: referencias por actor, sem conteudo financeiro",
                    tags=TAGS, clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":memory")),
                )["memory"]
                memory_entry = state.record("memory.instance", {
                    "id": created["id"], "arn": created["arn"], "name": MEMORY_NAME,
                }, lesson="15")
            deadline = time.monotonic() + 300
            while True:
                response = control.get_memory(memoryId=memory_entry["id"])
                current = response["memory"]
                if current["status"] == "ACTIVE":
                    break
                assert current["status"] == "CREATING", ("MEMORY_FAILED", current.get("failureReason"))
                if time.monotonic() >= deadline:
                    raise TimeoutError("MEMORY_NOT_ACTIVE")
                time.sleep(5)
            assert current["arn"] == memory_entry["arn"] and current["name"] == memory_entry["name"] == MEMORY_NAME
            assert current["eventExpiryDuration"] == 7 and not current.get("strategies")
            assert not current.get("memoryExecutionRoleArn") and not current.get("encryptionKeyArn")
            owned(control.list_tags_for_resource(resourceArn=memory_entry["arn"])["tags"])
            print({"memory": memory_entry["id"], "status": "ACTIVE",
                   "request_id": response["ResponseMetadata"]["RequestId"]})
            """,
        ),
        *step(
            "Criar a fonte sintética no DynamoDB",
            "A tabela tem um documento canônico e uma visão autorizada por "
            "actor. PAY_PER_REQUEST evita provisionar capacidade fixa. Os "
            "participantes não recebem Scan, Query nem escrita na tabela. "
            "CreateTable não inclui tags opcionais: o editor do evento não "
            "possui TagResource. Guardamos o TableId imutável retornado pela "
            "criação, além de ARN e nome. Retomada e limpeza recusam uma "
            "tabela recriada com o mesmo nome e outro TableId.",
            """
            TABLE_NAME = NAME_PREFIX + "-memory-source"
            table_entry = state.get("memory.source_table")
            if table_entry is None:
                created = dynamodb.create_table(
                    TableName=TABLE_NAME, BillingMode="PAY_PER_REQUEST",
                    AttributeDefinitions=[
                        {"AttributeName": "PK", "AttributeType": "S"},
                        {"AttributeName": "SK", "AttributeType": "S"},
                    ],
                    KeySchema=[
                        {"AttributeName": "PK", "KeyType": "HASH"},
                        {"AttributeName": "SK", "KeyType": "RANGE"},
                    ],
                )["TableDescription"]
                assert created["TableId"], "TABLE_ID_REQUIRED"
                table_entry = state.record("memory.source_table", {
                    "name": TABLE_NAME, "arn": created["TableArn"], "table_id": created["TableId"],
                }, lesson="15")
            dynamodb.get_waiter("table_exists").wait(TableName=table_entry["name"])
            table = dynamodb.describe_table(TableName=table_entry["name"])["Table"]
            assert table["TableArn"] == table_entry["arn"] and table_entry["name"] == TABLE_NAME
            assert table["TableId"] == table_entry["table_id"], "SOURCE_TABLE_REPLACED"
            assert table["TableStatus"] == "ACTIVE"
            assert table["KeySchema"] == [
                {"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"},
            ]
            assert table["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
            print({"source": "SYNTHETIC_AUTHORIZED_VIEW", "table": table_entry["name"], "table_id": table_entry["table_id"]})
            """,
        ),
        *step(
            "Materializar as concessões iniciais",
            "O operador da aula escreve o documento e as duas linhas "
            "autorizadas. PutItem exige ausência da chave; uma linha existente "
            "não é sobrescrita. Uma concessão revogada numa execução anterior "
            "da aula permanece revogada durante a retomada.",
            """
            DOCUMENT_ID = "documento-001"
            CONTENT = "Dados sinteticos: cliente-001 possui risco baixo; nenhum dado bancario real."
            ITEMS = {
                "canonical": {
                    "PK": {"S": "DOCUMENT#" + DOCUMENT_ID}, "SK": {"S": "CONTENT"},
                    "document_id": {"S": DOCUMENT_ID}, "content": {"S": CONTENT},
                    "workshop_run": {"S": state.data["run_id"]},
                },
                **{person: {
                    "PK": {"S": "ACTOR#" + actor_id}, "SK": {"S": "DOCUMENT#" + DOCUMENT_ID},
                    "document_id": {"S": DOCUMENT_ID}, "content": {"S": CONTENT},
                    "workshop_run": {"S": state.data["run_id"]},
                } for person, actor_id in actors.items()},
            }
            for name, item in ITEMS.items():
                key = "memory.source_item." + name
                row_key = {field: item[field] for field in ("PK", "SK")}
                digest = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
                if key in state.data.get("released_resources", {}):
                    assert name == "analista", "UNEXPECTED_RELEASED_SOURCE_ITEM"
                    existing = dynamodb.get_item(
                        TableName=table_entry["name"], Key=row_key, ConsistentRead=True,
                    )
                    assert "Item" not in existing, "REVOKED_SOURCE_GRANT_REAPPEARED"
                    continue
                entry = state.get(key)
                if entry is None:
                    dynamodb.put_item(
                        TableName=table_entry["name"], Item=item,
                        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
                    )
                    entry = state.record(key, {
                        "table_name": table_entry["name"], "key": row_key, "item_sha256": digest,
                    }, lesson="15")
                assert entry["table_name"] == table_entry["name"] and entry["key"] == row_key
                assert entry["item_sha256"] == digest
                actual = dynamodb.get_item(
                    TableName=table_entry["name"], Key=row_key, ConsistentRead=True,
                )["Item"]
                assert actual == item, "SOURCE_ITEM_CHANGED"
            print({"source_document": DOCUMENT_ID, "contains_real_data": False})
            """,
        ),
        *step(
            "Criar roles com isolamento nativo de actor e partition key",
            "Memory avalia bedrock-agentcore:actorId. DynamoDB avalia "
            "dynamodb:LeadingKeys no GetItem. A policy restringe cada role "
            "ao actor autenticado e à sua visão autorizada. Somente o Identity Pool "
            "pode emitir estas sessões. O participante controla as duas contas "
            "Cognito sintéticas para estudar os controles.",
            """
            INLINE_NAME = "Lesson15ActorAndSource"
            memory_roles = {}
            created_any = False
            for person, actor_id in actors.items():
                role_name = NAME_PREFIX + "-memory-" + person
                document = {"Version": "2012-10-17", "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents"],
                        "Resource": memory_entry["arn"],
                        "Condition": {"StringEquals": {"bedrock-agentcore:actorId": actor_id}},
                    },
                    {
                        "Effect": "Allow", "Action": ["dynamodb:GetItem"], "Resource": table_entry["arn"],
                        "Condition": {"ForAllValues:StringEquals": {"dynamodb:LeadingKeys": ["ACTOR#" + actor_id]}},
                    },
                ]}
                digest = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
                print(person, json.dumps(document, indent=2))
                key = "memory.role." + person
                entry = state.get(key)
                if entry is None:
                    role = iam.create_role(
                        RoleName=role_name, AssumeRolePolicyDocument=json.dumps(TRUST),
                        Description="Workshop: actor Memory e visao autorizada da fonte",
                        Tags=[{"Key": key, "Value": value} for key, value in TAGS.items()],
                    )["Role"]
                    entry = state.record(key, {
                        "name": role_name, "arn": role["Arn"], "actor_id": actor_id,
                        "identity_pool_id": identity_pool["id"], "policy_name": INLINE_NAME,
                        "policy_sha256": digest, "memory_arn": memory_entry["arn"], "table_arn": table_entry["arn"],
                    }, lesson="15")
                    created_any = True
                assert entry["name"] == role_name and entry["actor_id"] == actor_id
                assert entry["identity_pool_id"] == identity_pool["id"] and entry["policy_sha256"] == digest
                assert entry["memory_arn"] == memory_entry["arn"] and entry["table_arn"] == table_entry["arn"]
                role = iam.get_role(RoleName=role_name)["Role"]
                assert role["Arn"] == entry["arn"] and role["AssumeRolePolicyDocument"] == TRUST
                assert not role.get("PermissionsBoundary")
                owned({tag["Key"]: tag["Value"] for tag in role["Tags"]})
                attached = iam.list_attached_role_policies(RoleName=role_name)
                assert not attached["AttachedPolicies"] and not attached.get("IsTruncated")
                inline = iam.list_role_policies(RoleName=role_name)
                assert set(inline["PolicyNames"]) <= {INLINE_NAME} and not inline.get("IsTruncated")
                if INLINE_NAME not in inline["PolicyNames"]:
                    iam.put_role_policy(RoleName=role_name, PolicyName=INLINE_NAME, PolicyDocument=json.dumps(document))
                    created_any = True
                assert iam.get_role_policy(RoleName=role_name, PolicyName=INLINE_NAME)["PolicyDocument"] == document
                memory_roles[person] = entry
            if created_any:
                time.sleep(10)
            """,
        ),
        *step(
            "Mapear o sub autenticado e obter credenciais temporárias",
            "SetIdentityPoolRoles associa cada sub à sua role. Se nenhuma regra "
            "combinar, AmbiguousRoleResolution=Deny recusa o acesso. GetId e "
            "GetCredentialsForIdentity trocam o ID token por uma sessão AWS "
            "temporária. Tokens e credenciais ficam somente em memória.",
            """
            MAPPING = {
                "Roles": {},
                "RoleMappings": {PROVIDER + ":" + client_entry["id"]: {
                    "Type": "Rules", "AmbiguousRoleResolution": "Deny",
                    "RulesConfiguration": {"Rules": [{
                        "Claim": "sub", "MatchType": "Equals", "Value": people[person]["sub"],
                        "RoleARN": memory_roles[person]["arn"],
                    } for person in people]},
                }},
            }
            mapping_entry = state.get("memory.identity_mapping")
            actual = federation.get_identity_pool_roles(IdentityPoolId=identity_pool["id"])
            actual_mapping = {key: actual.get(key, {}) for key in ("Roles", "RoleMappings")}
            if mapping_entry is None:
                assert actual_mapping == {"Roles": {}, "RoleMappings": {}}, "UNREGISTERED_IDENTITY_MAPPING"
                mapping_entry = state.record("memory.identity_mapping", {
                    "pool_id": identity_pool["id"], "document": MAPPING,
                }, lesson="15")
            assert mapping_entry["pool_id"] == identity_pool["id"] and mapping_entry["document"] == MAPPING
            assert actual_mapping in ({"Roles": {}, "RoleMappings": {}}, MAPPING), "IDENTITY_MAPPING_CHANGED"
            if actual_mapping != MAPPING:
                federation.set_identity_pool_roles(IdentityPoolId=identity_pool["id"], **MAPPING)
            actual = federation.get_identity_pool_roles(IdentityPoolId=identity_pool["id"])
            assert {key: actual.get(key, {}) for key in MAPPING} == MAPPING
            print(json.dumps(MAPPING, indent=2))
            sessions = {}
            try:
                for person, token in login_tokens.items():
                    login = {PROVIDER: token}
                    federated_id = federation.get_id(
                        AccountId=ACCOUNT_ID, IdentityPoolId=identity_pool["id"], Logins=login,
                    )["IdentityId"]
                    issued = federation.get_credentials_for_identity(IdentityId=federated_id, Logins=login)
                    credentials = issued["Credentials"]
                    sessions[person] = boto3.Session(
                        aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretKey"],
                        aws_session_token=credentials["SessionToken"], region_name=REGION,
                    )
                    print({"person": person, "identity_id": federated_id,
                           "request_id": issued["ResponseMetadata"]["RequestId"]})
            finally:
                login_tokens.clear()
            del credentials, issued, login, token
            try:
                federation.get_id(AccountId=ACCOUNT_ID, IdentityPoolId=identity_pool["id"])
            except ClientError as error:
                assert error.response["Error"]["Code"] == "NotAuthorizedException"
                print({"anonymous_identity": "DENY", "request_id": error.response["ResponseMetadata"]["RequestId"]})
            else:
                raise AssertionError("ANONYMOUS_IDENTITY_MUST_BE_DENIED")
            """,
        ),
        *step(
            "Registrar uma referência na memória da pessoa",
            "CreateEvent persiste somente o ID do documento. O actor e a sessão "
            "são parâmetros da API, sujeitos à condição IAM. A resposta fornece "
            "o eventId usado na retomada e na limpeza.",
            """
            reference = {"document_id": DOCUMENT_ID, "source_kind": "SYNTHETIC_AUTHORIZED_VIEW"}
            payload = [{"conversational": {
                "role": "USER", "content": {"text": json.dumps(reference, sort_keys=True)},
            }}]
            analyst_memory = sessions["analista"].client("bedrock-agentcore")
            SESSION_ID = NAME_PREFIX + "-memory-session"
            payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            request_entry = state.get("memory.event_request.analista")
            if request_entry is None:
                request_entry = state.record("memory.event_request.analista", {
                    "timestamp": datetime.now(UTC).isoformat(), "memory_id": memory_entry["id"],
                    "actor_id": actors["analista"], "session_id": SESSION_ID, "payload_sha256": payload_hash,
                }, lesson="15")
            assert request_entry["memory_id"] == memory_entry["id"]
            assert request_entry["actor_id"] == actors["analista"] and request_entry["session_id"] == SESSION_ID
            assert request_entry["payload_sha256"] == payload_hash
            event_entry = state.get("memory.event.analista")
            if event_entry is None:
                created = analyst_memory.create_event(
                    memoryId=memory_entry["id"], actorId=actors["analista"], sessionId=SESSION_ID,
                    eventTimestamp=datetime.fromisoformat(request_entry["timestamp"]), payload=payload,
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":memory-reference")),
                )["event"]
                event_entry = state.record("memory.event.analista", {
                    "id": created["eventId"], "memory_id": memory_entry["id"],
                    "actor_id": actors["analista"], "session_id": SESSION_ID,
                    "payload_sha256": payload_hash,
                }, lesson="15")
            assert event_entry["memory_id"] == memory_entry["id"] and event_entry["actor_id"] == actors["analista"]
            assert event_entry["session_id"] == SESSION_ID
            assert event_entry["payload_sha256"] == payload_hash

            def read_reference():
                deadline = time.monotonic() + 60
                while True:
                    response = analyst_memory.list_events(
                        memoryId=memory_entry["id"], actorId=actors["analista"],
                        sessionId=SESSION_ID, includePayloads=True, maxResults=100,
                    )
                    if response["events"]:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("MEMORY_EVENT_NOT_VISIBLE")
                    time.sleep(2)
                assert not response.get("nextToken"), "UNEXPECTED_MEMORY_EVENTS"
                assert len(response["events"]) == 1
                event = response["events"][0]
                assert event["eventId"] == event_entry["id"]
                assert event["payload"] == payload, "MEMORY_REFERENCE_CHANGED"
                print({"memory_reference": "READ", "request_id": response["ResponseMetadata"]["RequestId"]})
                return json.loads(event["payload"][0]["conversational"]["content"]["text"])

            assert read_reference() == reference
            """,
        ),
        *step(
            "Testar o isolamento entre actors e visões da fonte",
            "A sessão do auditor tenta ler o actor do analista. A sessão do "
            "analista tenta acessar a visão do auditor. Ambas as chamadas "
            "precisam receber uma negativa IAM do serviço AWS, com Request ID.",
            """
            def require_denial(label, call):
                try:
                    call()
                except ClientError as error:
                    assert error.response["Error"]["Code"] in {"AccessDeniedException", "AccessDenied"}
                    assert error.response["ResponseMetadata"]["HTTPStatusCode"] in {400, 403}
                    assert error.response["ResponseMetadata"]["RequestId"]
                    print({"case": label, "decision": "IAM_DENY",
                           "request_id": error.response["ResponseMetadata"]["RequestId"]})
                else:
                    raise AssertionError("CROSS_PERSON_ACCESS_ALLOWED: " + label)

            require_denial("other_memory_actor", lambda: sessions["auditor"].client("bedrock-agentcore").list_events(
                memoryId=memory_entry["id"], actorId=actors["analista"],
                sessionId=SESSION_ID, includePayloads=True,
            ))
            require_denial("other_source_partition", lambda: sessions["analista"].client("dynamodb").get_item(
                TableName=table_entry["name"], ConsistentRead=True,
                Key={field: ITEMS["auditor"][field] for field in ("PK", "SK")},
            ))
            """,
        ),
        *step(
            "Revogar a concessão e reler a referência antiga",
            "O operador remove somente a linha autorizada do analista. "
            "A referência continua no Memory, mas uma leitura consistente "
            "da fonte não devolve mais conteúdo para essa pessoa. O documento "
            "canônico e a visão do auditor permanecem na AWS.",
            """
            source = sessions["analista"].client("dynamodb")
            row_key = {field: ITEMS["analista"][field] for field in ("PK", "SK")}
            grant_entry = state.get("memory.source_item.analista")
            if grant_entry:
                before = source.get_item(TableName=table_entry["name"], Key=row_key, ConsistentRead=True)
                assert before["Item"] == ITEMS["analista"]
                print({"source_before_revocation": "AUTHORIZED_VIEW_PRESENT",
                       "request_id": before["ResponseMetadata"]["RequestId"]})
                # Somente o operador tem DeleteItem; a role da pessoa não tem escrita.
                removed = dynamodb.delete_item(
                    TableName=table_entry["name"], Key=row_key,
                    ConditionExpression="workshop_run = :run",
                    ExpressionAttributeValues={":run": {"S": state.data["run_id"]}},
                    ReturnValues="ALL_OLD",
                )
                assert removed["Attributes"] == ITEMS["analista"]
                state.forget("memory.source_item.analista", expected=grant_entry)
            remembered = read_reference()
            assert remembered["document_id"] == DOCUMENT_ID
            after = source.get_item(TableName=table_entry["name"], Key=row_key, ConsistentRead=True)
            assert "Item" not in after, "REVOKED_GRANT_RETURNED_CONTENT"
            for name in ("canonical", "auditor"):
                current = dynamodb.get_item(
                    TableName=table_entry["name"],
                    Key={field: ITEMS[name][field] for field in ("PK", "SK")}, ConsistentRead=True,
                )
                assert current["Item"] == ITEMS[name]
            print({"memory_reference": "STILL_PRESENT", "source_after_revocation": "NO_CURRENT_GRANT",
                   "content_returned": False, "request_id": after["ResponseMetadata"]["RequestId"]})
            """,
        ),
        md("""
        ### Resultado e limites

        Memory persistiu uma referência sob um actor protegido por IAM.
        Acesso a outro actor e a outra visão DynamoDB foi negado pela AWS.
        A concessão atual da fonte foi removida, e o conteúdo deixou de estar
        disponível ao analista, mesmo com a referência antiga ainda na memória.

        O modelo didático materializa conteúdo permitido em linhas por pessoa.
        Uma integração real com Databricks precisa avaliar as permissões atuais
        da fonte e não pode tratar esse simulador como Unity Catalog.
        No Entra ID, o mapeamento equivalente parte de issuer e subject
        verificados; atribuir roles ou trocar tokens exige sua federação.

        A aula 99 verifica os eventos, itens e roles desta execução antes de
        removê-los. Reiniciar a aula não recria silenciosamente a concessão
        revogada; um ciclo novo começa depois da limpeza.
        """),
    ]
