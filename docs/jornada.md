# Jornada de aprendizado

Uma pessoa pede a um assistente informações sobre um cliente fictício. Começamos
com uma ferramenta simples. A cada etapa surge uma pergunta: quem pode chamá-la,
qual agente está atuando, como encontrar outras ferramentas, como atravessar
contas e como preservar as permissões dos dados?

Os laboratórios respondem a essas perguntas com código, diagramas e verificações.
Todos usam dados sintéticos. A numeração de 00 a 16 acompanha a sequência
de aprendizado. Os ramos AWS são opcionais e têm ambientes independentes.

## 1. Entender uma chamada antes de construir um agente

No [00 — Preparação](../notebooks/00_preflight.ipynb), confira o kernel e observe
os componentes da bancada local. Diferencie um serviço configurado de uma chamada
realmente executada. Você deve conseguir apontar onde ficam código, ferramentas,
identidade, autorização e catálogo.

No [01 — Gateway e MCP](../notebooks/01_gateway_targets.ipynb), uma consulta vira
uma ferramenta com nome e argumentos. Execute `initialize`, `tools/list` e
`tools/call`. Compare um servidor MCP com um target Lambda. O primeiro resultado
é compreender como um cliente encontra e chama uma ferramenta, antes de usar LLM.

**Ao avançar:** explique por que listar uma ferramenta não deveria autorizar sua execução.

## 2. Descobrir quem está pedindo e o que pode fazer

No [02 — Identity e OBO](../notebooks/02_identity_entra_obo.ipynb), examine um JWT
e entenda emissor, audiência e expiração. Compare a identidade de uma aplicação
(M2M) com a delegação em nome de uma pessoa (OBO). O teste local rejeita a audiência
errada; o exercício AWS compara o usuário no Microsoft Graph.

No [03 — Identidade do agente](../notebooks/03_identity_agente_mcp.ipynb), mantenha
a pessoa e troque a aplicação chamadora. O supervisor consegue consultar Fraude;
o agente de Riscos não. A identidade do usuário e a identidade do agente são
parte da decisão.

No [04 — Policy e Cedar](../notebooks/04_policy_cedar.ipynb), transforme essa
decisão em regras verificáveis. Varie usuário, chamador, ferramenta e limite de
registros. Observe onde uma recusa acontece e confira que o backend negado não
executou na bancada local.

No [05 — Autoria de políticas](../notebooks/05_policy_autoria.ipynb), passe da
intenção à regra: gere Cedar, revise condições e execute a matriz. Diferencie
gerar um rascunho, validá-lo e publicar uma política.

**Ao avançar:** explique por que um JWT válido pode resultar em uma chamada negada.

## 3. Encontrar capacidades sem ampliar permissões

No [06 — Governança do Registry](../notebooks/06_registry_governanca.ipynb),
publique, submeta e aprove um registro local. O publicador não pode aprovar
a própria publicação com esse papel; somente registros aprovados aparecem na busca.

No [07 — Quatro personas](../notebooks/07_registry_personas.ipynb), acompanhe
a mesma entrega: o desenvolvedor testa MCP e agente; o publicador registra
os descritores; o aprovador revisa o conteúdo; o consumidor descobre e usa o agente.
Compare DRAFT, PENDING_APPROVAL, APPROVED e REJECTED, e experimente descobrir
sem ter autorização de execução. O ramo AWS usa roles reais e um pipeline IaC
próprio em uma conta; veja o [guia do Registry](registry/README.md).

No [08 — Descoberta e execução](../notebooks/08_registry_descoberta_execucao.ipynb),
o supervisor encontra Riscos e Fraude no catálogo. A Policy continua decidindo
quais chamadas são permitidas. O endpoint descoberto é conferido antes de enviar
credenciais.

**Ao avançar:** diferencie aprovação no catálogo de autorização de uma chamada.

## 4. Colocar os componentes na AWS

No [09 — Runtime, Gateway e Identity com Terraform](../notebooks/09_terraform_runtime_gateway_identity.ipynb),
implante uma solução em uma conta. O Runtime executa Python, Identity obtém um
token Cognito M2M e o Gateway chama uma Lambda com dados sintéticos.

Leia os arquivos Terraform, construa o pacote ARM64, revise o plano e aplique-o.
Teste chamadas válidas e inválidas. Depois habilite o LLM: ele escolhe a ferramenta,
mas continua sujeito ao mesmo contrato. Termine conferindo ausência de drift e
aprenda a planejar a remoção.

