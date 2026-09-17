"""Stack de AWS CDK v2 (Python): red (VPC), registro de contenedor (ECR),
base de datos RDS PostgreSQL, clúster de ECS y servicio Fargate detrás de un
Application Load Balancer.

Esta propuesta provisiona el RDS que ese
camino necesita.
"""
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_rds as rds
from constructs import Construct

DATABASE_NAME = "mensajesnequi"


class ChatApiInfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Red (VPC) con tres grupos de subredes: públicas (para el ALB),
        #    privadas con salida a internet (para que las tareas de Fargate
        #    puedan tirar de ECR) y aisladas sin salida a internet (para
        #    RDS — la base de datos no necesita, ni debería tener, acceso
        #    saliente a internet).
        vpc = ec2.Vpc(
            self,
            "ChatApiVpc",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(
                    name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
                ),
            ],
        )

        # 2. Repositorio ECR para la imagen Docker de FastAPI. La imagen se
        #    construye y se sube por fuera de este stack (ver README.md,
        #    sección "Cómo se usaría") — CDK no compila el Dockerfile en
        #    este flujo, solo referencia el repositorio.
        ecr_repo = ecr.Repository(
            self,
            "ChatApiEcrRepo",
            repository_name="nequi-chat-api",
            image_scan_on_push=True,
        )

        # 3. Clúster de ECS.
        cluster = ecs.Cluster(self, "ChatApiCluster", vpc=vpc)

        # 3.5. Base de datos: RDS PostgreSQL en subredes aisladas (sin
        #      salida a internet), con credenciales generadas y guardadas en
        #      Secrets Manager — nunca en texto plano en el código ni en la
        #      definición de la tarea.
        database = rds.DatabaseInstance(
            self,
            "ChatApiDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16_4),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO),
            allocated_storage=20,
            credentials=rds.Credentials.from_generated_secret(DATABASE_NAME),
            database_name=DATABASE_NAME,
            storage_encrypted=True,
            # SNAPSHOT (no DESTROY): si alguien destruye el stack por error,
            # RDS toma un snapshot final en vez de borrar los datos.
            removal_policy=RemovalPolicy.SNAPSHOT,
            deletion_protection=False,  # en un ambiente productivo real: True
        )

        # 4. Servicio Fargate con Application Load Balancer.
        #    Nota sobre `DATABASE_URL`: la app espera una sola variable de
        #    entorno con el string de conexión completo
        #    (`postgresql+psycopg://usuario:password@host:puerto/nombre`).
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ChatApiFargateService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            public_load_balancer=True,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(ecr_repo),
                container_port=8000,  # puerto expuesto por FastAPI (ver Dockerfile)
                environment={
                    "DB_HOST": database.db_instance_endpoint_address,
                    "DB_PORT": database.db_instance_endpoint_port,
                    "DB_NAME": DATABASE_NAME,
                },
                secrets={
                    "DB_USERNAME": ecs.Secret.from_secrets_manager(database.secret, field="username"),
                    "DB_PASSWORD": ecs.Secret.from_secrets_manager(database.secret, field="password"),
                },
            ),
        )

        # Abre el puerto 5432 desde el security group de las tareas de
        # Fargate hacia el de la base de datos — sin esto, la conexión a RDS
        # se queda colgada por firewall, no por credenciales.
        database.connections.allow_default_port_from(fargate_service.service)

        fargate_service.target_group.configure_health_check(path="/health")


        # 6. Salidas.
        CfnOutput(
            self,
            "ApiLoadBalancerUrl",
            value=fargate_service.load_balancer.load_balancer_dns_name,
            description="URL pública para consumir la API de chat",
        )
        CfnOutput(
            self,
            "DatabaseEndpoint",
            value=database.db_instance_endpoint_address,
            description="Host de la base de datos RDS (para construir DATABASE_URL manualmente si hace falta)",
        )
        CfnOutput(
            self,
            "DatabaseSecretArn",
            value=database.secret.secret_arn,
            description="ARN del secreto en Secrets Manager con las credenciales generadas de RDS",
        )
