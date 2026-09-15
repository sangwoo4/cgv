variable "telegram_bot_token" {
  type      = string
  sensitive = true
}

variable "telegram_chat_id" {
  type = string
}

variable "discord_webhook_url" {
  type      = string
  default   = ""
  sensitive = true
}

variable "poll_interval" {
  description = "폴링 간격(초)"
  type        = number
  default     = 30
}
