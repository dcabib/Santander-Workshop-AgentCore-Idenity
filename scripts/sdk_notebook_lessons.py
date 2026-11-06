"""Células didáticas com chamadas SDK visíveis, sem implantação anterior."""

from scripts.aws_notebook_lessons import md, step


def context():
    return [
        *step(
            "Abrir uma sessão AWS e conferir a identidade",
            "O SDK usa a sessão autorizada do seu ambiente AWS. STS informa "
            "quem está executando e em qual conta. A região é uma escolha da "
            "aula; ajuste-a antes de criar recursos. Nenhuma chave deve ser "
            "colada no notebook.",
            """
            import json
            import os
            import uuid
            from pathlib import Path

            import boto3
            from IPython.display import display

            REGION = boto3.Session().region_name or "us-west-2"
            aws = boto3.Session(region_name=REGION)
            sts = aws.client("sts")
            identity = sts.get_caller_identity()
            ACCOUNT_ID = identity["Account"]
            expected_account = os.environ.get("WORKSHOP_EXPECTED_ACCOUNT")
            if expected_account and ACCOUNT_ID != expected_account:
                raise RuntimeError(
                    "WORKSHOP_ACCOUNT_MISMATCH: a sessão não corresponde à conta esperada."
                )
            PARTITION = identity["Arn"].split(":")[1]
            print({
                "account": ACCOUNT_ID,
                "region": REGION,
                "principal": identity["Arn"],
                "request_id": identity["ResponseMetadata"]["RequestId"],
            })
            """,
        ),
        *step(
            "Registrar identificadores desta execução",
            "As próximas aulas precisam lembrar os IDs retornados pelas chamadas "
            "de criação. Este registro contém apenas identificadores, está "
            "vinculado à conta/região e permite reiniciar o kernel. Ele é criado "
            "agora: você não precisa receber um arquivo privado do instrutor. "
            "O helper abaixo não chama AWS nem cria serviços.",
            """
            from santander_demo.notebook_state import NotebookState

            ROOT = next(
                path for path in [Path.cwd(), *Path.cwd().parents]
                if (path / "pyproject.toml").is_file()
            )
            state = NotebookState(
                ROOT / ".workshop", account_id=ACCOUNT_ID, region=REGION,
            )
            NAME_PREFIX = state.prefix
            TAGS = state.tags
            print({
                "execution": state.data["run_id"],
                "resource_name_prefix": NAME_PREFIX,
                "recorded_resources": sorted(state.data["resources"]),
                "execution_status": state.data.get("status", "ACTIVE"),
            })
            """,
        ),
    ]


