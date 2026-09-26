data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
resource "aws_instance" "relay" {
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.relay_instance_type
  subnet_id                   = aws_subnet.app[local.azs[0]].id
  associate_public_ip_address = false
  vpc_security_group_ids      = [aws_security_group.relay.id]
  iam_instance_profile        = aws_iam_instance_profile.relay.name
  metadata_options { http_tokens = "required" }
  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }
  tags       = { Name = "contact-form-ssm-relay" }
  depends_on = [aws_route_table_association.app, aws_iam_role_policy_attachment.relay]
}
