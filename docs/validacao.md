# Validar o que cada laboratório ensina

Uma resposta correta pode ter vindo de uma simulação, de uma ferramenta real
ou de um modelo. Antes de concluir que a arquitetura funciona, identifique
**qual caminho foi executado e qual afirmação foi verificada**.
Este guia acompanha a [jornada](jornada.md) e ajuda a interpretar seus resultados.

Calcule as expectativas a partir do requisito escrito, separadamente da
configuração usada pela aplicação. Se implementação e teste lerem a mesma
permissão errada, ambos podem concordar e ainda contrariar o workshop.

## Três níveis de evidência

| Nível | O que verifica | O que ainda precisa de prova |
|---|---|---|
| Local | Contratos, validação de entradas, lógica de autorização, empacotamento e comportamento dos testes | IAM, emissão de tokens e integração dos serviços |
| Integração real | Chamada autenticada, resultado esperado e erro específico nos serviços implantados | Percurso completo quando faltam logs ou IDs correlacionados |
| Correlação | A mesma operação observada nas fronteiras relevantes, incluindo o destino | Não comprova cenários que não foram exercitados |

`LOCAL_SIMULATION` identifica simulação; `NOT_RUN` identifica uma etapa pulada.
`PENDING_EVIDENCE` exige completar uma prova. `PASS` tem o alcance do teste que
o produziu: o sucesso de uma célula não é aprovação automática de toda a solução.
Timeout, erro de rede e credencial expirada não são prova de bloqueio por Policy.

## Executar a verificação local

Na raiz do projeto:

```bash
uv sync --frozen --extra banking
uv run --frozen --extra banking pytest -q
uv run --frozen --extra banking python scripts/verify_notebooks.py
```

O segundo comando testa o código. O terceiro executa os 17 notebooks em kernels
novos, com as opções de nuvem desativadas. Verifica a execução das células e a
limpeza local. Grava `evidence/notebooks.json` e cópias em `evidence/executed/`;
os notebooks distribuídos permanecem sem outputs.

Para comparar o conteúdo com valores e efeitos observados, além da execução:

```bash
uv run --frozen --extra banking python -m scripts.audit_notebooks
uv run --frozen --extra banking python -m scripts.audit_notebook_faults
```

Esses comandos usam expectativas independentes da configuração da aplicação.
Uma falha injetada só aprova o controle quando a asserção correspondente a rejeita.
Os controles incluem perda de acesso de C a Fraude, resposta MCP de outro
cliente e permissão indevida para C008 em Retail. Uma exceção incidental de
rede, importação ou sintaxe não aprova esses controles.

`audit_notebooks` observa o catálogo, as chamadas a backends, as decisões Cedar,
os documentos entregues ao modelo, a memória e os contadores de cotas. Os
arquivos `evidence/notebook-audit*.json` registram esperado, observado e hash
do notebook. Um notebook novo precisa de expectativas próprias no verificador;
executar suas células sem erro não basta para aprovar seu conteúdo.

Para validar templates após regenerá-los, use `cfn-lint` no diretório do cenário
indicado em seu guia. No Terraform, `validate` confere a configuração e
`terraform test` usa providers simulados, conforme o [laboratório 09](terraform/README.md).
Nenhum desses resultados substitui o teste da implantação.

## Pontos de verificação durante a jornada

| Etapa | Resultado que precisa ser observado |
|---|---|
| 00–01 | A ferramenta conhecida recebe a entrada esperada e retorna o contrato documentado |
| 02–03 | Usuário e aplicação são distinguidos; audiência e assinatura são verificadas |
| 04–05 | Casos permitidos e negados correspondem às condições Cedar; rascunho não vira política automaticamente |
| 06–08 | Papéis, publicação e aprovação são separados; descobrir não concede execução nem permite enviar credenciais a qualquer destino |
| 09 | O plano Terraform corresponde ao ambiente; Runtime, Identity e Gateway completam uma chamada |
| 10 | Contas e roles correspondem à topologia; uma chamada real exige invocação e logs |
| 11 | O agente hospedado consulta as três áreas; escrita permanece sem permissão |
| 12 | `whoami` preserva `tid:oid`; negativas da plataforma e de Retail são distinguíveis |
| 13 e 14 | Identidade na fonte e grant de `SELECT` são verificados separadamente |
| 15 | Alterar ACL ou excluir um documento impede sua reutilização, inclusive pela memória local |
| 16 | Policy vincula usuário e contexto; a KB retorna apenas documentos autorizados |

Para uma negativa de ferramenta, execute também um caso permitido com a mesma
infraestrutura. No cenário integrado, use o [guia de trace](journey/trace.md)
para comprovar em qual fronteira a chamada parou.

