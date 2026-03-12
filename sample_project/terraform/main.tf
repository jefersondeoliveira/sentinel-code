provider "aws" {
  region = var.aws_region
}

# PROBLEMA: aws_db_instance com multi_az = false
# → aciona SINGLE_AZ: banco sem alta disponibilidade, ponto único de falha
resource "aws_db_instance" "main" {
  identifier        = "${var.project_name}-db"
  engine            = "postgres"
  engine_version    = "14"
  instance_class    = "db.t3.medium"
  allocated_storage = 20
  username          = "store_user"
  password          = "store_pass"

  # PROBLEMA: multi_az desativado
  multi_az = false

  skip_final_snapshot = true
}

# PROBLEMA: aws_instance com t3.small — capacidade ~1000 RPS
# → aciona UNDERSIZED_INSTANCE quando max_rps > 1000 (ex: --nfr '{"max_rps": 2000}')
resource "aws_instance" "app" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.small"

  tags = {
    Name = "${var.project_name}-app"
  }
}

# PROBLEMA: aws_ecs_service sem aws_appautoscaling_target correspondente
# → aciona MISSING_AUTOSCALING: sem auto scaling, a aplicação não responde a picos de carga
resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8080
  }
}

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

# Sem aws_appautoscaling_target → MISSING_AUTOSCALING confirmado
