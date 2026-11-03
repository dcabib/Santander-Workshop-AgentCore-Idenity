# Quatro contas AWS

**Pré-requisito: quatro contas AWS distintas. Este bloco não executa em
conta única.** As aulas 10–14 exigem plataforma, Retail, Transaction e Lending
no manifesto atual. As aulas 10–11 usam as quatro diretamente; 12–14 mantêm
dependências da implantação completa. Veja a
[matriz de contas](../contas-e-elegibilidade.md).

As aulas 10–12 usam plataforma, Retail, Transaction e Lending em contas
separadas. O STS compara cada sessão com seu ID configurado e rejeita contas
duplicadas. Cada domínio tem Gateway, Policy ENFORCE, Runtime MCP, fonte
sintética DynamoDB e Memory próprios.

O Gateway da plataforma encaminha chamadas a três Gateways de domínio. Cada
fronteira autentica a pessoa e autoriza a ferramenta e seus parâmetros. A
fonte verifica os grants independentemente. O agente de plataforma executa
Bedrock Converse no Runtime; não há agente hospedado no kernel do notebook.

O exemplo oficial que inspirou a organização por domínios permanece como
referência em `docs/banking/UPSTREAM-LICENSE`. A implementação executável desta
jornada está em `infra/workshop` e `src/santander_demo/aws_workshop`.

[Sequência de deploy](../deploy.md) · [Conceitos](../conceitos.md)
