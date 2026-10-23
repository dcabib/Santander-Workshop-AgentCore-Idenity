"""Conceitos e leituras oficiais incorporados aos notebooks pelos seus geradores."""

from textwrap import dedent

import nbformat as nb

AGENTCORE = "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/"
ENTRA = "https://learn.microsoft.com/pt-br/entra/identity-platform/"

# A numeração acompanha a ordem pedagógica dos laboratórios.
LEARNING_PATH = (
    ("00_preflight", "Primeira execução"),
    ("01_gateway_targets", "Gateway e ferramentas"),
    ("02_identity_entra_obo", "Identidade e OBO"),
    ("03_identity_agente_mcp", "Identidade do agente"),
    ("04_policy_cedar", "Autorização Cedar"),
    ("05_policy_autoria", "Autoria de políticas"),
    ("06_registry_governanca", "Governança do catálogo"),
    ("07_registry_personas", "Ciclo de vida com quatro personas"),
    ("08_registry_descoberta_execucao", "Descoberta e execução"),
    ("09_terraform_runtime_gateway_identity", "Implantação com Terraform"),
    ("10_santander_multi_conta", "Arquitetura entre contas"),
    ("11_blog_multi_account_gateway_mcp", "Agente central e três áreas"),
    ("12_gateways_por_conta_identity_policy", "Gateway por conta"),
    ("13_databricks_e_evidencias", "Identidade na fonte"),
    ("14_cenario_santander_integrado", "Cenário integrado"),
    ("15_ingestao_acl_memoria", "Ingestão, ACL e memória"),
    ("16_rag_managed_identity_policy", "RAG por usuário"),
)
LEARNING_ORDER = tuple(name[:2] for name, _ in LEARNING_PATH)

