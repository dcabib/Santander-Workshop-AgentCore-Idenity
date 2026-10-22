terraform {
  required_version = ">= 1.6"
  required_providers {
    azuread = { source = "hashicorp/azuread", version = "~> 3.0" }
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "azuread" {
  tenant_id = var.tenant_id
}

provider "aws" {
  profile             = var.aws_profile
  region              = var.aws_region
  allowed_account_ids = [var.hub_account_id]
}

variable "tenant_id" { type = string }
variable "aws_profile" { type = string }
variable "aws_region" { type = string }
variable "hub_account_id" { type = string }
variable "secret_expiration" {
  type        = string
  description = "Expiração ISO8601 explícita do segredo de laboratório."
}
variable "name" {
  type    = string
  default = "santander-demo"
}

locals {
  gateway_scope_id = "c2d9d145-21cc-4d91-ab3d-7a9cb2aa15e1"
  fraud_scope_id   = "e236f7c3-ce67-4bc4-ae40-9404499b7e69"
  graph_client_id  = "00000003-0000-0000-c000-000000000000"
  graph_user_read  = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
}

resource "azuread_application" "fraud" {
  display_name     = "${var.name}-fraud-api"
  sign_in_audience = "AzureADMyOrg"
  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      id                         = local.fraud_scope_id
      value                      = "access_as_user"
      type                       = "Admin"
      enabled                    = true
      admin_consent_display_name = "Consultar Fraude sintética como usuário"
      admin_consent_description  = "Delegação exclusiva ao laboratório Santander"
    }
  }
}
resource "azuread_application_identifier_uri" "fraud" {
  application_id = azuread_application.fraud.id
  identifier_uri = "api://${azuread_application.fraud.client_id}"
}
resource "azuread_service_principal" "fraud" {
  client_id = azuread_application.fraud.client_id
}
data "azuread_service_principal" "graph" {
  client_id = local.graph_client_id
}

resource "azuread_application" "gateway" {
  display_name     = "${var.name}-gateway-api"
  sign_in_audience = "AzureADMyOrg"
  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      id                         = local.gateway_scope_id
      value                      = "access_as_user"
      type                       = "Admin"
      enabled                    = true
      admin_consent_display_name = "Invocar Gateway do workshop como usuário"
      admin_consent_description  = "Acesso às tools sintéticas do workshop Santander"
    }
  }
  required_resource_access {
    resource_app_id = local.graph_client_id
    resource_access {
      id   = local.graph_user_read
      type = "Scope"
    }
  }
  required_resource_access {
    resource_app_id = azuread_application.fraud.client_id
    resource_access {
      id   = local.fraud_scope_id
      type = "Scope"
    }
  }
}
resource "azuread_application_identifier_uri" "gateway" {
  application_id = azuread_application.gateway.id
  identifier_uri = "api://${azuread_application.gateway.client_id}"
}
resource "azuread_service_principal" "gateway" {
  client_id = azuread_application.gateway.client_id
}
resource "azuread_service_principal_delegated_permission_grant" "graph" {
  service_principal_object_id          = azuread_service_principal.gateway.object_id
  resource_service_principal_object_id = data.azuread_service_principal.graph.object_id
  claim_values                         = ["User.Read"]
}
resource "azuread_service_principal_delegated_permission_grant" "fraud" {
  service_principal_object_id          = azuread_service_principal.gateway.object_id
  resource_service_principal_object_id = azuread_service_principal.fraud.object_id
  claim_values                         = ["access_as_user"]
}

