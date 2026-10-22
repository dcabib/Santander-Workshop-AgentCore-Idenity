"""Fonte dos dez notebooks. Saídas ficam vazias no material distribuído."""

from pathlib import Path
from textwrap import dedent

import nbformat as nb
from generate_diagrams import PAGES, image_cell
from notebook_cleanup import cleanup_cells

ROOT = Path(__file__).resolve().parents[1]
SETUP_TEXT = """
### Preparar o ambiente deste notebook

Vamos importar os componentes do workshop, localizar a pasta do projeto e ler
`WORKSHOP_MODE`, cujo padrão é `local`. A instância `lab` reúne o emissor de
tokens de teste, o catálogo em memória, as políticas Cedar e o registro de
evidências que serão usados nas próximas células.

Se o modo for `aws`, também carregaremos `config/local.json` e inicializaremos
o cliente do ambiente configurado. Ao final, a mensagem mostrará o modo ativo;
`LOCAL_SIMULATION` indica que os resultados locais não comprovam a integração
com AWS ou Entra. Reexecutar esta célula reinicia o estado local do laboratório.
"""
SETUP = """
import os
from pathlib import Path
from santander_demo.local import Workshop
from santander_demo.contracts import CLIENTE, DemoError

ROOT = Path.cwd()
if not (ROOT / "pyproject.toml").exists():
    ROOT = ROOT.parent
MODE = os.environ.get("WORKSHOP_MODE", "local")
assert MODE in {"local", "aws"}, "WORKSHOP_MODE deve ser local ou aws"
lab = Workshop()
cloud = None
if MODE == "aws":
    from santander_demo.config import Environment
    from santander_demo.cloud import CloudWorkshop
    config = Environment.load(ROOT / "config/local.json")
    cloud = CloudWorkshop(config)
print("LOCAL_SIMULATION — nenhuma prova de AWS/Entra" if MODE == "local" else "AWS — integração real")
"""
AUTH_TEXT = """
### Obter e verificar a identidade usada nas chamadas

Vamos preparar a variável `token` para as próximas chamadas. No modo local,
o emissor do laboratório criará um JWT de teste para o usuário `ambos`,
habilitado aos cenários de Riscos e Fraude, e verificará sua validade.

No modo AWS, a célula solicitará um token Entra já obtido para a audiência
do Gateway, com entrada oculta por `getpass`, e o validará antes de continuar.
A saída será um resumo da identidade verificada; o token ficará em memória
e não será impresso. Esta etapa prepara a autenticação, mas ainda não executa
uma ferramenta nem demonstra uma troca OBO.
"""
AUTH = """
if MODE == "aws":
    from getpass import getpass
    # Ou use login_confidential_agent(config), que obtém o token via OBO do agente.
    token = getpass("Token Entra de teste para a audiência do Gateway: ")
    identity = cloud.verify_token(token)
    print(identity.summary())
else:
    token = lab.idp.token("ambos")
    print(lab.idp.verifier.verify(token).summary())
"""


def md(text):
    return nb.v4.new_markdown_cell(dedent(text).strip())


def code(text):
    return nb.v4.new_code_cell(dedent(text).strip())


