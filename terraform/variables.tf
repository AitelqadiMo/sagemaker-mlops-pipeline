variable "project" {
  description = "Project name used as a prefix for all resources."
  type        = string
  default     = "churn-model"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "force_destroy" {
  description = "Allow Terraform to destroy the non-empty artifact bucket. Keep false in production."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
