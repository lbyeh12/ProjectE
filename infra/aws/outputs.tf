output "s3_bucket_name" {
  value = aws_s3_bucket.data_lake.bucket
}

output "pipeline_user_name" {
  value = aws_iam_user.pipeline_user.name
}

output "pipeline_user_arn" {
  value = aws_iam_user.pipeline_user.arn
}

output "glue_database_name" {
  value = aws_glue_catalog_database.projecte_lake.name
}

output "glue_crawler_name" {
  value = aws_glue_crawler.events_crawler.name
}
