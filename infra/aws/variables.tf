variable "aws_region" {
  description = "리소스를 생성할 AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "bucket_name" {
  description = "데이터 레이크 S3 버킷 이름 (전역적으로 고유해야 함)"
  type        = string
  default     = "projecte-data-lake"
}

variable "glue_database_name" {
  description = "Glue Data Catalog 데이터베이스 이름"
  type        = string
  default     = "projecte_lake"
}
