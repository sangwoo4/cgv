terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  profile = "personal"
  region  = "ap-northeast-2"
  default_tags {
    tags = { Project = "cgv-alarm", Ephemeral = "true" }
  }
}

# Amazon Linux 2023 ARM64 최신 AMI
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

data "aws_vpc" "default" {
  default = true
}

# 인바운드 없음 (봇은 outbound만 필요). 접속은 SSM Session Manager로.
resource "aws_security_group" "cgv_alarm" {
  name        = "cgv-alarm"
  description = "cgv-alarm: egress only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "cgv_alarm" {
  name = "cgv-alarm-ec2"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.cgv_alarm.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "cgv_alarm" {
  name = "cgv-alarm-ec2"
  role = aws_iam_role.cgv_alarm.name
}

resource "aws_instance" "cgv_alarm" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = "t4g.nano"
  vpc_security_group_ids = [aws_security_group.cgv_alarm.id]
  iam_instance_profile   = aws_iam_instance_profile.cgv_alarm.name

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    telegram_bot_token  = var.telegram_bot_token
    telegram_chat_id    = var.telegram_chat_id
    discord_webhook_url = var.discord_webhook_url
    poll_interval       = var.poll_interval
  })

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
  }

  tags = { Name = "cgv-alarm" }
}
