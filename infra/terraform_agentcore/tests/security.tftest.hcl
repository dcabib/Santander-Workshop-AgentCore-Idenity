# Terraform executa estes testes sem credenciais e sem provisionar AWS.
mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock-workshop"
    }
  }
  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:us-east-1:123456789012:function:mock-workshop"
    }
  }
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
    arn        = "arn:aws:iam::123456789012:user/test"
    user_id    = "test"
  }
}

override_data {
  target = data.aws_partition.current
  values = {
    partition  = "aws"
    dns_suffix = "amazonaws.com"
  }
}

override_data {
  target = data.aws_iam_policy_document.agentcore_trust
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"sts:AssumeRole\",\"Principal\":{\"Service\":\"bedrock-agentcore.amazonaws.com\"}}]}"
  }
}

run "security_contract" {
  command = apply

  assert {
    condition     = aws_bedrockagentcore_gateway.banking.authorizer_type == "CUSTOM_JWT"
    error_message = "Gateway precisa exigir JWT."
  }
  assert {
    condition     = aws_bedrockagentcore_gateway.banking.authorizer_configuration[0].custom_jwt_authorizer[0].allowed_clients == toset([aws_cognito_user_pool_client.machine["agent"].id])
    error_message = "Somente a aplicação do agente pode acessar o Gateway."
  }
  assert {
    condition     = aws_bedrockagentcore_gateway.banking.authorizer_configuration[0].custom_jwt_authorizer[0].allowed_scopes == toset(["santander-tf-lab/tools.read"])
    error_message = "Gateway precisa exigir o scope de leitura."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.artifacts.block_public_acls && aws_s3_bucket_public_access_block.artifacts.block_public_policy && aws_s3_bucket_public_access_block.artifacts.ignore_public_acls && aws_s3_bucket_public_access_block.artifacts.restrict_public_buckets
    error_message = "Artefatos não podem ser públicos."
  }
  assert {
    condition     = aws_s3_bucket_versioning.artifacts.versioning_configuration[0].status == "Enabled"
    error_message = "Versionamento precisa permanecer habilitado."
  }
  assert {
    condition     = length(aws_bedrockagentcore_agent_runtime.agent.authorizer_configuration) == 0
    error_message = "Runtime desta trilha usa IAM/SigV4."
  }
  assert {
    condition     = !contains(keys(aws_bedrockagentcore_agent_runtime.agent.environment_variables), "CLIENT_SECRET")
    error_message = "Segredo não deve ser entregue por variável de ambiente."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.gateway.policy).Statement[0].Action == ["lambda:InvokeFunction"]
    error_message = "Gateway deve ter somente permissão de invocar a ferramenta."
  }
}
