terraform {
  required_version = ">= 1.6"
  required_providers {
    azuread = { source = "hashicorp/azuread", version = "~> 3.0" }
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "tenant_id" { type = string }
variable "account_id" { type = string }
variable "region" { type = string }
variable "profile" { type = string }
variable "project" {
  type    = string
  default = "santander-rag"
}
variable "secret_expiration" {
  type        = string
  description = "Expiração ISO8601 explícita para a credencial do broker."
}

provider "azuread" { tenant_id = var.tenant_id }
provider "aws" {
  region              = var.region
  profile             = var.profile
  allowed_account_ids = [var.account_id]
}

locals {
  apis      = toset(["broker", "gateway"])
  scope_ids = { for name in local.apis : name => uuidv5("dns", "${var.project}.${name}.santander-demo.invalid") }
}

resource "azuread_application" "api" {
  for_each         = local.apis
  display_name     = "${var.project}-${each.key}"
  sign_in_audience = "AzureADMyOrg"
  api {
    requested_access_token_version = 2
    oauth2_permission_scope {
      id                         = local.scope_ids[each.key]
      value                      = "access_as_user"
      type                       = "Admin"
      enabled                    = true
      admin_consent_display_name = "Consultar o RAG como o usuário"
      admin_consent_description  = "Workshop: a Policy vincula o usuário autenticado à ACL da fonte."
    }
  }
  optional_claims {
    access_token {
      name      = "email"
      essential = true
    }
  }
  lifecycle { ignore_changes = [required_resource_access] }
}
resource "azuread_application_identifier_uri" "api" {
  for_each       = azuread_application.api
  application_id = each.value.id
  identifier_uri = "api://${each.value.client_id}"
}
resource "azuread_service_principal" "api" {
  for_each  = azuread_application.api
  client_id = each.value.client_id
}
resource "azuread_application_api_access" "broker_gateway" {
  application_id = azuread_application.api["broker"].id
  api_client_id  = azuread_application.api["gateway"].client_id
  scope_ids      = [local.scope_ids["gateway"]]
}
resource "azuread_service_principal_delegated_permission_grant" "broker_gateway" {
  service_principal_object_id          = azuread_service_principal.api["broker"].object_id
  resource_service_principal_object_id = azuread_service_principal.api["gateway"].object_id
  claim_values                         = ["access_as_user"]
}
resource "azuread_application" "login" {
  display_name                   = "${var.project}-login"
  sign_in_audience               = "AzureADMyOrg"
  fallback_public_client_enabled = true
  public_client { redirect_uris = ["http://localhost"] }
  required_resource_access {
    resource_app_id = azuread_application.api["broker"].client_id
    resource_access {
      id   = local.scope_ids["broker"]
      type = "Scope"
    }
  }
}
resource "azuread_service_principal" "login" {
  client_id = azuread_application.login.client_id
}
resource "azuread_service_principal_delegated_permission_grant" "login_broker" {
  service_principal_object_id          = azuread_service_principal.login.object_id
  resource_service_principal_object_id = azuread_service_principal.api["broker"].object_id
  claim_values                         = ["access_as_user"]
}
resource "azuread_application_password" "broker" {
  application_id = azuread_application.api["broker"].id
  display_name   = "agentcore-identity-obo"
  end_date       = var.secret_expiration
}
resource "aws_secretsmanager_secret" "broker" {
  name                    = "${var.project}/broker-obo"
  recovery_window_in_days = 7
}
resource "aws_secretsmanager_secret_version" "broker" {
  secret_id     = aws_secretsmanager_secret.broker.id
  secret_string = jsonencode({ client_secret = azuread_application_password.broker.value })
}
output "identity_configuration" {
  value = {
    tenant_id         = var.tenant_id
    login_client_id   = azuread_application.login.client_id
    broker_client_id  = azuread_application.api["broker"].client_id
    gateway_client_id = azuread_application.api["gateway"].client_id
    broker_secret_arn = aws_secretsmanager_secret.broker.arn
  }
}
