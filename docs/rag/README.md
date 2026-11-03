# RAG gerenciado — identidade, ACL e geração na AWS

A aula 16 utiliza Cognito, AgentCore Identity, Runtime, Gateway, Policy, S3,
Bedrock Knowledge Bases e Bedrock Converse. A orquestração e a geração de
resposta ficam no Runtime RAG. O notebook autentica a pessoa e invoca o agente.

| Pessoa | Documentos autorizados |
|---|---|
| A | Riscos: R1 e R2 |
| B | Fraude: F1 e F2 |
| C | Riscos e Fraude |
| D | Nenhum |

A identidade verificada determina o contexto enviado ao retrieval. A Policy
impede substituição por outra pessoa. O serviço de recuperação aplica ACL e
a geração recebe apenas os trechos autorizados. O cliente confere fontes,
citações e o conjunto de documentos antes de aceitar o resultado.

A role do Runtime possui Deny explícito para retrieval direto. A aula observa
essa negativa e a matriz A/B/C/D. Erro de rede não é prova de ACL.

```bash
uv run python scripts/build_artifacts.py --banking
uv run python scripts/rag_deploy.py bootstrap --execute
uv run python scripts/rag_deploy.py identity --execute
uv run python scripts/rag_deploy.py data --execute
uv run python scripts/rag_deploy.py access --execute
uv run python scripts/workshop_deploy.py rag-agent --execute
```

A fase data gerencia fonte S3, corpus sintético, ACL, Knowledge Base e ingestão
por custom resources CloudFormation. Aguarde os estados finais antes de
consultar. Access gerencia Gateway e Policy. A configuração gerada contém
identificadores e referências aos segredos.

Cognito é o provedor desta jornada. Com Entra ID, assinatura, emissor, audiência
e vínculo pessoa/aplicação seguem o mesmo princípio, mas os claims e eventuais
trocas OBO precisam da configuração específica do tenant e destino.

[Validação da aula](validacao.md) · [Runner AWS](../deploy.md)
