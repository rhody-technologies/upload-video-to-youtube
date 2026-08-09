module "yt_uploader_role" {
  source = "./modules/yt-uploader-role"
}

module "yt_uploader_secret" {
  source = "./modules/yt-uploader-secret"
}

module "yt_uploader_db" {
  source = "./modules/yt-uploader-db"
}

module "yt_uploader_lambda" {
  source = "./modules/yt-uploader-lambda"

  depends_on = [module.yt_uploader_role, module.yt_uploader_secret]
}

module "yt_uploader_schedule" {
  source = "./modules/yt-uploader-schedule"

  depends_on = [module.yt_uploader_lambda, module.yt_uploader_role]
}