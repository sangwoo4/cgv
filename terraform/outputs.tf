output "instance_id" {
  value = aws_instance.cgv_alarm.id
}

output "ssm_connect" {
  value = "aws ssm start-session --profile personal --region ap-northeast-2 --target ${aws_instance.cgv_alarm.id}"
}
