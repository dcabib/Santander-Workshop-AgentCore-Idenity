permit(
  principal,
  action == AgentCore::Action::"riscos___consultar_risco",
  resource == AgentCore::Gateway::"${Gateway.GatewayArn}"
)
when {
  principal.hasTag("tid") &&
  principal.getTag("tid") == "${TenantId}" &&
  principal.hasTag("oid") &&
  ["${RisksUserOid}", "${BothUserOid}", "${NoGrantUserOid}"].contains(principal.getTag("oid")) &&
  principal.hasTag("${CallerClaim}") &&
  ["${SupervisorClientId}", "${RisksClientId}"].contains(principal.getTag("${CallerClaim}")) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
};

permit(
  principal,
  action == AgentCore::Action::"riscos___consultar_conhecimento_k2",
  resource == AgentCore::Gateway::"${Gateway.GatewayArn}"
)
when {
  principal.hasTag("tid") &&
  principal.getTag("tid") == "${TenantId}" &&
  principal.hasTag("oid") &&
  ["${RisksUserOid}", "${BothUserOid}", "${NoGrantUserOid}"].contains(principal.getTag("oid")) &&
  principal.hasTag("${CallerClaim}") &&
  ["${SupervisorClientId}", "${RisksClientId}"].contains(principal.getTag("${CallerClaim}")) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
};

permit(
  principal,
  action == AgentCore::Action::"fraude___consultar_fraude",
  resource == AgentCore::Gateway::"${Gateway.GatewayArn}"
)
when {
  principal.hasTag("tid") &&
  principal.getTag("tid") == "${TenantId}" &&
  principal.hasTag("oid") &&
  ["${BothUserOid}"].contains(principal.getTag("oid")) &&
  principal.hasTag("${CallerClaim}") &&
  ["${SupervisorClientId}", "${FraudClientId}"].contains(principal.getTag("${CallerClaim}")) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
};

permit(principal, action == AgentCore::Action::"graph___getMyProfile",
 resource == AgentCore::Gateway::"${Gateway.GatewayArn}")
when { principal.hasTag("tid") && principal.getTag("tid") == "${TenantId}" &&
 principal.hasTag("oid") && ["${RisksUserOid}", "${BothUserOid}", "${NoGrantUserOid}"].contains(principal.getTag("oid")) &&
 principal.hasTag("${CallerClaim}") && principal.getTag("${CallerClaim}") == "${SupervisorClientId}" &&
 principal.hasTag("scp") };
