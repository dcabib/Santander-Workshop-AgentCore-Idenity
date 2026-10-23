# O IdP emite JWTs; AgentCore Identity guarda as credenciais e obtém os tokens.
# client_credentials representa a aplicação, nunca um usuário final.
resource "aws_cognito_user_pool" "lab" {
  name = "${var.project_name}-idp"
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_domain" "lab" {
  domain       = "${var.project_name}-${local.account_id}"
  user_pool_id = aws_cognito_user_pool.lab.id
}

resource "aws_cognito_resource_server" "tools" {
  identifier   = var.project_name
  name         = "Ferramentas de consulta do workshop"
  user_pool_id = aws_cognito_user_pool.lab.id
  scope {
    scope_name        = "tools.read"
    scope_description = "Consultar dados bancários sintéticos"
  }
}

# O segundo cliente tem token legítimo do mesmo issuer, mas NÃO está na
# allowlist do Gateway. Ele permite provar autorização, além de assinatura.
resource "aws_cognito_user_pool_client" "machine" {
  for_each                             = toset(["agent", "unauthorized"])
  name                                 = "${var.project_name}-${each.key}"
  user_pool_id                         = aws_cognito_user_pool.lab.id
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = aws_cognito_resource_server.tools.scope_identifiers
  supported_identity_providers         = ["COGNITO"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  access_token_validity                = 5
  token_validity_units {
    access_token = "minutes"
  }
}

# Identidade gerenciada pelo cliente, explícita no Terraform, para demonstrar
# GetWorkloadAccessToken. A identidade automática do Runtime é service-managed
# e não pode ser usada nessa API manual.
resource "aws_bedrockagentcore_workload_identity" "agent" {
  name = "${var.project_name}-workload"
}

resource "aws_bedrockagentcore_oauth2_credential_provider" "gateway" {
  name                       = "${var.project_name}-oauth"
  credential_provider_vendor = "CustomOauth2"
  oauth2_provider_config {
    custom_oauth2_provider_config {
      client_id     = aws_cognito_user_pool_client.machine["agent"].id
      client_secret = aws_cognito_user_pool_client.machine["agent"].client_secret
      oauth_discovery {
        discovery_url = "${local.issuer}/.well-known/openid-configuration"
      }
    }
  }
  # Cognito publica os endpoints OAuth depois da criação do domínio.
  depends_on = [aws_cognito_user_pool_domain.lab]
}
