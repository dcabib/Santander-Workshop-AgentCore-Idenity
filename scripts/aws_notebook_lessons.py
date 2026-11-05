"""Aulas executáveis: código de serviço, explicação e asserção sobre chamadas AWS."""

from textwrap import dedent

import nbformat


def md(text):
    return nbformat.v4.new_markdown_cell(dedent(text).strip())


def code(text):
    return nbformat.v4.new_code_cell(dedent(text).strip())


def step(title, explanation, implementation):
    return [md("### " + title + "\n\n" + explanation), code(implementation)]


def setup(number):
    return [
        md("""
        Todos os serviços e agentes desta jornada são implantados na AWS.
        O notebook é o roteiro e cliente das APIs; ferramentas, inferência,
        políticas, fontes e memória executam nos serviços indicados.
        Use o ambiente AWS descrito no [guia de implantação](../docs/deploy.md).
        Configure os identificadores dos stacks antes de executar. Uma
        dependência ausente bloqueia a aula antes das chamadas do exercício.
        Antes de usar “Run All”, selecione as aulas compatíveis com as contas
        preparadas. O bloco 10–14 exige quatro contas na implantação atual.
        """),
        *step("Carregar a configuração e conferir as dependências",
              "A configuração contém perfis/roles e IDs, nunca senhas ou tokens. "
              "O STS confirma a conta antes de consultar os stacks; o manifesto "
              "exige as dependências desta aula.",
              f"""
        import json
        import os
        import uuid
        from pathlib import Path
        from IPython.display import Code, display
        import inspect
        from santander_demo.aws_workshop.client import AWSWorkshop
        from santander_demo.aws_workshop.config import load
        from santander_demo.aws_workshop.manifest import require

        ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists())
        CONFIG = Path(os.environ.get("WORKSHOP_CONFIG", ROOT / "config/aws.workshop.json"))
        config = load(CONFIG)
        dependencies = require(config, "{number}")
        print({{"lab": "{number}", "dependencies": list(dependencies), "region": config["region"]}})
        """),
    ]


def core(domain="platform"):
    return step("Conectar ao ambiente implantado",
                "Lemos os outputs exatos do CloudFormation. O cliente não cria "
                "infraestrutura e não substitui um serviço indisponível.",
                f"""
    lab = AWSWorkshop(CONFIG, domain="{domain}")
    print(lab.preflight())
    """)


def authentication():
    return step("Autenticar a pessoa no Cognito",
                "O login usa USER_PASSWORD_AUTH para usuários sintéticos do workshop "
                "e SECRET_HASH para o cliente confidencial. Em uma aplicação de "
                "usuários finais, use authorization code com PKCE. O código abaixo "
                "mostra a chamada Cognito e a verificação de assinatura, emissor, "
                "audiência e token_use. Só imprimimos claims selecionadas.",
                """
    from santander_demo.aws_workshop.identity import login, verify
    display(Code(inspect.getsource(login), language="python"))
    display(Code(inspect.getsource(verify), language="python"))
    token = lab.login("c", "supervisor")
    claims = lab.claims(token)
    print({key: claims[key] for key in ["iss", "sub", "aud", "token_use"]})
    """)


def preflight():
    return [
        *core(),
        *step("Ler o Gateway pela API de controle",
              "Gateway reúne protocolo MCP, autenticação e Policy. READY "
              "indica prontidão; ENFORCE torna a decisão Cedar obrigatória "
              "antes de invocar um target.",
              """
        control = lab.aws.client("bedrock-agentcore-control")
        gateway = control.get_gateway(gatewayIdentifier=lab.gateway["GatewayId"])
        print({key: gateway[key] for key in ["gatewayArn", "status", "authorizerType",
                                            "policyEngineConfiguration"]})
        assert gateway["status"] == "READY"
        assert gateway["policyEngineConfiguration"]["mode"] == "ENFORCE"
        """),
        *step("Verificar a fronteira de autenticação",
              "Enviamos um initialize MCP sem Authorization. Só 401/403 "
              "comprovam a negativa; timeout ou erro de servidor fazem o teste falhar.",
              """
        display(Code(inspect.getsource(lab.deny_anonymous), language="python"))
        print(await lab.deny_anonymous())
        """),
        *step("Rejeitar um JWT inválido",
              "Um texto com formato de token não estabelece uma identidade. "
              "Exigimos a negativa HTTP do authorizer e o ID nativo da requisição.",
              """
        import httpx
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
            response = await http.post(lab.gateway["GatewayUrl"],
                headers={"Authorization": "Bearer invalid.token.value"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert response.status_code in {401, 403}
        assert response.headers.get("x-amzn-requestid")
        print({"invalid_jwt": "DENIED", "http_status": response.status_code,
               "gateway_request_id": response.headers["x-amzn-requestid"]})
        """),
        *step("Comprovar que o Runtime exige a role do Gateway",
              "O preflight confere a resource policy e a trust policy pelo IAM. "
              "Agora tentamos uma invocação direta com a role do runner: "
              "o serviço deve negar antes de executar o servidor MCP.",
              """
        display(Code(inspect.getsource(lab.deny_direct_runtime), language="python"))
        print(lab.deny_direct_runtime())
        """),
        md("""
        **Observe:** IAM controla quem administra os recursos; o authorizer JWT
        autentica chamadas MCP; Cedar autoriza pessoa, aplicação, ação e entrada.
        O Gateway não transforma uma permissão de descoberta em permissão de execução.

        **Entra ID:** o mesmo desenho usa discovery URL, chaves públicas e audiência
        do Entra. As claims `tid`, `oid`, `azp` e os consentimentos precisam de
        regras próprias. Não copie os valores Cognito para essas claims.
        """),
    ]


