data "aws_iam_policy_document" "agentcore_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["${local.prefix}:bedrock-agentcore:${var.aws_region}:${local.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "runtime" {
  name               = "${var.project_name}-runtime"
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
}

resource "aws_iam_role_policy" "runtime" {
  role = aws_iam_role.runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadOwnArtifact"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = "${aws_s3_bucket.artifacts.arn}/runtime/*"
      },
      {
        Sid      = "GetOwnWorkloadToken"
        Effect   = "Allow"
        Action   = ["bedrock-agentcore:GetWorkloadAccessToken"]
        Resource = [local.identity_dir, aws_bedrockagentcore_workload_identity.agent.workload_identity_arn]
      },
      {
        Sid    = "GetGatewayOAuthToken"
        Effect = "Allow"
        Action = ["bedrock-agentcore:GetResourceOauth2Token"]
        Resource = [
          local.identity_dir,
          aws_bedrockagentcore_workload_identity.agent.workload_identity_arn,
          local.token_vault,
          aws_bedrockagentcore_oauth2_credential_provider.gateway.credential_provider_arn,
        ]
      },
      {
        Sid      = "ReadOnlyProviderSecret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = "${local.prefix}:secretsmanager:${var.aws_region}:${local.account_id}:secret:bedrock-agentcore-identity!default/oauth2/${aws_bedrockagentcore_oauth2_credential_provider.gateway.name}*"
      },
      {
        Sid      = "RuntimeLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${local.prefix}:logs:${var.aws_region}:${local.account_id}:log-group:${local.runtime_logs}:*"
      },
      {
        Sid      = "DescribeLogs"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups"]
        Resource = "${local.prefix}:logs:${var.aws_region}:${local.account_id}:log-group:*"
      },
      {
        Sid      = "OptionalRegionalModel"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "${local.prefix}:bedrock:${var.aws_region}::foundation-model/${var.model_id}"
      },
    ]
  })
}

resource "aws_iam_role" "gateway" {
  name               = "${var.project_name}-gateway"
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
}

resource "aws_iam_role_policy" "gateway" {
  role = aws_iam_role.gateway.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.banking.arn
    }]
  })
}

resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-tool"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
    }]
  })
}