Esse ambiente é independente dos laboratórios Entra. Ele ensina implantação e
autenticação de aplicação; não reproduz as regras Cedar e OBO dos exercícios anteriores.

**Ao avançar:** desenhe os três tipos de credencial usados — IAM/SigV4, WAT e OAuth —
e indique o destinatário de cada um. Use o [guia Terraform](terraform/README.md).

## 5. Distribuir ferramentas e decisões entre contas

No [10 — Composição entre contas](../notebooks/10_santander_multi_conta.ipynb),
separe origem, hub e domínio. Entenda ARNs, sessões STS e a diferença entre
verificar uma topologia e executar uma chamada entre contas.

No [11 — Agente central e três áreas](../notebooks/11_blog_multi_account_gateway_mcp.ipynb),
um agente Strands hospedado consulta Retail, Transaction e Lending por um Gateway.
O usuário é avaliado na entrada; os destinos recebem credenciais M2M. Observe
as ferramentas escolhidas, a consulta documental e a operação de exclusão negada.

No [12 — Um Gateway por conta](../notebooks/12_gateways_por_conta_identity_policy.ipynb),
cada domínio passa a controlar sua entrada. Compare uma negativa na plataforma
com outra no domínio. OBO preserva a pessoa até os MCPs, e `whoami` verifica a
identidade recebida. O agente deste laboratório roda no kernel do notebook.

Esses cenários têm implantações próprias; não são atualizações do state Terraform
do laboratório 09. Consulte os guias de [agente central](banking/README.md) e
[Gateways federados](federation/README.md).

**Ao avançar:** explique por que a autorização da plataforma não obriga um domínio
a aceitar a chamada e por que OBO até o MCP não garante grants por usuário no banco.

## 6. Levar a identidade até a fonte dos dados

No [13 — Databricks isolado](../notebooks/13_databricks_e_evidencias.ipynb),
observe primeiro a fonte: token exchange, `current_user()` e uma consulta canário.
Compare um usuário com `SELECT` e outro sem esse grant. O caminho usa SQL REST;
serve para entender a prova que será exigida da integração.

No [14 — Agentes, hub e Databricks](../notebooks/14_cenario_santander_integrado.ipynb),
combine o que aprendeu. Dois agentes hospedados usam aplicações diferentes,
descobrem capacidades no Registry e atravessam Gateways até o MCP Databricks.
Uma chamada para na Policy; outra passa pela Policy e é negada na fonte.

Correlacione requisições e query IDs. A resposta de negócio e o trace completo
são evidências diferentes. O [guia integrado](journey/README.md) descreve os
pré-requisitos e o [procedimento de correlação](journey/trace.md).

**Ao avançar:** localize a fronteira de cada negativa sem confundir erro de rede,
token ou SQL com decisão de autorização.

## 7. Transformar documentos em conhecimento autorizado

No [15 — Ingestão, ACL e memória](../notebooks/15_ingestao_acl_memoria.ipynb),
troque tabelas por documentos. Registre conteúdo com permissões, recupere como
usuários diferentes, revogue uma ACL e exclua um documento. A memória guarda
referências e revalida o acesso. Tudo acontece localmente.

No [16 — RAG por usuário](../notebooks/16_rag_managed_identity_policy.ipynb),
leve o contrato a uma Managed Knowledge Base. A consulta é a mesma: A recebe
Riscos, B recebe Fraude, C pode consultar ambos e D é bloqueado. Tente falsificar
o usuário; observe a Policy vincular o JWT ao `userContext` antes da recuperação.
Somente trechos autorizados entram no modelo.

Uma busca retorna os documentos relevantes entre os permitidos. Por isso, o
laboratório verifica isolamento por resposta e cobertura por consultas específicas.
Veja os guias de [ingestão](ingestao/README.md) e [RAG](rag/README.md).

**Ao concluir:** explique onde autenticar, onde autorizar a ferramenta, onde
filtrar documentos e o que revalidar ao reutilizar memória.

## Como percorrer a jornada

Prepare o ambiente com [este guia](preparacao.md). Percorra primeiro os ramos locais;
os cenários cloud podem ser executados quando seus pré-requisitos estiverem disponíveis.
Não é necessário implantar todos os ambientes ao mesmo tempo.

Os tempos nos notebooks são estimativas do exercício, sem provisionamento e
preparação dos provedores externos. A jornada completa ocupa várias sessões.
Pare nos pontos de aprendizagem acima e retome pelo próximo laboratório.

Use o [glossário](conceitos.md) durante a leitura, o [guia de validação](validacao.md)
para interpretar os resultados e o [guia de limpeza](cleanup.md) ao encerrar.
