terraform {
  required_version = ">= 1.11.0, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.70.0"
    }
  }
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "Terraform"
      Purpose   = "AgentCoreWorkshop"
      Data      = "Synthetic"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  prefix       = "arn:${data.aws_partition.current.partition}"
  account_id   = data.aws_caller_identity.current.account_id
  runtime_name = replace("${var.project_name}_agent", "-", "_")
  scope        = "${var.project_name}/tools.read"
  issuer       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.lab.id}"
  oauth_origin = "https://${aws_cognito_user_pool_domain.lab.domain}.auth.${var.aws_region}.amazoncognito.com"
  identity_dir = "${local.prefix}:bedrock-agentcore:${var.aws_region}:${local.account_id}:workload-identity-directory/default"
  token_vault  = "${local.prefix}:bedrock-agentcore:${var.aws_region}:${local.account_id}:token-vault/default"
  runtime_logs = "/aws/bedrock-agentcore/runtimes/${local.runtime_name}-*"
}