resource "azuread_application" "clients" {
  for_each         = toset(["supervisor", "riscos", "fraude"])
  display_name     = "${var.name}-${each.key}-agent"
  sign_in_audience = "AzureADMyOrg"
  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      id                         = local.gateway_scope_id
      value                      = "access_as_user"
      type                       = "Admin"
      enabled                    = true
      admin_consent_display_name = "Acionar agente ${each.key} como usuário"
      admin_consent_description  = "Entrada delegada ao agente confidencial do laboratório"
    }
  }
  required_resource_access {
    resource_app_id = azuread_application.gateway.client_id
    resource_access {
      id   = local.gateway_scope_id
      type = "Scope"
    }
  }
}
resource "azuread_service_principal" "clients" {
  for_each  = azuread_application.clients
  client_id = each.value.client_id
}
resource "azuread_application_identifier_uri" "clients" {
  for_each       = azuread_application.clients
  application_id = each.value.id
  identifier_uri = "api://${each.value.client_id}"
}
resource "azuread_service_principal_delegated_permission_grant" "clients" {
  for_each                             = azuread_service_principal.clients
  service_principal_object_id          = each.value.object_id
  resource_service_principal_object_id = azuread_service_principal.gateway.object_id
  claim_values                         = ["access_as_user"]
}
resource "azuread_application" "frontend" {
  display_name                   = "${var.name}-workshop-login"
  sign_in_audience               = "AzureADMyOrg"
  fallback_public_client_enabled = true
  public_client {
    redirect_uris = ["http://localhost"]
  }
  dynamic "required_resource_access" {
    for_each = azuread_application.clients
    content {
      resource_app_id = required_resource_access.value.client_id
      resource_access {
        id   = local.gateway_scope_id
        type = "Scope"
      }
    }
  }
}
resource "azuread_service_principal" "frontend" {
  client_id = azuread_application.frontend.client_id
}
resource "azuread_service_principal_delegated_permission_grant" "frontend" {
  for_each                             = azuread_service_principal.clients
  service_principal_object_id          = azuread_service_principal.frontend.object_id
  resource_service_principal_object_id = each.value.object_id
  claim_values                         = ["access_as_user"]
}
resource "azuread_application_password" "clients" {
  for_each       = azuread_application.clients
  application_id = each.value.id
  display_name   = "confidential-agent-lab"
  end_date       = var.secret_expiration
}
resource "aws_secretsmanager_secret" "clients" {
  for_each                = azuread_application.clients
  name                    = "${var.name}/${each.key}-obo"
  recovery_window_in_days = 7
}
resource "aws_secretsmanager_secret_version" "clients" {
  for_each      = azuread_application_password.clients
  secret_id     = aws_secretsmanager_secret.clients[each.key].id
  secret_string = jsonencode({ client_secret = each.value.value })
}
resource "azuread_application_password" "gateway" {
  application_id = azuread_application.gateway.id
  display_name   = "agentcore-obo-lab"
  end_date       = var.secret_expiration
}
resource "aws_secretsmanager_secret" "gateway" {
  name                    = "${var.name}/entra-obo"
  recovery_window_in_days = 7
}
resource "aws_secretsmanager_secret_version" "gateway" {
  secret_id     = aws_secretsmanager_secret.gateway.id
  secret_string = jsonencode({ client_secret = azuread_application_password.gateway.value })
}

output "hub_identity_parameters" {
  value = {
    TenantId           = var.tenant_id
    DiscoveryUrl       = "https://login.microsoftonline.com/${var.tenant_id}/v2.0/.well-known/openid-configuration"
    GatewayAudience    = azuread_application.gateway.client_id
    GatewayClientId    = azuread_application.gateway.client_id
    CallerClaim        = "azp"
    SupervisorClientId = azuread_application.clients["supervisor"].client_id
    RisksClientId      = azuread_application.clients["riscos"].client_id
    FraudClientId      = azuread_application.clients["fraude"].client_id
    EntraSecretArn     = aws_secretsmanager_secret.gateway.arn
    FraudScope         = "api://${azuread_application.fraud.client_id}/access_as_user"
  }
}
output "fraud_audience" {
  value = azuread_application.fraud.client_id
}
output "login_scope" {
  value = "api://${azuread_application.clients["supervisor"].client_id}/access_as_user"
}
output "login_client_id" {
  value = azuread_application.frontend.client_id
}
output "agent_identities" {
  value = { for name, app in azuread_application.clients : name => {
    client_id  = app.client_id
    scope      = "api://${app.client_id}/access_as_user"
    secret_arn = aws_secretsmanager_secret.clients[name].arn
  } }
}
