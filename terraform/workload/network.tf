resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "contact-form-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "contact-form-igw" }
}

resource "aws_subnet" "public" {
  for_each                = toset(local.azs)
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, index(local.azs, each.key))
  map_public_ip_on_launch = false
  tags = {
    Name                     = "contact-form-public-${each.key}"
    "kubernetes.io/role/elb" = "1"
  }
}
resource "aws_subnet" "app" {
  for_each                = toset(local.azs)
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, 10 + index(local.azs, each.key))
  map_public_ip_on_launch = false
  tags = {
    Name                              = "contact-form-app-${each.key}"
    "kubernetes.io/role/internal-elb" = "1"
  }
}
resource "aws_subnet" "database" {
  for_each                = toset(local.azs)
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, 20 + index(local.azs, each.key))
  map_public_ip_on_launch = false
  tags                    = { Name = "contact-form-db-${each.key}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "contact-form-public" }
}
resource "aws_route_table_association" "public" {
  for_each       = toset(local.azs)
  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}
resource "aws_eip" "nat" {
  for_each = toset(local.azs)
  domain   = "vpc"
  tags     = { Name = "contact-form-nat-${each.key}" }
}
resource "aws_nat_gateway" "main" {
  for_each      = toset(local.azs)
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  depends_on    = [aws_route_table_association.public]
  tags          = { Name = "contact-form-nat-${each.key}" }
}
resource "aws_route_table" "app" {
  for_each = toset(local.azs)
  vpc_id   = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[each.key].id
  }
  tags = { Name = "contact-form-app-${each.key}" }
}
resource "aws_route_table_association" "app" {
  for_each       = toset(local.azs)
  subnet_id      = aws_subnet.app[each.key].id
  route_table_id = aws_route_table.app[each.key].id
}
# Database subnets have only the VPC local route; no NAT or IGW default.
resource "aws_route_table" "database" {
  for_each = toset(local.azs)
  vpc_id   = aws_vpc.main.id
  tags     = { Name = "contact-form-db-${each.key}" }
}
resource "aws_route_table_association" "database" {
  for_each       = toset(local.azs)
  subnet_id      = aws_subnet.database[each.key].id
  route_table_id = aws_route_table.database[each.key].id
}
