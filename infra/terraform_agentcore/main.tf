resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-banking"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "banking" {
  function_name    = "${var.project_name}-banking"
  role             = aws_iam_role.lambda.arn
  filename         = var.lambda_zip
  source_code_hash = filebase64sha256(var.lambda_zip)
  handler          = "backend.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  timeout          = 15
  memory_size      = 128
  depends_on       = [aws_iam_role_policy.lambda]
}

resource "aws_bedrockagentcore_gateway" "banking" {
  name            = "${var.project_name}-gateway"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "CUSTOM_JWT"
  protocol_type   = "MCP"
  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = "${local.issuer}/.well-known/openid-configuration"
      allowed_clients = [aws_cognito_user_pool_client.machine["agent"].id]
      allowed_scopes  = [local.scope]
    }
  }
  protocol_configuration {
    mcp {
      supported_versions = ["2025-03-26", "2025-06-18"]
      instructions       = "Ferramentas somente de leitura, com dados bancários sintéticos."
    }
  }
  depends_on = [aws_iam_role_policy.gateway]
}

resource "aws_bedrockagentcore_gateway_target" "banking" {
  name               = "banking"
  gateway_identifier = aws_bedrockagentcore_gateway.banking.gateway_id
  credential_provider_configuration {
    gateway_iam_role {}
  }
  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.banking.arn
        tool_schema {
          inline_payload {
            name        = "get_customer_profile"
            description = "Consulta o perfil e o saldo sintéticos de C001 ou C002. Somente leitura."
            input_schema {
              type = "object"
              property {
                name        = "customer_id"
                type        = "string"
                description = "Identificador sintético: C001 ou C002."
                required    = true
              }
            }
          }
        }
      }
    }
  }
}

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = local.runtime_name
  description        = "Workshop Terraform: Runtime -> Identity OAuth2 -> Gateway MCP -> Lambda"
  role_arn           = aws_iam_role.runtime.arn
  agent_runtime_artifact {
    code_configuration {
      entry_point = ["main.py"]
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket     = aws_s3_bucket.artifacts.id
          prefix     = aws_s3_object.runtime.key
          version_id = aws_s3_object.runtime.version_id
        }
      }
    }
  }
  # PUBLIC é o modo de saída de rede. A entrada continua protegida por AWS_IAM
  # (padrão do Runtime quando authorizer_configuration não é declarado).
  network_configuration {
    network_mode = "PUBLIC"
  }
  protocol_configuration {
    server_protocol = "HTTP"
  }
  lifecycle_configuration {
    idle_runtime_session_timeout = 60
    max_lifetime                 = 600
  }
  environment_variables = {
    WORKSHOP_REGION        = var.aws_region
    WORKSHOP_GATEWAY_URL   = aws_bedrockagentcore_gateway.banking.gateway_url
    WORKSHOP_WORKLOAD_NAME = aws_bedrockagentcore_workload_identity.agent.name
    WORKSHOP_PROVIDER_NAME = aws_bedrockagentcore_oauth2_credential_provider.gateway.name
    WORKSHOP_SCOPE         = local.scope
    WORKSHOP_MODEL_ID      = var.model_id
  }
  depends_on = [aws_iam_role_policy.runtime, aws_bedrockagentcore_gateway_target.banking]
}

resource "aws_cloudwatch_log_group" "runtime" {
  count             = var.manage_runtime_logs ? 1 : 0
  name              = "/aws/bedrock-agentcore/runtimes/${aws_bedrockagentcore_agent_runtime.agent.agent_runtime_id}-DEFAULT"
  retention_in_days = var.log_retention_days
}

# AgentCore cria este grupo durante CreateAgentRuntime. Seu nome contém um ID
# gerado pelo serviço, conhecido somente depois da primeira fase de apply.
# Na segunda fase o Terraform adota o grupo, configura retenção e gerencia cleanup.
import {
  for_each = var.manage_runtime_logs ? toset(["runtime"]) : toset([])
  to       = aws_cloudwatch_log_group.runtime[0]
  id       = "/aws/bedrock-agentcore/runtimes/${aws_bedrockagentcore_agent_runtime.agent.agent_runtime_id}-DEFAULT"
}
