# Laboratório 16 — RAG com documentos autorizados por usuário

No [laboratório 15](../ingestao/README.md), aprendemos a acompanhar a ACL durante
o ciclo de vida do documento. Agora usamos uma Amazon Bedrock Managed Knowledge
Base (`MANAGED`) para recuperar trechos autorizados e fornecê-los a um modelo.
A identidade precisa continuar vinculada à consulta em cada etapa.

[Abrir notebook 16](../../notebooks/16_rag_managed_identity_policy.ipynb) ·
[Voltar à jornada](../jornada.md) · [Validação](../validacao.md#laboratório-16)

O ambiente é autocontido em uma conta AWS: CloudFormation provisiona Cognito,
quatro usuários sintéticos, documentos, KB, Gateway, Identity e Policy. Ele não
depende da infraestrutura dos laboratórios multi-conta nem de um tenant Entra.
A vê Riscos, B vê Fraude, C vê ambos e D não pode consultar o RAG.

![Identidade, autorização da ferramenta e ACL documental](arquitetura.png)

## O que observar no notebook

As explicações seguem a ordem: requisito → motivo do controle → código →
resultado esperado → verificação. O notebook vem sem outputs salvos; as
tabelas **esperado × observado × PASS/FAIL** são produzidas na execução.
Uma negativa esperada para D é sucesso do teste. Erros de serviço ou rede
interrompem a execução e não contam como prova de autorização.

| Etapas | Conteúdo para acompanhar |
|---|---|
| 2–3 | Documentos sintéticos, ACLs de Riscos e Fraude e matriz extraída dos sidecars |
| 4–5 | JWT verificado, três regras Cedar completas e vínculo com `userContext` |
| 6–8 | Matriz local, tentativa A→C, claim ausente e contexto entregue ao modelo |
| 9–10 | Conector nativo e recursos CloudFormation que criam usuários, ACLs e policies |
| 11–13 | Preflight, negativas de autenticação/IAM, quatro logins e emissão de WAT |
| 14–19 | Resultados AWS por usuário, falsificação, evidências e diagnóstico de falhas |
| 20 | Revogação, limites do cenário e evolução |

Três diagramas ficam incorporados ao notebook e também podem ser abertos em SVG:

* [Arquitetura e responsabilidades](arquitetura.svg).
* [Criação pelo IaC: código, templates e quatro fases](provisionamento.svg).
* [Decisão de acesso: caminho permitido, negativas e falhas](decisao-acesso.svg).

## Por que existem três controles

| Controle | Responsabilidade |
|---|---|
| Cognito + autenticação de entrada do AgentCore | Validar assinatura, emissor, expiração, audiência e tipo do JWT |
| AgentCore Policy, `ENFORCE` | Autorizar `rag___Retrieve`; vincular `sub` e e-mail assinados ao `userContext.userId`; negar D |
| ACL nativa da Managed KB | Aplicar permissões nos documentos antes de devolver os trechos |

A KB faz filtragem por ACL, mas **não autentica o `userContext`**. Aceitar um
e-mail arbitrário na chamada permitiria consultar como outra pessoa. O cliente
deriva esse valor do JWT verificado, e o Cedar verifica novamente a igualdade
com a identidade configurada. O teste A→C envia deliberadamente um valor falso.

O Gateway possui uma workload identity do AgentCore Identity. O laboratório
também exercita `GetWorkloadAccessTokenForJWT` com uma workload provisionada pelo
IaC, inclusive para D: ter identidade não concede acesso aos documentos.
O WAT é um token interno do Identity, não substitui o JWT de entrada do Gateway.

O engine contém três regras `permit`, para A/B/C. D é negado pela decisão
padrão do Cedar: nenhum `permit` aplicável significa `DENY`. As três regras
usam `FAIL_ON_ANY_FINDINGS`: a validação da política precisa passar antes da
publicação. Autenticar D e emitir seu WAT não cria um `permit` para recuperar dados.

O conector nativo autentica o acesso à KB com a role IAM do Gateway. Por isso
não há troca OBO neste caminho AWS. O código opcional de Entra/OBO permanece em
`infra/rag/entra` e no template `access.json`, mas não é implantado pelo fluxo
Cognito, que usa `access-cognito.json`. A variante Entra exige seu próprio
tenant, aplicações, consentimentos e validação de delegação; não faz parte
do percurso autocontido deste notebook.

## Dados e matriz esperada

| Usuário | R1/R2 — Riscos | F1/F2 — Fraude | Geração |
|---|---|---|---|
| A | Permitido | Negado | Só com contexto de Riscos |
| B | Negado | Permitido | Só com contexto de Fraude |
| C | Permitido | Permitido | Com ambos |
| D | Negado | Negado | Não executa |

Cada documento tem um arquivo `.metadata.json`, com `document_id`, `domain` e
`accessControlList`. Há também ACLs por prefixo no arquivo global. Os metadados
identificam o documento; **o campo `domain` sozinho não é um controle de acesso**.
As ACLs são aplicadas pelo serviço gerenciado.

A fonte S3 tem `aclEnabled=true`. O preflight rejeita fontes extras, pois uma
fonte sem ACL poderia retornar resultados mesmo sem `userContext`. Mudanças
nas ACLs S3 exigem nova ingestão; não há verificação em tempo real nessa fonte.

## Construir o ambiente por fases

Na raiz do repositório:

```bash
uv sync --frozen --extra banking
uv run --frozen --extra banking pytest tests/test_rag*.py -q
uv run --frozen python -m infra.rag.generate
uv run --frozen cfn-lint infra/rag/templates/*.json
uv run --frozen --extra banking python scripts/build_artifacts.py --banking
```

O pipeline tem quatro fases. Execute uma de cada vez, aguardando o stack
anterior. `--execute` aplica o change set. Sem essa opção, o wrapper cria o
change set para revisão; a preparação pode publicar o ZIP no bucket de artefatos.
Todas as mutações de recursos, senhas, documentos e ingestão pertencem ao IaC.

```bash
uv run --frozen --extra banking python -m scripts.rag_deploy bootstrap --execute
uv run --frozen --extra banking python -m scripts.rag_deploy identity --execute
uv run --frozen --extra banking python -m scripts.rag_deploy data --execute
uv run --frozen --extra banking python -m scripts.rag_deploy access --execute
```

Os padrões são `--profile default --region us-east-1 --project santander-rag`.
Use os mesmos valores em todas as fases. O pipeline lê STS, resolve a role do
implantador e gera `config/local.rag.json` com identificadores reais, sem
senhas ou tokens. Os quatro subjects vêm dos usuários criados pelo Cognito.

O stack `identity` cria um pool com cadastro público desabilitado, um app
client, quatro usuários e quatro senhas aleatórias no Secrets Manager.
Um custom resource define as senhas permanentes. Não envia e-mails.

O stack `data` cria a Managed KB, a fonte S3 privada e uma função de
publicação/ingestão, chamada exclusivamente pelo CloudFormation. O stack
`access` cria Gateway, target nativo, workload identity, Policy, logs e uma
role de execução com **negação explícita de retrieval direto**. Essa role pode
invocar apenas o modelo configurado; o perfil de implantação não é a role do RAG.

O Gateway precisa de `GetPolicyEngine`, `AuthorizeAction` e
`PartiallyAuthorizeActions` já na criação. A permissão IAM usa o ARN exato do
engine e o prefixo `gateway/${Project}-*` na mesma conta e região, porque o
serviço verifica a autorização antes de disponibilizar o ARN gerado do Gateway.
As regras Cedar usam o ARN exato do Gateway após sua criação.

Com embeddings `MANAGED`, o serviço exige omitir `ChunkingConfiguration`.
A divisão dos documentos fica a cargo da configuração gerenciada padrão.

## Verificar recuperação, geração e isolamento

```bash
uv run --frozen --extra banking python -m scripts.rag_check
```

O comando primeiro confere o ambiente por APIs de leitura. Depois autentica
quatro sessões, solicita os WATs, consulta a tool MCP e chama `Converse`
somente após validar os trechos recebidos. Executa também a tentativa de A
consultar como C. Um retorno com documento indevido falha a consulta inteira;
não é escondido por um filtro local.
Verifica também a negativa de chamadas anônimas, de JWT inválido e de
retrieval direto com a role de execução.

Os testes usam o perfil do instrutor para ler as senhas sintéticas. Esse perfil
é administrador do ensaio e pode autenticar as quatro contas intencionalmente.
Em uma aplicação, cada pessoa faria seu próprio login; usuários finais não
receberiam as credenciais IAM ou acesso ao Secrets Manager do instrutor.

`evidence/rag-live.json` contém IDs de documentos, resultados e referências
pseudonimizadas. Não contém respostas, trechos, e-mails, senhas ou JWTs. O
resultado só recebe `PASS` com as cinco verificações e correlação dos logs.
Para A/B/C, quatro consultas adicionais pelos títulos dos documentos verificam
a cobertura de todas as permissões, sem novas chamadas ao modelo. Cada resposta
também precisa conter somente documentos autorizados. A validação aceita as
duas representações exatas da origem devolvidas pelo serviço: `s3://` e a URL
HTTPS do mesmo bucket/objeto.
Se a entrega de logs atrasar, repita apenas a leitura:

```bash
uv run --frozen --extra banking python -m scripts.rag_check --correlate-only
```

Erros de rede, autenticação, modelo ou configuração não contam como negativa
da Policy. A geração é sem histórico compartilhado e não utiliza tools: o
modelo só recebe a pergunta e os trechos já autorizados. RAG continua
probabilístico; os testes verificam isolamento e documentos recuperados,
não prometem que toda formulação de pergunta recuperará todos os documentos.
Falhas de transporte podem repetir somente `Retrieve`, até três tentativas,
sempre no mesmo Gateway e com o mesmo JWT e argumentos. Uma negativa MCP,
erro de validação ou falha do modelo não é repetida por esse mecanismo.

## Validar o notebook em um kernel novo

Depois de validar o código, regenere o workshop e execute suas células:

```bash
uv run --frozen --extra banking python -m scripts.generate_rag_notebook
uv run --frozen --extra banking python -m scripts.rag_notebook_check
uv run --frozen --extra banking python -m scripts.rag_notebook_check --live
```

O último comando usa os stacks existentes. Não aplica IaC nem executa cleanup
cloud. Os relatórios `evidence/rag-notebook-local.json` e
`evidence/rag-notebook-live.json` registram o hash do notebook e as células
executadas. O notebook distribuído permanece sem outputs e com `RUN_AWS=False`.

## Resolver falhas pelo IaC

Consulte eventos CloudFormation e os logs dos custom resources. Corrija a
fonte Python/templates, regenere, reconstrua o ZIP se o código mudou e
reaplique a fase correspondente. Um stack em `ROLLBACK_COMPLETE` precisa ser
removido pelo wrapper de cleanup antes da recriação, após conferir retenções.
Não altere roles, usuários, ACLs ou documentos manualmente para contornar erros.

Não substitua `MANAGED` por `VECTOR` se o serviço estiver indisponível:
região, habilitação da conta e suporte do CloudFormation precisam ser
diagnosticados. O cenário depende das ACLs nativas do modo Managed.

## Limpeza

Use `scripts/cleanup.py --scenario rag`, primeiro em modo de leitura, informando
template, nome real do stack, perfil, conta e região. Após revisar o ARN,
execute o mesmo wrapper com `--execute --confirm-stack-id ARN`.

Ordem: `access-cognito` (stack termina em `-access`), `data`, `identity`,
`bootstrap`. A KB, sua fonte e o bucket de documentos usam `RetainExceptOnCreate`:
uma criação malsucedida é limpa, mas a remoção normal de um ambiente criado
com sucesso preserva esses recursos. O bucket de artefatos usa `Retain`.
Apagar stacks não elimina todos os recursos ou custos. Qualquer descarte de recursos
retidos deve ser tratado explicitamente pelo seu IaC. Os segredos e usuários
do stack de identidade são exclusivos deste ensaio.

## Concluir a jornada

Explique o resultado usando três perguntas: quem foi autenticado, quem pôde
invocar a ferramenta e quais documentos a KB pôde devolver? Depois examine o
contexto recebido pelo modelo. Essa separação liga os conceitos da primeira
chamada à recuperação governada de conteúdo.

## Referências públicas

- [Criar uma Managed KB](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
- [ACLs e modelo de confiança](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
- [ACLs da fonte S3](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3-acl.html)
- [Retrieve com userContext](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-acl.html)
- [Conector nativo para Managed KB](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html)
- [Entrada JWT no Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html)
- [AgentCore Identity com Cognito](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-getting-started-cognito.html)
- [Claims no principal Cedar](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/example-policies-principal.html)
- [Permissões IAM para Policy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-permissions.html)
- [OBO para destinos OAuth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)
