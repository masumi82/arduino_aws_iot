data "aws_iot_endpoint" "current" {
  endpoint_type = "iot:Data-ATS"
}

output "iot_endpoint" {
  description = "AWS IoT Core endpoint (use in .env as IOT_ENDPOINT)"
  value       = data.aws_iot_endpoint.current.endpoint_address
}

output "cognito_identity_pool_id" {
  description = "Cognito Identity Pool ID (use in web/js/config.js)"
  value       = aws_cognito_identity_pool.web.id
}
