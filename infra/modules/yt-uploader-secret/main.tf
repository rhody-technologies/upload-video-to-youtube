resource "aws_secretsmanager_secret" "yt_uploader" {
  name = "yt-uploader-secret"
}

resource "aws_secretsmanager_secret_version" "yt_uploader" {
  secret_id = aws_secretsmanager_secret.yt_uploader.id

  secret_string = jsonencode({
    db_username = ""
    db_password = ""
    client_secret = ""
    token = ""
  }) // UPDATE IN AWS CONSOLE. If I really wanted to make this operational
  // I could also add it to GHA (my CI/CD pipeline as an env variable and have it set here
}

