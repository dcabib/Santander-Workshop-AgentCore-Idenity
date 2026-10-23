# Laboratório 15 — o acesso acompanha o documento

Depois de autorizar uma consulta à fonte, surge outra questão: o que acontece
quando copiamos conteúdo para uma base de conhecimento ou o reutilizamos numa
conversa? Este laboratório estuda o ciclo de vida do documento antes da
implantação do [RAG gerenciado no laboratório 16](../rag/README.md).

[Abrir notebook 15](../../notebooks/15_ingestao_acl_memoria.ipynb) ·
[Voltar à jornada](../jornada.md)

![Ingestão, recuperação e memória com ACL](arquitetura.png)

## O que vamos construir

`KnowledgeLab`, em [knowledge.py](../../src/santander_demo/knowledge.py), mantém
documentos sintéticos em dicionários. Cada documento tem ID, fonte, versão,
conteúdo e ACL. A busca compara texto por substring; não há embeddings ou
serviço de busca vetorial nesse exercício.

Os tipos SharePoint, Databricks, SQL local e API AWS descrevem contratos de
origem com estado `CONTRACT_ONLY`. Os textos normalizados já vêm das fixtures.
O código não acessa essas fontes nem executa Bedrock Data Automation.

## Experimento passo a passo

1. **Registrar:** examine R1 (Riscos) e F1 (Fraude), seus metadados e permissões.
   O catálogo de capacidades diz qual ferramenta existe; a ingestão trata o
   conteúdo que essa ferramenta poderá recuperar.
2. **Recuperar:** faça a mesma busca com usuários diferentes. A autorização deve
   filtrar os documentos antes de qualquer uso posterior.
3. **Atualizar:** incremente a versão sequencialmente. A versão controla a
   atualização e o hash registra qual conteúdo entrou na auditoria.
4. **Revogar:** remova acesso de um usuário. A próxima recuperação precisa
   refletir a nova ACL.
5. **Lembrar:** guarde IDs de documentos numa sessão. A memória é separada por
   usuário e sessão e revalida a ACL a cada leitura; ela não guarda uma cópia
   permanente do texto autorizado anteriormente.
6. **Excluir:** remova um documento e confirme que ele não retorna pela busca
   nem pela memória.

A condição de sucesso é observável: outro usuário não lê a sessão; uma
revogação impede reutilização; um documento excluído deixa de ser encontrado.
Os testes estão em [tests](../../tests/), e o notebook exporta um resumo local.

## Executar e encerrar

Siga a [preparação](../preparacao.md), selecione `.venv/bin/python` e execute o
notebook de cima para baixo. Não há infraestrutura para implantar. A célula de
limpeza remove as referências locais e permite reiniciar o exercício.

No [laboratório 16](../rag/README.md), substituímos essa bancada por uma Managed
Knowledge Base com ACL nativa. A memória continua sendo um conceito distinto:
o laboratório 16 não provisiona AgentCore Memory.

## Aprofundar

- [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html)
- [Memória e RAG](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-ltm-rag.html)
- [ACLs de Managed Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