def gateway():
    return [
        *core(), *authentication(),
        *step("Executar tools/list no Gateway",
              "Abra uma sessão MCP sobre HTTPS. initialize negocia o protocolo; "
              "tools/list devolve os schemas dos targets. Os prefixos qualificam "
              "os nomes que aparecem nas ações Cedar.",
              """
        from santander_demo.aws_workshop.client import gateway_session, content
        async with gateway_session(lab.gateway["GatewayUrl"], token) as mcp:
            announced = await mcp.list_tools()
            for tool in announced.tools:
                print(tool.name, tool.inputSchema)
        assert "riscos___consultar_risco" in {t.name for t in announced.tools}
        """),
        *step("Chamar o target Lambda",
              "O JWT é validado na entrada. Após o permit da Policy, o Gateway "
              "assina a invocação Lambda com sua role IAM. O backend valida "
              "a entrada e retorna dados sintéticos.",
              """
        async with gateway_session(lab.gateway["GatewayUrl"], token) as mcp:
            response = await mcp.call_tool("riscos___consultar_risco", {
                "cliente_id": "C001", "max_registros": 1, "request_id": str(uuid.uuid4())
            })
        risk = content(response)
        assert risk["customer_id"] == "C001" and risk["synthetic"] is True
        print(risk)
        """),
        *step("Chamar o servidor MCP no Runtime",
              "O segundo target é um servidor MCP hospedado no AgentCore Runtime. "
              "O Gateway assina a chamada com IAM/SigV4. O interceptor encaminha "
              "o JWT verificado da pessoa em um header separado; o backend valida "
              "assinatura/audiência antes de ler sua ACL independente.",
              """
        fraud = await lab.call(token, "especialista___consultar_fraude",
                               {"cliente_id": "C001", "max_registros": 1})
        assert fraud["result"]["source_kind"] == "AWS_SIMULATED_DATABRICKS"
        assert fraud["result"]["verified_subject"] == claims["sub"]
        print(fraud)
        """),
        *step("Inspecionar IAM, JWT humano e a restrição de entrada",
              "A API não aceita JWT_PASSTHROUGH para esse tipo de target. "
              "Usamos GATEWAY_IAM_ROLE com assinatura bedrock-agentcore. O JWT "
              "segue em um header próprio, sobrescrito pelo interceptor. A resource "
              "policy do Runtime nega qualquer role diferente da role do Gateway. "
              "AllowedWorkloadConfiguration exige transaction tokens do target "
              "nativo HTTP de Runtime e não se aplica a esta agregação MCP.",
              """
        from santander_demo.aws_workshop.interceptor import transform
        from santander_demo.aws_workshop.backend import verified_source_claims
        from santander_demo.aws_workshop.runtime_boundary import policy
        display(Code(inspect.getsource(transform), language="python"))
        display(Code(inspect.getsource(verified_source_claims), language="python"))
        display(Code(json.dumps(policy(lab.backend["RuntimeArn"], lab.gateway["GatewayRoleArn"]),
                                indent=2), language="json"))
        """),
        md("**Aceite:** ferramentas descobertas pelo MCP, resposta Lambda válida e "
           "resposta do Runtime ligada ao `sub` autenticado. As três provas vêm da AWS."),
    ]


def identity():
    return [
        *core(), *authentication(),
        *step("Inspecionar o workload do agente",
              "AgentCore Identity mantém uma identidade de workload separada "
              "da pessoa. O agente hospedado chama GetWorkloadAccessTokenForJWT "
              "usando sua role IAM e o JWT recebido. O WAT fica em memória no "
              "Runtime e não aparece nos outputs.",
              """
        from santander_demo.aws_workshop.agent import answer
        environment = lab.outputs("agent")
        control = lab.aws.client("bedrock-agentcore-control")
        workload = control.get_workload_identity(name=environment["WorkloadName"])
        print({"workloadArn": workload["workloadIdentityArn"]})
        display(Code(inspect.getsource(answer), language="python"))
        """),
        *step("Executar o agente hospedado com identidade e evidência",
              "A inferência Bedrock e as chamadas de ferramentas executam no "
              "Runtime. O notebook envia a pergunta e verifica se houve uma "
              "chamada real de ferramenta.",
              """
        response = await lab.invoke_agent(token, "Consulte o risco de C001 e explique o resultado.")
        assert response["workload_identity"] == "VERIFIED"
        assert response["execution"] == "AWS_AGENTCORE_RUNTIME"
        assert any(x["tool"] == "riscos___consultar_risco" for x in response["tool_calls"])
        print(response)
        """),
        md("""
        **Cognito e Entra ID:** assinatura, emissor, audiência, expiração, identidade
        humana e identidade da aplicação existem nos dois desenhos. Nesta jornada
        Cognito, Gateway e Runtime confiam explicitamente na mesma audiência e
        propagam o JWT para essa cadeia. Isso não é uma troca OBO.

        No Entra, registre APIs/audiências próprias, configure o provider OAuth
        do AgentCore Identity e o grant OBO suportado, e valide o token emitido
        para cada destino. Microsoft Graph `/me` exige um token Graph delegado;
        Cognito não emite esse token. O laboratório 09 demonstra separadamente M2M,
        que representa uma aplicação e não herda permissões de uma pessoa.
        """),
    ]


def applications():
    return [
        *core(),
        *step("Obter dois tokens reais para a mesma pessoa",
              "Os clientes confidenciais supervisor e riscos usam segredos "
              "distintos gerados pelo Cognito e guardados no Secrets Manager. "
              "Mudamos a aplicação que solicita o token, preservando o usuário.",
              """
        supervisor = lab.login("c", "supervisor")
        riscos = lab.login("c", "riscos")
        first, second = lab.claims(supervisor), lab.claims(riscos)
        assert first["sub"] == second["sub"]
        assert first["aud"] != second["aud"]
        print({"same_person": True, "different_applications": True})
        """),
        *step("Comparar decisões para a ferramenta Fraude",
              "O supervisor recebe permit; a aplicação de Riscos deve receber "
              "uma negativa de Policy. Uma falha de rede não conta como negativa.",
              """
        arguments = {"cliente_id": "C001", "max_registros": 1}
        print(await lab.call(supervisor, "especialista___consultar_fraude", arguments))
        denied = await lab.expect_denial(riscos, "especialista___consultar_fraude", arguments)
        print(denied)
        """),
        *step("Testar um caminho alternativo",
              "A restrição também cobre a ferramenta genérica de tabelas. "
              "A fonte revalida pessoa e aplicação, além da decisão do Gateway.",
              """
        print(await lab.expect_denial(riscos, "especialista___consultar_tabela",
                                      {"tabela": "fraude"}))
        """),
        md("**Entra ID:** faça a mesma comparação com tokens obtidos por dois "
           "clientes registrados. Valide `azp`/`appid` conforme a versão do token; "
           "não altere claims em um JWT já assinado."),
    ]


