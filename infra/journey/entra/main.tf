terraform {
  required_version = ">= 1.6"
  required_providers {
    azuread = { source = "hashicorp/azuread", version = "~> 3.0" }
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "tenant_id" { type = string }
variable "region" { type = string }
variable "origin_account_id" { type = string }
variable "platform_account_id" { type = string }
variable "origin_profile" { type = string }
variable "platform_profile" { type = string }
variable "secret_expiration" {
  type        = string
  description = "Expiração ISO8601 explícita, definida para o sandbox."
}
variable "project" {
  type    = string
  default = "santander-journey"
}

provider "azuread" { tenant_id = var.tenant_id }
provider "aws" {
  alias               = "origin"
  region              = var.region
  profile             = var.origin_profile
  allowed_account_ids = [var.origin_account_id]
}
provider "aws" {
  alias               = "platform"
  region              = var.region
  profile             = var.platform_profile
  allowed_account_ids = [var.platform_account_id]
}

locals {
  apis = toset(["origin", "riscos", "fraude", "platform", "data"])
  scope_ids = {
    for name in local.apis : name => uuidv5("dns", "${var.project}.${name}.santander-demo.invalid")
  }
  grants = {
    origin_riscos = { caller = "origin", target = "riscos" }
    origin_fraude = { caller = "origin", target = "fraude" }
    riscos_hub    = { caller = "riscos", target = "platform" }
    fraude_hub    = { caller = "fraude", target = "platform" }
    hub_data      = { caller = "platform", target = "data" }
  }
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
      admin_consent_display_name = "Delegação do usuário para ${each.key}"
      admin_consent_description  = "Sandbox Santander; usuário permanece sujeito às Policies e aos grants da fonte"
    }
  }
  optional_claims {
    access_token {
      name      = "email"
      essential = true
    }
  }
  lifecycle {
    # As permissões são geridas pelos recursos application_api_access abaixo.
    ignore_changes = [required_resource_access]
  }
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
resource "azuread_application_api_access" "obo" {
  for_each       = local.grants
  application_id = azuread_application.api[each.value.caller].id
  api_client_id  = azuread_application.api[each.value.target].client_id
  scope_ids      = [local.scope_ids[each.value.target]]
}
resource "azuread_service_principal_delegated_permission_grant" "obo" {
  for_each                             = local.grants
  service_principal_object_id          = azuread_service_principal.api[each.value.caller].object_id
  resource_service_principal_object_id = azuread_service_principal.api[each.value.target].object_id
  claim_values                         = ["access_as_user"]
}
resource "azuread_application" "login" {
  display_name                   = "${var.project}-login"
  sign_in_audience               = "AzureADMyOrg"
  fallback_public_client_enabled = true
  public_client { redirect_uris = ["http://localhost"] }
  required_resource_access {
    resource_app_id = azuread_application.api["origin"].client_id
    resource_access {
      id   = local.scope_ids["origin"]
      type = "Scope"
    }
  }
}
resource "azuread_service_principal" "login" {
  client_id = azuread_application.login.client_id
}
resource "azuread_service_principal_delegated_permission_grant" "login" {
  service_principal_object_id          = azuread_service_principal.login.object_id
  resource_service_principal_object_id = azuread_service_principal.api["origin"].object_id
  claim_values                         = ["access_as_user"]
}
resource "azuread_application_password" "obo" {
  for_each       = toset(["origin", "riscos", "fraude", "platform"])
  application_id = azuread_application.api[each.key].id
  display_name   = "agentcore-identity-obo"
  end_date       = var.secret_expiration
}
resource "aws_secretsmanager_secret" "origin" {
  provider                = aws.origin
  for_each                = toset(["origin", "riscos", "fraude"])
  name                    = "${var.project}/${each.key}-obo"
  recovery_window_in_days = 7
}
resource "aws_secretsmanager_secret_version" "origin" {
  provider      = aws.origin
  for_each      = aws_secretsmanager_secret.origin
  secret_id     = each.value.id
  secret_string = jsonencode({ client_secret = azuread_application_password.obo[each.key].value })
}
resource "aws_secretsmanager_secret" "platform" {
  provider                = aws.platform
  name                    = "${var.project}/platform-obo"
  recovery_window_in_days = 7
}
resource "aws_secretsmanager_secret_version" "platform" {
  provider      = aws.platform
  secret_id     = aws_secretsmanager_secret.platform.id
  secret_string = jsonencode({ client_secret = azuread_application_password.obo["platform"].value })
}
output "identity_configuration" {
  value = {
    tenant_id       = var.tenant_id
    login_client_id = azuread_application.login.client_id
    applications    = { for name, app in azuread_application.api : name => app.client_id }
    subject_claim   = "email"
    secret_arns = merge(
      { for name, secret in aws_secretsmanager_secret.origin : name => secret.arn },
      { platform = aws_secretsmanager_secret.platform.arn }
    )
  }
}
