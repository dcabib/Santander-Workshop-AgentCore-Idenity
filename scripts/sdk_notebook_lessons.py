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
            import uuid
            from pathlib import Path

            import boto3
            from IPython.display import display

            REGION = boto3.Session().region_name or "us-west-2"
            aws = boto3.Session(region_name=REGION)
            sts = aws.client("sts")
            identity = sts.get_caller_identity()
            ACCOUNT_ID = identity["Account"]
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
            })
            """,
        ),
    ]


def preflight():
    return [
        *context(),
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

        **Estado da revisão:** esta aula foi convertida para o novo formato.
        As demais aulas ainda estão sendo migradas; não execute a jornada inteira
        como se a conversão e o aceite AWS já estivessem concluídos.
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
        10–14 contém os cenários de múltiplas contas: consulte o requisito de cada
        cenário antes de executá-lo. Uma conta não simula uma fronteira entre contas.

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
    from scripts.sdk_cleanup_lesson import cleanup

    return build_sdk_notebook(
        "99_cleanup_sdk", "Remover os recursos criados pelas aulas SDK",
        [*context(), *cleanup()],
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


def build_sdk_notebook(name, title, cells):
    import hashlib

    import nbformat

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
            "migration_status": "IN_PROGRESS",
        },
    })
    notebook.cells = [
        md(f"""
        # {name[:2]} — {title}

        Vamos criar e configurar os serviços durante as aulas, observar as
        respostas da AWS e testar cada componente antes de avançar.

        Referência: [workshops AgentCore](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops).

        **Pré-requisitos:** uma conta AWS autorizada, região escolhida e o kernel
        **Santander Workshop (.venv)** preparado por `scripts/setup.sh`.
        Use seu ambiente de notebooks na AWS. Os serviços, ferramentas e agentes
        desta jornada executam na AWS.
        """),
        *cells,
    ]
    for index, cell in enumerate(notebook.cells):
        cell.id = hashlib.sha256(f"{name}:{index}:{cell.source}".encode()).hexdigest()[:16]
    return notebook