def policy():
    return [
        *core(),
        *step("Ler o Cedar que o IaC publica",
              "As regras vinculam o principal ao sub, o cliente à audiência, "
              "a ação ao nome qualificado e o recurso ao ARN do Gateway. "
              "Observe o limite de entrada e a ausência de permit para D.",
              """
        from santander_demo.aws_workshop.contracts import policies
        cedar = policies(lab.gateway["GatewayArn"], lab.identity["Issuer"],
                         lab.identity["SupervisorClientId"], lab.identity["RiscosClientId"],
                         {x: lab.identity[f"User{x.upper()}Oid"] for x in "abc"})
        for name, text in cedar.items():
            print(name)
            display(Code(text, language="text"))
        """),
        *step("Executar a matriz no Gateway gerenciado",
              "Cada linha faz uma chamada HTTPS real. Validamos separadamente "
              "permit e uma negativa de Policy; infraestrutura indisponível "
              "interrompe o exercício.",
              """
        import time
        since_ms = int(time.time() * 1000)
        cases = [
            ("a", "supervisor", "riscos___consultar_risco", 1, True),
            ("b", "supervisor", "riscos___consultar_risco", 1, False),
            ("c", "supervisor", "especialista___consultar_fraude", 1, True),
            ("a", "supervisor", "especialista___consultar_fraude", 1, False),
            ("c", "riscos", "especialista___consultar_fraude", 1, False),
            ("d", "supervisor", "riscos___consultar_risco", 1, False),
            ("c", "supervisor", "riscos___consultar_risco", 11, False),
        ]
        rows = []
        for user, application, tool, limit, allowed in cases:
            jwt_token = lab.login(user, application)
            arguments = {"cliente_id": "C001", "max_registros": limit}
            evidence = (await lab.call(jwt_token, tool, arguments) if allowed else
                        await lab.expect_denial(jwt_token, tool, arguments))
            rows.append({"user": user, "application": application, "tool": tool,
                         "expected": "ALLOW" if allowed else "DENY", "evidence": evidence})
        print(json.dumps(rows, indent=2))
        """),
        *step("Correlacionar Policy e execução da ferramenta",
              "O ID AWS identifica a decisão nativa; request_id identifica "
              "o registro backend_invoked. Enviamos controles permitidos após "
              "as negativas e aguardamos sua entrega no CloudWatch. Ausência "
              "de logs sozinha não comprova uma negativa: exigimos também DENY "
              "nativo, controles entregues e uma janela adicional de observação.",
              """
        import asyncio
        from santander_demo.aws_workshop.evidence import correlate_policy
        for tool in ["riscos___consultar_risco", "especialista___consultar_fraude"]:
            rows.append({"user": "c", "application": "supervisor", "tool": tool,
                         "expected": "ALLOW", "control_after_denials": True,
                         "evidence": await lab.call(lab.login("c"), tool,
                             {"cliente_id": "C001", "max_registros": 1})})
        stable_since = None
        for attempt in range(48):
            correlate_policy(lab, rows, since_ms)
            ready = all(row["correlation"]["native_policy_verified"]
                        and row["correlation"]["backend_observed"] == (row["expected"] == "ALLOW")
                        for row in rows)
            stable_since = (stable_since or time.monotonic()) if ready else None
            if stable_since is not None and time.monotonic() - stable_since >= 20:
                break
            await asyncio.sleep(5)
        else:
            raise AssertionError("CORRELACAO_POLICY_BACKEND_INCOMPLETA")
        print(json.dumps({"observation_after_controls_seconds": 20, "rows": rows}, indent=2))
        """),
        md("**Exercício:** explique qual condição nega cada linha. Para mudar "
           "uma regra, edite o gerador IaC, revise o diff e faça o deploy do "
           "stack `bindings`; não edite a Policy diretamente pela API."),
    ]


def policy_authoring():
    return [
        *core(),
        *step("Ler a geração assistida criada pelo CloudFormation",
              "A fase policy-draft solicita um rascunho ao serviço. Ela não "
              "publica uma Policy. Compare a linguagem natural com o Cedar "
              "gerado e procure permissões mais amplas que a intenção.",
              """
        environment = lab.outputs("policy-draft")
        control = lab.aws.client("bedrock-agentcore-control")
        generation = control.get_policy_generation(
            policyEngineId=lab.gateway["PolicyEngineId"],
            policyGenerationId=environment["PolicyGenerationId"],
        )
        assert generation["status"] == "GENERATED"
        print(json.dumps(generation, indent=2, default=str))
        assets, cursor = [], None
        while True:
            page = control.list_policy_generation_assets(
                policyEngineId=lab.gateway["PolicyEngineId"],
                policyGenerationId=environment["PolicyGenerationId"],
                **({"nextToken": cursor} if cursor else {}),
            )
            assets.extend(page["policyGenerationAssets"])
            cursor = page.get("nextToken")
            if not cursor:
                break
        assert assets, "O estado GENERATED precisa ter um rascunho para revisão"
        for asset in assets:
            definition = asset["definition"]
            statement = definition.get("cedar", definition.get("policy", {})).get("statement")
            assert statement
            print({"fragment": asset.get("rawTextFragment"), "findings": asset.get("findings", [])})
            display(Code(statement, language="text"))
        """),
        *step("Comparar políticas ativas com as declarações revisadas",
              "A geração assistida não deve alterar permissões ativas. "
              "Consultamos cada Policy do stack bindings e comparamos "
              "o statement Cedar com o contrato gerado pelo IaC.",
              """
        from santander_demo.aws_workshop.contracts import policies
        expected = policies(lab.gateway["GatewayArn"], lab.identity["Issuer"],
                            lab.identity["SupervisorClientId"], lab.identity["RiscosClientId"],
                            {x: lab.identity[f"User{x.upper()}Oid"] for x in "abc"})
        base = dict(expected)
        targets, cursor = [], None
        while True:
            page = control.list_gateway_targets(
                gatewayIdentifier=lab.gateway["GatewayId"],
                **({"nextToken": cursor} if cursor else {}),
            )
            targets.extend(x["name"] for x in page["items"])
            cursor = page.get("nextToken")
            if not cursor:
                break
        for domain in ["Retail", "Transaction", "Lending"]:
            if domain.lower() in targets:
                expected.update({domain + name: statement.replace(
                    'AgentCore::Action::"', f'AgentCore::Action::"{domain.lower()}___')
                    for name, statement in base.items()})
        active, cursor = {}, None
        while True:
            page = control.list_policies(
                policyEngineId=lab.gateway["PolicyEngineId"],
                **({"nextToken": cursor} if cursor else {}),
            )
            active.update({item["name"]: item for item in page["policies"]})
            cursor = page.get("nextToken")
            if not cursor:
                break
        assert set(active) == set(expected), "Políticas fora do contrato IaC"
        observed = {}
        for name, statement in expected.items():
            policy = control.get_policy(
                policyEngineId=lab.gateway["PolicyEngineId"],
                policyId=active[name]["policyId"],
            )
            assert policy["status"] == "ACTIVE" and policy["enforcementMode"] == "ACTIVE"
            assert policy["definition"]["cedar"]["statement"].strip() == statement.strip()
            observed[name] = {"policy_id": policy["policyId"], "matches_iac": True}
        print(json.dumps(observed, indent=2))
        """),
        *step("Mostrar a operação que produz o rascunho",
              "Este é o código executado pelo provider CloudFormation. "
              "A publicação é uma mudança separada no template bindings, "
              "com validação e revisão; o notebook não publica sugestões do modelo.",
              """
        print((ROOT / "infra/providers/policy_draft_handler.py").read_text())
        print((ROOT / "infra/workshop/templates/bindings.json").read_text())
        """),
        md("**Aceite:** geração em GENERATED e políticas ativas ainda iguais "
           "às declaradas no IaC. **Entra ID:** altere as condições de identidade "
           "para os claims verificados do token Entra antes de publicar."),
    ]


