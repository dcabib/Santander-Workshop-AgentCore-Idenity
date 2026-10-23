"""Notebooks 14/15 e diagramas incorporados; geração inteiramente local."""

import base64
import subprocess
from pathlib import Path

import nbformat as nb
from generate_banking_notebook import code, md
from generate_diagrams import TINT, C, Diagram, write_gallery
from notebook_cleanup import cleanup_cells
from notebook_learning import learning_cell

ROOT = Path(__file__).resolve().parents[1]


def compact(d, x, y, w, title, subtitle, tone, icon):
    d.rect(x, y, w, 90, stroke=C["border"], shadow=True)
    d.rect(x + 14, y + 21, 48, 48, TINT[tone], radius=12)
    d.icon(x + 23, y + 30, icon, C[tone], 30)
    d.text(x + 78, y + 35, title, 22, weight=700)
    d.text(x + 78, y + 63, subtitle, 17, C["muted"])


def diagram(knowledge=False):
    if knowledge:
        page = {
            "id": "15_ingestao_acl_memoria",
            "title": "Conhecimento compartilhado. Acesso individual.",
            "subtitle": "Um contrato de ingestão; ACL revalidada no retrieval e na memória.",
            "status": "INGESTÃO · EXERCÍCIO LOCAL",
            "takeaway": "Indexar juntos não significa conceder o mesmo acesso a todos.",
            "description": "Conectores, BDA, OpenSearch/KB e Memory AWS são a arquitetura proposta. O notebook executa o contrato local de ciclo de vida, ACL e memória.",
        }
        d = Diagram(page)
        for y, title in [
            (262, "SharePoint"),
            (392, "Databricks Silver/Gold"),
            (522, "SQL on-prem"),
            (652, "APIs e backends AWS"),
        ]:
            compact(
                d, 64, y, 420, title, "Fonte + versão + ACL do proprietário", "azure", "database"
            )
            d.arrow([(484, y + 45), (545, y + 45), (545, 456), (610, 456)], "azure")
        d.node(
            610,
            358,
            370,
            196,
            "Indexador comum",
            ["Discover · register", "Update · delete", "Markdown + metadados ACL"],
            "gateway",
            "gateway",
        )
        d.tag(610, 585, 370, "BDA / KB / índice: desenho cloud", "local", height=42, size=17)
        d.node(
            1110,
            274,
            420,
            169,
            "Retrieval autorizado",
            ["Grupos vindos do IdP", "Fonte e versão na resposta"],
            "policy",
            "shield",
        )
        d.node(
            1110,
            552,
            420,
            169,
            "Memória por usuário",
            ["Referências a documentos", "Revalida ACL e exclusões"],
            "registry",
            "catalog",
        )
        d.arrow([(980, 420), (1046, 420), (1046, 358), (1110, 358)], "policy")
        d.arrow([(1320, 443), (1320, 552)], "registry")
        folder = ROOT / "docs/ingestao"
    else:
        page = {
            "id": "14_cenario_santander_integrado",
            "title": "Uma chamada entre áreas, até a fonte.",
            "subtitle": "Conta A → conta central → conta B → Databricks Azure, com identidade humana.",
            "status": "CENÁRIO INTEGRADO · ENSAIO CLOUD PENDENTE",
            "takeaway": "No hub, azp distingue os agentes. Unity Catalog aplica os grants do usuário.",
            "description": "Três Gateways e três Policies; Identity em cada troca OBO. Agentes hospedados na origem consultam o Registry central antes de executar uma capacidade.",
        }
        d = Diagram(page)
        compact(
            d,
            64,
            219,
            460,
            "Usuário + notebook",
            "Login Entra · nenhuma identidade no prompt",
            "identity",
            "laptop",
        )
        d.panel(64, 338, 460, 465, "CONTA A · ORIGEM", "", "gateway")
        d.panel(574, 338, 450, 465, "CONTA CENTRAL", "", "registry")
        d.panel(1074, 338, 460, 286, "CONTA B · DADOS", "", "gateway")
        compact(
            d, 88, 401, 412, "Gateway da origem", "Entrada dos dois agentes", "gateway", "gateway"
        )
        d.tag(88, 521, 412, "Policy local + Identity OBO", "policy", height=40, size=18)
        d.node(
            88,
            606,
            412,
            161,
            "2 agentes em Runtime",
            ["Riscos e Fraude", "Um app Entra por agente"],
            "identity",
            "agent",
        )
        d.node(
            598,
            401,
            402,
            161,
            "Gateway central",
            ["Cedar: usuário + agente + tool", "Somente SQL canário aprovado"],
            "gateway",
            "gateway",
        )
        d.tag(598, 579, 402, "Identity OBO → audiência Dados", "identity", height=40, size=18)
        compact(
            d,
            598,
            671,
            402,
            "Registry governado",
            "Owner · versão · instância · aprovação",
            "registry",
            "catalog",
        )
        compact(
            d,
            1098,
            401,
            412,
            "Gateway de dados",
            "Confia no hub; aplica Policy local",
            "gateway",
            "gateway",
        )
        d.tag(1098, 521, 412, "Identity → token do usuário", "identity", height=40, size=18)
        d.panel(1074, 667, 460, 136, "AZURE · FONTE", "", "azure")
        d.text(1100, 735, "Databricks MCP DBSQL", 23, weight=700)
        d.text(1100, 770, "Unity Catalog · grants por pessoa", 20, C["muted"])
        d.arrow([(460, 309), (460, 401)], "identity")
        d.arrow([(294, 491), (294, 521)], "identity")
        d.arrow([(294, 561), (294, 606)], "identity")
        d.arrow([(500, 648), (549, 648), (549, 476), (598, 476)], "identity")
        d.arrow([(1000, 476), (1098, 476)], "identity")
        d.arrow([(1304, 491), (1304, 521)], "identity")
        d.arrow([(1304, 561), (1304, 667)], "identity")
        d.label(1304, 642, "RFC 8693 · sem fallback M2M", "identity", 17)
        d.arrow([(500, 722), (598, 722)], "registry", dashed=True)
        folder = ROOT / "docs/journey"
    folder.mkdir(parents=True, exist_ok=True)
    svg, png = folder / "arquitetura.svg", folder / "arquitetura.png"
    svg.write_text(d.finish().replace("12 / 09", "LAB 14").replace("13 / 09", "LAB 15"))
    subprocess.run(
        ["rsvg-convert", "-w", "2400", "-h", "1500", "-o", str(png), str(svg)], check=True
    )
    return png


