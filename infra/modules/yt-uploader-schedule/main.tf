data "aws_lambda_function" "yt_uploader" {
  function_name = "yt-uploader-lambda"
}

data "aws_iam_role" "scheduler" {
  name = "yt-uploader-schedule-role"
}

resource "aws_scheduler_schedule" "yt_uploader" {
  name                = "yt-uploader-schedule"
  schedule_expression = "rate(1 day)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = data.aws_lambda_function.yt_uploader.arn
    role_arn = data.aws_iam_role.scheduler.arn
  }
}