def source():
    return [
        *core("transaction-banking"), *authentication(),
        md("""
        O workspace Databricks foi substituído, a pedido do usuário, por um
        **simulador hospedado na AWS**: Runtime MCP + DynamoDB. Ele representa
        `current_user()` e grants por pessoa com dados sintéticos. Não executa
        SQL Warehouse, token exchange Databricks ou Unity Catalog, e não
        comprova esses produtos.
        """),
        *step("Verificar a identidade na fonte",
              "A fonte valida o JWT recebido. Não aceita user_id fornecido "
              "nos argumentos da ferramenta. Compare o subject retornado "
              "com aquele verificado no login.",
              """
        proof = await lab.call(token, "especialista___identidade_fonte", {})
        assert proof["result"]["verified_subject"] == claims["sub"]
        print(proof)
        """),
        *step("Comparar grants de B e C na fonte",
              "A ferramenta de consulta é permitida pelo Gateway, mas a "
              "fonte mantém uma ACL independente. B pode usar a ferramenta "
              "genérica e não tem grant na tabela Riscos.",
              """
        result = await lab.call(token, "especialista___consultar_tabela", {"tabela": "riscos"})
        assert result["result"]["rows"][0]["cliente_id"] == "C001"
        denied = await lab.expect_denial(lab.login("b"), "especialista___consultar_tabela",
                                        {"tabela": "riscos"}, expected="SOURCE_DENY")
        print({"allowed": result, "source_denied": denied})
        """),
        *step("Ler a implementação da ACL independente",
              "GetItem lê a ACL com consistência forte antes de buscar a "
              "linha de dados. A identidade vem do JWT verificado.",
              """
        from santander_demo.aws_workshop.backend import Source
        display(Code(inspect.getsource(Source.read), language="python"))
        """),
        md("**Databricks real na AWS:** substitua este target por uma integração "
           "com workspace AWS e SQL Warehouse, use credencial delegada suportada "
           "pelo provedor e valide `SELECT current_user()` mais queries canário "
           "permitidas/negadas. Com Entra ID, o princípio é semelhante, mas "
           "federation policy, audience e token exchange exigem configuração própria."),
    ]


def memory():
    return [
        *core(), *authentication(),
        *step("Ler a fase implantada pelo IaC",
              "A aula tem cinco transições: inclusão, atualização, revogação, "
              "exclusão e reingestão. O pipeline workshop_lifecycle.py atualiza "
              "os stacks e inicia esta aula em CodeBuild. O runner só observa "
              "a infraestrutura e invoca os serviços; cada fase precisa passar "
              "antes de aplicar a próxima, preservando o mesmo session_id.",
              """
        import os
        from santander_demo.aws_workshop.lifecycle import revision, stage
        from santander_demo.rag.deployment import outputs as rag_outputs
        rag_config = json.loads((ROOT / config["integrations"]["rag"]["config"]).read_text())
        rag_data = rag_outputs(lab.aws, rag_config, "data")
        lifecycle_stage = stage(os.environ.get("WORKSHOP_LIFECYCLE_STAGE", "baseline"))
        session_id = os.environ.get("WORKSHOP_MEMORY_SESSION", "aula15-" + uuid.uuid4().hex)
        assert lab.backend["LifecycleStage"] == lifecycle_stage
        assert rag_data["LifecycleStage"] == lifecycle_stage
        display(Code((ROOT / "scripts/workshop_lifecycle.py").read_text(), language="python"))
        print({"stage": lifecycle_stage, "session_id": session_id,
               "ingestion_job": rag_data["IngestionJobId"]})
        """),
        *step("Inspecionar Memory e a implementação da fonte",
              "AgentCore Memory mantém eventos separados por actor/session. "
              "actor é derivado de issuer/sub verificados; session_id sozinho "
              "não identifica uma pessoa. Guardamos referências para evitar "
              "que uma cópia antiga devolva conteúdo após revogação.",
              """
        control = lab.aws.client("bedrock-agentcore-control")
        memory_resource = control.get_memory(memoryId=lab.backend["MemoryId"])["memory"]
        assert memory_resource["status"] == "ACTIVE"
        print({"memory_id": memory_resource["id"], "status": memory_resource["status"]})
        from santander_demo.aws_workshop.backend import Source
        display(Code(inspect.getsource(Source.remember), language="python"))
        display(Code(inspect.getsource(Source.recall), language="python"))
        """),
        *step("Gravar uma referência no Runtime na primeira fase",
              "O Runtime verifica a ACL de k2 e usa CreateEvent no Memory. "
              "As fases seguintes reutilizam esse evento; gravar outra referência "
              "após a revogação esconderia a prova de reautorização.",
              """
        if lifecycle_stage == "baseline":
            event = await lab.call(token, "especialista___memorizar_referencia",
                                  {"tabela": "k2", "session_id": session_id})
            assert event["result"]["stored"] == "reference_only"
            print(event)
        else:
            assert os.environ.get("WORKSHOP_MEMORY_SESSION"), "Reutilize a sessão da fase baseline"
        """),
        *step("Reautorizar a referência e isolar outra pessoa",
              "C deve receber a versão atual, nunca a cópia antiga. Nas fases "
              "revoked e deleted, a referência antiga precisa produzir uma lista "
              "vazia. A usa o mesmo session_id e permanece isolado em outro actor.",
              """
        own = await lab.call(token, "especialista___recuperar_memoria", {"session_id": session_id})
        other = await lab.call(lab.login("a"), "especialista___recuperar_memoria",
                               {"session_id": session_id})
        documents = own["result"]["documents"]
        assert own["result"]["references_seen"] == 1, "A referência original deve continuar no Memory"
        if lifecycle_stage in {"revoked", "deleted"}:
            assert documents == []
        else:
            assert [x["table"] for x in documents] == ["k2"]
            assert documents[0]["rows"][0]["revision"] == revision(lifecycle_stage)
        assert other["result"]["documents"] == []
        assert other["result"]["references_seen"] == 0
        print({"own": own, "other": other})
        """),
        *step("Conferir ingestão e consultar o documento pela ACL nativa",
              "O provider publica conteúdo e ACL em S3 e aguarda o job de ingestão. "
              "F1 muda de versão, perde o grant de C, é excluído e depois "
              "reingestado. A consulta atravessa o Gateway da Knowledge Base "
              "com JWT Cognito; não usa Retrieve direto com credenciais administrativas.",
              """
        import asyncio
        from santander_demo.rag.client import _retrieve, checked_results, retrieval_arguments, verify_token
        from santander_demo.rag.cognito import login as rag_login
        from santander_demo.rag.transport import correlate
        from santander_demo.journey.evidence import payload
        import time
        rag_access = rag_outputs(lab.aws, rag_config, "access")
        job = lab.aws.client("bedrock-agent").get_ingestion_job(
            knowledgeBaseId=rag_data["KnowledgeBaseId"], dataSourceId=rag_data["DataSourceId"],
            ingestionJobId=rag_data["IngestionJobId"],
        )["ingestionJob"]
        assert job["status"] == "COMPLETE"
        assert job.get("statistics", {}).get("numberOfDocumentsFailed", 0) == 0
        rag_token = rag_login(lab.aws, rag_config, rag_outputs(lab.aws, rag_config, "identity"), "c")
        identity = verify_token(rag_token, rag_config, destination="gateway")
        request_ids = []
        since_ms = int(time.time() * 1000)
        for attempt in range(12):
            result = await _retrieve(
                rag_access["GatewayUrl"], rag_token,
                retrieval_arguments(identity, "Documento F1 dispositivo desconhecido CICLO-F1"),
                request_ids,
            )
            assert not result.isError
            chunks = checked_results(payload(result), "c", rag_data["SourceBucket"])
            selected = [chunk for chunk in chunks if chunk["id"] == "F1"]
            if lifecycle_stage == "revoked":
                matched = not any(chunk["domain"] == "fraude" for chunk in chunks)
            elif lifecycle_stage == "deleted":
                matched = not selected
            else:
                marker = f"CICLO-F1-V{revision(lifecycle_stage)}"
                matched = bool(selected) and all(marker in chunk["text"] for chunk in selected)
            if matched:
                break
            await asyncio.sleep(5)
        assert matched, "A ingestão terminou, mas a mudança ainda não foi comprovada na consulta"
        row = {"case": "c", "gateway_request_ids": request_ids}
        for attempt in range(12):
            correlate(lab.aws, rag_access, [row], since_ms)
            if row["gateway_log_correlation_verified"]:
                break
            await asyncio.sleep(5)
        assert row["gateway_log_correlation_verified"]
        print({"stage": lifecycle_stage, "ingestion_job": rag_data["IngestionJobId"],
               "document_ids": sorted({chunk["id"] for chunk in chunks}), "gateway": row})
        """),
        md("Execute `workshop_lifecycle.py` na ordem baseline → updated → revoked "
           "→ deleted → reingested, com o mesmo `--memory-session`. Cada fase "
           "produz um build e um notebook executado. Depois, aplique baseline "
           "para restaurar o corpus compartilhado antes da jornada completa. "
           "Versões S3 são preservadas; a exclusão didática só alcança F1."),
    ]


