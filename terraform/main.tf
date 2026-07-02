###############################################################################
# MLOps foundation for SageMaker
#
# Provisions the shared infrastructure an ML pipeline needs:
#   - S3 bucket for datasets, model artifacts, and pipeline outputs
#   - ECR repository for the training / inference container image
#   - SageMaker execution role scoped to the bucket
#   - A Model Package Group (the model registry) for versioned model approval
###############################################################################

data "aws_partition" "current" {}

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${var.project}-artifacts-${var.environment}"
  force_destroy = var.force_destroy
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ecr_repository" "model" {
  name                 = "${var.project}-${var.environment}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

# SageMaker execution role.
data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.project}-sagemaker-exec-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = var.tags
}

# Baseline SageMaker permissions. In production, prefer a scoped policy over the
# managed one; kept here for a clean starting point.
resource "aws_iam_role_policy_attachment" "sagemaker" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSageMakerFullAccess"
}

# Least-privilege access to just this project's artifact bucket.
data "aws_iam_policy_document" "bucket_access" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "bucket_access" {
  name   = "artifact-bucket-access"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.bucket_access.json
}

# The model registry: versioned models land here and move through
# PendingManualApproval -> Approved before deployment.
resource "aws_sagemaker_model_package_group" "this" {
  model_package_group_name        = "${var.project}-${var.environment}"
  model_package_group_description = "Versioned model registry for ${var.project} (${var.environment})."
  tags                            = var.tags
}
