# Aula 01 — criação Lambda e permissão de tags

Status em 03/11/2026: **alternativa A aprovada e aplicada na AWS**.
A Lambda ficou ativa e o Gateway foi criado. A criação do target encontrou
um [novo bloqueio de AssumeRole](decisao-propagacao-iam-gateway-sdk.md).

## Erro observado

Após a aprovação e aplicação da alternativa Cognito, o notebook criou os dois
usuários, configurou suas senhas e criou o grupo de logs e a role Lambda.
`CreateFunction` parou com:

```text
AccessDeniedException: not authorized to perform: lambda:TagResource
on resource: arn:aws:lambda:us-west-2:456332459064:function:santander-6825d3096100-customer-risk
because no identity-based policy allows the lambda:TagResource action
```

`GetFunction`, em consulta somente de leitura, confirmou que a função não foi
criada. A policy Lambda consultada permite `CreateFunction`, `GetFunction`,
`InvokeFunction` e `DeleteFunction`, mas não contém `TagResource`.
Naquele momento, o Gateway e o target ainda não haviam sido criados.

## A — Criar a função sem tags e conferir sua identidade completa

Código preparado em
[`scripts/sdk_gateway_lesson.py`](../scripts/sdk_gateway_lesson.py) e
[`scripts/sdk_cleanup_lesson.py`](../scripts/sdk_cleanup_lesson.py):

* A célula chama `CreateFunction` sem o parâmetro opcional `Tags`. Não é um
  fallback automático após erro: esta é a definição da função no notebook.
* A descrição recebe um marcador da execução. O registro guarda ARN, nome,
  marcador, role e hash do ZIP enviado.
* A espera usa `GetFunction`, já disponível, e mostra a consulta de estado.
* Retomada e limpeza exigem correspondência de ARN, nome, descrição, hash do
  código e role. A role continua identificada pelas tags da execução. Qualquer
  divergência interrompe a operação.
* Um conflito de criação não provoca adoção de outra função. O notebook não
  lista funções por prefixo para apagá-las.

A função permanece acessível por invocação IAM, com role e permissões
restritas. Não há Function URL. Cognito, validação JWT e a configuração do
Gateway não mudam. Nenhuma policy do ambiente é alterada.

Os testes verificam que a retomada e a limpeza recusam alterações na descrição,
no ARN, na role ou no hash do código. A criação da função passou na AWS; a
invocação via MCP continua pendente do target.

## B — Manter tags Lambda e ajustar permissões do evento

O administrador da conta pode avaliar a concessão de `lambda:TagResource`
para essa função e das permissões de leitura necessárias, pelo mecanismo que
administra o evento. Em seguida, podemos manter a criação com tags.
Não faremos alterações diretas nas policies protegidas da role do VS Code.

## Motivo da pausa original

Sua regra de AGENTS.md exige diagnosticar cada novo bloqueio e escolher uma
alternativa antes de retomar mutações. Improvisar uma alteração na role do
evento criaria divergência de permissões fora do material do workshop.
A alternativa A deste documento já foi autorizada e aplicada. A pausa atual
é a descrita na decisão de AssumeRole vinculada no início. Os recursos criados
permanecem registrados; a limpeza não foi executada.