def registry_setup():
    return step("Carregar o catálogo implantado",
                "O catálogo tem roles diferentes para desenvolver, publicar, "
                "aprovar e consumir. Os SDKs atuais são agent-registry-control "
                "para governança e agent-registry para descoberta.",
                """
    from santander_demo.registry_workflow.client import RegistryLab
    registry_config = json.loads((ROOT / dependencies["registry"]["config"]).read_text())
    registry = RegistryLab(registry_config)
    assert registry_config["RegistryArn"].startswith("arn:aws:agent-registry:")
    print({"registry": registry_config["RegistryArn"], "states": registry.states()})
    """)


def registry_governance():
    return [
        *registry_setup(),
        *step("Ler o ciclo declarativo de publicação",
              "publish cria o pacote, submit o coloca em revisão e approve "
              "aplica uma decisão com o digest revisado. São stacks separados, "
              "executados pelo pipeline scripts/registry_deploy.py. Inspecione "
              "o recurso e a role responsáveis por cada transição.",
              """
        for phase in ["publish", "submit", "approve"]:
            document = json.loads((ROOT / "infra/registry_workflow/templates" / f"{phase}.json").read_text())
            print(phase)
            display(Code(json.dumps(document, indent=2), language="json"))
        """),
        *step("Verificar estado e histórico do CloudFormation",
              "Consultamos os registros atuais e os stacks responsáveis pelas "
              "transições. Reabrir esta aula não publica nem aprova outro "
              "pacote: para uma nova versão, altere o bundle e execute as fases "
              "pelo pipeline, revisando o digest antes de approve.",
              """
        states = registry.states()
        assert set(states.values()) == {"APPROVED"}
        cfn = registry.operator.client("cloudformation")
        history = {}
        for phase in ["publish", "submit", "approve"]:
            stack = cfn.describe_stacks(StackName=registry_config["prefix"] + "-" + phase)["Stacks"][0]
            assert stack["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
            history[phase] = {"stack": stack["StackName"], "status": stack["StackStatus"]}
        print({"records": states, "pipeline": history})
        """),
        md("**Separação de responsabilidades:** a aprovação autoriza publicar "
           "metadados no catálogo. IAM e Policy continuam decidindo se uma "
           "capacidade pode ser invocada. Nenhuma sugestão de um modelo é "
           "aprovada automaticamente."),
    ]


def registry_personas():
    return [
        *registry_setup(),
        *step("Inspecionar AssumeRole e permissões por persona",
              "STS emite sessões temporárias para as quatro roles. O código "
              "não usa uma credencial administrativa para fingir cada persona. "
              "A matriz consulta o simulador IAM; seu resultado é distinto "
              "das invocações reais da próxima etapa.",
              """
        display(Code(inspect.getsource(registry.persona), language="python"))
        display(Code(inspect.getsource(registry.iam_matrix), language="python"))
        rows = registry.iam_matrix()
        print(json.dumps(rows, indent=2))
        """),
        *step("Executar como consumidor",
              "A descoberta usa a API de dados do Registry. O registro AGENT "
              "é validado contra o ARN e endpoint implantados antes da invocação.",
              """
        records = registry.discover()
        record = next(x for x in records if x["recordId"] == registry_config["AgentRecordId"])
        result = registry.invoke(record)
        assert result["result"]["customer_id"] == "C001"
        print(result)
        """),
        md("**Entra ID/Cognito:** uma aplicação pode autenticar pessoas com "
           "qualquer um desses provedores. Neste exercício a governança é "
           "administrativa e usa IAM/STS; isso não constitui OBO humano."),
    ]


