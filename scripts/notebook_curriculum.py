"""Roteiro didático aplicado pelos geradores sem modificar as células executáveis."""

import base64
from dataclasses import dataclass
from pathlib import Path

import nbformat

from santander_demo.notebook_catalog import display_number

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "docs" / "diagramas" / "aulas"
LEGACY = {"10", "11", "12", "13", "14"}

# A definição apresenta o serviço; cada aula acrescenta sua função no cenário.
SERVICES = {
    "sts": (
        "AWS Security Token Service (STS)",
        "Identifica o principal da sessão e emite credenciais temporárias ao assumir uma role.",
    ),
    "iam": (
        "AWS Identity and Access Management (IAM)",
        "Controla quais ações uma identidade pode executar em quais recursos. "
        "A trust policy define quem pode assumir uma role; a policy de permissões define seu acesso.",
    ),
    "cognito": (
        "Amazon Cognito — User Pool",
        "Mantém usuários e aplicações e emite JWTs assinados após a autenticação. "
        "Issuer identifica o emissor, sub identifica a pessoa e aud identifica a aplicação destinatária.",
    ),
    "federation": (
        "Amazon Cognito — Identity Pool",
        "Troca a identidade autenticada por credenciais AWS temporárias de uma role IAM. "
        "É um recurso diferente do User Pool que emite o JWT.",
    ),
    "gateway": (
        "Amazon Bedrock AgentCore Gateway",
        "Expõe ferramentas por MCP, autentica chamadas e encaminha operações aos targets. "
        "O schema informa nome, argumentos e contrato de cada ferramenta.",
    ),
    "lambda": (
        "AWS Lambda",
        "Executa a função sob demanda com sua própria role. "
        "A configuração do Gateway determina como os argumentos MCP chegam ao handler.",
    ),
    "runtime": (
        "Amazon Bedrock AgentCore Runtime",
        "Hospeda código de agentes ou servidores MCP com sessão, endpoint e role de execução. "
        "A identidade que invoca o endpoint é distinta da identidade usada pelo código hospedado.",
    ),
    "policy": (
        "Amazon Bedrock AgentCore Policy",
        "Avalia regras Cedar sobre principal, ação, recurso e contexto de uma chamada. "
        "O engine associado ao Gateway em ENFORCE aplica suas decisões antes da ferramenta.",
    ),
    "registry": (
        "Agent Registry",
        "Cataloga descritores de capacidades e controla publicação, aprovação e descoberta. "
        "Encontrar um endpoint no catálogo não concede permissão para invocá-lo.",
    ),
    "secrets": (
        "AWS Secrets Manager",
        "Armazena segredos e controla sua leitura por IAM. "
        "O notebook registra o ARN do segredo, sem gravar seu conteúdo no Git.",
    ),
    "s3": (
        "Amazon Simple Storage Service (Amazon S3)",
        "Armazena objetos, como pacotes de código e documentos. "
        "Bucket, chave e permissões delimitam o artefato que outro serviço poderá ler.",
    ),
    "logs": (
        "Amazon CloudWatch Logs",
        "Organiza logs por grupos e streams e aplica retenção. "
        "IDs de requisição ajudam a relacionar a resposta da API à execução do serviço.",
    ),
    "memory": (
        "Amazon Bedrock AgentCore Memory",
        "Armazena eventos de interação associados a actor e sessão. "
        "Nesta aula usamos eventos com referências; não configuramos extração de memória de longo prazo.",
    ),
    "dynamodb": (
        "Amazon DynamoDB",
        "Armazena itens acessados por chave. "
        "Nesta demonstração, chaves de partição e condições IAM isolam as visões de dados.",
    ),
    "kb": (
        "Amazon Bedrock Knowledge Bases",
        "Ingere documentos e recupera trechos relevantes. "
        "Nesta aula a base MANAGED e o conector de dados usam ACL nativa por usuário.",
    ),
    "model": (
        "Amazon Bedrock — inferência de modelos",
        "Executa modelos fundacionais por API. "
        "A chamada Converse recebe a pergunta e o contexto recuperado para gerar a resposta.",
    ),
}


@dataclass(frozen=True)
class Checkpoint:
    marker: str
    title: str
    expected: tuple[tuple[str, str, str], ...]
    analysis: str


@dataclass(frozen=True)
class Guide:
    question: str
    goals: tuple[str, ...]
    prerequisites: str
    creates: str
    reuses: str
    services: tuple[tuple[str, str], ...]
    reading: str
    checkpoints: tuple[Checkpoint, ...]
    conclusion: str
    limits: str
    discussion: str


