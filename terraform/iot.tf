resource "aws_iot_thing" "device" {
  name = var.device_id
}

resource "aws_iot_certificate" "device" {
  active = true
}

data "aws_iam_policy_document" "iot_device" {
  statement {
    effect    = "Allow"
    actions   = ["iot:Connect"]
    resources = ["arn:aws:iot:${var.aws_region}:*:client/${var.device_id}"]
  }

  statement {
    effect  = "Allow"
    actions = ["iot:Publish", "iot:RetainPublish"]
    resources = [
      "arn:aws:iot:${var.aws_region}:*:topic/device/${var.device_id}/telemetry",
      "arn:aws:iot:${var.aws_region}:*:topic/device/${var.device_id}/status",
    ]
  }

  statement {
    effect  = "Allow"
    actions = ["iot:Subscribe", "iot:Receive"]
    resources = [
      "arn:aws:iot:${var.aws_region}:*:topicfilter/device/${var.device_id}/cmd",
      "arn:aws:iot:${var.aws_region}:*:topic/device/${var.device_id}/cmd",
    ]
  }
}

resource "aws_iot_policy" "device" {
  name   = "${var.device_id}-policy"
  policy = data.aws_iam_policy_document.iot_device.json
}

resource "aws_iot_thing_principal_attachment" "device" {
  thing     = aws_iot_thing.device.name
  principal = aws_iot_certificate.device.arn
}

resource "aws_iot_policy_attachment" "device" {
  policy = aws_iot_policy.device.name
  target = aws_iot_certificate.device.arn
}

resource "local_file" "certificate_pem" {
  content         = aws_iot_certificate.device.certificate_pem
  filename        = "${path.module}/certs/certificate.pem"
  file_permission = "0600"
}

resource "local_file" "private_key" {
  content         = aws_iot_certificate.device.private_key
  filename        = "${path.module}/certs/private.key"
  file_permission = "0600"
}