def registry_execution():
    return [
        *registry_setup(),
        *step("Descobrir com uma sessão que não pode invocar",
              "A session policy de STS reduz a sessão do consumidor somente "
              "à descoberta. Encontrar um registro não deve conceder "
              "InvokeAgentRuntime.",
              """
        from botocore.exceptions import ClientError
        restricted = registry.persona("Consumer", discovery_only=True)
        records = registry.discover(restricted)
        record = next(x for x in records if x["recordId"] == registry_config["AgentRecordId"])
        try:
            registry.invoke(record, restricted)
        except ClientError as error:
            assert error.response["Error"]["Code"] in {"AccessDeniedException", "AccessDenied"}
            print({"discovery": "SUCCESS", "invocation": "IAM_DENY"})
        else:
            raise AssertionError("A descoberta concedeu invocação indevida")
        """),
        *step("Invocar com a sessão autorizada",
              "A mesma capacidade pode ser executada pela sessão completa do "
              "consumidor. A resposta deve conter o cliente sintético esperado.",
              """
        result = registry.invoke(record)
        assert result["result"] == {"customer_id": "C001", "risk": "baixo"}
        print(result)
        """),
    ]


def terraform():
    return [
        *step("Ler os recursos Terraform do caminho M2M",
              "O HCL declara Cognito, Identity, Runtime, Gateway e Lambda. "
              "O Runtime usa sua role para obter uma credencial de aplicação "
              "pelo Identity. M2M não representa permissões de uma pessoa.",
              """
        for filename in ["main.tf", "identity.tf", "iam.tf"]:
            display(Code((ROOT / "infra/terraform_agentcore" / filename).read_text(), language="terraform"))
        """),
        *step("Carregar os outputs validados da implantação",
              "O pipeline Terraform verifica a conta, gera um plano revisável "
              "e só aplica esse plano quando os hashes dos arquivos e artefatos "
              "continuam iguais. Os outputs abaixo contêm identificadores, "
              "sem client_secret ou tokens.",
              """
        tf = json.loads((ROOT / dependencies["terraform"]["outputs"]).read_text())
        settings = json.loads((ROOT / dependencies["terraform"]["config"]).read_text())
        import boto3
        aws = boto3.Session(profile_name=settings.get("profile"), region_name=settings["region"])
        assert aws.client("sts").get_caller_identity()["Account"] == tf["account_id"]
        print({k: tf[k] for k in ["runtime_arn", "gateway_url", "workload_name", "provider_name"]})
        """),
        *step("Executar Identity → Gateway → Lambda dentro do Runtime",
              "Duas chamadas verificam clientes sintéticos diferentes. "
              "A terceira inclui inferência Bedrock no Runtime. O verificador "
              "exige IDs de requisição do Gateway e da Lambda.",
              """
        from santander_demo.terraform_lab.client import invoke_runtime
        display(Code(inspect.getsource(invoke_runtime), language="python"))
        for customer in ["C001", "C002"]:
            print(invoke_runtime(tf, aws, customer_id=customer))
        print(invoke_runtime(tf, aws, mode="llm"))
        """),
        md("**Equivalência com Entra:** um cliente confidencial Entra também "
           "pode obter um token de aplicação. Client credentials continua sendo "
           "M2M; delegar a pessoa exige um fluxo e permissões diferentes."),
    ]


def accounts():
    return [
        *step("Confirmar quatro contas reais",
              "Os perfis do operador ou as roles do runner identificam as "
              "contas. IDs repetidos não são aceitos como cenário entre contas.",
              """
        from santander_demo.aws_workshop.config import DOMAINS, check_accounts
        accounts = check_accounts(config, domains=DOMAINS)
        assert len({x["account_id"] for x in accounts.values()}) == 4
        print(json.dumps(accounts, indent=2))
        """),
        *step("Verificar Gateway, Runtime, Policy e Memory em cada domínio",
              "Cada consulta usa a sessão da conta correspondente e o stack "
              "exato. Uma aplicação implantada só na plataforma não satisfaz "
              "esta verificação.",
              """
        environments = {}
        for domain in DOMAINS:
            environments[domain] = AWSWorkshop(CONFIG, domain).preflight()
        print(json.dumps(environments, indent=2))
        """),
        md("**Mapa:** plataforma é o hub C; Retail é a origem A; Transaction "
           "é a fonte B; Lending é o terceiro domínio bancário. IAM/STS "
           "controlam administração e observação. Os Gateways validam a "
           "pessoa por JWT e aplicam suas próprias políticas."),
    ]


def multi_agent():
    return [
        *core(), *authentication(),
        *step("Inspecionar os targets do hub",
              "O Gateway da plataforma agrega os Gateways de Retail, "
              "Transaction e Lending. O schema está no IaC; não precisamos "
              "de um token humano durante a criação dos targets.",
              """
        display(Code((ROOT / "infra/workshop/templates/federation-bindings.json").read_text(), language="json"))
        names = [x["name"] for x in await lab.tools(token)]
        for prefix in ["retail___", "transaction___", "lending___"]:
            assert any(name.startswith(prefix) for name in names)
        print(names)
        """),
        *step("Fazer o agente consultar três contas",
              "O notebook envia perguntas. Escolha de ferramenta, inferência "
              "Bedrock e chamadas MCP executam no Runtime da plataforma.",
              """
        results = {}
        for domain in ["retail-banking", "transaction-banking", "lending-wealth"]:
            result = await lab.invoke_agent(token, "Consulte o risco sintético de C001.", domain=domain)
            assert result["execution"] == "AWS_AGENTCORE_RUNTIME"
            results[domain] = result
        print(json.dumps(results, indent=2, ensure_ascii=False))
        """),
        md("**Relação com os exemplos oficiais:** o serviço Gateway centraliza "
           "a descoberta MCP. Aqui preservamos a pessoa com JWT Cognito e "
           "políticas independentes. O fluxo M2M de aplicação é demonstrado "
           "separadamente no laboratório 09; não equivale a OBO."),
    ]


def federation():
    return [
        *core(), *authentication(),
        *step("Comparar política central e política do domínio",
              "A chamada atravessa dois Gateways. Cada um possui uma engine "
              "em ENFORCE. A decisão do hub não substitui a decisão do domínio.",
              """
        data = AWSWorkshop(CONFIG, "transaction-banking")
        print({"platform": lab.preflight(), "data_account": data.preflight()})
        allowed = await lab.call(token, "transaction___riscos___consultar_risco",
                                 {"cliente_id": "C001", "max_registros": 1})
        print(allowed)
        """),
        *step("Exigir a negativa em ambos os pontos de entrada",
              "B não tem permissão para a ferramenta Riscos. A tentativa "
              "pelo hub e a tentativa no Gateway do domínio devem ser negadas.",
              """
        restricted = lab.login("b")
        arguments = {"cliente_id": "C001", "max_registros": 1}
        print(await lab.expect_denial(restricted, "transaction___riscos___consultar_risco", arguments))
        print(await data.expect_denial(restricted, "riscos___consultar_risco", arguments))
        """),
        md("**Entra ID:** APIs com audiências distintas normalmente exigem "
           "token exchange/OBO configurado para cada salto. A jornada Cognito "
           "declara a mesma audiência de aplicação para a cadeia. O interceptor "
           "REQUEST valida e propaga o JWT pelo header Authorization. "
           "Esse mecanismo não cria um grant OBO no Cognito."),
    ]


