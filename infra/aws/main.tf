terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- S3 (adrs/0011) ---

resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- IAM: 파이프라인 전용 최소 권한 사용자 (adrs/0011) ---
# infra/aws/iam-policy.json 은 콘솔에서 수동으로 붙여넣을 때 참고용으로
# 남겨두고, Terraform에서는 같은 내용을 jsonencode로 직접 작성해서
# 버킷 ARN이 변수(var.bucket_name)와 항상 정확히 일치하도록 한다.

resource "aws_iam_policy" "pipeline_policy" {
  name = "projecte-data-pipeline-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3BucketAccess"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      },
      {
        Sid    = "GlueCrawlerAndCatalog"
        Effect = "Allow"
        Action = [
          "glue:GetCrawler", "glue:StartCrawler", "glue:CreateCrawler",
          "glue:GetDatabase", "glue:CreateDatabase",
          "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable"
        ]
        Resource = "*"
      },
      {
        Sid    = "AthenaQuery"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution", "athena:GetQueryExecution",
          "athena:GetQueryResults", "athena:GetWorkGroup"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_user" "pipeline_user" {
  name = "projecte-data-pipeline"
}

resource "aws_iam_user_policy_attachment" "pipeline_attach" {
  user       = aws_iam_user.pipeline_user.name
  policy_arn = aws_iam_policy.pipeline_policy.arn
}

# --- IAM: Glue Crawler 서비스 역할 (adrs/0011) ---

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_crawler_role" {
  name               = "projecte-glue-crawler-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_service_role" {
  role       = aws_iam_role.glue_crawler_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3_access" {
  name = "projecte-glue-s3-access"
  role = aws_iam_role.glue_crawler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3BucketAccess"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      }
    ]
  })
}

# --- Glue (adrs/0012) ---

resource "aws_glue_catalog_database" "projecte_lake" {
  name = var.glue_database_name
}

resource "aws_glue_crawler" "events_crawler" {
  name          = "projecte-events-crawler"
  role          = aws_iam_role.glue_crawler_role.arn
  database_name = aws_glue_catalog_database.projecte_lake.name

  s3_target {
    path = "s3://${aws_s3_bucket.data_lake.bucket}/raw/raw_events/"
  }

  s3_target {
    path = "s3://${aws_s3_bucket.data_lake.bucket}/curated/fact_events/"
  }
}
