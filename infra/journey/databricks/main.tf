terraform {
  required_version = ">= 1.6"
  required_providers {
    databricks = { source = "databricks/databricks", version = "~> 1.0" }
  }
}

variable "databricks_account_id" { type = string }
variable "tenant_id" { type = string }
variable "data_gateway_client_id" { type = string }
variable "subject_claim" {
  type    = string
  default = "email"
  validation {
    condition     = contains(["email", "preferred_username", "upn"], var.subject_claim)
    error_message = "Mapeie a claim que contém exatamente o username Databricks."
  }
}

provider "databricks" {
  host       = "https://accounts.azuredatabricks.net"
  account_id = var.databricks_account_id
  # Credenciais pelo mecanismo aprovado do pipeline; não pelo notebook/tfvars.
}

# Conta Databricks, não federation de um service principal.
# Usuários, memberships, warehouse e grants pertencem ao IaC do sandbox.
resource "databricks_account_federation_policy" "santander_users" {
  description = "Santander demo: Entra v2 users entering through the data Gateway audience"
  oidc_policy = {
    issuer        = "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
    audiences     = [var.data_gateway_client_id]
    subject_claim = var.subject_claim
  }
}

output "federation_policy_id" {
  value = databricks_account_federation_policy.santander_users.policy_id
}