def integrated():
    return [
        *registry_setup(),
        *step("Localizar as capacidades publicadas",
              "O Registry oferece metadados aprovados. Endpoints de execução "
              "permanecem limitados aos outputs do IaC, impedindo que uma "
              "descrição de catálogo redirecione credenciais. Os registros "
              "Riscos e Fraude descrevem os dois Runtimes desta aula.",
              """
        from santander_demo.aws_workshop.catalog import origin_bundle, validate_origin_record
        origin = AWSWorkshop(CONFIG, "retail-banking")
        runtimes = {label: origin.outputs("agent-" + label.lower())["RuntimeArn"]
                    for label in ["Riscos", "Fraude"]}
        expected = origin_bundle(origin.identity,
                                 AWSWorkshop(CONFIG).gateway["GatewayUrl"], runtimes)
        records = registry.discover()
        discovered = {}
        reviewer = registry.persona("Approver").client("agent-registry-control")
        for label in ["Riscos", "Fraude"]:
            record = next(x for x in records if x["recordId"] == registry_config[label + "RecordId"])
            assert validate_origin_record(record, expected[label]) == runtimes[label]
            state = reviewer.get_registry_record(
                registryId=registry_config["RegistryId"], recordId=record["recordId"])
            assert state["status"] == "APPROVED"
            discovered[label] = record
            display(Code(record["descriptors"]["custom"]["data"], language="json"))
        print({label: value["recordId"] for label, value in discovered.items()})
        """),
        *step("Examinar as fases de governança dessas capacidades",
              "O pipeline workshop_catalog.py publica descriptors imutáveis, "
              "submete cada registro e aplica a decisão com seu digest revisado. "
              "Os registros dos fundamentos permanecem em seus próprios stacks.",
              """
        for phase in ["origin-publish", "origin-submit", "origin-approve"]:
            display(Code((ROOT / "infra/registry_workflow/templates" / (phase + ".json")).read_text(),
                         language="json"))
        display(Code(inspect.getsource(validate_origin_record), language="python"))
        """),
        *step("Executar os agentes na origem A e consultar a fonte B via hub C",
              "Riscos e Fraude são dois Runtimes na conta Retail. Eles usam "
              "o Gateway da plataforma para chegar ao Gateway de Transaction. "
              "O Runtime da fonte verifica pessoa/aplicação e consulta a ACL.",
              """
        risk_token = origin.login("c", "riscos")
        fraud_token = origin.login("c", "supervisor")
        risk = await origin.invoke_agent(risk_token, "Consulte o risco de C001.",
                                         domain="transaction-banking", phase="agent-riscos")
        fraud = await origin.invoke_agent(fraud_token, "Consulte os indícios de fraude de C001.",
                                          domain="transaction-banking", phase="agent-fraude")
        assert all(x["execution"] == "AWS_AGENTCORE_RUNTIME" for x in [risk, fraud])
        print(json.dumps({
            "riscos": {"registry_record_id": discovered["Riscos"]["recordId"], **risk},
            "fraude": {"registry_record_id": discovered["Fraude"]["recordId"], **fraud},
        }, indent=2, ensure_ascii=False))
        """),
        *step("Negar a audiência da outra aplicação na entrada do Runtime",
              "Um registro aprovado não altera o authorizer. O token de "
              "Supervisor não deve entrar no Runtime de Riscos, nem o token "
              "de Riscos no de Fraude. A rejeição deve acontecer antes do agente.",
              """
        import httpx
        from urllib.parse import quote
        denied = []
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as http:
            for label, wrong_token in [("Riscos", fraud_token), ("Fraude", risk_token)]:
                endpoint = (f"https://bedrock-agentcore.{config['region']}.amazonaws.com/runtimes/"
                            + quote(runtimes[label], safe="") + "/invocations?qualifier=DEFAULT")
                response = await http.post(endpoint, headers={
                    "Authorization": "Bearer " + wrong_token,
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4()),
                }, json={"question": "Consulte C001.", "domain": "transaction-banking"})
                assert response.status_code in {401, 403}
                assert response.headers.get("x-amzn-requestid")
                denied.append({"agent": label, "wrong_audience": "DENIED",
                               "runtime_request_id": response.headers["x-amzn-requestid"]})
        print(denied)
        """),
        md("**Limite da demonstração:** os serviços AgentCore e as contas são "
           "reais. O backend Databricks é um simulador AWS explicitamente "
           "identificado. A aprovação no Registry, a decisão Cedar e o grant "
           "na fonte são evidências distintas."),
    ]