def main(only=None):
    modules = [
        (
            "00_preflight",
            "Preflight e contrato da demo",
            "10 minutos • Referências I5, P1/P3, R1/R2",
            [
                md("""
            O modo **local** usa um emissor JWT efêmero e o avaliador Cedar real. Gateway,
            Registry, contas e fontes são simulados. O modo **aws** faz chamadas reais,
            requer `config/local.json` e os stacks do [runbook](../docs/deploy.md).

            Objetivo: conhecer o ambiente antes de apresentar. Nenhuma célula provisiona recursos.
            Não execute os exemplos AWS originais de criação/limpeza diretamente.
            """),
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            ### Conferir dependências e prontidão

            Vamos exibir as versões instaladas de `boto3`, `mcp`, `cedarpy` e
            `pyjwt` para identificar o ambiente de execução. No modo local,
            verificaremos se as três ferramentas do laboratório estão disponíveis
            e mostraremos quais componentes são simulados.

            No modo AWS, `cloud.preflight()` consultará a configuração existente
            e verificará Gateway e Registry em `READY`, Policy em `ENFORCE` e
            autenticação configurada. Uma asserção interromperá a célula se
            alguma condição não for atendida; passar aqui ainda não comprova OBO.
            """),
                code("""
            import importlib.metadata as metadata
            versions = {name: metadata.version(name) for name in ["boto3", "mcp", "cedarpy", "pyjwt"]}
            print(versions)
            if MODE == "aws":
                print(cloud.preflight())
            else:
                assert len(lab.tools()) == 3
                print({"gateway": "simulado", "registry": "simulado", "cedar": "nativo local",
                       "customer": CLIENTE, "cloud_validated": False})
            """),
                md("""
            **Aceite:** no modo AWS, Gateway e Registry em READY; autoApproval=false;
            JWT Entra com audiência/emissor declarados; Policy em ENFORCE. Um erro encerra o
            exercício. Não “corrigir” configuração via boto3.

            **Para discutir:** quais contas representam origem A, hub C e domínio B?
            Qual aplicação é identificada por `azp`/`appid`? A lista de usuários da demo é
            uma allowlist de OIDs no tenant, não um espelho de grupos produtivos.
            """),
            ],
        ),
        (
            "01_gateway_targets",
            "Gateway: Lambda e servidor MCP",
            "20 minutos • Referências G1, G2, G8",
            [
                md("""
            As tools de Riscos/K2 são Lambda; Fraude é um especialista MCP hospedado em Runtime.
            O supervisor só usa os nomes qualificados anunciados pelo Gateway.
            O teste stdio abaixo valida de verdade o protocolo MCP do backend local; o
            roteamento e o authorizer gerenciados exigem o modo AWS.
            """),
                md(SETUP_TEXT),
                code(SETUP),
                md(AUTH_TEXT),
                code(AUTH),
                md("""
            ### Descobrir os nomes anunciados pelo Gateway

            Vamos montar a lista de ferramentas disponíveis. Em AWS, abriremos
            uma sessão MCP autenticada, faremos `tools/list` e exigiremos os
            nomes qualificados `riscos___consultar_risco` e
            `fraude___consultar_fraude`. Localmente, leremos o catálogo do laboratório.

            Observe os prefixos na lista impressa: eles identificam o target e
            devem coincidir com os nomes usados nas chamadas e nas ações Cedar.
            Listar uma ferramenta ainda não significa ter autorização para executá-la.
            """),
                code("""
            if MODE == "aws":
                from santander_demo.cloud import gateway_session, list_tools
                async with gateway_session(config.gateway_url, token, {config.gateway_url}) as session:
                    names = [t.name for t in await list_tools(session)]
                assert "riscos___consultar_risco" in names
                assert "fraude___consultar_fraude" in names
            else:
                names = [t["name"] for t in lab.tools()]
                assert set(names) == {
                    "riscos___consultar_risco",
                    "riscos___consultar_conhecimento_k2",
                    "fraude___consultar_fraude",
                }
            print(names)
            """),
                md("""
            ### Executar uma chamada e verificar o retorno

            No modo local, vamos iniciar o servidor MCP de Fraude em um processo
            Python, concluir o handshake pelo transporte `stdio` e chamar
            `consultar_fraude` para o cliente sintético, com limite de dez registros.
            Esperamos uma resposta sem erro e `backend_mcp_protocol: PASS`.

            No modo AWS, o ramo executado será outro: chamaremos a ferramenta
            Lambda de Riscos pelo Gateway e verificaremos a marca `synthetic`
            no retorno. O teste local comprova o protocolo do backend; o retorno
            `lambda_via_gateway: PASS` depende da chamada real em AWS.
            """),
                code("""
            import sys
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            if MODE == "local":
                params = StdioServerParameters(command=sys.executable,
                                               args=["-m", "santander_demo.mcp_server"])
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        answer = await session.call_tool("consultar_fraude",
                            {"cliente_id": CLIENTE, "max_registros": 10})
                        assert not answer.isError
                        print({"backend_mcp_protocol": "PASS", "gateway_aws": "NOT_RUN"})
            else:
                result = await cloud.call(token, "riscos___consultar_risco",
                                          {"cliente_id": CLIENTE, "max_registros": 10})
                assert result["synthetic"] is True
                print({"lambda_via_gateway": "PASS"})
            """),
                md("""
            **Exercício:** localize o nome exato em `tools/list` e compare com a ação Cedar.
            A busca semântica interna do Gateway escolhe tools do mesmo Gateway. A busca no
            Registry escolhe capacidades publicadas. Uma não substitui a outra.
            """),
            ],
        ),
        (
            "02_identity_entra_obo",
            "Identity: usuário, M2M e OBO",
            "30 minutos • Referências I1–I3, I5",
            [
                md("""
            No cenário principal, o Gateway valida o token para sua API e o Identity troca
            essa credencial pelo token delegado do Microsoft Graph. A única operação Graph
            exposta é `/me`; não há leitura de emails ou escrita.

            M2M autentica a aplicação. USER_FEDERATION envolve login/consentimento ao recurso.
            OBO usa uma asserção do usuário que já chegou à aplicação. São fluxos distintos.
            """),
                md(SETUP_TEXT),
                code(SETUP),
                md(AUTH_TEXT),
                code(AUTH),
                md("""
            ### Verificar a audiência e a identidade no destino

            No modo AWS, vamos consultar `/me` do Microsoft Graph pelo fluxo
            configurado no Gateway. O helper comparará o OID do usuário do token
            e o ID devolvido pelo Graph com `expected_graph_oid`; esperamos
            `graph_user_matches: True`.

            No modo local, faremos um teste negativo: tentaremos validar o token
            da origem com um verificador que exige a audiência `graph`.
            Esperamos `AUTH_INVALID_TOKEN`, comprovando a separação entre
            audiências. Nesse ramo, Entra OBO e Graph continuarão como `NOT_RUN`.
            """),
                code("""
            if MODE == "aws":
                proof = await cloud.graph_me(token)
                assert proof["graph_user_matches"]
                print(proof)
            else:
                from santander_demo.identity import JwtVerifier
                wrong_audience = JwtVerifier(key=lab.idp._key.public_key(),
                    issuer=lab.idp.issuer, tenant=lab.idp.tenant, audience="graph")
                try:
                    wrong_audience.verify(token)
                    raise AssertionError("Token da origem aceito no destino!")
                except DemoError as exc:
                    assert exc.code == "AUTH_INVALID_TOKEN"
                print({"audience_boundary": "PASS", "entra_obo": "NOT_RUN",
                       "graph_me": "NOT_RUN"})
            """),
                md("""
            **Prova AWS:** execute com usuário A, ajuste `expected_graph_oid` ao OID desse
            usuário e repita com B. A asserção compara IDs exatos, não formato de email.
            `azp` (v2) ou `appid` (v1) identifica o cliente que obteve o token; `tid+oid`
            identifica o principal humano nesse tenant.

            O modo local não emula uma troca OBO bem-sucedida. Registre Entra/Graph como
            não executados até observar as duas identidades reais.
            """),
            ],
        ),
        (
            "03_identity_agente_mcp",
            "Identidade técnica e contexto delegado",
            "25 minutos • Referência I4",
            [
                md("""
            O contrato implantado usa OBO nativo no Gateway também para o Runtime Fraude.
            O Runtime valida sua própria audiência, a aplicação do Gateway e a restrição de
            workload. É uma adaptação de I4: o agente não recebe nem manipula um token Graph.

            O modelo alternativo de I4 (M2M para MCP + token Graph em header separado) é
            material de comparação; não está implantado por este projeto.
            """),
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            ### Comparar dois agentes atuando pelo mesmo usuário

            Vamos emitir dois tokens locais para o usuário `ambos`, mudando
            apenas a aplicação chamadora: `supervisor` ou `riscos`. Primeiro,
            confirmaremos que o supervisor consegue consultar Fraude. Depois,
            repetiremos a consulta como agente de Riscos e exigiremos `POLICY_DENY`.

            O contador de invocações será medido antes e depois da tentativa
            negada para verificar que ela não chegou ao backend. A saída esperada
            é `same_user_different_caller: PASS`. Esta célula usa o laboratório
            local mesmo quando `WORKSHOP_MODE` está definido como `aws`.
            """),
                code("""
            permitted = lab.idp.token("ambos", "supervisor")
            restricted = lab.idp.token("ambos", "riscos")
            assert lab.call(permitted, "fraude___consultar_fraude",
                            {"cliente_id": CLIENTE, "max_registros": 1})["synthetic"]
            before = lab.evidence.backend_invocations
            try:
                lab.call(restricted, "fraude___consultar_fraude",
                         {"cliente_id": CLIENTE, "max_registros": 1})
                raise AssertionError("Chamador indevido autorizado")
            except DemoError as exc:
                assert exc.code == "POLICY_DENY"
            assert lab.evidence.backend_invocations == before
            print({"mode": "LOCAL_SIMULATION", "same_user_different_caller": "PASS"})
            """),
                md("""
            **Prova AWS:** com o mesmo usuário, obtenha tokens por dois clientes Entra
            distintos (supervisor e riscos). Repita a chamada de Fraude; valide a negativa no
            Gateway e a ausência de execução no backend. Não altere `azp` manualmente:
            isso invalida a assinatura.

            Verifique também que chamar o Runtime Fraude diretamente é recusado. O template
            configura `AllowedWorkloadConfiguration` com o ARN do Gateway. A disponibilidade
            desse vínculo para o caminho MCP e entre as contas escolhidas é um gate do ensaio.
            """),
            ],
        ),
        (
            "04_policy_cedar",
            "Policy: autorização por identidade, tool e entrada",
            "35 minutos • Referências P1, P3",
            [
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            A política exige simultaneamente tenant, usuário, aplicação cliente, contexto
            delegado, ação, Gateway e limite de entrada. As allowlists de OIDs são explícitas
            para evitar correspondência ambígua de grupos serializados.

            As mesmas funções geram o Cedar local e o template CloudFormation. A projeção de
            claims para tags no serviço gerenciado ainda precisa ser comprovada em AWS.
            """),
                md("""
            ### Ler as regras Cedar que serão avaliadas

            Vamos renderizar `lab.policy` como texto Cedar para inspecionar as
            regras antes dos testes. Procure as condições de identidade, os
            nomes qualificados das ações, o recurso Gateway e o limite de entrada.

            A saída será o código das políticas gerado pela fonte compartilhada
            com o IaC. Esta célula apenas exibe as regras locais; não publica
            nem avalia uma política no serviço gerenciado.
            """),
                code("""
            from santander_demo.policy import render
            print(render(lab.policy))
            """),
                md("""
            ### Executar a matriz de autorização local

            Vamos rodar os doze cenários de `policy_matrix()`, variando usuário,
            aplicação, ferramenta, limite de registros e claims do token.
            A matriz compara cada resultado com o esperado e verifica que
            chamadas recusadas não aumentam o contador do backend.

            Cada linha mostrará o cenário, o resultado e a quantidade de
            execuções do backend. Esperamos `passed: True` em todas as linhas.
            Observe que erro de autenticação, schema inválido e negativa de
            Policy são resultados distintos; `aws_policy` permanecerá `NOT_RUN`.
            """),
                code("""
            rows = lab.policy_matrix()
            for row in rows:
                print(row)
            assert all(row["passed"] for row in rows)
            print({"mode": "LOCAL_SIMULATION", "aws_policy": "NOT_RUN"})
            """),
                md("""
            ### Conferir a configuração da Policy em AWS

            Se o modo for `aws`, vamos consultar o ambiente para confirmar o
            vínculo do Gateway com a engine e o modo `ENFORCE`, além dos demais
            requisitos do preflight. A saída também indicará o roteiro da
            matriz live em `docs/aceite.md`.

            Esta consulta não executa a matriz no serviço nem modifica a engine.
            No modo local, a saída será `aws_preflight: NOT_RUN`.
            """),
                code("""
            if MODE == "aws":
                # Verifica vínculo e modo efetivo, sem modificar a engine.
                print(cloud.preflight())
                print("Execute a matriz live descrita em docs/aceite.md; registre a evidência nativa.")
            else:
                print({"aws_preflight": "NOT_RUN", "aws_policy_matrix": "NOT_RUN"})
            """),
                md("""
            **Desafio:** mude o limite local de 50 para 51 na política e reexecute os testes.
            O caso de aceite deve falhar. Não transforme erro de schema, erro OAuth ou falha
            do backend em uma suposta negação Cedar. A demo principal mantém ENFORCE.
            """),
            ],
        ),
        (
            "05_policy_autoria",
            "Autoria, revisão e promoção de Cedar",
            "25 minutos • Referência P2",
            [
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            Intenção: “usuários habilitados a Riscos, usando uma aplicação autorizada,
            consultam até 50 registros do Gateway do workshop”.

            A autoria determinística roda localmente. Para geração assistida pelo serviço,
            o stack `policy-draft` recebe o texto em `RawText` e cria um rascunho via IaC.
            O notebook apenas lê esse resultado. O provider não possui permissão para
            publicar políticas. A API não expõe exclusão do histórico de geração; por isso
            o template marca o rascunho como Retain, sem confundi-lo com uma policy ativa.
            """),
                md("""
            ### Inspecionar a regra de Riscos e suas verificações locais

            Vamos obter a regra de `riscos___consultar_risco` e confirmar no texto
            a presença do limite de cinquenta registros e da checagem da tag
            `oid`. Também executaremos a matriz local e verificaremos que ela
            contém os doze cenários previstos.

            Se todas as asserções passarem, a célula imprimirá o Cedar para
            revisão. Trata-se de geração determinística a partir da fonte do
            projeto; esta etapa não solicita geração em linguagem natural ao serviço.
            """),
                code("""
            from santander_demo.policy import statements
            cedar = statements(lab.policy)["riscos___consultar_risco"]
            assert "context.input.max_registros <= 50" in cedar
            assert 'principal.hasTag("oid")' in cedar
            assert len(lab.policy_matrix()) == 12
            print(cedar)
            """),
                md("""
            ### Ler um rascunho gerado anteriormente

            Vamos ler `POLICY_GENERATION_ID` para identificar um rascunho já
            criado pelo stack de autoria. Com esse identificador e o modo AWS
            ativos, consultaremos os assets gerados e exibiremos suas definições
            Cedar e findings, que são os apontamentos retornados para revisão.

            O helper exige que a geração esteja concluída e entrega o resultado
            para revisão, sem publicá-lo. Sem o identificador ou no modo local,
            a saída será `managed_generation: NOT_RUN`; nenhuma geração será iniciada.
            """),
                code("""
            generation_id = os.environ.get("POLICY_GENERATION_ID")
            if MODE == "aws" and generation_id:
                draft = cloud.policy_draft(generation_id)
                assert draft["review_required"] and not draft["published"]
                for asset in draft["assets"]:
                    print({"definition": asset["definition"], "findings": asset.get("findings", [])})
            else:
                print({"managed_generation": "NOT_RUN", "local_cedar": "VALIDATED_LOCAL",
                       "human_review": "PENDING"})
            """),
                md("""
            **Revisão em dupla:**
            1. Tenant, OID e aplicação vêm de claims assinadas?
            2. A ação e o recurso são exatos?
            3. O limite está no mesmo `permit` das condições de identidade?
            4. Há testes de usuário, chamador, claim ausente e nomes semelhantes?
            5. O change set usa `FAIL_ON_ANY_FINDINGS`?

            Altere a fonte em `src/santander_demo/policy.py`, gere os templates, execute os
            testes e revise o change set antes do deploy pelo pipeline do projeto.
            """),
            ],
        ),
        (
            "06_registry_governanca",
            "Registry: publicação, aprovação e consumo",
            "25 minutos • Referências R1, R2, R5",
            [
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            O laboratório usa Registry com busca AWS_IAM, sessões STS e autoApproval=false.
            Entra autentica o Gateway; não é usado como authorizer do Registry nesta variante.
            Publisher publica/submete; Approver aprova/rejeita; Consumer busca.

            No modo AWS, os estados são preparados por recursos de CloudFormation. As
            operações de publicação abaixo alteram apenas o modelo em memória.
            """),
                md("""
            ### Percorrer publicação, submissão e aprovação local

            Vamos criar o registro `exercicio` no catálogo em memória e submetê-lo
            como `publisher`. Em seguida, tentaremos aprová-lo com esse mesmo
            papel e esperaremos `REGISTRY_APPROVAL_DENIED`. A aprovação será
            repetida como `approver`, após o que uma busca deverá encontrar a proposta.
            Também verificaremos que ela fica invisível na busca enquanto
            estiver em `DRAFT` ou `PENDING_APPROVAL`.

            A saída mostrará os estados dos registros locais e permitirá observar
            a separação de responsabilidades. Esta célula sempre usa `lab.registry`;
            para repetir o exercício desde o início, reexecute a preparação do ambiente.
            """),
                code("""
            from santander_demo.registry import Record
            registry = lab.registry
            registry.publish(Record("exercicio", "demo", "proposta de capacidade"), "publisher")
            assert registry.records["exercicio"].state == "DRAFT"
            assert not registry.search("proposta")
            registry.submit("exercicio", "publisher")
            assert registry.records["exercicio"].state == "PENDING_APPROVAL"
            assert not registry.search("proposta")
            try:
                registry.decide("exercicio", "APPROVED", "publisher")
                raise AssertionError("Publisher aprovou a própria publicação")
            except DemoError as exc:
                assert exc.code == "REGISTRY_APPROVAL_DENIED"
            assert registry.records["exercicio"].state == "PENDING_APPROVAL"
            registry.decide("exercicio", "APPROVED", "approver")
            assert [record["name"] for record in registry.search("proposta")] == ["exercicio"]
            print({"mode": "LOCAL_SIMULATION", "states": {k: r.state for k, r in registry.records.items()}})
            """),
                md("""
            ### Consultar os estados existentes no Registry AWS

            No modo AWS, vamos listar os registros do Registry configurado e
            verificar se o conjunto inclui `DRAFT`, `PENDING_APPROVAL`, `APPROVED`
            e `REJECTED`, preparados anteriormente pelo CloudFormation.

            Esperamos ver os nomes e estados dos registros. Se algum dos quatro
            estados estiver ausente, a asserção falhará. No modo local, esta
            célula não fará consultas e mostrará `aws_registry_states: NOT_RUN`.
            """),
                code("""
            if MODE == "aws":
                states = cloud.registry_states()
                assert {"DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED"} <= {r["status"] for r in states}
                print(states)
            else:
                print({"aws_registry_states": "NOT_RUN"})
            """),
                md("""
            **Gate IAM:** validar permissões dos três roles com `iam simulate-principal-policy`
            (read-only) e revisar as trust policies. Não criar usuários/chaves para o workshop.
            O provider de publicação não tem `UpdateRegistryRecordStatus`; o de aprovação
            não tem `CreateRegistryRecord`. Aprovação de um registro não autoriza a tool.
            """),
            ],
        ),
        (
            "07_registry_descoberta_execucao",
            "Descoberta em runtime e execução autorizada",
            "20 minutos • Referências R3, R4",
            [
                md(SETUP_TEXT),
                code(SETUP),
                md(AUTH_TEXT),
                code(AUTH),
                md("""
            ### Buscar capacidades e executar com a identidade disponível

            Vamos pedir ao supervisor que descubra capacidades no Registry e
            tente usá-las pelo Gateway. Em AWS, `cloud.analyze(token)` utilizará
            a identidade verificada na célula anterior e retornará os resultados
            das integrações configuradas.

            Localmente, a célula criará deliberadamente um token do usuário
            `riscos`, em vez de reutilizar o token `ambos`. Esperamos duas consultas
            de Riscos bem-sucedidas e `POLICY_DENY` para Fraude, mostrando que
            descobrir Fraude no catálogo não concede permissão para executá-la.
            """),
                code("""
            if MODE == "aws":
                result = await cloud.analyze(token)
            else:
                result = lab.analyze(lab.idp.token("riscos"))
                local_results = {item["tool"]: item for item in result["results"]}
                assert len(local_results) == 3
                assert local_results["riscos___consultar_risco"]["synthetic"]
                assert local_results["riscos___consultar_conhecimento_k2"]["synthetic"]
                assert local_results["fraude___consultar_fraude"]["outcome"] == "POLICY_DENY"
            print(result)
            """),
                md("""
            O supervisor determinístico busca no catálogo, valida estado/endpoint/schema,
            conecta ao Gateway e recebe a decisão de Policy. Em AWS a busca é semântica;
            localmente é lexical. Não há LLM nesta trilha para manter a prova reproduzível.

            **Exercício:** compare os resultados de Riscos e Riscos+Fraude. A capacidade
            Fraude pode ser encontrada pelos dois; apenas o segundo está autorizado.
            Caso a busca não retorne registros recém-aprovados, aguarde a propagação do
            índice e registre a latência. Não chame o backend diretamente para contornar isso.
            """),
            ],
        ),
        (
            "08_santander_multi_conta",
            "Composição A → C → B",
            "25 minutos • Referências G5, I4/I5, P3, R3",
            [
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            A: supervisor Runtime; C: Registry, Gateway, Identity e Policy; B: Fraude MCP.
            A busca usa AssumeRole temporário em C. A chamada leva o JWT destinado ao Gateway.
            C faz OBO para a audiência de B; B verifica também o workload do Gateway.

            Contas diferentes no desenho não provam uma execução multi-conta.
            """),
                md("""
            ### Verificar a distribuição declarada entre as contas

            No modo AWS, vamos inspecionar a configuração e exigir três IDs de
            conta distintos. O helper também verificará se os ARNs do supervisor,
            Gateway, Registry e Runtime Fraude correspondem às contas e à região
            declaradas. Esperamos `distinct_accounts: 3` e `execution_verified: False`.

            Essa validação examina os identificadores configurados, sem invocar
            o supervisor nem comprovar comunicação entre contas. No modo local,
            a saída listará os pré-requisitos e manterá `multi_account_verified: False`.
            """),
                code("""
            if MODE == "aws":
                from santander_demo.live import topology
                print(topology(config))
            else:
                print({"mode": "LOCAL_SIMULATION", "multi_account_verified": False,
                       "requires": ["AWS A/C/B", "Entra apps", "Registry READY", "Runtime READY"]})
            """),
                md("""
            Para a prova, use `invoke_supervisor` em `santander_demo.live` com token em memória,
            depois registre Gateway/Runtime request IDs e logs por fronteira. O resultado
            deve conter as tools de Riscos e Fraude. O helper recusa chamar “multi-conta”
            quando A, B e C são a mesma conta. Veja o [aceite](../docs/aceite.md).

            **Limite:** essa composição demonstra as ferramentas sintéticas. Não demonstra
            automaticamente o produto K2 nem grants de uma fonte real.
            """),
            ],
        ),
        (
            "09_databricks_e_evidencias",
            "Delegação na fonte e fechamento das evidências",
            "10 minutos + extensão • Referências D1, D2, G6",
            [
                md(SETUP_TEXT),
                code(SETUP),
                md("""
            Esta é uma prova isolada por SQL REST. O fluxo integrado Gateway → MCP DBSQL
            está no [notebook 12](12_cenario_santander_integrado.ipynb).

            Esta extensão exige federation de usuários no nível da conta Databricks,
            token exchange, um warehouse Azure e uma tabela canário sintética com grants distintos.
            A preparação desses recursos deve seguir o IaC do cliente. O projeto não altera
            Unity Catalog, BDAGs ou permissões do cliente.

            O adapter recusa token ausente, troca inválida e principal divergente. Não há
            fallback para service principal. Formato de email não comprova identidade.
            """),
                md("""
            ### Comprovar o usuário delegado e o acesso à tabela canário

            Esta etapa só será executada com `WORKSHOP_MODE=aws` e
            `RUN_DATABRICKS=true`. Vamos conferir os parâmetros do workspace,
            solicitar o JWT Entra com entrada oculta e usar o adapter para
            realizar a troca de token e consultar o SQL Warehouse.

            O helper deverá comprovar que `current_user()` coincide exatamente
            com o usuário esperado e que ele consegue acessar a tabela canário
            configurada. Após a chamada, a variável do JWT será removida.
            Sem os dois controles ativos, Databricks e grants ficarão como `NOT_RUN`.
            """),
                code("""
            proof = None
            if MODE == "aws" and os.environ.get("RUN_DATABRICKS") == "true":
                from getpass import getpass
                from santander_demo.databricks import DelegatedDatabricks
                assert all([config.databricks_host, config.databricks_warehouse,
                            config.expected_databricks_user, config.databricks_canary_table])
                delegated = DelegatedDatabricks(config.databricks_host,
                    config.databricks_warehouse, config.expected_databricks_user)
                user_jwt = getpass("Token Entra para a federation do Databricks: ")
                try:
                    proof = delegated.prove(user_jwt, config.databricks_canary_table,
                                            expect_grant=True)
                finally:
                    del user_jwt
                    delegated.http.close()
                print(proof)
            else:
                print({"databricks_azure": "NOT_RUN", "unity_catalog_grants": "NOT_RUN"})
            """),
                md("""
            ### Salvar as evidências dos testes locais

            Vamos executar novamente a matriz de autorização para registrar seus
            resultados no coletor local. Em seguida, exportaremos as evidências
            em JSON para `evidence/local-notebook.json`, criando a pasta caso
            necessário e substituindo esse arquivo se ele já existir.

            A saída mostrará o caminho salvo e `LOCAL_SIMULATION`. O arquivo
            documenta os testes de `lab`, inclusive quando o notebook está no
            modo AWS. A prova Databricks, se executada, será salva separadamente
            em `evidence/databricks-rest-live.json`, sem token ou e-mail.
            """),
                code("""
            import json
            lab.policy_matrix()
            target = ROOT / "evidence/local-notebook.json"
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(lab.evidence.export(), ensure_ascii=False, indent=2))
            print({"evidence": str(target), "mode": "LOCAL_SIMULATION"})
            if proof is not None:
                (ROOT / "evidence/databricks-rest-live.json").write_text(
                    json.dumps(proof, ensure_ascii=False, indent=2) + "\\n")
            """),
                md("""
            Repita a prova Databricks com usuário sem grant e `expect_grant=False`. O helper
            exige erro de permissão, não aceita erro SQL genérico como evidência.
            Para fechar: complete `docs/aceite.md`, separe PASS local de PASS AWS e remova
            outputs de notebooks interativos que possam conter informações do ambiente.
            """),
            ],
        ),
    ]
    path = ROOT / "notebooks"
    path.mkdir(exist_ok=True)
    diagrams = {page["id"]: page for page in PAGES}
    for filename, title, timing, cells in modules:
        if only is not None and filename != only:
            continue
        diagram = nb.from_dict(image_cell(diagrams[filename]))
        diagram.source = "".join(diagram.source)
        notebook = nb.v4.new_notebook(
            cells=[
                md(
                    f"# {title}\n\n{timing}\n\n"
                    "Referências: [catálogo e links fixados](../referencias-notebooks-agentcore.md).\n"
                    "Execute com o kernel Python de `.venv`."
                )
            ]
            + [diagram]
            + cells
            + cleanup_cells(filename, "workshop"),
            metadata={
                "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                "language_info": {"name": "python", "version": "3.12"},
            },
        )
        nb.validate(notebook)
        nb.write(notebook, path / f"{filename}.ipynb")


if __name__ == "__main__":
    main()