GUIDES = {
    "00": Guide(
        "Como começar em uma conta efêmera e saber qual identidade fará as chamadas?",
        (
            "Conferir conta, região e principal antes de criar recursos.",
            "Distinguir uma execução nova de uma retomada pelos IDs registrados.",
            "Verificar se o SDK instalado conhece as operações usadas nas próximas aulas.",
        ),
        "Kernel preparado por `scripts/setup.sh` e uma sessão AWS autorizada.",
        "Somente o registro de identificadores desta execução no ambiente do notebook.",
        "A sessão AWS do participante. Não é necessário ter serviços da solução já criados.",
        (
            ("sts", "GetCallerIdentity retorna a conta e o ARN usados como referência em toda a jornada."),
            ("iam", "As permissões da sessão serão avaliadas a cada chamada; autenticação não garante autorização."),
        ),
        "A seta até STS é uma consulta real. O registro de IDs pertence ao ambiente do notebook "
        "e não é um serviço AWS. O conjunto de serviços à direita representa as aulas seguintes; "
        "nenhum deles é criado neste preflight.",
        (
            Checkpoint('"mode": "RESUME"', "execução nova ou retomada", (
                ("Conta nova ou limpeza concluída", "`mode: NEW` e prefixo próprio", "Nenhum ID de outra conta foi reaproveitado."),
                ("Recursos já registrados nesta conta", "`mode: RESUME`", "As próximas aulas vão conferir e reutilizar esses recursos."),
            ), "NEW e RESUME são caminhos válidos. RESUME não comprova uma construção do zero; "
               "ele preserva a continuidade da execução cujo run_id foi mostrado."),
            Checkpoint('"validation": "SDK_AVAILABLE"', "compatibilidade do SDK", (
                ("Operações requeridas", "`validation: SDK_AVAILABLE`", "O modelo de serviço do boto3 conhece as APIs listadas."),
            ), "Esta célula inspeciona o SDK instalado. O resultado não testa permissões de criação, "
               "quotas, acesso ao modelo ou disponibilidade regional: essas condições serão exercitadas nas aulas."),
        ),
        "Você estabeleceu uma referência de conta, região e execução. Esses valores permitem "
        "atribuir os recursos e as evidências das próximas aulas à sessão correta.",
        "O preflight não é uma certificação de que qualquer conta AWS executará a jornada. "
        "00–09 e 15–16 usam uma conta; 13–14 e 90–92 pertencem à arquitetura legada de quatro contas.",
        "Se o ARN de STS for o esperado, mas CreateGateway retornar AccessDenied, o que o preflight comprovou?",
    ),
    "01": Guide(
        "Como transformar uma função Python em uma ferramenta MCP autenticada na AWS?",
        (
            "Criar User Pool, aplicação e pessoas sintéticas no Cognito.",
            "Publicar o código da ferramenta no Lambda e seu schema no Gateway.",
            "Comparar a negativa sem identidade válida com uma chamada MCP autenticada.",
        ),
        "Aula 00 concluída nesta conta e região.",
        "Cognito, segredo das senhas sintéticas, roles IAM, Lambda, logs, Gateway e target.",
        "O registro da execução iniciado em 00.",
        (
            ("cognito", "O ID token desta aplicação é a credencial humana aceita pelo authorizer."),
            ("gateway", "Publica customer_risk por MCP e valida issuer e audiência na entrada."),
            ("lambda", "Executa TOOL_SOURCE e devolve o risco sintético de cliente-001."),
            ("iam", "Separa a role que o Gateway usa para invocar da role que a função usa para executar."),
            ("secrets", "Guarda as senhas das duas pessoas sintéticas criadas durante a aula."),
            ("logs", "Recebe os logs da função com retenção definida."),
        ),
        "Siga o login até o Cognito e depois o JWT até o Gateway. A ferramenta só é chamada "
        "após a autenticação. O salto Gateway → Lambda usa IAM; a função não recebe uma identidade "
        "humana delegada por OBO. Policy/Cedar será acrescentado na aula 04.",
        (
            Checkpoint('from santander_demo.aws_endpoints import gateway_region',
                       "entrada sem identidade válida", (
                ("Chamada sem token ou com token inválido", "`http_status: 401` e Request ID", "O Gateway não aceita essa entrada como sessão MCP autenticada."),
            ), "Uma negativa neste ponto é o resultado esperado. Ela testa o authorizer, "
               "enquanto a próxima validação prova que o caminho autorizado realmente chega à função."),
            Checkpoint('discovered = await mcp.list_tools()', "descoberta e execução MCP", (
                ("tools/list", "Ferramenta com sufixo `___customer_risk`", "O target publicou o contrato MCP."),
                ("tools/call para cliente-001", "`status: PASS`, `risk: low`, `execution: AWS_LAMBDA`", "A função AWS devolveu o conteúdo sintético esperado."),
                ("Evidência da função", "`lambda_request_id` preenchido", "Há uma referência à invocação que produziu a resposta."),
            ), "Listar uma ferramenta e executá-la são verificações diferentes. O PASS exige o conteúdo "
               "e a identificação da execução Lambda, não apenas uma conexão HTTP bem-sucedida."),
        ),
        "A combinação de negativa de entrada e execução autenticada demonstra o caminho completo "
        "Cognito → Gateway → Lambda. O schema MCP oferece descoberta e contrato; IAM permite a invocação do target.",
        "A resposta é determinística e sintética. Não há inferência de modelo nem autorização Cedar "
        "por cliente nesta aula. O uso de ID token é uma escolha explícita deste authorizer.",
        "Qual componente precisaria mudar para permitir a pessoa, mas negar apenas a consulta a cliente-002?",
    ),
    "02": Guide(
        "Por que um token assinado corretamente ainda pode ser rejeitado?",
        (
            "Separar pessoa (`sub`), emissor (`iss`) e aplicação (`aud`).",
            "Criar uma segunda aplicação e comparar tokens emitidos pelo mesmo pool.",
            "Testar audiência errada, assinatura adulterada e audiência permitida.",
        ),
        "Aula 01 concluída. Execute a aula 02 antes de acrescentar políticas mais restritivas.",
        "Um segundo app client Cognito no mesmo User Pool.",
        "Pessoas, segredo, Gateway e ferramenta Lambda da aula 01.",
        (
            ("cognito", "Emite tokens para dois clientes; o emissor é o mesmo, mas as audiências diferem."),
            ("gateway", "Aceita somente a audiência configurada e exige assinatura válida."),
            ("lambda", "Fornece o resultado permitido que confirma a validade do caminho de controle."),
        ),
        "Os dois logins partem da mesma pessoa e do mesmo pool. A aplicação A está autorizada "
        "no Gateway; a B não. A alteração manual de aud no segundo token não recalcula a "
        "assinatura e também deve ser rejeitada.",
        (
            Checkpoint('modified_claims = dict(', "assinatura e audiência", (
                ("Token da outra aplicação", "`valid_signature_wrong_audience: DENY`", "Confiar no emissor não basta para aceitar qualquer aplicação."),
                ("aud adulterado sem nova assinatura", "`allowed_audience_invalid_signature: DENY`", "O payload não pode ser alterado mantendo a autenticidade."),
            ), "Os dois casos retornam HTTP 403 e o erro MCP esperado nesta implementação. "
               "A célula exige o formato da negativa e um Request ID; timeout ou erro de rede não contam como aprovação."),
            Checkpoint('"case": "allowed_audience"', "controle com token permitido", (
                ("Token original da aplicação do notebook", "`allowed_audience: PASS` e resultado Lambda", "O sistema continua funcional para a combinação válida."),
            ), "O teste positivo evita concluir que o controle funciona apenas porque todas as chamadas falharam."),
        ),
        "As negativas isolam duas propriedades: destino do token e integridade criptográfica. "
        "O controle positivo confirma que a pessoa consegue executar a ferramenta com o token adequado.",
        "No Microsoft Entra ID também se configuram emissor, aplicação/audiência, chaves e claims. "
        "O fluxo OBO da Microsoft exige configuração e troca de tokens próprias; dois app clients Cognito não implementam OBO.",
        "Por que mudar apenas o campo aud no JSON de um JWT não transforma um token da aplicação B em um token válido para A?",
    ),
    "03": Guide(
        "Qual identidade o código de um agente usa quando executa no AgentCore Runtime?",
        (
            "Ler o servidor MCP, empacotar dependências ARM64 e armazenar o ZIP no S3.",
            "Criar Runtime e role de execução e aguardar READY.",
            "Comparar o principal do participante com o principal retornado pelo código hospedado.",
        ),
        "Aula 00 e sessão autorizada para criar IAM, S3, Runtime e logs.",
        "Bucket de artefatos, ZIP, role IAM, Runtime MCP e registro de logs.",
        "A sessão e o registro de IDs da execução.",
        (
            ("runtime", "Hospeda a ferramenta workload_identity e protege sua invocação por IAM."),
            ("s3", "Armazena o pacote que será lido pelo Runtime."),
            ("iam", "Autoriza a entrada e define a role usada pelo código hospedado."),
            ("sts", "É chamado dentro do Runtime para revelar a identidade do workload."),
            ("logs", "Permite localizar os logs e limitar sua retenção a sete dias."),
        ),
        "O caminho tracejado S3 → Runtime representa implantação do código. No caminho de execução, "
        "o SDK assina a invocação com a sessão do participante; o Runtime consulta STS com sua própria role.",
        (
            Checkpoint('def mcp_result(response, request_id)', "identidade observada dentro do Runtime", (
                ("Descoberta MCP", "`workload_identity` presente", "O servidor empacotado está acessível."),
                ("Invocação", "`runtime_workload_identity: PASS`", "Conta e run_id correspondem à execução."),
                ("Principal retornado", "`assumed-role/...-runtime/...`, diferente do participante", "O código executa com a role do workload."),
            ), "O ARN de STS é produzido pelo servidor MCP na AWS. O Request ID do Runtime identifica "
               "a invocação externa, e sts_request_id identifica a consulta feita pelo código hospedado."),
        ),
        "Você demonstrou a separação entre quem invoca e quem executa. O mesmo servidor MCP "
        "será usado pelas personas do Registry e, depois, como target do Gateway.",
        "A ferramenta consulta STS e não gera respostas por modelo. Este Runtime usa IAM na entrada; "
        "o Runtime HTTP com JWT humano da aula 16 é outro recurso.",
        "O principal retornado por workload_identity deveria ser o ARN da pessoa que iniciou o notebook? Por quê?",
    ),
    "04": Guide(
        "Como autorizar uma ferramenta para uma pessoa e um argumento específicos?",
        (
            "Criar Policy Engine e associá-lo ao Gateway em ENFORCE.",
            "Ler o permit Cedar como principal, ação, recurso e condições.",
            "Alterar pessoa e cliente separadamente e comparar as decisões.",
        ),
        "Aula 01 concluída com Cognito, Gateway e target Lambda.",
        "Policy Engine, permissão IAM de avaliação, associação ENFORCE e regra Cedar ACTIVE.",
        "Pessoas, ferramenta e roles da aula 01.",
        (
            ("cognito", "Autentica analista e auditor; ambos têm tokens válidos."),
            ("policy", "Permite somente a combinação analista, ferramenta e cliente-001 definida na regra."),
            ("gateway", "Encaminha a ferramenta quando a decisão aplicada permite a chamada."),
            ("lambda", "Executa o caso permitido e devolve seu Request ID."),
            ("iam", "Permite à role do Gateway consultar o engine desta aula."),
        ),
        "Cognito responde quem é a pessoa. O ponto Policy no caminho do Gateway responde se "
        "ela pode fazer esta operação com estes argumentos. Um DENY deve ocorrer antes do target.",
        (
            Checkpoint('("analyst_allowed_customer",', "matriz de autorização Cedar", (
                ("Analista / cliente-001", "`ALLOW` e Request ID Lambda", "A combinação prevista pela regra chega à ferramenta."),
                ("Analista / cliente-002", "`DENY` identificado como Policy", "Mudar o argumento sai do escopo autorizado."),
                ("Auditor / cliente-001", "`DENY` identificado como Policy", "Autenticação válida não concede o permit do analista."),
            ), "Leia a mensagem MCP, não somente o status HTTP: nesta integração uma negativa "
               "de Policy pode vir em HTTP 200 ou 403. Os asserts exigem uma decisão reconhecível, "
               "não uma falha genérica do backend."),
        ),
        "O caso permitido e os dois contraexemplos mostram o efeito da regra. "
        "A ausência de um permit aplicável nega a operação; a assinatura válida do token continua necessária.",
        "Essa matriz cobre a ferramenta e os argumentos definidos aqui. Ela não prova cobertura de todas "
        "as futuras ferramentas nem substitui a autorização independente de uma fonte de dados.",
        "Qual parte da regra muda para permitir outro cliente ao analista sem conceder o mesmo acesso ao auditor?",
    ),
    "05": Guide(
        "Como transformar uma intenção em Cedar e revisar o resultado antes de aplicá-lo?",
        (
            "Solicitar geração de política ao serviço AWS e examinar assets e findings.",
            "Executar casos e contraexemplos contra o Cedar gerado.",
            "Adicionar o rascunho em LOG_ONLY sem substituir a proteção ACTIVE.",
        ),
        "Aula 04 concluída, incluindo a matriz permitida/negada.",
        "Uma geração de política e uma política de rascunho LOG_ONLY.",
        "Engine ENFORCE, política ACTIVE, Cognito, Gateway e Lambda.",
        (
            ("policy", "Gera Cedar e mantém separados o rascunho LOG_ONLY e a política que autoriza as chamadas."),
            ("gateway", "Permite repetir a matriz real após a criação do rascunho."),
            ("cognito", "Fornece identidades verificadas para os testes reais."),
        ),
        "A trilha de autoria começa na intenção, passa pelo Cedar e pela revisão e termina no "
        "rascunho LOG_ONLY. A trilha de execução continua protegida pela política ACTIVE no engine ENFORCE.",
        (
            Checkpoint('parsed = cedarpy.PolicySet.from_str', "semântica do rascunho", (
                ("Caso previsto na intenção", "Avaliador Cedar permite", "A regra expressa o caso positivo."),
                ("Pessoa, ação, recurso ou contexto fora do escopo", "Contraexemplos negados", "A regra não ficou permissiva para os casos examinados."),
            ), "O avaliador Cedar roda no kernel como verificação do documento. "
               "Isso não substitui as chamadas reais ao Gateway, realizadas mais adiante."),
            Checkpoint('("analyst_allowed_customer",', "proteção após adicionar LOG_ONLY", (
                ("Matriz da aula 04", "Um `ALLOW` e dois `DENY`", "A proteção ACTIVE continua valendo após adicionar o rascunho."),
            ), "O resultado não demonstra promoção do rascunho. LOG_ONLY permite observar a política "
               "sem fazê-la conceder acesso; a autorização continua sustentada pela política ACTIVE."),
        ),
        "Você separou geração, revisão semântica e observação. Uma intenção em linguagem natural "
        "só se torna uma candidata útil depois de inspecionar o código Cedar e seus contraexemplos.",
        "Não há promoção automática para ACTIVE. Texto gerado e findings não garantem que todos os "
        "casos de negócio foram cobertos; os casos escolhidos delimitam o que foi verificado.",
        "Se os testes reais passaram com LOG_ONLY, isso prova que o rascunho sozinho protegeria a ferramenta?",
    ),
    "06": Guide(
        "Como criar um catálogo de capacidades com descoberta autenticada e aprovação manual?",
        (
            "Criar Registry e aguardar o estado READY.",
            "Conferir autenticação AWS_IAM e ausência de aprovação automática.",
            "Consultar o catálogo com e sem assinatura.",
        ),
        "Aula 00 e permissões para as APIs de Agent Registry.",
        "Um Registry com descoberta IAM e aprovação manual.",
        "A sessão e o registro da execução.",
        (
            ("registry", "Armazena os registros que serão publicados e aprovados na aula 08."),
            ("iam", "Protege a API de descoberta; chamadas sem assinatura não recebem o catálogo."),
        ),
        "O Registry guarda descritores, não o código do servidor. A consulta autenticada segue "
        "para a descoberta; a consulta anônima é negada. A publicação de um endpoint será estudada depois.",
        (
            Checkpoint('records = []', "catálogo autenticado", (
                ("Consulta assinada", "`discovery: AUTHENTICATED` e contagem de registros", "A sessão tem acesso à descoberta."),
                ("Consulta sem assinatura", "`anonymous_discovery: DENY`, HTTP 401/403", "A descoberta não é anônima."),
            ), "Um catálogo vazio é normal em uma execução nova: o registro só será publicado na aula 08. "
               "Em uma retomada, registros aprovados podem já aparecer."),
        ),
        "Você criou o ponto de governança do catálogo e verificou sua entrada IAM. "
        "A aprovação manual estabelece uma etapa a ser exercitada pelas personas.",
        "Ainda não houve publicação/aprovação de uma capacidade. READY indica disponibilidade do catálogo, "
        "não autorização de invocação de um Runtime catalogado.",
        "Por que a permissão de consultar o catálogo deve ser separada de InvokeAgentRuntime?",
    ),
    "07": Guide(
        "Como separar publicação, aprovação e consumo usando sessões IAM reais?",
        (
            "Ler trust policies e permissões de três personas.",
            "Criar as roles previstas pelo workshop e assumir cada uma via STS.",
            "Comparar acesso permitido ao catálogo e acesso restrito ao Runtime.",
        ),
        "Aulas 03 e 06 concluídas; a sessão deve poder assumir as três roles indicadas na aula.",
        "`publisher_persona`, `admin_persona` (Approver) e `consumer_persona`, com policies delimitadas.",
        "Runtime MCP e Registry. Developer usa a sessão do editor.",
        (
            ("iam", "Separa o direito de assumir uma role das ações concedidas dentro dela."),
            ("sts", "Emite uma sessão temporária para cada persona testada."),
            ("registry", "Permite GetRegistry para as três personas."),
            ("runtime", "Só Consumer tem GetAgentRuntime nesta matriz."),
        ),
        "A sessão do participante assume cada persona para a demonstração. As setas de cada role "
        "representam permissões diferentes, não três pessoas diferentes conectadas ao notebook.",
        (
            Checkpoint('for name, entry in persona_entries.items():', "matriz IAM com chamadas reais", (
                ("Publisher, Approver e Consumer / GetRegistry", "Três `ALLOW`", "As personas conseguem identificar o catálogo."),
                ("Publisher e Approver / GetAgentRuntime", "Dois `DENY` IAM", "Essas roles não recebem leitura do Runtime."),
                ("Consumer / GetAgentRuntime", "`ALLOW`", "A role consumidora tem o acesso previsto."),
            ), "A matriz usa credenciais STS e APIs reais, sem depender de SimulatePrincipalPolicy. "
               "Uma falha em AssumeRole ocorre antes da ação testada e não equivale ao DENY esperado de GetAgentRuntime."),
        ),
        "Trust e permissões têm responsabilidades distintas. Assumir uma persona permite "
        "executar as ações de sua policy, sem herdar todas as permissões da sessão do editor.",
        "Esta aula cobre leitura; 08 completa publicação, aprovação e execução. A mesma pessoa "
        "assume todos os papéis para aprender, portanto o exercício não comprova segregação organizacional.",
        "Uma trust policy que permite assumir Publisher também concede aprovação de registros?",
    ),
    "08": Guide(
        "Como uma capacidade passa de rascunho a descoberta e depois a execução autorizada?",
        (
            "Publicar um descritor que corresponda ao servidor MCP implantado.",
            "Submeter e aprovar o registro usando personas diferentes.",
            "Descobrir e invocar como Consumer e repetir a descoberta sem permissão de invocação.",
        ),
        "Aulas 03, 06 e 07 concluídas.",
        "Registro MCP versionado no Registry e suas transições de submissão/aprovação.",
        "Runtime, Registry e as três personas IAM.",
        (
            ("registry", "Mantém o descritor, o estado de aprovação e a visão descobrível do registro."),
            ("sts", "Cria as sessões das personas, incluindo Consumer limitado por session policy."),
            ("iam", "Controla quem publica, aprova, descobre e invoca."),
            ("runtime", "Executa a ferramenta indicada pelo descritor aprovado."),
        ),
        "A trilha de controle é Publisher → submissão → Approver → registro aprovado. "
        "A trilha de consumo é Consumer → descoberta → Runtime. A segunda seta exige autorização própria.",
        (
            Checkpoint('current = reviewed_record(approver)', "aprovação do descritor", (
                ("Conteúdo revisado", "Descritor corresponde ao Runtime e à ferramenta", "A revisão aprova a capacidade realmente implantada."),
                ("Transição como Approver", "Estado `APPROVED`", "O registro pode entrar na descoberta."),
            ), "Leia o descritor antes de interpretar APPROVED. Aprovar um endpoint é uma decisão de "
               "governança sobre aquele registro; a execução continua dependendo de IAM."),
            Checkpoint('limited = assume_persona("consumer", discovery_only=True)',
                       "descoberta sem invocação", (
                ("Consumer limitado / descoberta", "Registro aprovado continua visível", "A session policy preserva a descoberta."),
                ("Mesma sessão / invocação", "`discovery_only_invocation: DENY`", "Conhecer o endpoint não concede InvokeAgentRuntime."),
            ), "Este contraexemplo isola a permissão de execução. A chamada anterior com Consumer completo "
               "mostra que o Runtime funciona; o DENY da sessão limitada decorre de IAM."),
        ),
        "Publicação e aprovação controlam o catálogo; a autorização do endpoint controla o uso. "
        "O descritor revisado liga o que foi descoberto à ferramenta que efetivamente executa na AWS.",
        "As permissões são específicas desta capacidade. A retomada pode encontrar um registro já aprovado; "
        "isso não representa uma nova aprovação organizacional.",
        "Qual evidência separa um problema de descoberta de uma negativa de invocação?",
    ),
    "09": Guide(
        "Como combinar identidade humana, Policy e identidade do workload em um único fluxo?",
        (
            "Registrar o Runtime MCP como target do Gateway.",
            "Conceder à role do Gateway invocação somente desse Runtime.",
            "Comparar analista e auditor e identificar o principal que executa o código.",
        ),
        "Aulas 01, 03 e 04 concluídas.",
        "Target MCP do Runtime, permissão de invocação e regra Cedar da nova ferramenta.",
        "Cognito, Gateway ENFORCE, Policy Engine e Runtime MCP.",
        (
            ("cognito", "Autentica a pessoa na entrada do Gateway."),
            ("policy", "Permite a ferramenta workload_identity somente ao analista."),
            ("gateway", "Usa GATEWAY_IAM_ROLE para assinar o salto ao Runtime."),
            ("iam", "Autoriza a role do Gateway no endpoint e identifica a role executora."),
            ("runtime", "Executa workload_identity e consulta STS sob a role do workload."),
            ("sts", "Fornece a evidência da identidade usada dentro do servidor."),
        ),
        "Leia as três fronteiras: JWT da pessoa na entrada, Cedar sobre a ferramenta e IAM/SigV4 "
        "no salto ao Runtime. O servidor MCP não recebe o JWT humano neste fluxo; sua consulta STS usa a role de execução.",
        (
            Checkpoint('"gateway_runtime": "DENY"', "pessoa e workload no mesmo caminho", (
                ("Analista", "`gateway_runtime: ALLOW` e identidade do Runtime", "Cedar permite e o salto IAM chega ao servidor."),
                ("Auditor autenticado", "`gateway_runtime: DENY` de Policy", "O Gateway bloqueia a ferramenta para outra pessoa."),
                ("Principal dentro do Runtime", "Role `...-runtime`, conta e run_id esperados", "A execução usa a identidade do workload."),
            ), "O teste exige a mensagem de Policy para o auditor e o conteúdo STS para o analista. "
               "Esses sinais distinguem uma negativa de negócio de uma falha da permissão Gateway → Runtime."),
        ),
        "O fluxo combina controles complementares: Cognito autentica, Cedar decide a operação "
        "humana, IAM autoriza o salto e a role do Runtime identifica a execução.",
        "Não há OBO nem delegação do JWT humano ao MCP nesta aula. Personas com IAM apropriado "
        "continuam podendo invocar diretamente o Runtime; a aula não afirma exclusividade do Gateway.",
        "Se o analista passar no Cedar mas a role do Gateway perder InvokeAgentRuntime, onde a chamada falhará?",
    ),
    "10": Guide(
        "Como verificar que uma arquitetura usa fronteiras reais entre contas AWS?",
        ("Identificar plataforma, Retail, Transaction e Lending.", "Comparar IDs STS e disponibilidade dos ambientes de cada domínio."),
        "Legado: quatro contas distintas, configuração e recursos da arquitetura anterior preparados.",
        "Nenhum recurso; as células inspecionam ambientes previamente implantados.",
        "As quatro contas e a configuração do legado. Esta aula não usa apenas os recursos criados em 00–09.",
        (("sts", "Confirma IDs distintos, evitando confundir perfis diferentes com contas diferentes."),
         ("iam", "Controla as sessões entre contas e suas permissões."),
         ("gateway", "Fornece uma entrada por domínio."),
         ("runtime", "Hospeda as capacidades em cada domínio."),
         ("policy", "Mantém decisões por domínio."),
         ("memory", "Faz parte dos ambientes consultados pelo preflight legado.")),
        "Cada caixa externa é uma conta AWS diferente. A plataforma é o hub C, Retail é a origem A "
        "e Transaction é a fonte B. Lending é a quarta conta exigida pelo manifesto legado, mesmo sem participar de todos os fluxos.",
        (Checkpoint('assert len({x["account_id"]', "quatro identidades de conta", (
            ("Sessões configuradas", "Quatro account_id distintos", "Perfis não estão apontando para a mesma conta."),
        ), "Este assert só comprova a distinção das contas. O preflight seguinte consulta os recursos "
           "de cada domínio; quatro credenciais válidas não comprovam que os serviços foram implantados."),),
        "A leitura permite discutir isolamento administrativo e limites de confiança entre contas.",
        "O fluxo executável permanece legado e não foi validado na atual jornada de conta única. "
        "Sem as quatro contas e a implantação anterior, use esta aula somente para estudo da arquitetura.",
        "Dois perfis com o mesmo account_id demonstram uma integração entre contas?",
    ),
    "11": Guide(
        "Como um ponto central de descoberta alcança capacidades distribuídas em três domínios?",
        ("Relacionar os prefixos MCP aos domínios.", "Seguir a chamada do agente central até o Runtime do domínio solicitado."),
        "Legado: quatro contas e os targets federados previamente implantados.",
        "Nenhum recurso; inspeciona targets e chama os agentes do ambiente legado.",
        "Plataforma central, Cognito e os três domínios preparados na arquitetura anterior.",
        (("gateway", "Centraliza a descoberta e apresenta prefixos retail, transaction e lending."),
         ("runtime", "Executa o agente e as capacidades distribuídas."),
         ("policy", "Aplica autorização no caminho federado."),
         ("cognito", "Identifica a pessoa nas chamadas do cenário."),
         ("iam", "Delimita as permissões dos serviços entre contas.")),
        "O hub reúne contratos MCP, mas os serviços e suas permissões continuam em contas separadas. "
        "Siga cada ramificação até a conta correspondente; centralizar descoberta não move os dados para a plataforma.",
        (Checkpoint('results = {}', "execução nos domínios", (
            ("Retail, Transaction e Lending", "Resposta `execution: AWS_AGENTCORE_RUNTIME` para cada domínio", "O helper recebeu respostas de execução Runtime."),
        ), "Compare domínio, IDs de requisição e conteúdo de cada resposta. A marca de execução é "
           "o assert visível desta célula; ela sozinha não constitui auditoria completa de todas as fronteiras."),),
        "A arquitetura separa descoberta central de execução distribuída e torna visível o roteamento por domínio.",
        "Os resultados desta versão não foram revalidados na conta efêmera atual. "
        "O cenário depende de quatro contas e do fluxo legado de implantação.",
        "Qual parte é centralizada pelo hub, e quais decisões continuam pertencendo aos domínios?",
    ),
    "12": Guide(
        "Uma entrada central elimina a necessidade de autorização na conta de destino?",
        ("Comparar Gateway e Policy da plataforma e da conta Transaction.", "Testar a negativa nas duas entradas."),
        "Legado: quatro contas preparadas; o fluxo ilustrado destaca plataforma e Transaction.",
        "Nenhum recurso; consulta as configurações e exerce chamadas existentes.",
        "Gateways, engines e identidades da implantação anterior.",
        (("gateway", "Mantém entradas distintas no hub e no domínio."),
         ("policy", "Impõe autorização em cada entrada examinada."),
         ("cognito", "Fornece as pessoas usadas nos controles permitido e negado."),
         ("runtime", "Executa a ferramenta no domínio de destino.")),
        "Há dois pontos de controle visíveis: a entrada no hub e a entrada direta do domínio. "
        "O diagrama mostra duas contas ativas no fluxo e as outras duas exigidas pela configuração legada.",
        (Checkpoint('restricted = lab.login("b")', "negativa nas duas entradas", (
            ("Pessoa restrita pelo hub", "expect_denial confirma a negativa", "A entrada central aplica seu controle."),
            ("Mesma pessoa diretamente no domínio", "expect_denial confirma a negativa", "A entrada do domínio também controla acesso."),
        ), "A chamada permitida anterior é o controle positivo. Compare a origem da negativa em cada "
           "resposta; falhas de autenticação ou rede não demonstram a equivalência das políticas."),),
        "A arquitetura exige examinar a autorização em cada caminho de entrada, inclusive o acesso direto ao domínio.",
        "Esta é uma análise do código legado, sem novo aceite AWS. Audiências diferentes no Entra ID "
        "exigem desenho de tokens por API; um JWT não deve ser presumido válido em todos os saltos.",
        "Se só a entrada central aplicar a regra, o que muda quando alguém conhece o endpoint do domínio?",
    ),
    "13": Guide(
        "Como manter uma autorização de fonte independente do acesso à ferramenta?",
        ("Identificar a pessoa verificada na fonte.", "Comparar leitura permitida com SOURCE_DENY.", "Explicitar o que o simulador representa e o que não representa."),
        "Legado: quatro contas preparadas e simulador na conta Transaction.",
        "Nenhum recurso; inspeciona e chama o simulador existente.",
        "Runtime MCP, DynamoDB, Cognito e Gateway da arquitetura anterior.",
        (("runtime", "Executa o servidor MCP e a verificação de identidade da fonte."),
         ("dynamodb", "Armazena dados e concessões sintéticos do simulador."),
         ("gateway", "Expõe as ferramentas de identidade e consulta."),
         ("cognito", "Emite a identidade humana conferida no backend.")),
        "A verificação no Runtime antecede a leitura no DynamoDB. O rótulo Databricks descreve "
        "o contrato simulado; não existe workspace Databricks, SQL Warehouse ou Unity Catalog neste desenho.",
        (Checkpoint('expected="SOURCE_DENY"', "autorização independente na fonte", (
            ("Pessoa permitida", "Linha sintética de C001", "A consulta passou também na autorização da fonte."),
            ("Pessoa sem concessão", "`SOURCE_DENY`", "Chegar à ferramenta não é suficiente para obter dados."),
        ), "SOURCE_DENY deve vir da verificação da fonte feita pelo backend. Não confunda essa "
           "evidência com uma negativa anterior do authorizer do Gateway."),),
        "O cenário ilustra uma fronteira adicional: a autorização da ferramenta e a concessão dos dados "
        "são verificações separadas.",
        "Sem aceite atual desta aula legada. O simulador AWS não testa o protocolo de autenticação, "
        "as permissões nem as APIs de uma instalação real do Databricks.",
        "Qual controle precisaria ser reimplementado e testado ao substituir o simulador por um SQL Warehouse real?",
    ),
    "14": Guide(
        "Como ligar descoberta, identidade de aplicação e execução em contas de origem, hub e fonte?",
        ("Relacionar registros aprovados aos agentes Riscos e Fraude.", "Acompanhar A → C → B.", "Testar tokens de uma aplicação no endpoint da outra."),
        "Legado: quatro contas, Registry e capacidades de origem previamente publicadas e aprovadas.",
        "Nenhum recurso; descobre registros, inspeciona fases e invoca os agentes já implantados.",
        "Registry, Cognito, Runtimes de origem, hub e fonte sintética da arquitetura anterior.",
        (("registry", "Liga descritores aprovados aos agentes implantados."),
         ("cognito", "Distingue as aplicações Riscos e Fraude por audiência."),
         ("runtime", "Executa os agentes na origem e o backend na fonte."),
         ("gateway", "Intermedeia a descoberta e o acesso federado pelo hub."),
         ("policy", "Aplica as decisões previstas no caminho."),
         ("dynamodb", "Representa a fonte sintética de dados.")),
        "Retail é a origem A; plataforma é o hub C; Transaction é a fonte B. "
        "Lending continua sendo a quarta conta requerida pelo legado. O Registry descreve capacidades; "
        "o JWT e as policies controlam as chamadas entre os componentes.",
        (Checkpoint('denied = []', "isolamento entre aplicações", (
            ("Token Fraude no endpoint Riscos e vice-versa", "HTTP 401/403 com Request ID", "A entrada não aceita a audiência da outra aplicação."),
        ), "Compare com as duas execuções permitidas da célula anterior. O teste negativo cobre "
           "a entrada do Runtime; não comprova, sozinho, cada autorização dos saltos posteriores."),),
        "A arquitetura conecta governança do catálogo a identidades de aplicação e serviços em contas distintas.",
        "Esta jornada legada continua pendente de conversão e novo teste. A fonte é sintética "
        "e não é uma integração real com Databricks; três contas no caminho não reduzem o requisito atual de quatro.",
        "Por que um registro aprovado não torna intercambiáveis os tokens de Riscos e Fraude?",
    ),
    "15": Guide(
        "Uma referência salva na memória deve continuar liberando dados depois da revogação?",
        (
            "Federar usuários Cognito para sessões AWS isoladas por pessoa.",
            "Criar Memory por actor e visões sintéticas no DynamoDB.",
            "Revogar a concessão atual e reler uma referência antiga.",
        ),
        "Aula 01 concluída com as duas pessoas Cognito.",
        "Identity Pool, Memory, tabela DynamoDB, visões por pessoa, roles e evento com referência.",
        "User Pool, aplicação e segredo da aula 01.",
        (
            ("cognito", "Autentica a pessoa e fornece sub assinado."),
            ("federation", "Mapeia o sub verificado para uma role e emite credenciais temporárias."),
            ("iam", "Restringe Memory ao actor e DynamoDB à partition key daquela pessoa."),
            ("memory", "Guarda somente document_id e tipo da fonte, sem copiar o conteúdo protegido."),
            ("dynamodb", "Materializa a visão autorizada atual; a revogação remove a visão do analista."),
        ),
        "Depois do login, o Identity Pool fornece a sessão da pessoa. Essa sessão acessa seu "
        "actor em Memory e sua partição no DynamoDB. A memória conserva uma referência; "
        "a leitura do conteúdo exige uma nova consulta à fonte.",
        (
            Checkpoint('def require_denial(label, call)', "isolamento por pessoa", (
                ("Auditor lendo actor do analista", "`other_memory_actor: IAM_DENY`", "A role não autoriza outro actor."),
                ("Analista lendo partição do auditor", "`other_source_partition: IAM_DENY`", "A chave alheia é bloqueada por IAM."),
            ), "A identidade do actor vem de issuer/sub verificados, não de um campo arbitrário "
               "enviado pela pessoa. Os asserts exigem uma negativa IAM real."),
            Checkpoint('source = sessions["analista"].client("dynamodb")', "referência após revogação", (
                ("Memória antiga", "`memory_reference: STILL_PRESENT`", "A lembrança continua existindo."),
                ("Fonte após retirar a concessão", "`NO_CURRENT_GRANT`, `content_returned: False`", "A referência não restaura o conteúdo removido da visão."),
            ), "Aqui a revogação retira o item da visão autorizada do analista. GetItem na própria "
               "partição continua permitido, mas não retorna Item. Isso difere do AccessDenied ao tentar outra partição."),
        ),
        "O resultado separa persistência de memória e autorização atual dos dados. "
        "Guardar uma referência evita transformar a memória em cópia duradoura de conteúdo que pode ser revogado.",
        "Esta é uma fonte sintética e uma demonstração de eventos de Memory. "
        "Não há Databricks real nem estratégia de memória de longo prazo configurada.",
        "Se o evento guardasse o texto completo em vez de document_id, remover a visão no DynamoDB retiraria esse texto da memória?",
    ),
    "16": Guide(
        "Como gerar respostas com documentos autorizados para a pessoa autenticada?",
        (
            "Criar corpus e ACL, base MANAGED e ingestão.",
            "Conectar Retrieve ao Gateway e vincular userContext ao sub verificado em Cedar.",
            "Executar o agente no Runtime e comparar fraude de identidade, retrieval direto e respostas por pessoa.",
        ),
        "Aulas 01 e 04 concluídas. Região com os serviços e o modelo usados pela aula disponíveis.",
        "Corpus S3, role da base, Knowledge Base MANAGED, fonte/ingestão, target Retrieve, regras Cedar e Runtime RAG.",
        "Cognito, Gateway e engine ENFORCE. O Runtime RAG é distinto do MCP da aula 03.",
        (
            ("s3", "Armazena os documentos sintéticos R1/F1 e os arquivos de ACL."),
            ("kb", "Ingere os documentos e filtra a recuperação usando a ACL nativa."),
            ("cognito", "Fornece o JWT verificado na entrada do Runtime e no Gateway."),
            ("runtime", "Deriva userContext do sub, recupera contexto e gera a resposta na AWS."),
            ("gateway", "Expõe o conector nativo rag___Retrieve."),
            ("policy", "Exige que userContext.userId corresponda ao sub autenticado."),
            ("iam", "Permite retrieval pela role do Gateway e o nega diretamente à role do Runtime."),
            ("model", "Nova Lite recebe a pergunta e os trechos autorizados via Converse."),
            ("logs", "Registra a execução do Runtime para inspeção."),
        ),
        "A trilha de ingestão vai de S3 à base. Na trilha de pergunta, o Runtime valida o JWT, "
        "chama Gateway/Policy e recebe somente os trechos permitidos pela ACL. Depois chama "
        "o modelo. O caminho direto Runtime → Retrieve está explicitamente negado por IAM.",
        (
            Checkpoint('parser_tree = ast.parse(SERVER_SOURCE)', "ACL, identidade e geração", (
                ("Analista enviando userContext do auditor", "`rag_user_context_spoof: POLICY_DENY`", "Não pode escolher outra pessoa na recuperação."),
                ("Runtime tentando Retrieve diretamente", "`direct_retrieval: IAM_DENY`", "A role do agente não contorna o Gateway."),
                ("Resposta ao analista", "`generated: True`, `document_ids: ['R1']`", "A recuperação forneceu somente o documento autorizado do analista."),
                ("Resposta ao auditor", "`generated: True`, `document_ids: ['F1']`", "A recuperação forneceu somente o documento autorizado do auditor."),
            ), "Compare document_ids, subject e os Request IDs do Runtime, Gateway e modelo. "
               "A redação gerada pode variar; os asserts verificam a origem dos documentos e as fronteiras "
               "de acesso, não uma frase fixa do modelo."),
        ),
        "Três controles se complementam: JWT identifica a pessoa, Cedar impede fraude de userContext "
        "e a ACL da base filtra os documentos. A negativa IAM impede que o próprio agente use retrieval direto.",
        "A geração por modelo não garante correção factual de qualquer resposta. Este corpus tem dois "
        "documentos sintéticos; examine a resposta e suas fontes sem tratar este teste como avaliação abrangente de qualidade RAG.",
        "Se Cedar validasse a ferramenta, mas não vinculasse userContext ao sub, qual ataque a matriz pretende revelar?",
    ),
    "99": Guide(
        "Como encerrar a execução sem apagar recursos de outra aula ou de outro usuário?",
        (
            "Conferir propriedade e dependências antes das exclusões.",
            "Remover consumidores antes de seus recursos de suporte e aguardar exclusões assíncronas.",
            "Distinguir limpeza completa de reconstrução parcial do Runtime RAG.",
        ),
        "A execução cujos recursos serão removidos deve estar registrada nesta conta e região.",
        "Nenhum recurso; remove somente os recursos SDK registrados no escopo escolhido.",
        "O registro de IDs, hashes e configurações verificados durante as aulas.",
        (
            ("runtime", "É removido antes das roles e artefatos que utiliza."),
            ("gateway", "Tem seus targets removidos antes do Gateway e do engine associado."),
            ("kb", "Exige aguardar a exclusão da fonte antes de remover a base."),
            ("memory", "Tem eventos e recurso removidos dentro da execução registrada."),
            ("registry", "Perde registros e dependências antes de ser excluído."),
            ("iam", "As roles são retiradas depois dos serviços e conferidas antes da alteração."),
            ("s3", "Somente objetos registrados e buckets vazios são removidos."),
            ("cognito", "Pessoas e clientes da aula são removidos com o pool."),
            ("secrets", "A exclusão preserva uma janela de recuperação de sete dias."),
        ),
        "As setas indicam ordem de remoção, não fluxo de dados. Primeiro confira o escopo; "
        "depois remova integrações e serviços, dados/artefatos e identidades. "
        "A ausência deve ser confirmada antes de retirar o recurso do registro.",
        (
            Checkpoint('CLEANUP_SCOPE = os.environ.get', "escopo e propriedade antes da exclusão", (
                ("Escopo padrão", "`all` e conferências de recursos aprovadas", "A limpeza considera a jornada SDK registrada."),
                ("Escopo opcional", "`rag-runtime`", "Somente o Runtime RAG e seus suportes específicos serão reconstruídos."),
            ), "Pare para ler o inventário e o escopo antes das próximas células: elas excluem recursos. "
               "Uma dependência desconhecida interrompe a limpeza em vez de ser incorporada automaticamente."),
            Checkpoint('"cleanup": "COMPLETE"', "confirmação da limpeza completa", (
                ("Escopo all concluído", "`cleanup: COMPLETE` e registro sem resources", "Todas as dependências registradas foram conciliadas."),
                ("Segredo", "`SCHEDULED_FOR_DELETION`, recuperação de 7 dias", "A exclusão foi agendada, não concluída fisicamente de imediato."),
            ), "COMPLETE só é emitido no escopo all. Uma limpeza parcial não deve apresentar esse resultado. "
               "Se houver timeout, os IDs pendentes permanecem para retomar; não interprete a solicitação de Delete como confirmação de ausência."),
        ),
        "A limpeza faz parte do ciclo da conta efêmera. Ao concluir all, a próxima aula 00 "
        "arquiva o registro encerrado e inicia uma execução com nomes novos.",
        "A aula 99 cobre os recursos da jornada SDK, não a implantação legada 13–14 e 90–92 nem o editor do evento. "
        "Segredos agendados e assets com expiração administrada pelo serviço seguem seus próprios prazos.",
        "Por que remover uma entrada do registro logo após Delete, sem confirmar o estado final, prejudica a retomada?",
    ),
}


