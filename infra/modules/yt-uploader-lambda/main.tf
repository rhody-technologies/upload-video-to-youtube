data "aws_iam_role" "yt_uploader" {
  name = "yt-uploader-lambda-role"
}

data "aws_secretsmanager_secret" "yt_uploader" {
  name = "yt-uploader-secret"
}

resource "null_resource" "install_lambda_dependencies" {
  triggers = {
    requirements_hash = filemd5("${path.root}/../requirements.txt")
    source_hash       = filemd5("${path.root}/../main.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      rm -rf ${path.module}/build
      mkdir -p ${path.module}/build
      pip3 install -r ${path.root}/../requirements.txt -t ${path.module}/build --quiet
      cp ${path.root}/../main.py ${path.module}/build/main.py
    EOT
  }
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/lambda.zip"

  depends_on = [null_resource.install_lambda_dependencies]
}

resource "aws_lambda_function" "yt_uploader" {
  function_name    = "yt-uploader-lambda"
  role             = data.aws_iam_role.yt_uploader.arn
  handler          = "main.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 900

  environment {
    variables = {
      SECRET_ARN = data.aws_secretsmanager_secret.yt_uploader.arn
    }
  }
}