def preflight():
    return [
        *context(),
        *step(
            "Iniciar ou retomar a execução desta conta efêmera",
            "Uma conta nova recebe seu próprio registro e nomes exclusivos. "
            "Não importamos IDs da conta anterior. Na mesma conta, retomamos "
            "os recursos existentes; após concluir a limpeza 99, arquivamos "
            "o registro e escolhemos novos nomes. Isso também evita colisão "
            "com segredos ainda na janela de recuperação de sete dias.",
            """
            if state.is_closed:
                archive = state.start_new_execution()
                NAME_PREFIX = state.prefix
                TAGS = state.tags
                print({"previous_execution_archive": str(archive.relative_to(ROOT))})
            print({
                "account": ACCOUNT_ID, "region": REGION,
                "execution": state.data["run_id"], "resource_name_prefix": NAME_PREFIX,
                "mode": "RESUME" if state.data["resources"] else "NEW",
            })
            """,
        ),
        md("""
        ### O que vamos construir durante as aulas

        | Componente | Criação e demonstração |
        |---|---|
        | IAM e Cognito | Roles, trust policies, usuários e clientes; autenticar a pessoa |
        | Gateway | Criar o Gateway, configurar o authorizer, adicionar targets e chamar ferramentas |
        | Runtime | Preparar o código, criar o Runtime na AWS, aguardar disponibilidade e invocar |
        | Identity | Separar identidade da pessoa, workload e autorização no serviço de destino |
        | Policy | Criar engine e políticas Cedar; observar permissões e negativas |
        | Registry | Criar personas, Registry e registros; publicar, aprovar e descobrir |
        | Memory e RAG | Criar recursos de memória e recuperação; testar isolamento e ACL |

        Os recursos são construídos progressivamente. Quando uma aula usa algo
        criado anteriormente, ela aponta a etapa de criação correspondente.
        Este notebook inicial não exige Gateway, Runtime ou stacks existentes.

        Uma conta efêmera exige repetir esta construção a cada novo evento.
        Confira o [roteiro de contas efêmeras](../docs/contas-efemeras.md):
        preparar kernel e sessão, criar os recursos nas aulas, testar,
        guardar evidências sem segredos e limpar antes do encerramento.

        **Jornada validada:** 00–09 e 15–16 constroem e testam os serviços por SDK
        em uma conta; a aula 99 encerra esse ciclo. As aulas 13–14 e 90–92 ainda são
        legadas, exigem quatro contas e estão pendentes de conversão e novo aceite.
        Não execute “Run All” na coleção inteira em uma conta única.
        """),
        *step(
            "Conferir o SDK que executará as chamadas",
            "Esta inspeção confere se a versão instalada conhece as APIs que "
            "vamos estudar. Ela não cria recursos nem comprova permissões, "
            "quotas ou disponibilidade do serviço na conta. Esses requisitos "
            "serão verificados na etapa que usa cada serviço.",
            """
            import importlib.metadata

            control = aws.client("bedrock-agentcore-control")
            needed = [
                "CreateGateway", "CreateGatewayTarget", "CreateAgentRuntime",
                "CreateMemory", "CreatePolicyEngine", "CreatePolicy",
            ]
            available = set(control.meta.service_model.operation_names)
            missing = [operation for operation in needed if operation not in available]
            if missing:
                raise RuntimeError(
                    "SDK incompatível com as aulas: " + ", ".join(missing)
                    + ". Execute scripts/setup.sh com o uv.lock do repositório."
                )
            print({
                "boto3": importlib.metadata.version("boto3"),
                "control_plane_operations": needed,
                "validation": "SDK_AVAILABLE",
            })
            """,
        ),
        md("""
        ### Permissões, região e contas

        A identidade exibida pelo STS precisa de autorização para criar e
        administrar os recursos das aulas, incluindo passar as roles de execução
        para os serviços AWS correspondentes. A criação de IAM não concede ao
        participante permissão para alterar a própria role ou contornar um Deny.

        Uma resposta `AccessDenied` deve ser examinada com o responsável pela
        conta. Trocar SDK, CLI ou ferramenta de implantação não remove uma
        restrição IAM. As permissões necessárias serão mostradas junto às
        operações; não é necessário usar uma role com um nome específico.

        A jornada de conta única corresponde às aulas 00–09 e 15–16. O bloco
        13–14 e 90–92 contém referências avançadas de múltiplas contas, sem código
        executável. Uma conta não simula uma fronteira entre contas.

        Região, disponibilidade do AgentCore, acesso ao modelo e quotas também
        fazem parte dos pré-requisitos. Credenciais válidas e SDK disponível não
        comprovam que toda a jornada funcionará nessa conta.
        """),
        md("""
        ### Cognito, Entra ID e fonte Databricks

        Criaremos os recursos Cognito nas aulas de autenticação. Os textos
        relacionam issuer, audiência, chaves públicas e claims aos conceitos de
        Entra ID. Consentimentos e OBO têm diferenças que serão explicadas;
        Cognito não será apresentado como uma implementação do OBO da Microsoft.

        A fonte Databricks desta demonstração é um simulador com dados sintéticos,
        hospedado na AWS. A aula de integração mostrará sua criação e suas
        limitações.

        ### Encerramento desta etapa

        Até aqui consultamos STS e inspecionamos o SDK. Nenhum serviço do workshop
        foi criado. O arquivo de identificadores foi iniciado para registrar a
        construção que ocorrerá nas próximas aulas.
        """),
    ]


def build_preflight():
    return build_sdk_notebook(
        "00_preflight", "Preparar a construção da solução na AWS", preflight(),
    )


def build_gateway():
    from scripts.sdk_gateway_lesson import gateway

    return build_sdk_notebook(
        "01_gateway_targets", "Criar Cognito, Lambda e AgentCore Gateway",
        [*context(), *gateway()],
    )


