"""Notebook 12 e diagrama: cada conta decide independentemente."""

import base64
import shutil
import subprocess
from pathlib import Path

import nbformat as nb
from generate_banking_notebook import code, md
from generate_diagrams import TINT, C, Diagram
from notebook_cleanup import cleanup_cells
from notebook_learning import learning_cell

ROOT = Path(__file__).resolve().parents[1]


def diagram():
    page = {
        "id": "12_gateways_por_conta_identity_policy",
        "title": "Cada conta tem sua própria porta.",
        "subtitle": "Quatro Gateways. Quatro decisões locais. O mesmo usuário em todos os saltos.",
        "status": "OBO ENTRA · ARQUITETURA AWS A VALIDAR",
        "takeaway": "Permitir na plataforma não obriga a conta de destino a permitir.",
        "description": "Gateway autentica. Policy autoriza. Identity troca o token para a próxima audiência. O Runtime aceita o workload do Gateway local.",
    }
    d = Diagram(page)

    def compact(x, y, w, h, title, tone, icon, subtitle=None):
        d.raw(f'<g class="node" data-x="{x}" data-y="{y}" data-w="{w}" data-h="{h}">')
        d.rect(x, y, w, h, stroke=C["border"], shadow=True)
        d.rect(x + 14, y + 12, 42, 42, TINT[tone], radius=12)
        d.icon(x + 21, y + 19, icon, C[tone], 28)
        d.text(x + 70, y + (28 if subtitle else 41), title, 21, weight=700, cls="node-text")
        if subtitle:
            d.text(x + 70, y + 49, subtitle, 17, C["muted"], cls="node-text")
        d.raw("</g>")

    d.node(
        64,
        245,
        288,
        184,
        "Notebook + agente",
        ["Login Entra · JWT humano", "Strands no kernel local", "Bedrock na plataforma"],
        "local",
        "laptop",
    )
    d.panel(430, 215, 1106, 261, "CONTA PLATAFORMA", "", "gateway")
    d.node(
        462,
        290,
        336,
        151,
        "Gateway Plataforma",
        ["Valida JWT e roteia tools", "Entrada das três áreas"],
        "gateway",
        "gateway",
    )
    compact(837, 289, 313, 66, "Policy Plataforma", "policy", "shield")
    compact(837, 376, 313, 66, "Identity · OBO", "identity", "key")
    d.node(
        1190,
        290,
        314,
        151,
        "Registry",
        ["Capacidades aprovadas", "Descoberta via IAM"],
        "registry",
        "catalog",
    )
    d.arrow([(352, 368), (462, 368)], "identity")
    d.label(403, 342, "JWT", "identity", 17)
    d.arrow([(837, 324), (798, 324)], "policy", dashed=True)
    d.arrow([(798, 409), (837, 409)], "identity", dashed=True)
    for x, title, gateway, backend in [
        (64, "CONTA RETAIL", "Gateway Retail", "DynamoDB local"),
        (568, "CONTA TRANSACTION", "Gateway Transaction", "DynamoDB local"),
        (1072, "CONTA LENDING", "Gateway Lending", "DynamoDB + Knowledge Base"),
    ]:
        d.panel(x, 535, 464, 292, title, "", "gateway")
        compact(x + 24, 588, 416, 68, gateway, "gateway", "gateway")
        d.tag(x + 24, 672, 194, "Policy local", "policy", height=38, size=18)
        d.tag(x + 230, 672, 210, "Identity · OBO", "identity", height=38, size=18)
        d.arrow([(x + 232, 710), (x + 232, 738)], "identity")
        compact(x + 24, 744, 416, 62, "Runtime MCP", "local", "database", backend)
    # Saídas da plataforma carregam tokens para as audiências dos Gateways locais.
    d.arrow([(630, 441), (630, 500), (296, 500), (296, 535)], "identity")
    d.arrow([(630, 500), (800, 500), (800, 535)], "identity")
    d.arrow([(800, 500), (1304, 500), (1304, 535)], "identity")
    d.label(1030, 501, "OBO · audiência por destino", "identity", 17)
    d.arrow([(208, 245), (208, 201), (1347, 201), (1347, 290)], "registry", dashed=True)
    d.label(1070, 202, "Descoberta IAM", "registry", 15)
    path = ROOT / "docs/federation/arquitetura.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(d.finish().replace("11 / 09", "LAB 12"))
    renderer = shutil.which("rsvg-convert")
    if not renderer:
        raise SystemExit("Instale librsvg para gerar o PNG.")
    png = path.with_suffix(".png")
    subprocess.run([renderer, "-w", "2400", "-h", "1500", "-o", str(png), str(path)], check=True)
    return png


