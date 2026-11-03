# Memória e fonte autorizada

A aula 15 usa AgentCore Memory com actor derivado de issuer/sub e sessão do
exercício. A ferramenta de gravação verifica a ACL da fonte e armazena somente
uma referência de tabela. Ao recuperar, o Runtime lê novamente o grant e os
dados no DynamoDB. Uma revogação não é desfeita pelo histórico da memória.

Os grants e o parâmetro `LifecycleStage` pertencem ao stack backend. O pipeline
da aula também altera F1 e suas ACLs no corpus S3 da Knowledge Base. O provider
aguarda a ingestão antes de iniciar a verificação na AWS.

| Fase | Memory → fonte DynamoDB | Knowledge Base → F1 |
|---|---|---|
| baseline | Grava referência; recupera versão 1 | Ingestão da versão 1 |
| updated | A mesma referência recupera versão 2 | Recuperação da versão 2 |
| revoked | Referência existe, mas C não recebe conteúdo | ACL nega documentos Fraude a C |
| deleted | Referência existe, mas a fonte foi excluída | F1 excluído e ingestão concluída |
| reingested | A mesma referência recupera versão 3 | F1 volta na versão 3 |

Use o mesmo `--memory-session` em todas as fases:

```bash
uv run python scripts/workshop_lifecycle.py baseline \
  --memory-session aula15-IDENTIFICADOR-UNICO --execute
```

Aguarde o build passar e obtenha suas evidências antes de executar a próxima
fase. O runner não tem permissões de deploy: as transições passam pelos
wrappers CloudFormation. A exclusão didática só alcança F1; o versionamento S3
preserva versões anteriores. Depois do ciclo, execute baseline novamente para
restaurar os dados compartilhados antes da jornada completa.

As cinco fases passaram em CodeBuild em 03/11/2026, preservando a sessão
`aula15-20261103-675ffc8a`. A exclusão registrou um documento removido e zero
falhas no job nativo de ingestão. A restauração de baseline também passou.
O índice das execuções está em `evidence/workshop-lifecycle.json`, obtido pelo
pipeline; os notebooks executados permanecem nos artefatos privados de cada build.
A aula 16 acrescenta a inferência Bedrock no Runtime e a matriz A/B/C/D.
Memory não substitui o índice de recuperação nem armazena senhas, tokens ou
cópias de documentos restritos.

[Guia RAG](../rag/README.md) · [Validação](../validacao.md)
