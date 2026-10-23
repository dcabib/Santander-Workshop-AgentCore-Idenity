# Somente identificadores. Nunca exportar client_secret ou tokens.
output "workshop" {
  description = "Contrato consumido pelo notebook e pelo verificador ponta a ponta."
  value = {
    region               = var.aws_region
    account_id           = local.account_id
    project_name         = var.project_name
    runtime_arn          = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
    runtime_id           = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_id
    gateway_id           = aws_bedrockagentcore_gateway.banking.gateway_id
    gateway_url          = aws_bedrockagentcore_gateway.banking.gateway_url
    workload_name        = aws_bedrockagentcore_workload_identity.agent.name
    workload_arn         = aws_bedrockagentcore_workload_identity.agent.workload_identity_arn
    provider_name        = aws_bedrockagentcore_oauth2_credential_provider.gateway.name
    provider_arn         = aws_bedrockagentcore_oauth2_credential_provider.gateway.credential_provider_arn
    user_pool_id         = aws_cognito_user_pool.lab.id
    agent_client_id      = aws_cognito_user_pool_client.machine["agent"].id
    denied_client_id     = aws_cognito_user_pool_client.machine["unauthorized"].id
    token_endpoint       = "${local.oauth_origin}/oauth2/token"
    scope                = local.scope
    tool_name            = "banking___get_customer_profile"
    lambda_name          = aws_lambda_function.banking.function_name
    runtime_log_group    = "/aws/bedrock-agentcore/runtimes/${aws_bedrockagentcore_agent_runtime.agent.agent_runtime_id}-DEFAULT"
    runtime_logs_managed = var.manage_runtime_logs
    lambda_log_group     = aws_cloudwatch_log_group.lambda.name
    model_id             = var.model_id
    artifacts_bucket     = aws_s3_bucket.artifacts.id
    runtime_zip_sha256   = filesha256(var.runtime_zip)
  }
}
