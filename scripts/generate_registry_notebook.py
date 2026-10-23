"""Notebook 07: autoria, publicação, aprovação e consumo da mesma capacidade."""

import base64
import subprocess
from pathlib import Path
from textwrap import dedent

import nbformat as nb

from scripts.generate_diagrams import Diagram, write_gallery
from scripts.notebook_cleanup import cleanup_cells
from scripts.notebook_learning import learning_cell

ROOT = Path(__file__).resolve().parents[1]


def md(value):
    return nb.v4.new_markdown_cell(dedent(value).strip())


def code(value):
    return nb.v4.new_code_cell(dedent(value).strip())


def diagrams():
    folder = ROOT / "docs/registry"
    folder.mkdir(exist_ok=True)
    pages = [
        (
            "arquitetura",
            "Uma capacidade, quatro responsabilidades",
            "Do código testado ao catálogo aprovado e à chamada autorizada.",
            [
                (
                    "Desenvolvedor",
                    ["Implementa MCP e agente", "Testa código e descritores"],
                    "code",
                    "local",
                ),
                ("Publicador", ["Cria DRAFT", "Submete à revisão"], "document", "registry"),
                ("Aprovador", ["Confere bundle e hash", "Aprova ou rejeita"], "check", "policy"),
                (
                    "Consumidor",
                    ["Descobre MCP e AGENT", "Valida destino e executa"],
                    "search",
                    "identity",
                ),
            ],
            "Aprovação publica metadados. IAM continua autorizando cada chamada.",
        ),
        (
            "fronteiras",
            "Catálogo e execução têm portas diferentes",
            "O Registry descreve a capacidade; a role do chamador controla seu uso.",
            [
                ("Registry", ["Busca e leitura: IAM", "Somente APPROVED"], "search", "registry"),
                ("Consumidor", ["Confere ARN e versão", "InvokeAgentRuntime"], "user", "identity"),
                ("Runtime", ["Agente determinístico", "Sessão MCP + SigV4"], "agent", "gateway"),
                (
                    "Gateway + Lambda",
                    ["InvokeGateway: IAM", "Fixture C001 → baixo"],
                    "lambda",
                    "allow",
                ),
            ],
            "Sem InvokeAgentRuntime, a pessoa encontra o agente e recebe AccessDenied ao usá-lo.",
        ),
    ]
    for name, title, subtitle, boxes, takeaway in pages:
        d = Diagram(
            {
                "id": "07_registry_personas",
                "title": title,
                "subtitle": subtitle,
                "status": "LOCAL + AWS · PAPÉIS SEPARADOS",
                "takeaway": takeaway,
                "description": title + ". " + subtitle,
            }
        )
        for i, (label, lines, icon, color) in enumerate(boxes):
            x = 64 + 382 * i
            d.node(x, 270, 326, 205, label, lines, color, icon)
            if i < 3:
                d.arrow([(x + 327, 370), (x + 382, 370)], color)
        d.panel(
            64,
            550,
            1472,
            233,
            "OBSERVE AS FRONTEIRAS",
            "Uma identidade não herda automaticamente as permissões da outra.",
            "local",
        )
        if name == "arquitetura":
            d.text(96, 655, "DRAFT → PENDING_APPROVAL → APPROVED ou REJECTED", 27, "#087f82", 700)
            d.text(
                96,
                719,
                "Publicação e aprovação: stacks separados, providers com roles distintas.",
                25,
                "#415571",
            )
        else:
            d.text(
                96,
                655,
                "Catálogo: ler metadados    |    Runtime: invocar agente    |    Gateway: chamar ferramenta",
                24,
                "#087f82",
                700,
            )
            d.text(
                96,
                719,
                "Sessão STS limitada à descoberta: busca permitida, execução negada.",
                25,
                "#415571",
            )
        svg = folder / (name + ".svg")
        svg.write_text(d.finish())
        subprocess.run(
            [
                "rsvg-convert",
                "-w",
                "2400",
                "-h",
                "1500",
                "-o",
                str(folder / (name + ".png")),
                str(svg),
            ],
            check=True,
        )


def image(name, caption):
    data = base64.b64encode((ROOT / "docs/registry" / (name + ".svg")).read_bytes()).decode()
    c = md(f"![{caption}](attachment:{name}.svg)")
    c.attachments = {name + ".svg": {"image/svg+xml": data}}
    return c