# Os caminhos relativos são resolvidos a partir de notebooks/, onde o aluno lê.
LESSONS = {
    "07": {
        "concepts": """
        **Desenvolver** produz código e um contrato testado. **Publicar** registra
        esse contrato como rascunho e o submete à revisão. **Aprovar** torna os
        metadados disponíveis para descoberta. **Consumir** exige ainda autorização
        no serviço anunciado. As quatro responsabilidades não são intercambiáveis.

        Um registro **MCP** descreve um servidor e suas ferramentas; um registro
        **AGENT** descreve um agente. Aqui o agente é determinístico, usa Runtime
        HTTP e um descritor `custom`; não anuncia compatibilidade A2A.
        O hash SHA-256 vincula a decisão ao bundle revisado, sem substituir
        assinatura, autenticação ou teste do código.

        O caminho AWS usa a API atual `agent-registry`, funções CloudFormation
        com roles separadas e sessões temporárias STS. A bancada em memória
        ensina os estados; somente os testes AWS verificam os serviços.
        """,
        "references": [
            ("Tipos de registros e descritores", AGENTCORE + "registry-supported-record-types.html"),
            ("Ciclo de vida de um registro", AGENTCORE + "registry-record-lifecycle.html"),
            ("Permissões IAM de controle e descoberta", AGENTCORE + "registry-iam-permissions.html"),
        ],
    },
    "00": {
        "concepts": """
        **Preflight** é uma conferência de pré-requisitos: um recurso em `READY`
        está disponível, mas esse estado não comprova uma chamada ponta a ponta.
        **Runtime** hospeda o código; **Gateway** expõe ferramentas; **Identity**
        gerencia identidades de workload e credenciais para outros serviços.
        **Policy** decide se uma chamada é permitida; **Registry** cataloga capacidades.

        **Autenticação** verifica quem apresenta a credencial e a quem ela se destina.
        **Autorização** decide quais ações essa identidade pode executar. Por isso,
        aceitar um JWT não significa permitir todas as ferramentas.

        Leia `CloudWorkshop.preflight()` em [cloud.py](../src/santander_demo/cloud.py)
        e compare suas asserções com a saída. Nesta etapa, `user_obo_verified=False`
        é esperado: a troca de token será exercitada em outro notebook.
        """,
        "references": [
            ("Visão geral dos componentes AgentCore", AGENTCORE + "what-is-bedrock-agentcore.html"),
            ("Autenticação de entrada do Gateway", AGENTCORE + "gateway-inbound-auth.html"),
            ("Modos de aplicação de Policy", AGENTCORE + "policy-enforcement-modes.html"),
        ],
    },
    "01": {
        "concepts": """
        **MCP (Model Context Protocol)** padroniza a conversa entre cliente e servidor:
        `initialize` negocia a sessão, `tools/list` descreve ferramentas e
        `tools/call` executa uma delas. O **schema** declara os argumentos aceitos.
        `stdio` transporta mensagens entre processos locais; na AWS usamos HTTP.

        Um **target** é o destino conectado ao Gateway. Uma Lambda recebe argumentos
        como evento; um servidor MCP já implementa o protocolo. O Gateway acrescenta
        o prefixo `target___tool` para distinguir ferramentas de destinos diferentes.
        Esse nome também aparece na ação autorizada pelo Cedar.

        Compare [mcp_server.py](../src/santander_demo/mcp_server.py), que implementa
        o servidor local, com `gateway_session()` em
        [cloud.py](../src/santander_demo/cloud.py). O teste local de protocolo
        não passa pelo authorizer nem pelo roteamento do Gateway AWS.
        """,
        "references": [
            ("Especificação MCP: ferramentas", "https://modelcontextprotocol.io/specification/2025-11-25/server/tools"),
            ("Target Lambda e contrato do evento", AGENTCORE + "gateway-add-target-lambda.html"),
            ("Target de servidor MCP", AGENTCORE + "gateway-target-MCPservers.html"),
        ],
    },
    "02": {
        "concepts": """
        **JWT** é um formato de token com claims, isto é, informações assinadas.
        `iss` identifica o emissor, `aud` a API destinatária e `exp` a expiração.
        **JWKS** publica as chaves usadas para verificar a assinatura; simplesmente
        decodificar o token não valida sua autenticidade.

        **M2M**, com `client_credentials`, representa uma aplicação. **OBO
        (on-behalf-of)** permite que uma aplicação obtenha um novo token delegado
        para outra API em nome do usuário. O token original não deve ser reutilizado
        numa API de audiência diferente. O fluxo exige configuração e consentimentos
        no provedor de identidade (**IdP**).

        No Entra, `tid` + `oid` identifica o usuário no tenant; `azp`/`appid`
        identifica a aplicação chamadora. Confira a verificação em
        [identity.py](../src/santander_demo/identity.py) e a comparação com Graph
        em `CloudWorkshop.graph_me()` de [cloud.py](../src/santander_demo/cloud.py).
        """,
        "references": [
            ("Microsoft: fluxo OBO", ENTRA + "v2-oauth2-on-behalf-of-flow"),
            ("Microsoft: claims de access tokens", ENTRA + "access-token-claims-reference"),
            ("AgentCore Identity: troca OBO", AGENTCORE + "on-behalf-of-token-exchange.html"),
        ],
    },
    "03": {
        "concepts": """
        **Usuário, aplicação e workload são identidades diferentes.** A pessoa pode
        usar vários agentes; cada agente apresenta sua própria identidade de aplicação.
        Uma workload é a execução de software, como um Gateway ou Runtime.

        A política deste exercício combina o usuário (`oid`) e o chamador (`azp`).
        Por isso, manter o usuário e trocar `supervisor` por `riscos` pode mudar
        a decisão. Os argumentos da ferramenta não escolhem essas claims.

        A **restrição de workload** do Runtime é uma fronteira adicional ao JWT:
        no IaC, ela limita o chamador ao Gateway declarado. O teste desta célula
        verifica apenas Cedar local. A recusa de acesso direto ao Runtime exige
        o ensaio AWS com a audiência correta, descrito depois.
        Veja [policy.py](../src/santander_demo/policy.py) e
        [infra/generate.py](../infra/generate.py).
        """,
        "references": [
            ("Entrada e saída autenticadas no Runtime", AGENTCORE + "runtime-oauth.html"),
            ("Claims que identificam usuário e aplicação", ENTRA + "access-token-claims-reference"),
            ("Identity: delegação OBO", AGENTCORE + "on-behalf-of-token-exchange.html"),
        ],
    },
    "04": {
        "concepts": """
        **Cedar** expressa decisões sobre `principal` (quem), `action` (o quê),
        `resource` (qual recurso) e `context` (dados adicionais da chamada).
        Aqui, o recurso é o Gateway e os argumentos aparecem em `context.input`.

        Uma regra `permit` precisa satisfazer todas as suas condições. Sem um
        `permit` aplicável, o acesso é negado; um `forbid` aplicável prevalece sobre
        permissões. **ENFORCE** aplica a decisão. **LOG_ONLY** permite observar
        avaliações sem usar suas negativas como bloqueio.

        `Workshop.call()` em [local.py](../src/santander_demo/local.py) verifica
        JWT, nome da ferramenta e entrada antes de avaliar Cedar. Só depois chama
        o backend. Isso explica os resultados distintos `AUTH_INVALID_TOKEN`,
        `UNKNOWN_TOOL`, `SCHEMA_INVALID` e `POLICY_DENY` na matriz.
        """,
        "references": [
            ("Sintaxe e semântica das políticas Cedar", "https://docs.cedarpolicy.com/policies/syntax-policy.html"),
            ("Autoria de políticas no AgentCore", AGENTCORE + "policy-authoring-guide.html"),
            ("ENFORCE e LOG_ONLY", AGENTCORE + "policy-enforcement-modes.html"),
        ],
    },
    "05": {
        "concepts": """
        **Autoria**, **validação** e **publicação** são etapas diferentes.
        Descrever a intenção em linguagem natural produz um candidato a política;
        não concede acesso por si só. Os **findings** são apontamentos do serviço
        sobre o candidato e precisam ser examinados junto com o comportamento desejado.

        Este notebook tem dois caminhos: geração determinística de Cedar a partir
        de [policy.py](../src/santander_demo/policy.py), e leitura de um rascunho
        gerado previamente pelo stack `policy-draft`. Nenhum deles publica uma
        política por esta célula.

        Um **change set** mostra as alterações propostas ao CloudFormation antes
        de aplicá-las. `FAIL_ON_ANY_FINDINGS` é uma propriedade de validação dos
        recursos de Policy no template; revise-a junto com o change set.
        **Retain** preserva o recurso ao excluir o stack: não significa que o
        rascunho foi aprovado ou se tornou uma política ativa.
        """,
        "references": [
            ("Validação de políticas geradas", AGENTCORE + "policy-generation-validation.html"),
            ("Guia de autoria de Policy", AGENTCORE + "policy-authoring-guide.html"),
            ("CloudFormation: revisão de change sets", "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html"),
        ],
    },
    "06": {
        "concepts": """
        **Registry** é um catálogo de metadados de capacidades. Um registro descreve
        uma ferramenta ou servidor; ele não armazena uma permissão para executar
        qualquer coisa publicada ali.

        Neste contrato, o **publicador** cria e submete; o **aprovador** decide;
        o **consumidor** pesquisa registros aprovados. Os estados usados são
        `DRAFT` → `PENDING_APPROVAL` → `APPROVED` ou `REJECTED`.
        Desativar aprovação automática separa publicação de disponibilidade na busca.

        [registry.py](../src/santander_demo/registry.py) simula esses papéis com
        strings em memória. Na AWS, a separação depende de roles e políticas IAM,
        com credenciais temporárias do STS. O teste local de papel não comprova
        que as permissões IAM do ambiente estão corretas.
        """,
        "references": [
            ("Conceitos do AWS Agent Registry", AGENTCORE + "registry.html"),
            ("Revisão e aprovação de registros", AGENTCORE + "registry-reviewing-records.html"),
            ("Pesquisa de registros", AGENTCORE + "registry-search-records.html"),
        ],
    },
    "08": {
        "concepts": """
        **Descoberta** encontra uma capacidade; **autorização** decide se ela pode
        ser usada naquela chamada. A busca lexical local compara texto; a busca
        semântica AWS procura registros relevantes para o significado da consulta.

        O endpoint descoberto precisa coincidir com o Gateway permitido antes de
        enviar um **bearer token**: quem possui esse token pode apresentá-lo ao
        serviço destinatário. Um catálogo não deve encaminhar a credencial para
        qualquer URL anunciada.

        Em [cloud.py](../src/santander_demo/cloud.py), `search()` filtra registros
        aprovados do Registry configurado; `analyze()` valida endpoints e nomes
        conhecidos; `call()` confirma que a ferramenta é anunciada pelo Gateway.
        A validação do schema de entrada é responsabilidade do caminho de execução,
        não uma validação completa dos documentos JSON do Registry pelo supervisor.
        """,
        "references": [
            ("Busca no Agent Registry", AGENTCORE + "registry-search-records.html"),
            ("Autenticação de entrada no Gateway", AGENTCORE + "gateway-inbound-auth.html"),
            ("Autorização das interações com Policy", AGENTCORE + "policy.html"),
        ],
    },
    "10": {
        "concepts": """
        Uma arquitetura **multi-conta** distribui propriedade e permissões.
        **AssumeRole** obtém uma sessão IAM temporária em outra conta; a role
        precisa permitir a operação e confiar no chamador.

        A sessão IAM usada para pesquisar o Registry e o JWT usado para chamar
        o Gateway têm finalidades distintas. A troca **OBO** produz a credencial
        destinada à API seguinte; não transforma automaticamente uma role IAM
        numa identidade humana.

        `topology()` em [live.py](../src/santander_demo/live.py) confere contas,
        região e ARNs declarados. Um **ARN** é o identificador de um recurso AWS.
        Somente `invoke_supervisor()` envia a chamada ao Runtime; mesmo uma
        resposta correta precisa dos logs para comprovar todo o percurso.
        """,
        "references": [
            ("IAM: acesso entre contas por roles", "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_aws-accounts.html"),
            ("Autenticação do Runtime", AGENTCORE + "runtime-oauth.html"),
            ("Autenticação de saída do Gateway", AGENTCORE + "gateway-outbound-auth.html"),
        ],
    },
    "13": {
        "concepts": """
        **Federação** permite que o destino confie num provedor de identidade externo.
        **Token exchange** troca essa credencial por outra aceita pelo Databricks.
        O **SQL Warehouse** executa SQL; **Unity Catalog** controla permissões
        como `SELECT` sobre os dados.

        `current_user()` mostra quem a fonte reconheceu, enquanto uma consulta
        à tabela canário verifica um grant específico. São duas provas distintas:
        login válido não garante acesso à tabela. Uma tabela **canário** contém
        dados sintéticos preparados para tornar esse teste observável.

        `DelegatedDatabricks.prove()` em
        [databricks.py](../src/santander_demo/databricks.py) compara a identidade
        exata e verifica sucesso ou um código de permissão esperado. A consulta
        usa `SELECT 1 ... LIMIT 1`; o objetivo é provar acesso, sem exibir os dados.
        """,
        "references": [
            ("Databricks: função current_user", "https://learn.microsoft.com/pt-br/azure/databricks/sql/language-manual/functions/current_user"),
            ("Databricks: API SQL Statement Execution", "https://learn.microsoft.com/pt-br/azure/databricks/dev-tools/sql-execution-tutorial"),
            ("Unity Catalog: gerenciamento de privilégios", "https://learn.microsoft.com/pt-br/azure/databricks/data-governance/unity-catalog/manage-privileges/"),
        ],
    },
    "11": {
        "concepts": """
        **LOB (line of business)** significa área de negócio. Aqui Retail,
        Transaction e Lending pertencem a contas diferentes. **Strands** executa
        o ciclo do agente: o modelo solicita ferramentas, recebe resultados e
        produz uma resposta. A escolha feita pelo modelo não concede permissão.

        **RAG (geração aumentada por recuperação)** fornece ao modelo trechos
        recuperados de uma base de conhecimento (**KB**). Na LOB Lending,
        `Retrieve` busca os trechos com a role IAM do servidor MCP. Esta variante
        não transmite a identidade humana até a KB.

        **Guardrails** avaliam conteúdo de entrada e saída; **Policy** autoriza
        ferramentas. Veja a aplicação explícita do Guardrail em
        [banking/agent.py](../src/santander_demo/banking/agent.py).
        O IaC em [infra/banking/generate.py](../infra/banking/generate.py)
        publica `ReadTools` e `NeverDelete`, deixando `WriteTools` fora do deploy.
        """,
        "references": [
            ("Gateway: credenciais de saída", AGENTCORE + "gateway-outbound-auth.html"),
            ("Bedrock Guardrails", "https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html"),
            ("Bedrock Converse: mensagens e inferência", "https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html"),
        ],
    },
    "12": {
        "concepts": """
        **Federação de Gateways** preserva decisões independentes: permitir na
        plataforma não obriga a área de negócio a permitir. O nome
        `retail___backend___get_profile` reflete os dois targets atravessados.

        Em cada troca **OBO**, o destinatário (`aud`) e a aplicação (`azp`) podem
        mudar. A pessoa continua identificada por `tid` + `oid`; `sub` pode variar
        entre aplicações. **Whoami** é uma ferramenta diagnóstica que verifica
        o JWT recebido e relata uma prova reduzida da identidade.

        Veja `verify_chain()` em
        [federation/client.py](../src/santander_demo/federation/client.py)
        e a verificação no destino em
        [runtime_identity.py](../src/santander_demo/federation/runtime_identity.py).
        A delegação termina nos MCPs; DynamoDB e KB continuam usando roles IAM
        das LOBs. Isso não comprova grants individuais nessas duas fontes.
        """,
        "references": [
            ("Entra: fluxo OBO", ENTRA + "v2-oauth2-on-behalf-of-flow"),
            ("AgentCore Identity: troca OBO", AGENTCORE + "on-behalf-of-token-exchange.html"),
            ("Entrada JWT no AgentCore", AGENTCORE + "inbound-jwt-authorizer.html"),
        ],
    },
    "14": {
        "concepts": """
        **Policy no Gateway** controla quem chama qual ferramenta; **grants na
        fonte** controlam quem consulta o dado. Este roteiro demonstra por que
        precisamos dos dois: B pode passar pela Policy e receber uma negativa
        de `SELECT` no Unity Catalog.

        **Trace** é a correlação de eventos entre componentes por identificadores
        de requisição. Um `request_id` no retorno não demonstra, sozinho, que um
        backend deixou de executar. Por isso
        [journey/evidence.py](../src/santander_demo/journey/evidence.py)
        mantém pendências até reunir as evidências por fronteira.

        **QPM** limita consultas por minuto; **TPM** limita tokens por minuto;
        **orçamento mensal** limita custo acumulado. O contador em
        [governance.py](../src/santander_demo/governance.py) usa valores sintéticos
        e chaves por agente/ferramenta. Ele não é um medidor de faturamento AWS,
        nem a implementação de Policy temporal do serviço.
        """,
        "references": [
            ("Policy no AgentCore", AGENTCORE + "policy.html"),
            ("Unity Catalog: privilégios na fonte", "https://learn.microsoft.com/pt-br/azure/databricks/data-governance/unity-catalog/manage-privileges/"),
            ("Policy temporal: sessões e propagação", AGENTCORE + "policy-session-based-temporal.html"),
        ],
    },
    "15": {
        "concepts": """
        **Ingestão** transforma conteúdo e metadados da fonte numa representação
        pesquisável. **ACL (lista de controle de acesso)** define quem pode acessar
        um documento. Preservar o texto e perder sua ACL pode expor informação.
        **BDA (Bedrock Data Automation)** é um serviço de extração de informações;
        nesta bancada, os textos normalizados já são fornecidos como fixtures.

        **Recuperação (retrieval)** busca conteúdo para uma pergunta. **Memória**
        preserva informações entre interações. Aqui a memória guarda somente IDs
        de documentos, separados por usuário e sessão; cada leitura revalida a ACL.
        Revogar acesso ao documento também precisa impedir sua reutilização.

        [knowledge.py](../src/santander_demo/knowledge.py) usa dicionários e busca
        textual por substring. Não há embeddings, busca vetorial ou Memory AWS.
        `version` exige atualização sequencial; o hash registra o conteúdo na
        auditoria. O código não sincroniza fontes externas automaticamente.
        """,
        "references": [
            ("AgentCore Memory: conceitos", AGENTCORE + "memory.html"),
            ("Diferenças entre memória e RAG", AGENTCORE + "memory-ltm-rag.html"),
            ("ACLs em Managed Knowledge Bases", "https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html"),
        ],
    },
    "16": {
        "concepts": """
        **RAG** combina recuperação de trechos e geração de resposta. **ACL** limita
        quais documentos podem ser recuperados; relevância determina quais dos
        documentos autorizados aparecem numa consulta. Ter acesso a quatro documentos
        não obriga uma busca semântica a devolver os quatro.

        **Cognito** autentica os usuários; o **Gateway** verifica o JWT; **Policy**
        vincula a identidade assinada ao `userContext`; a **Managed KB** aplica
        as ACLs. **Identity** emite o WAT, um token de identidade da workload.
        Neste roteiro esse WAT é exercitado separadamente: o bearer do Gateway
        continua sendo o JWT Cognito, e o conector da KB usa IAM.

        Leia `ask()` e `coverage_probe()` em
        [rag/client.py](../src/santander_demo/rag/client.py). A primeira faz uma
        consulta e só gera resposta após obter trechos autorizados; a segunda
        testa cobertura com consultas específicas, sem usar o modelo.
        Para D, a negativa encerra o caminho antes da geração.
        """,
        "references": [
            ("Managed KB: criação e funcionamento", "https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html"),
            ("Managed KB: ACLs", "https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html"),
            ("Identity: workload access tokens", AGENTCORE + "get-workload-access-token.html"),
        ],
    },
    "09": {
        "concepts": """
        **Infrastructure as Code (IaC)** descreve recursos em arquivos versionados.
        O **provider** traduz essa configuração em operações da AWS.
        O **state** registra os recursos gerenciados; `plan` calcula diferenças;
        `apply` executa o plano. **Drift** é uma divergência entre a configuração
        desejada e os recursos observados.

        **Runtime** hospeda o Python; **Gateway** publica a Lambda como ferramenta
        MCP; **Identity** fornece uma credencial OAuth para o agente chamar o Gateway.
        **Cognito** emite essa credencial. O **scope** declara uma permissão do
        token; a allowlist do Gateway restringe quais aplicações são aceitas.

        **WAT (workload access token)** identifica a workload perante Identity.
        **SigV4** assina chamadas AWS com credenciais IAM. Esses mecanismos têm
        destinatários distintos, como mostra a tabela seguinte.
        Este notebook não implanta uma engine Cedar nem autorização por pessoa:
        seu controle é de aplicação M2M. Veja o wrapper
        [terraform_deploy.py](../scripts/terraform_deploy.py) e o
        [código do Runtime](../src/santander_demo/terraform_lab/runtime.py).
        """,
        "references": [
            ("Terraform: finalidade do state", "https://developer.hashicorp.com/terraform/language/state"),
            ("Terraform: importação declarativa", "https://developer.hashicorp.com/terraform/language/import"),
            ("Cognito: endpoint OAuth e client_credentials", "https://docs.aws.amazon.com/cognito/latest/developerguide/token-endpoint.html"),
        ],
    },
}


def learning_cell(name):
    """Retorna uma célula Markdown com conceitos, fonte e links da trilha."""
    key = name[:2]
    lesson = LESSONS[key]
    position = LEARNING_ORDER.index(key)
    navigation = ["[Jornada completa](../docs/jornada.md)"]
    for offset, label in ((-1, "Anterior"), (1, "Próximo")):
        index = position + offset
        if 0 <= index < len(LEARNING_PATH):
            filename, title = LEARNING_PATH[index]
            navigation.append(f"[{label}: {title}]({filename}.ipynb)")
    links = "\n".join(f"* [{label}]({url})" for label, url in lesson["references"])
    return nb.v4.new_markdown_cell(
        f"**Etapa {position + 1} de {len(LEARNING_PATH)} na jornada.** "
        + " · ".join(navigation)
        + "\n\n## Conceitos para acompanhar este laboratório\n\n"
        + dedent(lesson["concepts"]).strip()
        + "\n\n**Documentação oficial para aprofundar:**\n\n"
        + links
        + "\n\nAs explicações estão em português; nomes de APIs, claims e campos "
        "permanecem como aparecem no código. As páginas oficiais podem estar em inglês.",
        id=f"conceitos-{key}",
    )