## Laboratório 07

Durante as fases IaC, confira que MCP e AGENT ficam ocultos em
DRAFT/PENDING_APPROVAL e aparecem após a aprovação. No consumo, compare
cliente, risco e resposta do agente com a entrada enviada. Runtime e Gateway
devem recusar chamadas anônimas; uma sessão limitada à descoberta deve receber
negativa ao invocar o agente.

Versão rejeitada e hash alterado são exercícios locais. A matriz IAM usa
simulação de políticas; a negativa do consumidor é uma invocação real.
As roles de publicação e aprovação executam providers distintos, mas um
operador do sandbox orquestra o pipeline.

```bash
uv run --frozen --extra banking pytest tests/test_registry_workflow.py -q
uv run --frozen --extra banking python scripts/registry_check.py --live
```

O segundo comando verifica uma implantação já aprovada e grava
`evidence/registry-personas.json`. O [guia do Registry](registry/README.md)
explica como reproduzir as fases a partir de rascunhos e como limpar o ambiente.
Para conferir estados, dados retornados, request IDs e decisões IAM do
ambiente já aprovado, use:

```bash
uv run --frozen --extra banking python -m scripts.audit_live_notebooks registry
```

Essa verificação não repete publicação e aprovação. Para acompanhar essas
transições, execute o notebook junto com as fases do IaC, conforme o guia.

## Laboratório 09

Após implantar pelo [Terraform](terraform/README.md), execute:

```bash
uv run --frozen --extra banking python scripts/terraform_check.py --llm
uv run --frozen --extra banking python scripts/terraform_deploy.py drift
uv run --frozen --extra banking python scripts/terraform_notebook_check.py --live
```

O verificador testa autenticação, cliente OAuth não autorizado, catálogo MCP,
cliente sintético inexistente, consultas pelo Runtime e uso da ferramenta pelo
modelo. O relatório `evidence/terraform-agentcore-live.json` só recebe
`AWS_LIVE/PASS` quando todas as asserções solicitadas passam. `--live` executa uma
cópia do notebook contra o ambiente existente, sem habilitar apply ou destroy.

O caso C999 comprova **erro sem perfil retornado**, com `cause=NOT_PROVEN`:
o erro genérico do Gateway não identifica cliente inexistente nem comprova
uma recusa de permissão. Trate esse caso separadamente das negativas HTTP.

Para comparar os perfis com os valores esperados, conferir a resposta do
agente e encontrar os IDs de Gateway/Lambda no CloudWatch:

```bash
uv run --frozen --extra banking python -m scripts.audit_live_notebooks terraform
```

Esse comando executa o notebook com AWS e LLM ativados e confere as evidências
do ambiente existente. Provisionamento e remoção continuam desativados.

## Laboratório 16

Após o deploy do [RAG](rag/README.md):

```bash
uv run --frozen --extra banking python -m scripts.rag_check
```

A/B/C devem recuperar somente documentos autorizados e gerar uma resposta com
esse contexto. Consultas adicionais pelos títulos verificam a cobertura das ACLs
sem chamar o modelo novamente. D deve parar antes da geração; a tentativa de A
usar a identidade de C também precisa falhar.

O relatório `evidence/rag-live.json` reúne as verificações e a correlação dos logs.
Se apenas a entrega dos logs estiver pendente, `--correlate-only` repete a leitura
sem repetir consultas ou inferências. A existência do notebook ou dos testes
locais não significa que esse relatório AWS tenha sido produzido.

O [guia de validação do RAG](rag/validacao.md) explica como comparar as ACLs
no S3, os trechos recuperados e o contexto enviado ao modelo. Para executar
essas comparações durante o notebook e conferir a decisão nativa do Policy:

```bash
uv run --frozen --extra banking python -m scripts.audit_live_notebooks rag
```

## Registrar e compartilhar

Guarde o cenário, a versão do código, região, horário, casos executados e IDs
reais de correlação nos relatórios locais em `evidence/`, ignorados pelo Git.
Mantenha em `docs/` as instruções para reproduzir e interpretar a validação.

Os relatórios do RAG omitem senhas, tokens e e-mails; alguns verificadores
registram dados e respostas sintéticos. Revise outputs de células antes de
compartilhar uma cópia executada. A evidência precisa permitir entender a
conclusão sem expor as credenciais usadas para obtê-la.

Ao terminar, siga a [limpeza](cleanup.md). Recursos retidos e ambientes ainda
implantados continuam com seu próprio ciclo de vida e possíveis custos.