def build_notebook():
    cells = [
        md("""
        # 07 — Do desenvolvimento ao consumo: quatro personas no Registry

        No 06 aprendemos os estados do catálogo. Agora acompanharemos uma entrega
        completa: **um MCP de consulta de risco e um agente que usa esse MCP**.
        Cada pessoa tem uma responsabilidade, uma entrega e uma fronteira de acesso.
        No 08 aplicaremos a descoberta ao supervisor de Riscos e Fraude.

        **Duração:** 60–90 minutos, além do provisionamento opcional.
        **Pré-requisitos:** notebooks 01 e 06; Python, MCP e noções de IAM.
        **Ao terminar:** explicar quem desenvolve, publica, aprova e consome;
        distinguir MCP de AGENT e comprovar que descobrir não autoriza executar.

        Toda a narrativa e os dados são sintéticos. **Run All funciona localmente**;
        a parte AWS permanece desativada. Consulte o
        [guia do laboratório](../docs/registry/README.md) para implantação, limites
        e resultados verificados. Os notebooks de origem não guardam outputs.
        """),
        learning_cell("07"),
        image("arquitetura", "Quatro personas: do código à descoberta da capacidade"),
        md("""
        ## 1. Definir as responsabilidades

        | Persona | Entrega | Permissão AWS no laboratório |
        |---|---|---|
        | Desenvolvedor do MCP/agente | Código, testes e bundle de descritores | Invocar Runtime e Gateway para testar; sem escrita no catálogo |
        | Publicador | Registros MCP e AGENT em DRAFT e depois PENDING_APPROVAL | Criar, submeter e remover registros da bancada; sem aprovar |
        | Aprovador | Decisão sobre o conteúdo revisado | Ler e mudar status; sem criar registros |
        | Consumidor | Descoberta e chamada ao agente | Listar, buscar e ler aprovados; invocar o Runtime autorizado |

        **Modelo local:** strings representam papéis; isso não prova IAM.
        **AWS:** roles reais e sessões temporárias STS. Publicação e aprovação
        acontecem em funções diferentes, acionadas pelos stacks CloudFormation.
        O operador do sandbox orquestra o pipeline com o perfil `default`;
        não há quatro logins humanos nem uma interface de aprovação neste exercício.
        Em uma equipe, a permissão de acionar cada fase do pipeline também precisa
        ser separada. O administrador do sandbox continua mais privilegiado.
        """),
        md("""
        ### Preparar a bancada e os controles de execução

        `RUN_AWS` habilita leituras e invocações reais. `RUN_PIPELINE` habilita
        as fases IaC; depende de `RUN_AWS`. Para usar a AWS, leia antes a seção 3,
        revise os templates e execute as células em ordem, observando cada estado.
        Recomeçar esta célula reinicia apenas o modelo local.
        """),
        code("""
        import copy
        import json
        import subprocess
        import sys
        from pathlib import Path

        from santander_demo.registry_workflow.contracts import (
            LOCAL_GATEWAY, LOCAL_RUNTIME, LocalLifecycle, bundle, digest, risk, validate_agent,
        )

        ROOT = Path.cwd()
        if not (ROOT / "pyproject.toml").exists():
            ROOT = ROOT.parent
        RUN_AWS = False
        RUN_PIPELINE = False
        assert not RUN_PIPELINE or RUN_AWS
        flow = LocalLifecycle()
        packages = bundle()
        registry_lab = None

        def expect_denial(operation, expected):
            try:
                operation()
            except (PermissionError, ValueError) as error:
                assert str(error) == expected, str(error)
                print({"negative_case": expected, "status": "PASS"})
            else:
                raise AssertionError("A operação deveria ter sido recusada")

        print({"mode": "LOCAL_CONTRACT", "aws_enabled": RUN_AWS})
        """),
        md("""
        ## 2. Desenvolvedor — construir e testar a capacidade

        A ferramenta `consultar_risco` aceita apenas `C001` ou `C002`. O agente
        é **determinístico**: chama uma ferramenta e compõe a resposta, sem LLM.
        Assim, as provas de governança não dependem de decisões probabilísticas.
        O notebook 09 acrescentará inferência Bedrock em outro cenário.

        Veja o [backend e os contratos](../src/santander_demo/registry_workflow/contracts.py)
        e o [agente HTTP](../src/santander_demo/registry_workflow/runtime.py).
        Esta célula testa a regra local e inspeciona o bundle. O teste AWS final
        verifica o percurso Runtime → MCP/Gateway → Lambda.

        O registro **MCP** descreve o servidor, o transporte e o schema da ferramenta.
        O registro **AGENT** usa um descritor `custom` com ARN, protocolo HTTP,
        autenticação IAM e dependência do MCP. Não é um AgentCard A2A:
        anunciar outro protocolo seria incompatível com o código.
        """),
        code("""
        assert risk({"customer_id": "C001"})["risk"] == "baixo"
        assert risk({"customer_id": "C002"})["risk"] == "alto"
        for kind, package in packages.items():
            print({"type": kind, "name": package["name"], "version": package["recordVersion"],
                   "descriptor": next(iter(package["descriptors"])), "sha256": digest(package)})
        expect_denial(lambda: flow.publish("desenvolvedor", packages["AGENT"]), "PUBLISH_DENIED")
        """),
        md("""
        ## 3. Preparar o ambiente AWS opcional

        O percurso **local** continua sem conta AWS. Para o percurso gerenciado,
        usamos **uma conta**, perfil **default**, região **us-east-1**, sem Entra.
        O ambiente é independente dos notebooks 06 e 08.

        No terminal, na raiz:

        ```bash
        uv sync --frozen --extra banking
        uv run python -m infra.registry_workflow.generate
        uv run cfn-lint infra/registry_workflow/templates/*.json
        uv run python scripts/build_artifacts.py --banking
        uv run python scripts/registry_deploy.py bootstrap
        uv run python scripts/registry_deploy.py bootstrap --execute
        uv run python scripts/registry_deploy.py foundation
        uv run python scripts/registry_deploy.py foundation --execute
        ```

        Sem `--execute`, o wrapper prepara um **change set**. Revise-o antes de
        aplicar. `foundation` cria Registry, Lambda, Gateway IAM, Runtime e roles.
        O código ARM64 é enviado ao bucket privado pelo próprio pipeline.
        As APIs do Registry são encapsuladas em custom resources com
        Create/Update/Delete; não há SDK de escrita nas células do notebook.

        A AWS usa agora os clientes `agent-registry-control` e `agent-registry`.
        O namespace preview `bedrock-agentcore` do Registry tem descontinuação
        anunciada para 30/10/2026. Leia o
        [guia de migração](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry-faq.html).
        O arquivo `config/local.registry.json` é gerado pelo wrapper e ignorado no Git.
        """),
        md("""
        ### Conectar a bancada ao pipeline

        A função abaixo só aplica uma fase se você habilitou `RUN_PIPELINE`.
        `RUN_AWS=True` com `RUN_PIPELINE=False` permite inspecionar uma fase já
        implantada; nesse caso, execute apenas as células compatíveis com o estado
        atual. Uma publicação já aprovada não volta a DRAFT ao reabrir o notebook.
        """),
        code("""
        def pipeline(phase, review_file=None):
            if RUN_PIPELINE:
                command = [sys.executable, "scripts/registry_deploy.py", phase, "--execute"]
                if review_file:
                    command += ["--review", str(review_file)]
                subprocess.run(command, cwd=ROOT, check=True)
            else:
                print({"pipeline_phase": phase, "status": "NOT_RUN"})

        if RUN_AWS:
            from santander_demo.registry_workflow.client import RegistryLab
            registry_config = json.loads((ROOT / "config/local.registry.json").read_text())
            registry_lab = RegistryLab(registry_config)
            packages = bundle(registry_config["GatewayUrl"], registry_config["RuntimeArn"])
            print({"mode": "AWS_CONNECTED", "region": registry_config["region"]})
        """),
        md("""
        ## 4. Publicador — registrar os dois rascunhos

        A publicação preserva nome, versão, descrição e descritores do bundle.
        DRAFT permite revisão, mas ainda não torna a capacidade descobrível.
        Nesta bancada as versões são imutáveis; em uma evolução, publique outra
        versão. Essa é uma escolha do laboratório, não uma restrição geral da API.

        O Registry armazena **metadados**, não o ZIP do código. Os artefatos do
        Runtime e da Lambda pertencem à infraestrutura, e o registro aponta para
        o destino. Publicar metadados não implanta código novo.
        """),
        code("""
        keys = {kind: flow.publish("publicador", package) for kind, package in bundle().items()}
        assert flow.discover() == []
        print({kind: flow.records[key]["status"] for kind, key in keys.items()})
        pipeline("publish")
        if RUN_AWS:
            registry_config = json.loads((ROOT / "config/local.registry.json").read_text())
            registry_lab = RegistryLab(registry_config)
            assert registry_lab.states() == {"Mcp": "DRAFT", "Agent": "DRAFT"}
            assert registry_lab.discover() == []
            print({"aws_drafts_hidden": "PASS"})
        """),
        md("""
        ## 5. Publicador — submeter, sem aprovar a própria entrega

        A submissão muda DRAFT para PENDING_APPROVAL. O aprovador pode ler o
        candidato pelo plano de controle; o consumidor continua sem encontrá-lo.
        A tentativa local de aprovar como publicador deve falhar.
        A matriz IAM adiante verifica essa mesma separação nas políticas reais.
        """),
        code("""
        for key in keys.values():
            flow.submit("publicador", key)
        expect_denial(
            lambda: flow.review("publicador", keys["AGENT"], "APPROVED", digest(bundle()["AGENT"])),
            "REVIEW_DENIED",
        )
        assert flow.discover() == []
        pipeline("submit")
        if RUN_AWS:
            assert registry_lab.states() == {"Mcp": "PENDING_APPROVAL", "Agent": "PENDING_APPROVAL"}
            assert registry_lab.discover() == []
            print({"aws_pending_hidden": "PASS"})
        """),
        md("""
        ## 6. Aprovador — revisar o contrato e decidir

        Confira: tipo de registro, versão, schema, endpoint/ARN, autenticação e
        dependência do MCP. O SHA-256 identifica o bundle exato revisado; não
        comprova sozinho a segurança do agente. Os testes e a revisão do código
        continuam necessários.

        Em `build/registry-bundle.json`, confira os metadados antes de copiar
        `build/registry-review-candidate.json` para `build/registry-review.json`.
        Esse arquivo contém dois digests e duas decisões, `APPROVED` ou `REJECTED`.
        A célula AWS exige esse arquivo previamente revisado. O provider lê o
        registro novamente e recusa a decisão se o hash divergir.

        Aqui aprovamos os dois registros para seguir com a execução. O caso de
        rejeição será exercitado localmente na seção 9.
        """),
        code("""
        for kind, key in keys.items():
            flow.review("aprovador", key, "APPROVED", digest(bundle()[kind]))
        print({kind: flow.records[key]["status"] for kind, key in keys.items()})
        review_path = ROOT / "build/registry-review.json"
        if RUN_PIPELINE:
            assert review_path.is_file(), "Revise o bundle e prepare build/registry-review.json"
        pipeline("approve", review_path)
        if RUN_AWS:
            assert registry_lab.states() == {"Mcp": "APPROVED", "Agent": "APPROVED"}
            print({"aws_approval": "PASS"})
        """),
        image("fronteiras", "Separação entre descoberta no Registry e autorização de execução"),
        md("""
        ## 7. Consumidor — descobrir e conferir antes de usar

        No modelo local, `discover()` lista somente os aprovados. Na AWS usamos
        `ListDiscoverableRegistryRecords` com paginação e
        `BatchGetDiscoverableRegistryRecord` para obter descritores.
        Uma página vazia com `nextToken` não encerra a paginação. Respostas batch
        podem ter erros parciais mesmo com HTTP 200; o cliente falha nesse caso.

        A busca semântica `SearchDiscoverableRegistryRecords` serve para procurar
        por intenção. A listagem é usada no teste para não depender do ranking.
        Busca/listagem autorizam no nível do catálogo; não use uma proibição de
        leitura de registro individual como garantia de ocultação dos metadados.
        Veja as [regras de descoberta IAM](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/registry-iam-permissions.html).

        Antes de invocar, compare o descritor com ARN, versão e Gateway esperados.
        O consumidor nunca aceita um destino arbitrário só porque veio do catálogo.
        """),
        code("""
        records = flow.discover()
        assert {record["recordType"] for record in records} == {"MCP", "AGENT"}
        agent_record = next(record for record in records if record["recordType"] == "AGENT")
        assert validate_agent(agent_record, gateway_url=LOCAL_GATEWAY,
                              runtime_arn=LOCAL_RUNTIME, version="1.0.0") == LOCAL_RUNTIME
        print([{"name": record["name"], "type": record["recordType"], "status": record["status"]}
               for record in records])
        """),
        md("""
        ## 8. Consumidor — encontrar não significa poder executar

        Primeiro mantemos a descoberta e retiramos a permissão de invocar. O
        resultado esperado é recusa, sem chamada ao backend local. Depois
        autorizamos a execução e esperamos `C001 → baixo`.

        Na AWS, `acceptance()` assume a role Consumer com uma **session policy**
        que permite apenas descoberta. Políticas de sessão restringem as
        permissões da role; não acrescentam privilégios. A busca deve funcionar
        e `InvokeAgentRuntime` deve retornar `AccessDeniedException`.
        Com a sessão normal, a chamada percorre Runtime → Gateway IAM → Lambda.
        A indexação do catálogo é assíncrona; o teste aguarda por até 120 segundos.

        A matriz `SimulatePrincipalPolicy` é uma verificação de políticas, não
        uma tentativa real de escrita proibida, nem uma prova de todos os efeitos
        de SCPs. Não fazemos chamadas create/update avulsas para testar recusas.
        """),
        code("""
        expect_denial(lambda: flow.execute(agent_record, {"customer_id": "C001"}, can_invoke=False),
                      "INVOKE_DENIED")
        assert flow.calls == 0
        result = flow.execute(agent_record, {"customer_id": "C001"}, can_invoke=True)
        assert result["result"] == {"customer_id": "C001", "risk": "baixo"}
        print({"mode": "LOCAL_CONTRACT", "result": result})
        if RUN_AWS:
            print(registry_lab.acceptance())
        else:
            print({"mode": "AWS_LIVE", "status": "NOT_RUN"})
        """),
        md("""
        ## 9. Exercitar rejeição e mudança de conteúdo

        Este ramo é **local**. Criamos a versão 1.1.0, demonstramos que um hash
        desatualizado impede a aprovação e depois rejeitamos o candidato.
        A versão 1.0.0 continua descobrível. Isso não testa atualizações de revisão
        na AWS: o serviço também permite editar registros e manter a revisão
        anteriormente aprovada disponível enquanto a nova é avaliada.

        Por fim, alteramos o ARN no descritor copiado. A validação deve recusar
        o destino antes de enviar credenciais ou executar qualquer código.
        """),
        code("""
        rejected = bundle(version="1.1.0")["AGENT"]
        rejected_key = flow.publish("publicador", rejected)
        flow.submit("publicador", rejected_key)
        expect_denial(lambda: flow.review("aprovador", rejected_key, "APPROVED", "stale"),
                      "REVIEW_CHANGED")
        flow.review("aprovador", rejected_key, "REJECTED", digest(rejected))
        assert all(record["recordVersion"] == "1.0.0" for record in flow.discover())
        changed = copy.deepcopy(agent_record)
        changed["descriptors"]["custom"]["data"] = '{"runtimeArn":"untrusted"}'
        expect_denial(lambda: validate_agent(changed, gateway_url=LOCAL_GATEWAY,
                                             runtime_arn=LOCAL_RUNTIME, version="1.0.0"),
                      "UNTRUSTED_AGENT_DESCRIPTOR")
        """),
        md("""
        ## 10. O que aprendemos e como verificar

        Explique a outra pessoa:

        1. Por que MCP e AGENT são dois registros, embora pertençam à mesma solução?
        2. Qual é a diferença entre submeter, aprovar e conceder `InvokeAgentRuntime`?
        3. O que o hash da revisão protege, e o que ele não verifica?
        4. Por que um administrador que orquestra todas as fases não representa
           uma separação completa de funções humanas?
        5. Se o endpoint anunciado mudar, onde a chamada deve ser interrompida?

        Para repetir as verificações:

        ```bash
        uv run pytest tests/test_registry_workflow.py -q
        uv run python scripts/registry_check.py --live
        ```

        O segundo comando exige a implantação aprovada e grava um relatório
        sanitizado em `evidence/registry-personas.json`. Não executa deploy.
        Continue no [08 — Descoberta e execução](08_registry_descoberta_execucao.ipynb):
        o supervisor compõe capacidades e a Policy decide cada chamada.
        """),
        *cleanup_cells("07", "registry_workflow"),
    ]
    for i, cell in enumerate(cells):
        cell.id = f"registry-personas-{i:03d}"
    return nb.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3 (.venv)",
                "language": "python",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "santander": {"local_validation_mode": "LOCAL_REGISTRY_LIFECYCLE"},
        },
    )


def main():
    diagrams()
    notebook = build_notebook()
    nb.validate(notebook)
    nb.write(notebook, ROOT / "notebooks/07_registry_personas.ipynb")
    write_gallery()


if __name__ == "__main__":
    main()
