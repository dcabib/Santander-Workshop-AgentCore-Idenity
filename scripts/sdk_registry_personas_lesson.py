"""Personas do workshop oficial, verificadas com sessões e chamadas AWS."""

from scripts.aws_notebook_lessons import md, step


def personas():
    return [
        md("""
        ### Separar desenvolvimento, publicação, aprovação e consumo

        | Persona | Responsabilidade |
        |---|---|
        | Developer (sessão do editor) | Consultar e invocar o Runtime desenvolvido |
        | Publisher | Criar, consultar e submeter registros do catálogo |
        | Approver | Consultar registros e decidir sua aprovação |
        | Consumer | Descobrir registros aprovados e invocar o Runtime permitido |

        **Pré-requisitos:** aulas 03 e 06 nesta conta. Criamos as três roles
        previstas pelo workshop oficial: `admin_persona` (Approver),
        `publisher_persona` e `consumer_persona`, limitadas aos recursos da aula.
        O editor do evento já permite assumir essas roles. Em outra conta,
        o organizador precisa autorizar `sts:AssumeRole` para esses três ARNs.
        Os nomes são únicos por conta: execute uma jornada por vez. Se uma
        role já existir sem pertencer a esta execução, a célula interrompe
        antes de criar qualquer persona. A role do editor não é alterada.

        O participante assume todas as personas para estudar a separação.
        Em uma organização, pessoas ou workloads distintos recebem cada papel.
        IAM não representa, sozinho, uma segregação organizacional quando
        a mesma pessoa pode assumir todos os papéis.
        """),
        *step(
            "Conferir recursos e identificar quem pode assumir as personas",
            "As trust policies confiam somente no principal IAM da sessão "
            "autorizada. Para uma sessão STS, GetRole resolve o ARN real da "
            "role, incluindo seu path. Não confiamos em toda a conta.",
            """
            import hashlib
            import time
            from botocore.exceptions import ClientError

            iam = aws.client("iam")
            registry_control = aws.client("agent-registry-control")
            control = aws.client("bedrock-agentcore-control")
            registry_entry = state.require("registry.instance", lesson="06")
            runtime_entry = state.require("runtime.instance", lesson="03")
            catalog = registry_control.get_registry(registryId=registry_entry["id"])
            assert catalog["status"] == "READY" and catalog["registryArn"] == registry_entry["arn"]
            assert catalog["discoveryConfiguration"] == {"authorizerType": "AWS_IAM"}
            assert not catalog.get("approvalConfiguration", {}).get("autoApprovalRules", [])
            tags = registry_control.list_tags_for_resource(resourceArn=registry_entry["arn"])["tags"]
            assert all(tags.get(key) == value for key, value in TAGS.items())
            runtime = control.get_agent_runtime(agentRuntimeId=runtime_entry["id"])
            assert runtime["status"] == "READY" and runtime["agentRuntimeArn"] == runtime_entry["arn"]
            assert runtime.get("authorizerConfiguration") is None, "IAM_RUNTIME_REQUIRED"
            tags = control.list_tags_for_resource(resourceArn=runtime_entry["arn"])["tags"]
            assert all(tags.get(key) == value for key, value in TAGS.items())
            caller_arn = identity["Arn"]
            if ":assumed-role/" in caller_arn:
                caller_role_name = caller_arn.split(":assumed-role/", 1)[1].split("/")[0]
                trusted_principal = iam.get_role(RoleName=caller_role_name)["Role"]["Arn"]
            else:
                assert caller_arn.startswith(f"arn:{PARTITION}:iam::{ACCOUNT_ID}:user/"), (
                    "IAM_USER_OR_ROLE_REQUIRED"
                )
                trusted_principal = caller_arn
            assert trusted_principal.startswith(f"arn:{PARTITION}:iam::{ACCOUNT_ID}:")
            TRUST = {"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"AWS": trusted_principal}, "Action": "sts:AssumeRole",
            }]}
            print(json.dumps(TRUST, indent=2))
            """,
        ),
        *step(
            "Escrever as permissões de cada persona",
            "As chamadas de descoberta usam agent-registry, mesmo quando "
            "o SDK de controle se chama agent-registry-control. "
            "BatchGetDiscoverableRegistryRecord exige a ação IAM "
            "GetDiscoverableRegistryRecord. Testaremos as sessões com chamadas "
            "reais; não é necessário acesso ao simulador IAM.",
            """
            REGISTRY_RESOURCES = [registry_entry["arn"], registry_entry["arn"] + "/record/*"]
            RUNTIME_RESOURCES = [runtime_entry["arn"], runtime_entry["arn"] + "/runtime-endpoint/DEFAULT"]
            DISCOVERY_ACTIONS = [
                "agent-registry:ListDiscoverableRegistryRecords",
                "agent-registry:GetDiscoverableRegistryRecord",
                "agent-registry:SearchDiscoverableRegistryRecords",
            ]
            INVOCATION_ACTIONS = [
                "bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:StopRuntimeSession",
            ]
            statements = {
                "publisher": [{
                    "Effect": "Allow", "Action": [
                        "agent-registry:CreateRegistryRecord",
                        "agent-registry:GetRegistryRecord",
                        "agent-registry:SubmitRegistryRecordForApproval",
                    ], "Resource": REGISTRY_RESOURCES,
                }],
                "approver": [{
                    "Effect": "Allow", "Action": [
                        "agent-registry:GetRegistryRecord", "agent-registry:UpdateRegistryRecordStatus",
                    ], "Resource": REGISTRY_RESOURCES,
                }],
                "consumer": [
                    {"Effect": "Allow", "Action": ["bedrock-agentcore:GetAgentRuntime"],
                     "Resource": runtime_entry["arn"]},
                    {"Effect": "Allow", "Action": DISCOVERY_ACTIONS, "Resource": REGISTRY_RESOURCES},
                    {"Effect": "Allow", "Action": INVOCATION_ACTIONS, "Resource": RUNTIME_RESOURCES},
                ],
            }
            PERSONA_POLICIES = {
                name: {"Version": "2012-10-17", "Statement": [
                    {"Effect": "Allow", "Action": ["agent-registry:GetRegistry"],
                     "Resource": registry_entry["arn"]},
                    *values,
                ]}
                for name, values in statements.items()
            }
            for name, document in PERSONA_POLICIES.items():
                print(name, json.dumps(document, indent=2))
            """,
        ),
        *step(
            "Criar as roles e aplicar somente as policies exibidas",
            "Registramos o ARN, o principal confiável e o hash da policy. "
            "A retomada confere trust, tags, permissions boundary e policies "
            "anexadas antes de usar a role. Uma policy inesperada interrompe "
            "a célula, sem ser substituída.",
            """
            PERSONA_INLINE = "Lesson07Persona"
            PERSONA_NAMES = {
                "publisher": "publisher_persona", "approver": "admin_persona",
                "consumer": "consumer_persona",
            }
            # Verifique todos os nomes antes da primeira criação: não adote roles de outra aula.
            for name, role_name in PERSONA_NAMES.items():
                if state.get("registry.role." + name) is None:
                    try:
                        iam.get_role(RoleName=role_name)
                    except iam.exceptions.NoSuchEntityException:
                        pass
                    else:
                        raise RuntimeError("PERSONA_NAME_ALREADY_IN_USE: " + role_name)
            created_any = False
            persona_entries = {}
            for name, document in PERSONA_POLICIES.items():
                role_name = PERSONA_NAMES[name]
                policy_hash = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
                key = "registry.role." + name
                entry = state.get(key)
                if entry is None:
                    created = iam.create_role(
                        RoleName=role_name, AssumeRolePolicyDocument=json.dumps(TRUST),
                        Description="Workshop Santander: persona " + name,
                        Tags=[{"Key": key, "Value": value} for key, value in TAGS.items()],
                    )["Role"]
                    entry = state.record(key, {
                        "name": role_name, "arn": created["Arn"], "trusted_principal": trusted_principal,
                        "registry_arn": registry_entry["arn"], "runtime_arn": runtime_entry["arn"],
                        "policy_name": PERSONA_INLINE, "policy_sha256": policy_hash,
                    }, lesson="07")
                    created_any = True
                assert entry["name"] == role_name and entry["trusted_principal"] == trusted_principal
                assert entry["registry_arn"] == registry_entry["arn"] and entry["runtime_arn"] == runtime_entry["arn"]
                assert entry["policy_sha256"] == policy_hash and entry["policy_name"] == PERSONA_INLINE
                role = iam.get_role(RoleName=role_name)["Role"]
                assert role["Arn"] == entry["arn"] and role["AssumeRolePolicyDocument"] == TRUST
                assert not role.get("PermissionsBoundary"), "UNEXPECTED_PERSONA_BOUNDARY"
                tags = {tag["Key"]: tag["Value"] for tag in role["Tags"]}
                assert all(tags.get(key) == value for key, value in TAGS.items())
                attached = iam.list_attached_role_policies(RoleName=role_name)
                assert not attached["AttachedPolicies"] and not attached.get("IsTruncated")
                inline = iam.list_role_policies(RoleName=role_name)
                assert set(inline["PolicyNames"]) <= {PERSONA_INLINE} and not inline.get("IsTruncated")
                if PERSONA_INLINE not in inline["PolicyNames"]:
                    iam.put_role_policy(
                        RoleName=role_name, PolicyName=PERSONA_INLINE, PolicyDocument=json.dumps(document),
                    )
                    created_any = True
                actual = iam.get_role_policy(RoleName=role_name, PolicyName=PERSONA_INLINE)["PolicyDocument"]
                assert actual == document, "PERSONA_POLICY_CHANGED"
                persona_entries[name] = entry
                print({"persona": name, "role_arn": entry["arn"]})
            if created_any:
                time.sleep(10)
            """,
        ),
        *step(
            "Assumir as três personas e testar acesso real",
            "Cada sessão consulta o Registry. Somente Consumer pode consultar "
            "o Runtime; Publisher e Approver devem receber AccessDenied. "
            "A aula 08 testa publicação, aprovação, descoberta e invocação.",
            """
            for name, entry in persona_entries.items():
                assumed = sts.assume_role(
                    RoleArn=entry["arn"], RoleSessionName=NAME_PREFIX + "-" + name,
                    DurationSeconds=900,
                )
                credentials = assumed["Credentials"]
                session = boto3.Session(
                    aws_access_key_id=credentials["AccessKeyId"],
                    aws_secret_access_key=credentials["SecretAccessKey"],
                    aws_session_token=credentials["SessionToken"], region_name=REGION,
                )
                del credentials, assumed
                catalog = session.client("agent-registry-control").get_registry(
                    registryId=registry_entry["id"],
                )
                assert catalog["registryArn"] == registry_entry["arn"]
                print({"persona": name, "action": "GetRegistry", "decision": "ALLOW",
                       "request_id": catalog["ResponseMetadata"]["RequestId"]})
                try:
                    actual = session.client("bedrock-agentcore-control").get_agent_runtime(
                        agentRuntimeId=runtime_entry["id"],
                    )
                except ClientError as error:
                    assert name != "consumer", "CONSUMER_RUNTIME_ACCESS_REQUIRED"
                    assert error.response["Error"]["Code"] in {"AccessDeniedException", "AccessDenied"}
                    assert error.response["ResponseMetadata"]["HTTPStatusCode"] == 403
                    print({"persona": name, "action": "GetAgentRuntime", "decision": "DENY",
                           "request_id": error.response["ResponseMetadata"]["RequestId"]})
                else:
                    assert name == "consumer", "UNEXPECTED_PERSONA_RUNTIME_ACCESS"
                    assert actual["agentRuntimeArn"] == runtime_entry["arn"]
                    print({"persona": name, "action": "GetAgentRuntime", "decision": "ALLOW",
                           "request_id": actual["ResponseMetadata"]["RequestId"]})
            """,
        ),
        md("""
        ### Limites da matriz

        As três roles e as verificações existem na AWS. Estes testes cobrem
        AssumeRole e acesso de leitura. A aula 08 completa a matriz com
        publicação, aprovação, descoberta e invocação, incluindo negativas.
        O Developer usa a sessão do editor; não representa uma quarta
        persona isolada.

        A aula 99 remove somente estas roles depois de verificar seus hashes,
        trust policies e dependências. Nenhuma role do ambiente é alterada.
        """),
    ]
