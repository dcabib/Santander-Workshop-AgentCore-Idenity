variable "aws_region" {
  description = "Região do laboratório com suporte a AgentCore Runtime, Gateway e Identity."
  type        = string
  default     = "us-east-1"
}

variable "expected_account_id" {
  description = "Conta sandbox confirmada pelo instrutor. O provider recusa outras contas."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Informe os 12 dígitos da conta de laboratório."
  }
}

variable "project_name" {
  description = "Prefixo exclusivo para esta turma; use letras minúsculas, números e hífen."
  type        = string
  default     = "santander-tf-lab"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,27}$", var.project_name))
    error_message = "Use de 3 a 28 caracteres, começando com letra minúscula."
  }
}

variable "runtime_zip" {
  description = "ZIP Linux ARM64 produzido pelo build local, sem upload fora do Terraform."
  type        = string
}

variable "lambda_zip" {
  description = "ZIP da ferramenta bancária sintética."
  type        = string
}

variable "model_id" {
  description = "Modelo regional para a etapa opcional com LLM (Converse com tool use)."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "log_retention_days" {
  description = "Retenção dos logs desta demo."
  type        = number
  default     = 7
}

variable "manage_runtime_logs" {
  description = "Segunda fase: importa o log group criado automaticamente pelo Runtime."
  type        = bool
  default     = false
}
