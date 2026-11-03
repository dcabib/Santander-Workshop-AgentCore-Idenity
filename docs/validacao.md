# Validação e evidências

**O aceite anterior é do ambiente de referência de quatro contas, não de
qualquer conta AWS.** Consulte a [matriz por aula](contas-e-elegibilidade.md)
antes de iniciar. O bloco 10–14 exige quatro contas no IaC atual, inclusive a
aula 14, cujo fluxo demonstra três. `--labs` não reduz os requisitos do runner.

Há duas verificações diferentes:

- `verify_notebooks.py --validate-only`: sintaxe, metadados AWS e explicação
  antes de cada bloco. Retorna VALID e não comprova operação dos serviços.
- `workshop_runner.py run --execute`: CodeBuild executa os notebooks contra
  os recursos AWS. A seleção passa por preflight antes do build e novamente
  antes do primeiro kernel. Uma dependência ausente bloqueia a seleção;
  uma asserção falha interrompe a execução.

```bash
uv run python scripts/generate_aws_notebooks.py
uv run python scripts/verify_notebooks.py --validate-only
uv run pytest -q
uv run python scripts/workshop_prerequisites.py --runner --check-aws
uv run python scripts/workshop_runner.py deploy --execute
uv run python scripts/workshop_runner.py run --execute
```

O planejamento por contas retorna `ACCOUNTS_CONFIGURED` ou `BLOCKED`; ele não
é aceite operacional. Uma seleção bloqueada antes dos kernels gera resultados
`BLOCKED / AWS_PREFLIGHT`, substituindo um eventual relatório antigo nesse
caminho. Aulas omitidas não contam como PASS. Em uma turma sem as
quatro contas preparadas, remova 10–14 da seleção do participante e use a
demonstração do instrutor. O runner completo só pode ser usado no ambiente
preparado descrito no deploy.

Cada aula verifica seu resultado: identidade autenticada, configuração dos
recursos, respostas de ferramentas, estados de catálogo ou matriz de acesso.
Erros de transporte, timeout, credencial expirada e recurso ausente não contam
como negativa de Policy. O simulador da fonte é identificado explicitamente
nos resultados; ele não comprova uma execução Databricks.

Na aula 04, o aceite exige decisões nativas ALLOW/DENY com os IDs AWS, registros
`backend_invoked` dos controles permitidos e ausência desses registros para as
negativas na janela observada. Páginas vazias de CloudWatch não encerram a busca.
A aula 05 compara todas as políticas ativas com o contrato IaC.

A aula 14 exige os registros aprovados dos próprios Runtimes de origem,
validando o descriptor antes do envio do JWT. A aula 16 expõe os trechos
autorizados enviados ao modelo, os IDs citados e o request ID do Bedrock,
verifica cobertura dos quatro documentos e correlaciona as decisões de
retrieval com os logs nativos.

O build produz `evidence/notebooks-aws.json` e cópias executadas dos notebooks.
O relatório inclui horário, hash SHA-256 da fonte, células executadas e status.
O registro do CodeBuild contém ARN/ID, fases, logs e localização S3 dos artefatos.
Use `workshop_runner.py fetch --build-id ...` para baixar a execução exata.

`audit_notebooks.py --evidence ... --executed ...` compara evidência e fonte:
rejeita falta de aulas, validação apenas estática, hash antigo, código alterado,
células sem execução e saídas de erro. Asserções sobre AWS fazem parte do
código executado, e os logs do build permitem auditar a execução.

Testes unitários cobrem JWT adulterado, issuer/audience/validade, acesso à fonte,
revogação, isolamento de memória e os controles de evidência. Fixtures desses
testes não são uma opção de execução da jornada.

Não publique tokens, senhas, segredos dos clients, state ou planos Terraform.
Os artefatos de execução ficam em S3 privado; revise outputs antes de compartilhá-los.
O [plano da revisão](plano-revisao-aws.md) registra os critérios de conclusão.