def markdown(text, tag):
    return nbformat.v4.new_markdown_cell(text, metadata={"tags": [tag]})


def introduction(name, guide):
    lab = name[:2]
    number = display_number(lab)
    image_name = f"{number}.png"
    image = (ART / image_name).read_bytes()
    diagram = markdown(
        "## Arquitetura desta aula\n\n"
        f"![Arquitetura da aula {number}; descrição do fluxo logo abaixo](attachment:{image_name})\n\n"
        f"**Como ler o desenho:** {guide.reading}\n\n"
        f"[Abrir PNG](../docs/diagramas/aulas/{number}.png) · "
        f"[Abrir SVG](../docs/diagramas/aulas/{number}.svg)",
        "workshop-architecture",
    )
    diagram.attachments = {image_name: {"image/png": base64.b64encode(image).decode()}}
    scope = (
        "**Estudo do legado — quatro contas AWS distintas.** Esta aula ainda depende da "
        "implantação anterior e não foi validada na jornada SDK atual. "
        "Não execute este notebook na conta única do Workshop Studio.\n\n"
        if lab in LEGACY else
        "**Jornada SDK — uma conta AWS.** Os serviços são construídos pelas células; "
        "quando houver dependências de outra aula, elas estão indicadas abaixo.\n\n"
    )
    goals = "\n".join(f"{index}. {goal}" for index, goal in enumerate(guide.goals, 1))
    objective = markdown(
        f"## O que você vai aprender\n\n**Pergunta da aula:** {guide.question}\n\n"
        f"{goals}\n\n{scope}"
        f"**Antes de começar:** {guide.prerequisites}\n\n"
        f"**O que esta aula cria ou remove:** {guide.creates}\n\n"
        f"**O que reutiliza:** {guide.reuses}",
        "workshop-objectives",
    )
    rows = "\n".join(
        f"| **{SERVICES[key][0]}** | {SERVICES[key][1]} | {purpose} |"
        for key, purpose in guide.services
    )
    services = markdown(
        "## Serviços AWS e suas responsabilidades\n\n"
        "| Serviço | O que ele faz | Papel nesta aula |\n"
        "|---|---|---|\n" + rows + "\n\n"
        "**Roteiro de execução:** leia a configuração e o código, execute a célula, "
        "aguarde o estado indicado e interprete a evidência antes de avançar. "
        "As seções **Validação** destacam chamadas e asserts já presentes na aula. "
        "Um erro inesperado não equivale a uma negativa autorizada esperada.",
        "workshop-services",
    )
    return [diagram, objective, services]


