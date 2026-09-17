# Propuesta de infraestructura en AWS (ECR + ECS Fargate + RDS)

> **Estado:** propuesta validada con `cdk synth` (sintetiza sin errores ni
> advertencias — 50 recursos de CloudFormation), pero **no desplegada**
> contra una cuenta AWS real.


La propuesta es: construir la imagen (ya existe el `Dockerfile`),
subirla a **ECR**, y correrla en **ECS Fargate** detrás de un **Application
Load Balancer** — el mismo contenedor, sin cambiar una línea de código de la
app, corriendo de forma administrada.


## Diagrama

```
Internet
  │
  ▼
Application Load Balancer (subred pública)
  │  HTTP + upgrade a WebSocket, mismo listener
  ▼
ECS Fargate — 1 tarea (subred privada con salida a internet, vía NAT, para poder
  │            tirar de ECR)
  │  DB_HOST / DB_PORT / DB_NAME (env vars) +
  │  DB_USERNAME / DB_PASSWORD (secrets de Secrets Manager, resueltos en runtime)
  ▼
RDS PostgreSQL (subred aislada, sin salida a internet)
```

La imagen del contenedor se construye y se sube a **ECR** por fuera de este
stack — CDK no compila el `Dockerfile` en este
flujo, solo referencia el repositorio (`ecs.ContainerImage.from_ecr_repository`).

## Archivos

- `app.py` — punto de entrada de la app CDK.
- `infrastructure_stack.py` — el stack: VPC (3 grupos de subredes), ECR, RDS
  PostgreSQL, clúster de ECS, servicio Fargate + ALB.
- `requirements.txt` — dependencias del CDK (separadas de las del backend).
- `cdk.json` — configuración estándar de la CLI de CDK.

## Cómo se usaría (si se decidiera desplegar)

```bash
cd infra
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt

cdk bootstrap   # una sola vez por cuenta/región
cdk deploy      # crea el ECR, la VPC, RDS, ECS/Fargate y el ALB

# Después del primer deploy, construir y subir la imagen al ECR creado:
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <ID_DE_CUENTA>.dkr.ecr.us-east-1.amazonaws.com

docker build -t nequi-chat-api ..
docker tag nequi-chat-api:latest <ID_DE_CUENTA>.dkr.ecr.us-east-1.amazonaws.com/nequi-chat-api:latest
docker push <ID_DE_CUENTA>.dkr.ecr.us-east-1.amazonaws.com/nequi-chat-api:latest

# ECS no vuelve a tirar de la imagen nueva solo: forzar un nuevo despliegue.
aws ecs update-service --cluster <nombre-del-cluster> --service <nombre-del-servicio> --force-new-deployment
```

`cdk deploy` imprime al final la URL del load balancer
(`ApiLoadBalancerUrl`), el host de la base de datos (`DatabaseEndpoint`) y el
ARN del secreto con las credenciales (`DatabaseSecretArn`).

## Alcance y limitaciones (léase antes de tomar esto como "listo para producción")

1. **`DATABASE_URL` no se compone automáticamente.** La app espera una sola
   variable de entorno con el string de conexión completo
   (`postgresql+psycopg://usuario:password@host:puerto/nombre`). Componer
   ese string de forma segura —sin exponer la contraseña en texto plano en
   la definición de tarea— requeriría un recurso custom de CDK, fuera del
   alcance de esta propuesta ilustrativa. Por eso el stack pasa las piezas
   por separado (`DB_HOST`, `DB_PORT`, `DB_NAME` como variables normales;
   `DB_USERNAME`/`DB_PASSWORD` como *secrets* de ECS). **Antes de un
   despliegue real** hace falta un ajuste chico en `app/core/config.py`:
   que `Settings` arme `database_url` a partir de esas piezas si
   `DATABASE_URL` no viene definido directamente — no está hecho en este
   repositorio.
2. **No incluye `API_KEY`** (autenticación de la app) como variable de
   entorno ni como secreto — se dejó fuera para mantener la propuesta
   enfocada en cómputo + base de datos; agregarla es una línea más de
   `environment`/`secrets` en `task_image_options`.
3. **No incluye pipeline de CI/CD** (build + push de la imagen a ECR en cada
   commit) — el paso de `docker build`/`push` de "Cómo se usaría" es manual;
   automatizarlo (CodePipeline, GitHub Actions, etc.) queda fuera del
   alcance de esta propuesta.
4. **Validado con `cdk synth`, no con `cdk deploy`.** El stack sintetiza sin
   errores ni advertencias de seguridad (50 recursos de CloudFormation:
   VPC completa, ECR, RDS, ECS/Fargate, ALB, IAM, Secrets Manager) — eso
   confirma que el código Python es correcto y que las referencias entre
   construcciones (VPC → RDS → ECS → ALB) están bien resueltas, pero no
   reemplaza probarlo contra una cuenta AWS real.
