# Gateways federados

**Aula 12: a chamada percorre duas contas, mas o manifesto e a federação
atuais exigem quatro contas preparadas.** Ela não executa em uma conta única.
Sem esse ambiente, acompanhe a demonstração do instrutor; consulte a
[matriz de contas](../contas-e-elegibilidade.md).

A aula 12 percorre Gateway Plataforma → Gateway de domínio → Runtime MCP.
Cognito emite o JWT da pessoa e aplicação; cada Gateway possui authorizer e
engine Policy em ENFORCE. Cedar autoriza cada trecho e a fonte reaplica sua ACL.

Os targets e destinos são declarados em `infra/workshop/generate.py`. A
propagação do cabeçalho Authorization usa o interceptor REQUEST documentado
pela AWS para chamadas entre Gateways. No último salto ao Runtime MCP, o
Gateway usa IAM/SigV4 e envia o JWT humano em um header separado, validado
novamente pelo backend. A resource policy nega invocação por qualquer outra
role. O preflight confere interceptor, authorizer, resource policy e trust
policy antes das chamadas.

Essa propagação usa audiência explicitamente compartilhada. Não é OBO.
Uma implantação Entra com audiências distintas exigiria troca OAuth para cada
destino e políticas correspondentes; isso deve ser implementado e validado
antes de alegar equivalência operacional.

[Deploy](../deploy.md) · [Documentação AWS sobre headers](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html)