def enrich_notebook(notebook, name):
    """Acrescenta apresentação e análise ao redor dos testes reais da aula."""
    guide = GUIDES[name[:2]]
    if notebook.metadata.get("workshop", {}).get("teaching_guide_version"):
        raise ValueError(f"Notebook já contém o roteiro didático: {name}")
    cells = list(notebook.cells)
    matches = {}
    for checkpoint in guide.checkpoints:
        found = [i for i, cell in enumerate(cells)
                 if cell.cell_type == "code" and checkpoint.marker in cell.source]
        if len(found) != 1:
            raise ValueError(f"Validação sem âncora única em {name}: {checkpoint.marker!r}: {found}")
        matches[found[0]] = checkpoint
    enriched = [cells[0], *introduction(name, guide)]
    for index, cell in enumerate(cells[1:], 1):
        checkpoint = matches.get(index)
        if checkpoint:
            table = "\n".join(f"| {case} | {expected} | {meaning} |"
                              for case, expected, meaning in checkpoint.expected)
            enriched.append(markdown(
                f"### Validação — {checkpoint.title}\n\n"
                "A célula abaixo executa as verificações deste ponto. "
                "Compare sua saída com os critérios antes de continuar.\n\n"
                "| Caso observado | Resultado esperado | O que comprova |\n|---|---|---|\n" + table,
                "workshop-validation-guide",
            ))
            cell.metadata.setdefault("tags", []).append("workshop-validation")
        enriched.append(cell)
        if checkpoint:
            enriched.append(markdown(
                f"### Leitura do resultado — {checkpoint.title}\n\n{checkpoint.analysis}",
                "workshop-result-reading",
            ))
    evidence = (
        "Esta aula continua **pendente de conversão e teste no ambiente atual**. "
        "Os resultados acima são critérios esperados do código legado, não uma nova evidência de execução."
        if name[:2] in LEGACY else
        "O [aceite AWS de 05/11/2026](../docs/aceite-notebooks-sdk.md) registra a execução "
        "bem-sucedida desta aula, incluindo o ciclo de limpeza e reconstrução. "
        "Esse histórico é uma referência; os outputs e Request IDs gerados agora são a evidência "
        "da sua conta e da sua execução."
    )
    enriched.append(markdown(
        f"## Análise dos resultados\n\n{guide.conclusion}\n\n"
        f"**Evidência e alcance:** {evidence}\n\n"
        f"**Limites da demonstração:** {guide.limits}\n\n"
        f"**Para discutir:** {guide.discussion}\n\n"
        "**Registro da aula:** anote conta/região, run_id quando disponível, casos permitidos/negados "
        "e IDs de requisição. Preserve a mensagem de uma falha inesperada; não publique tokens, "
        "senhas ou credenciais nas saídas. Os notebooks do repositório são distribuídos sem outputs.",
        "workshop-results",
    ))
    notebook.cells = enriched
    notebook.metadata.workshop["teaching_guide_version"] = 1
    return notebook