def rag():
    return [
        *step("Ler o conector nativo e a ingestão com ACL",
              "A base MANAGED usa documentos S3 com uma ACL global. O Gateway "
              "expõe o conector nativo e Cedar vincula userContext.userId "
              "ao email do JWT. O modelo só recebe trechos autorizados.",
              """
        from santander_demo.rag.deployment import outputs
        from santander_demo.rag.cognito import login
        from santander_demo.aws_workshop.config import session, stack_outputs
        from santander_demo.aws_workshop.client import stack_name
        rag_config = json.loads((ROOT / dependencies["rag"]["config"]).read_text())
        aws = session(config)
        identity = outputs(aws, rag_config, "identity")
        data = outputs(aws, rag_config, "data")
        access = outputs(aws, rag_config, "access")
        runtime = stack_outputs(aws, stack_name(config, "platform", "rag-agent"))
        display(Code((ROOT / "infra/rag/templates/data.json").read_text(), language="json"))
        kb = aws.client("bedrock-agent").get_knowledge_base(knowledgeBaseId=data["KnowledgeBaseId"])
        assert kb["knowledgeBase"]["status"] == "ACTIVE"
        print({"knowledge_base": data["KnowledgeBaseId"], "runtime": runtime["RuntimeArn"]})
        """),
        *step("Ler o código da recuperação e da geração no Runtime",
              "O Runtime deriva a identidade do token, obtém um WAT, chama "
              "o Gateway e só então invoca Bedrock Converse. A role do Runtime "
              "tem uma negativa explícita de retrieval direto.",
              """
        from santander_demo.aws_workshop.rag_agent import run
        from santander_demo.rag.client import ask
        display(Code(inspect.getsource(run), language="python"))
        display(Code(inspect.getsource(ask), language="python"))
        """),
        *step("Comprovar a negativa de retrieval direto",
              "Este probe executa com a role do próprio Runtime. Uma tentativa "
              "de Retrieve sem passar pelo Gateway deve receber AccessDeniedException "
              "do IAM. Timeout ou outro erro não contam como negativa.",
              """
        import httpx
        from urllib.parse import quote
        url = (f"https://bedrock-agentcore.{config['region']}.amazonaws.com/runtimes/"
               + quote(runtime["RuntimeArn"], safe="") + "/invocations?qualifier=DEFAULT")
        async with httpx.AsyncClient(timeout=240, follow_redirects=False) as http:
            response = await http.post(url, headers={
                "Authorization": "Bearer " + login(aws, rag_config, identity, "c"),
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4()),
            }, json={"operation": "probe_direct_retrieval"})
            response.raise_for_status()
            probe = response.json()
        assert probe == {"execution": "AWS_AGENTCORE_RUNTIME", "direct_retrieval": "IAM_DENY"}
        print(probe)
        """),
        *step("Tentar fornecer a identidade de outra pessoa",
              "Enviamos um JWT válido de A com userContext de C. A Policy deve "
              "negar a inconsistência antes da consulta; esta chamada sai do runner "
              "AWS e mantém os IDs nativos de requisição do Gateway.",
              """
        from santander_demo.rag.client import probe_identity_spoof
        import time
        since_ms = int(time.time() * 1000)
        spoof = await probe_identity_spoof(
            rag_config, access, login(aws, rag_config, identity, "a"),
            rag_config["users"]["c"]["email"],
        )
        assert spoof["outcome"] == "POLICY_DENY_REPORTED"
        assert spoof["gateway_request_ids"]
        print(spoof)
        """),
        *step("Fazer a mesma pergunta como A, B, C e D",
              "A e B recebem apenas documentos de suas áreas; C pode receber "
              "ambas; D deve ser negado antes da geração. Todas as chamadas "
              "de modelo e retrieval acontecem no Runtime.",
              """
        results = {}
        allowed = {"a": {"R1", "R2"}, "b": {"F1", "F2"}, "c": {"R1", "R2", "F1", "F2"}, "d": set()}
        async with httpx.AsyncClient(timeout=240, follow_redirects=False) as http:
            for label in "abcd":
                jwt_token = login(aws, rag_config, identity, label)
                response = await http.post(url, headers={"Authorization": "Bearer " + jwt_token,
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4())},
                    json={"question": "Quais são as políticas de riscos e fraude disponíveis?"})
                response.raise_for_status()
                result = response.json()
                assert result["execution"] == "AWS_AGENTCORE_RUNTIME"
                assert result["gateway_request_ids"]
                assert set(result["document_ids"]) <= allowed[label]
                if label == "d":
                    assert result["outcome"] == "POLICY_DENY_REPORTED" and not result["generated"]
                else:
                    assert result["document_ids"] and result["generated"]
                    assert result["model_request_id"] and result["citations"]
                    assert set(result["citations"]) <= set(result["document_ids"])
                    assert {chunk["id"] for chunk in result["retrieved_context"]} == set(result["document_ids"])
                results[label] = result
        print(json.dumps(results, indent=2, ensure_ascii=False))
        """),
        *step("Verificar cobertura do corpus e decisões nativas",
              "A busca pelos quatro títulos precisa alcançar todos os documentos "
              "permitidos para cada pessoa. O probe executa no mesmo Runtime, "
              "sem geração adicional. Correlacionamos cada Retrieve com o "
              "Gateway e sua decisão Policy antes de aceitar a matriz.",
              """
        import asyncio
        from santander_demo.rag.client import acceptance
        from santander_demo.rag.transport import correlate
        async with httpx.AsyncClient(timeout=240, follow_redirects=False) as http:
            for label in "abc":
                response = await http.post(url, headers={
                    "Authorization": "Bearer " + login(aws, rag_config, identity, label),
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4()),
                }, json={"operation": "coverage"})
                response.raise_for_status()
                coverage = response.json()
                assert coverage["execution"] == "AWS_AGENTCORE_RUNTIME"
                assert set(coverage["coverage_document_ids"]) == allowed[label]
                results[label].update(coverage)
        rows = [*results.values(), spoof]
        for attempt in range(48):
            correlate(aws, access, rows, since_ms)
            if all(row["gateway_log_correlation_verified"] for row in rows):
                break
            await asyncio.sleep(5)
        else:
            raise AssertionError("RAG_NATIVE_POLICY_LOGS_MISSING")
        report = acceptance(rows)
        assert report["status"] == "PASS", report
        print(json.dumps({"acceptance": report, "evidence": rows}, indent=2, ensure_ascii=False))
        """),
        md("**Entra ID:** identidade, Policy e ACL cumprem os mesmos papéis, "
           "mas o provider OAuth, a troca OBO e as claims são próprios do "
           "Entra. A fronteira final continua sendo a ACL nativa da fonte."),
    ]


LESSONS = {
    "00_preflight": ("Serviços AWS e prontidão", preflight),
    "01_gateway_targets": ("Gateway: Lambda e MCP no Runtime", gateway),
    "02_identity_entra_obo": ("Identity: Cognito, workload e adaptação para Entra", identity),
    "03_identity_agente_mcp": ("Pessoa e aplicação na autorização", applications),
    "04_policy_cedar": ("Policy: decisões Cedar no Gateway", policy),
    "05_policy_autoria": ("Policy: autoria assistida e revisão", policy_authoring),
    "06_registry_governanca": ("Registry: publicação e aprovação por IaC", registry_governance),
    "07_registry_personas": ("Registry: quatro personas e IAM", registry_personas),
    "08_registry_descoberta_execucao": ("Descoberta não concede execução", registry_execution),
    "09_integracao_runtime_gateway_identity": ("Runtime MCP, Gateway e identidades", terraform),
    "10_santander_multi_conta": ("Quatro contas AWS e suas fronteiras", accounts),
    "11_blog_multi_account_gateway_mcp": ("Agente central e três domínios AWS", multi_agent),
    "12_gateways_por_conta_identity_policy": ("Gateway e Policy em cada conta", federation),
    "13_databricks_e_evidencias": ("Fonte de dados: simulador Databricks na AWS", source),
    "15_ingestao_acl_memoria": ("AgentCore Memory, identidade e ACL atual", memory),
    "14_cenario_santander_integrado": ("Agentes na origem, hub e fonte entre contas", integrated),
    "16_rag_managed_identity_policy": ("RAG, ACL nativa e inferência no Runtime", rag),
}
