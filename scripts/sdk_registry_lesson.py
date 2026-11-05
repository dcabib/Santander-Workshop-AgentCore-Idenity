"""Registry criado nas células; governança separada de descoberta e execução."""

from scripts.aws_notebook_lessons import md, step


def registry():
    return [
        md("""
        ### Um catálogo não concede acesso ao serviço catalogado

        `Publicação → revisão → aprovação → descoberta → autenticação no serviço`

        Vamos criar um Registry nesta conta, com descoberta autenticada por
        IAM e aprovação manual. As próximas aulas acrescentam as personas
        e os registros. Criar o catálogo não cria um Runtime nem concede
        permissão para invocá-lo.

        **Pré-requisito:** aula 00 e acesso às APIs Agent Registry na região.
        Uma conta basta. Esta aula não exige Cognito, configuração privada
        do instrutor ou um Registry anterior. A configuração de descoberta
        por IAM é uma escolha explícita; Cognito/Entra ID são alternativas
        de authorizer JWT, com suas próprias audiências e claims.
        """),
        *step(
            "Conferir os clientes de controle e descoberta",
            "O cliente agent-registry-control administra o catálogo. O cliente "
            "agent-registry consulta registros aprovados. Conferimos as "
            "operações disponíveis no SDK antes de criar o recurso.",
            """
            import time
            from botocore import UNSIGNED
            from botocore.config import Config
            from botocore.exceptions import ClientError

            registry_control = aws.client("agent-registry-control")
            registry_discovery = aws.client("agent-registry")
            for client, operations in (
                (registry_control, {"CreateRegistry", "GetRegistry", "ListTagsForResource", "ListRegistryRecords"}),
                (registry_discovery, {"ListDiscoverableRegistryRecords", "BatchGetDiscoverableRegistryRecord"}),
            ):
                missing = operations - set(client.meta.service_model.operation_names)
                assert not missing, "REGISTRY_SDK_OPERATIONS_MISSING: " + str(sorted(missing))
            print({"region": REGION, "discovery_authentication": "AWS_IAM", "approval": "MANUAL"})
            """,
        ),
        *step(
            "Criar o Registry com aprovação manual",
            "A lista vazia de autoApprovalRules exige aprovação dos registros. "
            "CreateRegistry retorna o ARN: extraímos o ID dessa resposta, "
            "guardamos ambos e aguardamos READY. A retomada exige o mesmo "
            "nome, tags, authorizer e configuração de aprovação.",
            """
            REGISTRY_NAME = NAME_PREFIX + "-registry"
            registry_entry = state.get("registry.instance")
            if registry_entry is None:
                created = registry_control.create_registry(
                    name=REGISTRY_NAME,
                    description="Workshop Santander: catalogo com revisao manual",
                    discoveryConfiguration={"authorizerType": "AWS_IAM"},
                    approvalConfiguration={"autoApprovalRules": []},
                    clientToken=str(uuid.uuid5(uuid.NAMESPACE_URL, NAME_PREFIX + ":registry")),
                    tags=TAGS,
                )
                registry_entry = state.record("registry.instance", {
                    "arn": created["registryArn"],
                    "id": created["registryArn"].rsplit("/", 1)[1],
                    "name": REGISTRY_NAME,
                }, lesson="06")
            deadline = time.monotonic() + 300
            while True:
                catalog = registry_control.get_registry(registryId=registry_entry["id"])
                if catalog["status"] == "READY":
                    break
                if catalog["status"] in {"CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED", "DELETING"}:
                    raise RuntimeError("REGISTRY_FAILED: " + catalog.get("statusReason", ""))
                if time.monotonic() >= deadline:
                    raise TimeoutError("REGISTRY_NOT_READY")
                time.sleep(5)
            assert catalog["registryArn"] == registry_entry["arn"]
            assert catalog["registryId"] == registry_entry["id"]
            assert catalog["name"] == registry_entry["name"] == REGISTRY_NAME
            assert catalog["discoveryConfiguration"] == {"authorizerType": "AWS_IAM"}
            assert not catalog.get("approvalConfiguration", {}).get("autoApprovalRules", [])
            assert catalog.get("autoDetection", {}).get("status", "INACTIVE") == "INACTIVE"
            tags = registry_control.list_tags_for_resource(resourceArn=registry_entry["arn"])["tags"]
            assert all(tags.get(key) == value for key, value in TAGS.items()), "REGISTRY_OWNERSHIP_MISMATCH"
            print({
                "registry_id": registry_entry["id"], "status": catalog["status"],
                "request_id": catalog["ResponseMetadata"]["RequestId"],
            })
            """,
        ),
        *step(
            "Consultar o catálogo e comprovar a autenticação",
            "A chamada assinada usa a identidade da sessão AWS. Fazemos também "
            "uma chamada sem assinatura: somente uma negativa de autenticação "
            "com Request ID AWS conta como resultado esperado. Um catálogo "
            "vazio recém-criado é normal; as aulas seguintes publicarão registros.",
            """
            records = []
            args = {"registryId": registry_entry["id"], "maxResults": 100}
            while True:
                page = registry_discovery.list_discoverable_registry_records(**args)
                records.extend(page["registryRecords"])
                if not page.get("nextToken"):
                    break
                args["nextToken"] = page["nextToken"]
            assert all(record["registryArn"] == registry_entry["arn"] for record in records)
            print({
                "discovery": "AUTHENTICATED", "records": len(records),
                "request_id": page["ResponseMetadata"]["RequestId"],
            })
            unsigned = aws.client("agent-registry", config=Config(signature_version=UNSIGNED))
            try:
                unsigned.list_discoverable_registry_records(registryId=registry_entry["id"])
            except ClientError as error:
                metadata = error.response["ResponseMetadata"]
                assert metadata["HTTPStatusCode"] in {401, 403}
                assert metadata["RequestId"]
                assert error.response["Error"]["Code"] in {
                    "AccessDeniedException", "UnauthorizedException",
                    "UnrecognizedClientException", "MissingAuthenticationTokenException",
                }, "EXPECTED_REGISTRY_AUTHENTICATION_DENIAL"
                print({
                    "anonymous_discovery": "DENY", "http_status": metadata["HTTPStatusCode"],
                    "request_id": metadata["RequestId"],
                })
            else:
                raise AssertionError("ANONYMOUS_REGISTRY_DISCOVERY_ALLOWED")
            """,
        ),
        md("""
        ### O que demonstramos

        O Registry foi criado durante a aula, está READY e exige IAM na
        descoberta. A aprovação automática permanece desativada.
        A descoberta autenticada foi exercitada e a chamada anônima foi negada.
        Isso ainda não comprova publicação, aprovação ou invocação de um agente.

        A aula 99 chama `DeleteRegistry` somente depois de verificar que
        não existem registros ou associações desconhecidas. Ao acrescentar
        registros nas aulas seguintes, a limpeza também precisa contemplá-los.
        """),
    ]
