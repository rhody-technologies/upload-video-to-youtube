data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "yt_uploader" {
  name               = "yt-uploader-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.yt_uploader.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc_access" {
  role       = aws_iam_role.yt_uploader.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "secrets_access" {
  name = "yt-uploader-secrets-access"
  role = aws_iam_role.yt_uploader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]
        Resource = "arn:aws:secretsmanager:*:*:secret:yt-uploader-*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "ses_access" {
  name = "yt-uploader-ses-access"
  role = aws_iam_role.yt_uploader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
      }
    ]
  })
}

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

resource "aws_iam_role" "scheduler" {
  name               = "yt-uploader-schedule-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
}

resource "aws_iam_role_policy" "invoke_lambda" {
  name = "yt-uploader-schedule-invoke-lambda"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:yt-uploader-lambda"
      }
    ]
  })
}
