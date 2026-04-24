resource "aws_cognito_identity_pool" "web" {
  identity_pool_name               = "arduino_iot_web_pool"
  allow_unauthenticated_identities = true
}

data "aws_iam_policy_document" "cognito_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["cognito-identity.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "cognito-identity.amazonaws.com:aud"
      values   = [aws_cognito_identity_pool.web.id]
    }

    condition {
      test     = "ForAnyValue:StringLike"
      variable = "cognito-identity.amazonaws.com:amr"
      values   = ["unauthenticated"]
    }
  }
}

data "aws_iam_policy_document" "cognito_unauth" {
  statement {
    effect    = "Allow"
    actions   = ["iot:Connect"]
    resources = ["arn:aws:iot:${var.aws_region}:*:client/web-*"]
  }

  statement {
    effect  = "Allow"
    actions = ["iot:Subscribe", "iot:Receive"]
    resources = [
      "arn:aws:iot:${var.aws_region}:*:topicfilter/device/${var.device_id}/telemetry",
      "arn:aws:iot:${var.aws_region}:*:topicfilter/device/${var.device_id}/status",
      "arn:aws:iot:${var.aws_region}:*:topic/device/${var.device_id}/telemetry",
      "arn:aws:iot:${var.aws_region}:*:topic/device/${var.device_id}/status",
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["iot:Publish"]
    resources = ["arn:aws:iot:${var.aws_region}:*:topic/device/${var.device_id}/cmd"]
  }
}

resource "aws_iam_role" "cognito_unauth" {
  name               = "arduino_iot_cognito_unauth"
  assume_role_policy = data.aws_iam_policy_document.cognito_assume.json
}

resource "aws_iam_role_policy" "cognito_unauth" {
  name   = "iot-access"
  role   = aws_iam_role.cognito_unauth.id
  policy = data.aws_iam_policy_document.cognito_unauth.json
}

resource "aws_cognito_identity_pool_roles_attachment" "web" {
  identity_pool_id = aws_cognito_identity_pool.web.id

  roles = {
    unauthenticated = aws_iam_role.cognito_unauth.arn
  }
}
