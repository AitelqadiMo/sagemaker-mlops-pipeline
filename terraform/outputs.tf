output "artifact_bucket" {
  description = "S3 bucket for datasets, artifacts, and pipeline outputs."
  value       = aws_s3_bucket.artifacts.bucket
}

output "ecr_repository_url" {
  description = "ECR repository URL for the model image."
  value       = aws_ecr_repository.model.repository_url
}

output "execution_role_arn" {
  description = "SageMaker execution role ARN (pass to the pipeline)."
  value       = aws_iam_role.execution.arn
}

output "model_package_group" {
  description = "Name of the SageMaker Model Package Group (model registry)."
  value       = aws_sagemaker_model_package_group.this.model_package_group_name
}
