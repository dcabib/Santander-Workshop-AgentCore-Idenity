permit(
  principal,
  action == AgentCore::Action::"riscos___consultar_risco",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/local-demo"
)
when {
  principal.hasTag("tid") &&
  principal.getTag("tid") == "tenant-demo" &&
  principal.hasTag("oid") &&
  ["user-riscos", "user-ambos", "user-sem-grant"].contains(principal.getTag("oid")) &&
  principal.hasTag("azp") &&
  ["supervisor", "riscos"].contains(principal.getTag("azp")) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
};

permit(
  principal,
  action == AgentCore::Action::"riscos___consultar_conhecimento_k2",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/local-demo"
)
when {
  principal.hasTag("tid") &&
  principal.getTag("tid") == "tenant-demo" &&
  principal.hasTag("oid") &&
  ["user-riscos", "user-ambos", "user-sem-grant"].contains(principal.getTag("oid")) &&
  principal.hasTag("azp") &&
  ["supervisor", "riscos"].contains(principal.getTag("azp")) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
};

permit(
  principal,
  action == AgentCore::Action::"fraude___consultar_fraude",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/local-demo"
)
when {
  principal.hasTag("tid") &&
  principal.getTag("tid") == "tenant-demo" &&
  principal.hasTag("oid") &&
  ["user-ambos"].contains(principal.getTag("oid")) &&
  principal.hasTag("azp") &&
  ["supervisor", "fraude"].contains(principal.getTag("azp")) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
};