def picture(path, label):
    return nb.v4.new_markdown_cell(
        f"![{label}](attachment:arquitetura.png)\n\n[Ampliar imagem](../{path.relative_to(ROOT)})",
        attachments={
            "arquitetura.png": {"image/png": base64.b64encode(path.read_bytes()).decode()}
        },
    )


def save(name, cells, mode):
    cells.insert(2, learning_cell(name))
    notebook = nb.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3 (.venv)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.13"},
            "santander": {"local_validation_mode": mode},
        },
    )
    nb.write(notebook, ROOT / "notebooks" / (name + ".ipynb"))


def main():
    png = diagram()
    cells = [
        md("""
        # 14 — Santander: agente de uma área → hub → outra área → Databricks

        Depois de estudar Gateways por conta e identidade na fonte, vamos compor
        esses controles numa mesma chamada. Consulte a
        [jornada de aprendizagem](../docs/jornada.md) para retomar os pré-requisitos.

        Dois agentes **hospedados em Runtime na conta A** usam aplicações Entra
        diferentes. A conta central autoriza por usuário, agente e tool. A conta B
        publica o MCP Databricks e aplica sua própria Policy; a fonte aplica os
        grants reais de cada pessoa. Cada conta tem seu Gateway.

        O agente usa um fluxo determinístico para tornar os testes repetíveis.
        O notebook 11 exercita Strands/LLM; aqui isolamos a autorização. Veja as
        [responsabilidades de cada componente](../docs/journey/arquitetura.md).

        **Padrão:** local; valida Cedar e gera IaC. **Cloud:** opt-in, após os
        pré-requisitos do [runbook](../docs/journey/README.md). Resultado local
        não comprova OBO nem Unity Catalog.
        """),
        picture(png, "Três contas, agentes na origem e MCP Databricks"),
        md("""
        ## 1. Preparação

        Selecione `.venv/bin/python` após `uv sync --frozen --extra banking`.
        A célula localiza o projeto e define os controles. `RUN_AWS=False` não usa
        perfis AWS. `DEPLOY_PHASE=None` seleciona ensaio; uma fase seleciona
        preparação de parâmetros. `RUN_PIPELINE=False` não executa o wrapper.
        """),
        code("""
        import json
        import subprocess
        from pathlib import Path
        from IPython.display import display
        from santander_demo.journey.spec import local_matrix
        from santander_demo.journey.client import (
            PHASES, load_config, aws_sessions, prepare_phase, preflight, login, run_case,
        )
        from santander_demo.journey.evidence import acceptance
        from santander_demo.governance import local_quota_demo

        ROOT = Path.cwd()
        if not (ROOT / "pyproject.toml").exists():
            ROOT = ROOT.parent
        RUN_AWS = False
        DEPLOY_PHASE = None
        RUN_PIPELINE = False
        APPLY_CHANGESET = False
        CONFIG_PATH = ROOT / "config/local.journey.json"
        LIVE = RUN_AWS and DEPLOY_PHASE is None
        rows = []
        print("AWS opt-in" if RUN_AWS else "LOCAL: AWS / Entra / Databricks = NOT_RUN")
        """),
        md("""
        ## 2. Mesma pessoa, agentes diferentes

        Vamos executar o mesmo Cedar usado no IaC. Observe:

        * Riscos → tool Riscos permite; Fraude → tool Riscos nega.
        * Usar a tool Riscos com SQL da tabela Fraude também nega.
        * Usuário B passa Policy. Quem nega seu SELECT é o Unity Catalog, no ensaio.
        * O Gateway de dados recusa um caller que não seja a plataforma.

        A matriz é **LOCAL_CEDAR_ONLY**, sem respostas sintéticas atribuídas à AWS.
        """),
        code("""
        matrix = local_matrix()
        display(matrix)
        assert [r["decision"] for r in matrix["cases"]] == [
            "ALLOW", "DENY", "DENY", "ALLOW", "ALLOW", "DENY", "DENY", "DENY",
        ], "As oito decisões precisam corresponder aos casos descritos"
        """),
        md("""
        ## 3. Infraestrutura reproduzível

        A célula gera dez templates, sem acessar a nuvem. Há três Gateways,
        três engines Policy, dois Runtimes de agente e um Registry central.
        Os providers Identity são locais a cada conta; cada agente tem um provider
        OBO próprio. Workload identities também pertencem ao CloudFormation.

        O modo nativo sem autenticação de cliente do Databricks precisa estar
        habilitado pela AWS na conta/região; não basta definir um booleano.
        O [sample AWS fixado](../docs/journey/README.md#referências) explica essa
        dependência. Não use M2M como substituto silencioso.
        """),
        code("""
        subprocess.run(["uv", "run", "--extra", "banking", "python", "infra/journey/generate.py"], cwd=ROOT, check=True)
        templates = sorted(p.name for p in (ROOT / "infra/journey/templates").glob("*.json"))
        display(templates)
        assert len(templates) == 10
        """),
        md("""
        ## 4. Preparar fases do IaC ou conferir o ambiente implantado

        Primeiro siga o runbook: identidades Entra, federation de **usuários no
        nível da conta Databricks**, membership de A/B no workspace, grants
        distintos nas tabelas canário e build do artefato.

        Para implantar, escolha uma das `PHASES`, habilite `RUN_AWS` e reexecute
        desde a preparação. O helper consulta outputs e escreve parâmetros locais.
        Revise o comando/change set antes de habilitar sua execução. `registry`
        deixa registros pendentes; `approve-registry` é uma promoção separada.
        Para ensaiar depois da implantação, volte `DEPLOY_PHASE=None`.

        A célula seguinte não implanta nada no padrão. O preflight cloud verifica
        contas, audiências, callers, Cedar, targets OBO e fronteiras de Runtime.
        """),
        code("""
        if RUN_AWS:
            config = load_config(CONFIG_PATH)
            sessions = aws_sessions(config)
            if DEPLOY_PHASE is not None:
                plans = prepare_phase(ROOT, config, sessions, DEPLOY_PHASE)
                for plan in plans:
                    print(plan["command"])
                    if RUN_PIPELINE:
                        command = plan["args"] + (["--execute"] if APPLY_CHANGESET else [])
                        subprocess.run(command, cwd=ROOT, check=True)
            else:
                environment = preflight(config, sessions)
                print({"preflight": environment["mode"], "invocation_verified": False})
        else:
            print({"cloud": "NOT_RUN", "phases": PHASES})
        """),
        md("""
        ## 5. Usuário A, dois agentes e uma negativa

        Faça login como A (OID configurado). As três chamadas começam no
        **Gateway de origem**; o código do agente roda na AWS. Primeiro Riscos
        lê seu canário, depois Fraude lê o seu. Na terceira chamada, a mesma
        pessoa usa o agente Fraude para tentar a capacidade Riscos.

        Para as leituras, a prova inclui `current_user()` exato; ter um e-mail na
        resposta não basta. A negativa precisa dizer `POLICY_DENY_REPORTED`.
        Timeout, ausência de tool ou erro de token não contam como negação Cedar.
        O resultado do Registry também aparece, com owner/versão/instância.
        """),
        code("""
        if LIVE:
            token_a = login(config, "a")
            for case, agent, capability in [
                ("a_riscos", "riscos", "riscos"),
                ("a_fraude", "fraude", "fraude"),
                ("a_wrong_agent", "fraude", "riscos"),
            ]:
                row = await run_case(config, environment, token_a, user="a",
                                     agent=agent, capability=capability, case=case)
                rows.append(row)
                display(row)
            assert [row["outcome"] for row in rows[-3:]] == [
                "PER_USER_VERIFIED", "PER_USER_VERIFIED", "POLICY_DENY_REPORTED",
            ]
        else:
            print("Ensaio A: NOT_RUN — as decisões locais estão na seção 2.")
        """),
        md("""
        ## 6. Usuário B: Policy permite, Unity Catalog nega

        B deve pertencer ao workspace e poder executar a consulta de identidade
        no warehouse, mas não possuir SELECT no canário de Riscos. Ambos os
        usuários estão na allowlist das três Policies para que a negativa
        aconteça **na fonte**.

        A célula pede um novo login e verifica seu OID. O agente testa
        `current_user()` antes da consulta negada. Ela não remove nem adiciona
        grants. Esse estado é preparado pelo IaC Databricks do sandbox.
        """),
        code("""
        if LIVE:
            token_b = login(config, "b")
            row = await run_case(config, environment, token_b, user="b",
                                 agent="riscos", capability="riscos", case="b_sem_grant")
            rows.append(row)
            display(row)
            assert row["identity_verified"]
            assert row["outcome"] == "SOURCE_GRANT_DENY_REPORTED"
        else:
            print("Ensaio B / Unity Catalog: NOT_RUN")
        """),
        md("""
        ## 7. Trace até a query: o que já foi observado e o que falta

        Cada chamada carrega `request_id`; o agente registra o usuário
        pseudonimizado, agente, tool, hash da query, IDs HTTP do Gateway central
        e `statement_id/query_id` devolvido pelo MCP. Não exportamos JWT, e-mail,
        SQL completo nem dados da tabela.

        `acceptance()` mantém o resultado **PENDING_EVIDENCE** enquanto faltarem
        os logs correlacionados dos Gateways e a prova de não execução do backend
        na negativa. Siga o [procedimento de trace](../docs/journey/trace.md).
        Não altere booleans para produzir PASS: uma resposta correta não é um
        trace completo. O arquivo desta célula contém as observações reais quando
        `LIVE=True`, e uma declaração NOT_RUN caso contrário.
        """),
        code("""
        report = {
            "mode": "AWS_LIVE" if LIVE else "OFFLINE_PREPARATION",
            "calls": rows,
            "acceptance": acceptance(rows),
            "aws_oauth_databricks": "EXECUTED_REVIEW_EVIDENCE" if LIVE else "NOT_RUN",
        }
        target = ROOT / "evidence" / ("journey-live.json" if LIVE else "journey-local.json")
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\\n")
        display(report)
        """),
        md("""
        ## 8. Limites de consumo e orçamento: três contadores diferentes

        Execute o contrato **local** de contagem por agente/tool: duas chamadas
        permitidas, QPM negado, TPM negado e orçamento mensal negado. Mudar o minuto
        renova QPM/TPM, mas não renova orçamento.

        Os números são sintéticos. Este código não mede tokens de LLM nem a fatura
        AWS. A aplicação de cotas nos serviços depende dos controles do ambiente. Policy temporal nativa é por sessão; a documentação
        descreve expiração após 24h de inatividade e propagação entre saltos apenas
        na mesma conta e região. Ela não equivale ao orçamento mensal deste contrato.
        O [guia de arquitetura](../docs/journey/arquitetura.md) explica responsabilidades.
        """),
        code("""
        quota_demo = local_quota_demo()
        display(quota_demo)
        assert [row["decision"] for row in quota_demo] == [
            "ALLOW", "ALLOW", "QPM_DENY", "TPM_DENY", "BUDGET_DENY",
        ], "Os resultados precisam demonstrar as três negativas de consumo"
        assert all(row["billing_measured"] is False for row in quota_demo)
        """),
        md("""
        ## 9. Relacionar as decisões e avançar

        * O Gateway central distingue o agente e autoriza a ferramenta.
        * O Gateway de dados aplica sua própria Policy à plataforma e ao usuário.
        * O Unity Catalog verifica o grant na fonte, mesmo depois das permissões
          dos Gateways. Identidade válida e acesso ao dado são provas diferentes.
        * Os registros de chamada precisam de correlação para formar um trace.

        No [notebook 15](15_ingestao_acl_memoria.ipynb), acompanhe o que acontece
        com essas permissões quando um documento é ingerido, atualizado ou
        reutilizado na memória de uma conversa.
        """),
        *cleanup_cells("14", "journey"),
    ]
    save("14_cenario_santander_integrado", cells, "OFFLINE_PREPARATION")
    cells = [
        md("""
        # 15 — Ingestão, ACL e memória por usuário

        Exercício executável do **contrato local** de um indexador comum. Não
        chama SharePoint, BDA, OpenSearch, Bedrock Knowledge Bases ou Memory AWS.
        O objetivo é demonstrar o que cada conector precisa preservar antes de
        conectarmos os serviços reais. Veja o [guia do ciclo de vida documental](../docs/ingestao/README.md).
        """),
        picture(diagram(True), "Ingestão comum, ACL por usuário e memória isolada"),
        md("""
        ## 1. Contratos de fonte

        A célula lista quatro contratos de origem: SharePoint, Databricks Silver/Gold,
        SQL local e APIs AWS. O conteúdo de exercício é
        Markdown sintético, representando a saída normalizada de um conector/BDA.
        Nenhuma credencial de fonte é necessária.
        """),
        code("""
        import json
        from pathlib import Path
        from IPython.display import display
        from santander_demo.knowledge import KnowledgeLab, local_knowledge_demo
        ROOT = Path.cwd()
        if not (ROOT / "pyproject.toml").exists():
            ROOT = ROOT.parent
        sources = KnowledgeLab().discover()
        display(sources)
        """),
        md("""
        ## 2. Registrar → recuperar → atualizar ACL → excluir

        Dois documentos compartilham o mesmo catálogo em memória, mas usuários Riscos e Fraude
        enxergam conjuntos diferentes. O usuário Ambos vê os dois. O exercício
        grava referências na memória, troca a ACL e verifica que a referência
        antiga deixa de revelar o documento. Reusar o mesmo ID de sessão com
        outro usuário também não dá acesso à memória.

        A célula executa as operações e suas asserções. `version` exige uma sequência
        de atualização válida; o hash registra o conteúdo na auditoria.
        A exclusão elimina o documento dos resultados da recuperação.
        """),
        code("""
        knowledge_report = local_knowledge_demo()
        display(knowledge_report)
        assert knowledge_report["visibility_before"]["user-riscos"] == ["R1"]
        assert knowledge_report["visibility_before"]["user-fraude"] == ["F1"]
        assert knowledge_report["revoked_acl_in_memory"] == "DENIED"
        target = ROOT / "evidence/ingestao-local.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(knowledge_report, ensure_ascii=False, indent=2) + "\\n")
        """),
        md("""
        ## 3. Traduzir o contrato para os serviços

        Os grupos precisam vir de identidade verificada; o LLM não pode escolher
        ACL ou `user_id`. Na KB/OpenSearch, aplicar filtros no backend e impedir
        acesso direto à role de serviço. Mudanças de ACL e exclusões precisam
        invalidar índice, caches e memória. Unity Catalog continua sendo a
        autoridade dos dados Databricks.

        BDA normaliza conteúdo; não concede acesso. Agent Registry cataloga
        capacidades, enquanto a ingestão administra documentos e metadados.
        Este exercício não chama esses serviços: usa textos sintéticos e busca
        local para tornar atualização, revogação e exclusão observáveis.

        No [notebook 16](16_rag_managed_identity_policy.ipynb), implantaremos
        uma Managed Knowledge Base com ACL nativa, Gateway e Policy. O modelo
        receberá somente o contexto autorizado para a consulta.
        """),
        *cleanup_cells("15", "journey"),
    ]
    save("15_ingestao_acl_memoria", cells, "LOCAL_INGESTION_CONTRACT")
    write_gallery()


if __name__ == "__main__":
    main()