def build_cleanup():
    from textwrap import indent

    from scripts.sdk_cleanup_lesson import cleanup
    from scripts.sdk_rag_runtime_reset import reset

    cells = cleanup()
    check_index = next(index for index, cell in enumerate(cells)
                       if cell.cell_type == "code" and "supported =" in cell.source)
    cells[check_index].source = (
        'import os\n'
        'CLEANUP_SCOPE = os.environ.get("WORKSHOP_CLEANUP_SCOPE", "all")\n'
        'assert CLEANUP_SCOPE in {"all", "rag-runtime"}, "UNKNOWN_CLEANUP_SCOPE"\n'
        + cells[check_index].source
    )
    for cell in cells[check_index + 1:]:
        if cell.cell_type == "code":
            cell.source = (
                'if globals().get("CLEANUP_SCOPE", "all") == "all":\n'
                + indent(cell.source, "    ")
            )
    cells[check_index + 1:check_index + 1] = reset()

    return build_sdk_notebook(
        "99_cleanup_sdk", "Remover os recursos criados pelas aulas SDK",
        [*context(), *cells],
    )


def build_identity():
    from scripts.sdk_identity_lesson import identity

    return build_sdk_notebook(
        "02_identity_entra_obo", "Cognito: pessoa, aplicação e comparação com Entra ID",
        [*context(), *identity()],
    )


def build_runtime():
    from scripts.sdk_runtime_lesson import runtime

    return build_sdk_notebook(
        "03_identity_agente_mcp", "Runtime MCP e identidade IAM do workload",
        [*context(), *runtime()],
    )


def build_policy():
    from scripts.sdk_policy_lesson import policy

    return build_sdk_notebook(
        "04_policy_cedar", "Criar Policy Engine e testar decisões Cedar",
        [*context(), *policy()],
    )


def build_policy_authoring():
    from scripts.sdk_policy_authoring_lesson import authoring

    return build_sdk_notebook(
        "05_policy_autoria", "Gerar, revisar e observar um rascunho de política",
        [*context(), *authoring()],
    )


def build_registry():
    from scripts.sdk_registry_lesson import registry

    return build_sdk_notebook(
        "06_registry_governanca", "Criar o Registry e configurar a governança",
        [*context(), *registry()],
    )


def build_registry_personas():
    from scripts.sdk_registry_personas_lesson import personas

    return build_sdk_notebook(
        "07_registry_personas", "Criar personas e examinar suas permissões IAM",
        [*context(), *personas()],
    )


def build_registry_execution():
    from scripts.sdk_registry_execution_lesson import execution

    return build_sdk_notebook(
        "08_registry_descoberta_execucao", "Publicar, aprovar, descobrir e invocar na AWS",
        [*context(), *execution()],
    )


def build_integration():
    from scripts.sdk_integration_lesson import integration

    return build_sdk_notebook(
        "09_integracao_runtime_gateway_identity", "Integrar Runtime MCP, Gateway e identidades",
        [*context(), *integration()],
    )


def build_memory():
    from scripts.sdk_memory_lesson import memory

    return build_sdk_notebook(
        "15_ingestao_acl_memoria", "Memory por actor e autorização atual na fonte",
        [*context(), *memory()],
    )


def build_rag():
    from scripts.sdk_rag_lesson import rag

    return build_sdk_notebook(
        "16_rag_managed_identity_policy", "Criar RAG gerenciado com ACL nativa e geração no Runtime",
        [*context(), *rag()],
    )


def build_sdk_notebook(name, title, cells):
    import hashlib

    import nbformat

    from scripts.notebook_curriculum import enrich_notebook

    notebook = nbformat.v4.new_notebook()
    notebook.metadata.update({
        "kernelspec": {
            "display_name": "Santander Workshop (.venv)",
            "language": "python",
            "name": "santander-workshop",
        },
        "language_info": {"name": "python", "version": "3.12"},
        "workshop": {
            "execution": "AWS",
            "provisioning": "NOTEBOOK_SDK",
            "lab": name[:2],
            "required_count": 1,
            "migration_status": "SDK_IMPLEMENTED",
        },
    })
    notebook.cells = [
        md(f"""
        # {name[:2]} — {title}

        Comece pela arquitetura e pelos objetivos. Nas etapas executáveis,
        leia o código, observe a resposta da AWS e interprete as validações
        antes de avançar.

        Referência: [workshops AgentCore](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops).

        **Pré-requisitos:** uma conta AWS autorizada, região escolhida e o kernel
        **Santander Workshop (.venv)** preparado por `scripts/setup.sh`.
        Use seu ambiente de notebooks na AWS. Os serviços, ferramentas e agentes
        desta jornada executam na AWS.
        """),
        *cells,
    ]
    enrich_notebook(notebook, name)
    for index, cell in enumerate(notebook.cells):
        cell.id = hashlib.sha256(f"{name}:{index}:{cell.source}".encode()).hexdigest()[:16]
    return notebook