def main():
    png = diagram()
    cells = [
        md("""
        # 12 — Um Gateway por conta, com Identity e Policy locais

        **O que vamos demonstrar:** a plataforma orquestra ferramentas de três
        contas, mas cada conta decide se aceita a chamada. A pessoa é preservada
        por **OBO Entra**, enquanto a audiência e a aplicação chamadora mudam.

        **Entregas:** quatro Gateways, quatro providers Identity, quatro engines
        Policy em ENFORCE, três Runtimes MCP e um Registry na plataforma.
        O agente Strands roda **no kernel deste notebook**, usando Bedrock na
        plataforma. As ferramentas são executadas nos Runtimes AWS.

        Comece pelo [runbook](../docs/federation/README.md).
        Kernel: `.venv/bin/python`, após `uv sync --frozen --extra banking`.
        Reserve 60–90 minutos após preparar identidades, contas e Knowledge Base.
        """),
        nb.v4.new_markdown_cell(
            "![Um Gateway, Identity e Policy em cada conta](attachment:arquitetura.png)\n\n"
            "[Ampliar PNG](../docs/federation/arquitetura.png) · [SVG](../docs/federation/arquitetura.svg)",
            attachments={
                "arquitetura.png": {"image/png": base64.b64encode(png.read_bytes()).decode()}
            },
        ),
        md("""
        ## 1. Entenda os três controles em cada passagem

        | Controle | Pergunta respondida |
        |---|---|
        | Authorizer do Gateway | O JWT é válido, destinado a esta API e emitido para a aplicação esperada? |
        | Policy local | Este usuário e aplicação podem chamar esta tool com estes parâmetros? |
        | Identity local | O IdP permite obter um token delegado para a próxima API? |

        A plataforma usa seu Identity para chamar o **Gateway da LOB**. A LOB usa
        seu próprio Identity para chamar **seu Runtime MCP**. O Runtime exige o
        workload do Gateway local. Cada Policy consulta `tid`, `oid`, `azp` e `scp`.

        **Diferença para o notebook 11:** no artigo, um Gateway central chama
        diretamente os MCPs com M2M. Aqui os Gateways são encadeados e a delegação
        humana continua até os destinos. Os resultados retornam à plataforma.

        **Na próxima célula**, vamos importar os helpers, localizar o projeto e
        definir os controles do laboratório. `RUN_AWS=False` mantém a preparação
        offline; `DEPLOY_PHASE` escolhe uma fase de implantação. `LIVE` só fica
        ativo com AWS habilitada e nenhuma fase selecionada.
        `RUN_PIPELINE` e `APPLY_CHANGESET` controlarão o wrapper de IaC, enquanto
        `RUN_AGENT` habilitará a etapa opcional com Bedrock. A saída mostrará o
        modo escolhido; reexecute esta célula sempre que alterar os controles.
        """),
        code("""
        import json
        import subprocess
        import sys
        from pathlib import Path
        from IPython.display import Markdown, display
        from santander_demo.federation.spec import ACCOUNTS, central_name, local_matrix, tools_by_lob
        from santander_demo.federation.client import (
            load_config, aws_sessions, prepare_phase, preflight, login, verify_token,
            verify_chain, probe_policy, probe_wrong_audience,
        )
        from santander_demo.banking.client import call_tool
        from santander_demo.banking.spec import LOBS

        ROOT = Path.cwd()
        if not (ROOT / "pyproject.toml").exists():
            ROOT = ROOT.parent
        assert (ROOT / "infra/federation").is_dir()

        RUN_AWS = False
        DEPLOY_PHASE = None  # bootstrap / gateways / backends / domain-bindings / platform-bindings / registry
        RUN_PIPELINE = False
        APPLY_CHANGESET = False
        RUN_AGENT = False  # opcional: inferência Bedrock; primeiro prove os caminhos MCP
        CONFIG_PATH = ROOT / "config/local.federation.json"
        LIVE = RUN_AWS and DEPLOY_PHASE is None
        print("AWS REAL" if RUN_AWS else "PREPARAÇÃO LOCAL — AWS e OAuth: NOT_RUN")
        """),
        md("""
        ## 2. Veja uma autorização terminar no segundo Gateway

        Esta célula avalia o **Cedar real localmente**, usando a mesma fonte dos
        templates. Não emite tokens nem simula respostas de backend.

        | Consulta didática | Plataforma | Retail | Resultado |
        |---|---|---|---|
        | get_profile(C003) | Permite | Permite | Caminho autorizado |
        | get_profile(C007) | Nega | Nem precisa ser chamada | Para na plataforma |
        | get_profile(C008) | Permite | Nega | Para na conta Retail |

        O resultado `retail_policy_isolated` mostra o que a Policy Retail decidiria
        isoladamente. Se a plataforma nega, essa etapa não é executada no fluxo.
        As negativas C007/C008 pertencem apenas à tool `get_profile`.

        Vamos executar `local_matrix()` e exibir suas decisões para comparar
        os três clientes da tabela. As asserções comparam as decisões com a
        tabela escrita, além de confirmar `oauth_and_aws: NOT_RUN`.
        O resultado desta célula verifica as regras
        Cedar locais, enquanto os testes de identidade e dos Gateways AWS virão depois.
        """),
        code("""
        matrix = local_matrix()
        display(matrix)
        assert [
            (r["customer"], r["platform_policy"], r["retail_policy_isolated"], r["end_to_end_contract"])
            for r in matrix["cases"]
        ] == [
            ("C003", "ALLOW", "ALLOW", "ALLOW"),
            ("C007", "DENY", "ALLOW", "DENY"),
            ("C008", "ALLOW", "DENY", "DENY"),
        ], "As decisões divergem da matriz descrita"
        assert matrix["oauth_and_aws"] == "NOT_RUN"
        """),
        md("""
        ## 3. Prepare o ambiente por IaC

        As identidades Entra são pré-requisitos: login público, quatro aplicações
        de Gateway e três APIs de Runtime; grants OBO e quatro segredos nas contas
        locais. O [runbook](../docs/federation/README.md) detalha todas as relações.
        O módulo Entra da trilha original não configura esta variante.

        No terminal:

        ```bash
        uv run --extra banking python scripts/build_artifacts.py --banking
        cp config/federation.example.json config/local.federation.json
        ```

        Preencha perfis, contas, tenant, aplicações, ARNs de segredo, usuário e KB.
        Nenhum valor de segredo ou token deve ser salvo no JSON ou notebook.
        A célula abaixo gera **somente arquivos locais**.

        Vamos executar `infra/federation/generate.py` com o Python deste kernel
        e listar os JSONs gerados para confirmar a existência de treze templates,
        usados nos dezesseis stacks previstos. A saída também mostrará o comando
        de lint; esse comando será apenas exibido, não executado por esta célula.
        """),
        code("""
        subprocess.run([sys.executable, str(ROOT / "infra/federation/generate.py")], cwd=ROOT, check=True)
        templates = sorted((ROOT / "infra/federation/templates").glob("*.json"))
        assert len(templates) == 13
        print("13 templates locais / 16 stacks previstos / nenhum recurso criado.")
        print("Lint: uv run --extra banking cfn-lint infra/federation/templates/*.json")
        """),
        md("""
        ## 4. Implante por fases

        | Fase | Onde / o que |
        |---|---|
        | bootstrap | Quatro buckets de artefatos |
        | gateways | Gateway + Identity + Policy engine + logs em cada conta |
        | backends | Runtime MCP + DynamoDB nas três LOBs |
        | domain-bindings | Gateway local → seu Runtime e Policies locais |
        | platform-bindings | Gateway Plataforma → três Gateways e Policy central |
        | registry | Metadados aprovados para descoberta |

        Use `RUN_AWS=True` e uma fase por vez. Com `RUN_PIPELINE=False`, apenas
        os parâmetros e comandos são preparados. Com `RUN_PIPELINE=True`, o
        wrapper prepara change sets (inclui upload do artefato); depois da revisão,
        `APPLY_CHANGESET=True` aplica pelo CloudFormation.

        Na fase inicial os engines ainda não têm permits: chamadas ficam negadas.
        Se algo falhar, corrija IaC/parâmetros e repita a fase. Não há criação ou
        correção de recursos por SDK no notebook.

        Vamos carregar a configuração e validar os perfis via STS quando
        `RUN_AWS` estiver ativo. Com uma fase selecionada, a célula exibirá os
        planos por conta e, se `RUN_PIPELINE=True`, executará o wrapper do projeto.
        `APPLY_CHANGESET=True` acrescentará `--execute`. No padrão offline,
        a saída será `NOT_RUN` para STS, change sets e implantação.
        """),
        code("""
        config = sessions = None
        if RUN_AWS:
            config = load_config(CONFIG_PATH)
            sessions = aws_sessions(config)
            if DEPLOY_PHASE is not None:
                plans = prepare_phase(ROOT, config, sessions, DEPLOY_PHASE)
                for plan in plans:
                    print(plan["account"], plan["command"], sep="\\n")
                if RUN_PIPELINE:
                    for plan in plans:
                        subprocess.run(
                            plan["args"] + (["--execute"] if APPLY_CHANGESET else []),
                            cwd=ROOT, check=True,
                        )
        else:
            print("NOT_RUN: STS, change sets e implantação.")
        """),
        md("""
        ## 5. Confira quatro fronteiras independentes

        Depois da implantação, volte a `DEPLOY_PHASE=None` e reexecute a célula
        de configuração. O preflight lê os quatro Gateways, verifica Cedar
        implantado, OBO local, audiências, callers, targets e restrição de workload
        dos Runtimes. Configuração pronta ainda não prova chamadas bem-sucedidas.

        Vamos armazenar os identificadores validados em `environment` e exibir
        o número de Gateways, o modo das Policies e os log groups de cada conta.
        Esperamos quatro Gateways e `invocation_verified: False`, pois as
        chamadas ainda não ocorreram. Com `LIVE=False`, o preflight será ignorado.
        """),
        code("""
        environment = None
        if LIVE:
            environment = preflight(config, sessions)
            print({"mode": environment["mode"], "gateways": len(environment["gateways"]),
                   "policy": "ENFORCE em quatro contas", "invocation_verified": False})
            display({account: values["GatewayLogGroup"] for account, values in environment["gateways"].items()})
        else:
            print("NOT_RUN: preflight AWS.")
        """),
        md("""
        ## 6. Autentique uma pessoa, não uma credencial M2M

        O login solicita `api://<gateway-plataforma>/access_as_user`. A audiência
        do token v2 é o App ID da plataforma; `azp` é o App ID do login público.
        O token fica só na memória. Use o usuário esperado nas quatro allowlists.

        Se Device Code não for permitido, substitua somente a linha `login(config)`
        por `getpass.getpass(...)` para um access token obtido pelo fluxo interativo
        aprovado dessa aplicação. `verify_token` continua obrigatório.

        Vamos obter o token em `user_token` e executar `verify_token` antes
        de chamar as ferramentas. A saída será o resumo da verificação; uma
        falha de validação interromperá esta etapa. Com `LIVE=False`, o login
        não será iniciado e a saída indicará `NOT_RUN`.
        """),
        code("""
        user_token = None
        if LIVE:
            user_token = login(config)
            display(verify_token(user_token, config))
        else:
            print("NOT_RUN: login e verificação Entra.")
        """),
        md("""
        ## 7. Descubra ferramentas sem pular os Gateways

        O Registry publica o endpoint da **plataforma**, com nomes que carregam
        as duas camadas: `retail___backend___get_profile`.
        O cliente não usa o Registry para pegar um endpoint de backend e contornar
        a Policy. Schemas estáticos evitam sincronização que dependeria de usuário.

        Vamos primeiro exibir os contratos locais agrupados por LOB, disponíveis
        mesmo offline. Em modo live, consultaremos também o Registry pela sessão
        da plataforma e exibiremos as capacidades aprovadas. Esta célula realiza
        descoberta de metadados; as chamadas MCP serão feitas nas próximas etapas.
        """),
        code("""
        display(tools_by_lob())
        if LIVE:
            from santander_demo.federation.agent import discover
            display(discover(sessions["platform"], environment))
        else:
            print("Contratos locais exibidos; busca no Registry: NOT_RUN.")
        """),
        md("""
        ## 8. Prove a identidade que chegou aos três MCPs

        Cada `whoami` verifica o JWT recebido no Runtime usando JWKS do tenant.
        Esperamos a mesma pessoa (`hash(tid:oid)`), `azp` do Gateway local e `aud`
        do Runtime local. Não compare `sub` entre aplicações.
        Nenhuma claim é aceita a partir de argumentos de tool.

        Vamos usar `verify_chain` para chamar as ferramentas de identidade pelos
        caminhos federados e comparar as provas dos três destinos com a
        configuração esperada. O resultado ficará em `identity_evidence` para
        a exportação final. Com `LIVE=False`, as trocas OBO e a verificação
        nos Runtimes permanecerão como `NOT_RUN`.
        """),
        code("""
        identity_evidence = {"mode": "NOT_RUN"}
        if LIVE:
            identity_evidence = await verify_chain(environment, user_token, config)
            display(identity_evidence)
        else:
            print("NOT_RUN: duas trocas OBO por caminho e verificação nos Runtimes.")
        """),
        md("""
        ## 9. Consulte as três contas pelo Gateway da plataforma

        São chamadas MCP determinísticas, antes de introduzir decisões do LLM.
        Cada resultado atravessa **duas Policies** e **duas trocas OBO**.

        Vamos consultar perfil em Retail, pagamentos em Transaction e score
        em Lending para o cliente sintético `C003`. `central_name` montará os
        nomes qualificados anunciados pela plataforma, e as respostas serão
        armazenadas em `observations`. Esperamos uma entrada para cada LOB;
        com `LIVE=False`, nenhuma consulta será realizada.
        """),
        code("""
        observations = {}
        if LIVE:
            for lob, tool in [
                ("retail-banking", "get_profile"),
                ("transaction-banking", "get_payments"),
                ("lending-wealth", "get_credit_score"),
            ]:
                observations[lob] = await call_tool(
                    environment, user_token, central_name(lob, tool), {"customer_id": "C003"}
                )
            display(observations)
            assert set(observations) == set(LOBS)
        else:
            print("NOT_RUN: consultas em quatro contas.")
        """),
        md("""
        ## 10. Compare uma negativa central e uma negativa local

        C007 deve parar na plataforma. C008 deve passar pela plataforma e parar
        na Policy Retail. O código não altera permissões durante a demonstração.
        São tentativas de leitura; nenhum dado será escrito.

        Uma resposta de Policy comprova que houve negação. Para atribuir o salto
        e comprovar ausência de execução no backend, confira os log groups das
        contas na janela da chamada. Erro OAuth/rede não conta como negação Cedar.

        Vamos executar `probe_policy` para cada cliente e guardar os resultados
        em `denials`. Cada tentativa deverá retornar `POLICY_DENIAL_REPORTED`;
        qualquer outro resultado fará a asserção falhar. Offline, a célula
        lembrará que somente a matriz Cedar da seção 2 foi executada.
        """),
        code("""
        denials = []
        if LIVE:
            for customer in ["C007", "C008"]:
                denial = await probe_policy(environment, user_token, customer)
                display(denial)
                denials.append(denial)
                assert denial["outcome"] == "POLICY_DENIAL_REPORTED", (
                    "Negativa de Policy não comprovada; revise logs e integração."
                )
        else:
            print("NOT_RUN: negativas nos Gateways AWS. Cedar local foi testado na seção 2.")
        """),
        md("""
        ## 11. Tente reutilizar um token na conta errada

        O JWT da plataforma é enviado ao Gateway Retail somente como teste negativo.
        Ele tem audiência e aplicação incompatíveis com essa entrada. Esperamos
        HTTP 401/403. Esse teste não substitui o ensaio da restrição de workload
        do Runtime com um token que já tenha audiência válida.

        Vamos chamar `probe_wrong_audience` e salvar a evidência em
        `auth_evidence`. O helper verificará a recusa de autenticação antes de
        devolver o resultado, separando esse caso das negativas de Policy da
        seção anterior. Com `LIVE=False`, a tentativa não será enviada.
        """),
        code("""
        auth_evidence = {"mode": "NOT_RUN"}
        if LIVE:
            auth_evidence = await probe_wrong_audience(environment, user_token)
            display(auth_evidence)
        else:
            print("NOT_RUN: rejeição de audiência/aplicação incorretas.")
        """),
        md("""
        ## 12. Opcional: faça a pergunta ao agente Strands

        Ative `RUN_AGENT=True` e reexecute a configuração. O agente roda neste
        notebook; Bedrock usa o perfil da plataforma. A seleção de tools não
        substitui nenhuma das quatro Policies. Registry e Guardrail também são
        chamados na AWS. As respostas são somente para a demo com fixtures.

        Com `LIVE` e `RUN_AGENT` ativos, vamos pedir ao agente consultas sobre
        `C003` nas três áreas. A célula exibirá a resposta em português e o
        histórico de ferramentas, exigindo ao menos uma chamada bem-sucedida
        por LOB. Se algum dos controles estiver desativado, `agent_result`
        permanecerá vazio e a inferência será marcada como `NOT_RUN`.
        """),
        code("""
        agent_result = None
        if LIVE and RUN_AGENT:
            from santander_demo.federation.agent import run_agent
            agent_result = run_agent(
                "Consulte perfil e contas, pagamentos, score e empréstimos de C003 nas "
                "três áreas. Responda em português, cite as ferramentas e não faça alterações "
                "nem trate os dados sintéticos como uma decisão real de crédito.",
                user_token, environment, sessions["platform"],
            )
            display(Markdown(agent_result["response"]))
            display(agent_result["tool_calls"])
            observed = {c["lob"] for c in agent_result["tool_calls"] if c["status"] == "success"}
            assert set(LOBS) <= observed, "O agente não consultou as três áreas."
        else:
            print("NOT_RUN: inferência Strands/Bedrock opcional.")
        """),
        md("""
        ## 13. Registre somente o que foi observado

        A evidência não contém JWT, claims brutas, resposta bancária ou documentos.
        A atribuição da negativa ao Gateway correto e a ausência de chamada ao
        backend continuam pendentes até a revisão dos logs. Os recursos não são
        removidos automaticamente; use CloudFormation na ordem inversa do runbook.

        No modo live, vamos reunir horário, contagem de Gateways, provas de
        identidade, consultas observadas e resultados negativos em
        `evidence/federation.json`, substituindo o arquivo anterior se existir.
        Os campos pendentes permanecerão explícitos, incluindo a revisão dos
        logs e o teste de acesso direto ao Runtime com audiência válida.
        Offline, exibiremos os status de preparação sem salvar evidência AWS.
        Ao final, `user_token` será definido como `None`.
        """),
        code("""
        if LIVE:
            from datetime import datetime, timezone
            evidence = {
                "mode": "AWS_LIVE", "observed_at": datetime.now(timezone.utc).isoformat(),
                "gateway_count": len(environment["gateways"]),
                "obo": identity_evidence,
                "lob_calls_observed": sorted(observations),
                "policy_denials": denials,
                "wrong_audience": auth_evidence,
                "strands_bedrock": "OBSERVED" if agent_result else "NOT_RUN",
                "negative_boundary_and_no_backend_execution": "LOG_REVIEW_PENDING",
                "valid_audience_runtime_workload_bypass_test": "NOT_RUN",
            }
            target = ROOT / "evidence/federation.json"
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(evidence, indent=2) + "\\n")
            display(evidence)
        else:
            display({
                "mode": "OFFLINE_PREPARATION",
                "local_cedar": "PASS",
                "aws_gateways": "NOT_RUN", "identity_obo": "NOT_RUN",
                "policy_service": "NOT_RUN", "registry": "NOT_RUN",
            })
        user_token = None
        """),
    ]
    cells.insert(2, learning_cell("12"))
    notebook = nb.v4.new_notebook(
        cells=cells + cleanup_cells("12", "federation"),
        metadata={
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3 (.venv)",
                "language": "python",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "santander": {
                "local_validation_mode": "OFFLINE_PREPARATION",
                "aws_execution": "NOT_RUN",
            },
        },
    )
    nb.validate(notebook)
    path = ROOT / "notebooks/12_gateways_por_conta_identity_policy.ipynb"
    nb.write(notebook, path)
    print(path)


if __name__ == "__main__":
    main()
