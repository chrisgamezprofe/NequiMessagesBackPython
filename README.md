# MensajesNequi – Message Processing API (arquitectura por capas)

API RESTful para recibir, validar, procesar y consultar mensajes de un sistema de
chat. Aquí con **arquitectura limpia clásica
por capas** (controladores / servicios / repositorios) — tal como la pide el
PDF del reto **literalmente**: *"Separar responsabilidades (controladores,
servicios, repositorios), usar inyección de dependencias donde sea
apropiado, seguir principios SOLID"*.

## Tabla de contenido

- [Descripción general](#descripción-general)
- [Arquitectura](#arquitectura)
- [Comparación con la versión hexagonal](#comparación-con-la-versión-hexagonal)
- [Stack tecnológico](#stack-tecnológico)
- [Configuración e instalación](#configuración-e-instalación)
- [Ejecución](#ejecución)
- [Documentación de la API](#documentación-de-la-api)
- [Pruebas](#pruebas)
- [Docker / Podman](#docker--podman)
- [Propuesta de infraestructura en AWS (IaC)](#propuesta-de-infraestructura-en-aws-iac)
- [Alcance: qué SÍ y qué NO tiene este proyecto](#alcance-qué-sí-y-qué-no-tiene-este-proyecto)

## Descripción general

El servicio expone:

1. **`POST /api/messages`**: valida el formato del mensaje, filtra contenido
   inapropiado (censura simple por lista de palabras) y calcula metadatos
   (`word_count`, `character_count`, `processed_at`) antes de almacenarlo.
2. **`GET /api/messages/{session_id}`**: mensajes de una sesión, con
   paginación (`limit`/`offset`) y filtro opcional por remitente (`sender`).
3. **`GET /api/messages/search`** (punto extra): búsqueda de mensajes por
   contenido — incluye los que tienen una palabra censurada (ver
   [Documentación de la API](#documentación-de-la-api)).
4. **`WS /ws/messages/{session_id}`** (punto extra): notifica en tiempo real
   los mensajes nuevos de una sesión.

Además incluye autenticación simple por API key (punto extra), rate limiting
(punto extra), soporte Docker/Podman (punto extra) y una propuesta de
infraestructura en AWS con ECR + ECS Fargate + RDS (punto extra — ver
[Propuesta de infraestructura en AWS](#propuesta-de-infraestructura-en-aws-iac)).
**No** incluye la preparación para migrar a Postgres/DynamoDB en el código de
la app: eso se agregó en la versión hexagonal por pedido explícito y no
aporta nada a la comparación arquitectónica que es el objetivo de este
proyecto.

## Arquitectura

Capas técnicas clásicas — cada carpeta agrupa código por **tipo de
responsabilidad**, no por caso de uso:

```
app/
├── api/routes/          # Controladores HTTP: parsean la request y arman la respuesta
│   ├── messages.py      # (no contienen lógica de negocio)
│   └── websocket.py     # Endpoint WS /ws/messages/{session_id}
├── services/              # Casos de uso / reglas de negocio
│   ├── message_service.py      # pipeline: validar -> filtrar -> enriquecer -> guardar
│   └── profanity_filter.py     # filtrado simple de palabras inapropiadas
├── repositories/           # Único lugar que conoce SQLAlchemy
│   └── message_repository.py
├── models/                 # Entidades ORM (persistencia)
│   └── message.py
├── schemas/                # Contratos Pydantic de entrada/salida
│   └── message.py
├── core/                    # Infraestructura transversal
│   ├── config.py            # Settings (pydantic-settings, .env)
│   ├── database.py          # Fábrica de engine/sesión SQLAlchemy
│   ├── dependencies.py      # Cableado de inyección de dependencias
│   ├── exceptions.py        # Excepciones -> códigos HTTP
│   ├── api_key_auth.py      # Autenticación simple por API key (punto extra)
│   ├── broadcaster.py       # Bus de eventos en memoria para el WebSocket
│   └── rate_limit.py        # Middleware de rate limiting
└── main.py                  # App factory: middlewares, rutas, manejo de errores
```

**Separación de responsabilidades (SOLID):**

- Los **controladores** (`api/routes`) solo traducen HTTP ↔ esquemas
  Pydantic.
- Los **servicios** (`services`) contienen las reglas de negocio y no
  conocen FastAPI ni SQLAlchemy.
- El **repositorio** (`repositories/message_repository.py`) es el único
  punto de acceso a datos, con métodos de negocio (`list_by_session`,
  `search`) en vez de un CRUD genérico.
- La **inyección de dependencias** (`core/dependencies.py`) ensambla estas
  piezas en tiempo de request vía `Depends` de FastAPI.

## Comparación con la versión hexagonal

| | `MensajesNequi` (este proyecto) | Versión hexagonal (`NequiBot-Assessment-Backend`) |
|---|---|---|
| Organización | Por **capa técnica**: un `services/`, un `repositories/` para todo | Por **caso de uso**: cada slice en `features/` es autocontenido |
| Archivos para 3 endpoints | ~20 archivos de app | ~50 archivos de app (4 slices, `shared_kernel`, `bootstrap`) |
| Acceso a datos | 1 `MessageRepository` con todos los métodos | 1 puerto (`Protocol`) angosto por caso de uso + 1 adaptador |
| Cambiar de motor de BD | Tocar `message_repository.py` (un archivo, conocido) | No tocar `application/`; sí tocar 1 adaptador nuevo por puerto |
| WebSocket en tiempo real | `MessageService` importa `MessageBroadcaster` directamente | 2 puertos (`MessageNotifierPort`/`MessageSubscriptionPort`) + 2 adaptadores + 1 slice nuevo |
| Agregar un error nuevo (ej. `InvalidApiKeyError`) | Solo definir la subclase de `AppError` con su `status_code` — el manejador genérico ya sabe leerlo | Definir la subclase de `DomainError` (sin `status_code`, a propósito) + registrar el status code aparte en una tabla de `bootstrap/` |
| Curva de entrada | Baja — se entiende en un vistazo | Media — hay que entender puertos/adaptadores/slices primero |
| Qué pide el PDF | Exactamente esto | Más de lo pedido |

**¿Por qué existe este proyecto entonces?** Porque para el alcance real del
reto (3 endpoints, un solo motor de datos, un desarrollador) **esta es la
arquitectura correcta** — cumple el enunciado al pie de la letra, es más
fácil de revisar por un evaluador, y no paga el costo de abstracciones que
nadie va a usar. La versión hexagonal se justifica cuando aparece una
necesidad *real* (no especulativa) de aislar casos de uso entre sí, o de
soportar más de un adaptador concreto por puerto — cosas que en ese reto se
simularon a propósito (Postgres, DynamoDB) para demostrar el patrón, no
porque el problema las pidiera.

**La heurística para decidir en el futuro:** no pagues el costo de puertos y
slices hasta tener una *segunda implementación real* de un adaptador, o un
*segundo equipo* trabajando en paralelo sobre casos de uso distintos. Antes
de eso, tres capas simples — como este proyecto — es la opción que un tech
lead evaluando "calidad de código" esperaría ver.

## Stack tecnológico

- Python 3.10+ (probado con 3.12)
- FastAPI
- SQLAlchemy 2.0 + SQLite (desarrollo local) / PostgreSQL (propuesta de
  despliegue en AWS — ver [Propuesta de infraestructura en AWS](#propuesta-de-infraestructura-en-aws-iac))
- Pydantic v2 / pydantic-settings
- Pytest + pytest-cov
- AWS CDK (Python) para la propuesta de infraestructura

## Configuración e instalación

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# .venv\Scripts\Activate.ps1       # Windows (PowerShell)

pip install -r requirements-dev.txt
cp .env.example .env               # opcional
```

## Ejecución

```bash
uvicorn app.main:app --reload
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Health check: `GET /health`

La base de datos SQLite se crea automáticamente en `./data/messages.db` al
arrancar la aplicación.

## Documentación de la API

Todas las respuestas siguen el mismo sobre:

```json
// éxito
{ "status": "success", "data": { ... } }
// error
{ "status": "error", "error": { "code": "...", "message": "...", "details": "..." } }
```

### Autenticación (opcional)

Deshabilitada por defecto. Si configuras la variable de entorno `API_KEY`
(ver `.env.example`), **todos** los endpoints de `/api/messages*` (no
`/health`) exigen el header `X-API-Key` con ese valor exacto, o responden
`401` con `error.code = "INVALID_API_KEY"`. El WebSocket usa el mismo
mecanismo pero vía query param (`?api_key=...`), ya que un cliente WebSocket
de navegador no puede fijar headers custom en el *handshake*.

```bash
curl -X POST http://127.0.0.1:8000/api/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{ ... }'
```

### `POST /api/messages`

**Request**

```json
{
  "message_id": "msg-123456",
  "session_id": "session-abcdef",
  "content": "Hola, ¿cómo puedo ayudarte hoy?",
  "timestamp": "2023-06-15T14:30:00Z",
  "sender": "system"
}
```

| Campo        | Tipo   | Requerido | Notas                                   |
|--------------|--------|-----------|------------------------------------------|
| message_id   | string | sí        | Único; un duplicado devuelve `409`      |
| session_id   | string | sí        |                                          |
| content      | string | sí        | 1-5000 caracteres, no solo espacios      |
| timestamp    | string | sí        | ISO-8601 (acepta sufijo `Z`)             |
| sender       | string | sí        | `"user"` o `"system"`                    |

**Respuesta `201 Created`**

```json
{
  "status": "success",
  "data": {
    "message_id": "msg-123456",
    "session_id": "session-abcdef",
    "content": "Hola, ¿cómo puedo ayudarte hoy?",
    "original_content": "Hola, ¿cómo puedo ayudarte hoy?",
    "timestamp": "2023-06-15T14:30:00Z",
    "sender": "system",
    "metadata": {
      "word_count": 5,
      "character_count": 31,
      "processed_at": "2023-06-15T14:30:01.123456Z",
      "contains_filtered_content": false
    }
  }
}
```

`content` es siempre la versión segura de mostrar (censurada si hacía falta);
`original_content` conserva el texto tal como se recibió — el filtrado nunca
destruye el dato original, solo lo oculta visualmente en `content`. Ejemplo
con una palabra prohibida:

```json
{
  "content": "eso fue una ****** decision",
  "original_content": "eso fue una idiota decision",
  "metadata": { "contains_filtered_content": true, "...": "..." }
}
```

Si el contenido incluye una palabra de la lista de palabras prohibidas
(`app/core/config.py`, campo `banned_words`), esta se censura con asteriscos
en `content` y `metadata.contains_filtered_content` queda en `true`.

**Errores posibles**

| Código HTTP | `error.code`            | Causa                                         |
|-------------|--------------------------|------------------------------------------------|
| 422         | `INVALID_FORMAT`         | Campo faltante, tipo inválido, `sender` inválido, etc. |
| 401         | `INVALID_API_KEY`        | Falta el header `X-API-Key` o es incorrecto (solo si `API_KEY` está configurado) |
| 409         | `DUPLICATE_MESSAGE_ID`   | Ya existe un mensaje con ese `message_id`      |
| 429         | `RATE_LIMIT_EXCEEDED`    | Se superó el límite de solicitudes             |
| 500         | `INTERNAL_SERVER_ERROR`  | Error inesperado del servidor                  |

### `GET /api/messages/{session_id}`

| Parámetro | Tipo   | Default | Notas                          |
|-----------|--------|---------|----------------------------------|
| limit     | int    | 20      | 1-100                            |
| offset    | int    | 0       | ≥ 0                               |
| sender    | string | (todos) | `"user"` o `"system"`            |

Si la sesión no existe, devuelve `200` con una lista vacía.

### `GET /api/messages/search` (punto extra)

Busca mensajes cuyo texto contenga lo dado (`q`), sin distinguir
mayúsculas/minúsculas. Acepta `limit`/`offset`.

Busca sobre `original_content` (el texto real), no sobre `content` (la
versión censurada): si buscara sobre `content`, una palabra prohibida jamás
podría encontrarse, porque ya no existe ahí. La respuesta sigue devolviendo
`content` censurado como siempre — buscar por la palabra prohibida no la
"destapa" en el resultado.

### `WS /ws/messages/{session_id}` (punto extra)

Notifica en tiempo real los mensajes nuevos de una sesión. Cada
`POST /api/messages` exitoso con ese `session_id` se reenvía como un frame
JSON con el mismo cuerpo que devolvería la API REST (`content` censurado,
`original_content` disponible) — sin el sobre `{"status", "data"}`, porque el
WebSocket ya es en sí mismo el canal de eventos.

```bash
# ejemplo con websocat (o cualquier cliente WS)
websocat "ws://127.0.0.1:8000/ws/messages/session-abcdef"
```

O en la consola del navegador:

```js
const ws = new WebSocket("ws://127.0.0.1:8000/ws/messages/session-abcdef");
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

Si `API_KEY` está configurado, se conecta como
`ws://.../ws/messages/{session_id}?api_key=tu-api-key`; una key inválida
cierra la conexión con el código `4401` durante el *handshake*.

Implementación: `app/core/broadcaster.py` (`MessageBroadcaster`, un bus en
memoria por sesión) usado directamente por `MessageService` — sin puertos ni
adaptadores de por medio, a diferencia de la versión hexagonal. Ver
[Comparación con la versión hexagonal](#comparación-con-la-versión-hexagonal).

### `GET /health`

Chequeo de salud simple.

## Pruebas

```bash
pytest
```

`pyproject.toml` exige **mínimo 80% de cobertura** (`--cov-fail-under=80`);
el proyecto está en ~97%.

- `tests/unit/`: prueban `ProfanityFilter`, `MessageRepository`,
  `MessageService`, `MessageBroadcaster`, la autenticación por API key y los
  esquemas Pydantic de forma aislada.
- `tests/integration/`: prueban los endpoints reales vía `TestClient` de
  FastAPI (casos felices, validación, duplicados, paginación, filtros, rate
  limiting, autenticación, WebSocket).

Cada test usa una base de datos SQLite propia en un archivo temporal.

## Docker / Podman

```bash
podman build -t mensajesnequi .
podman run --rm -p 8000:8000 -v "$(pwd)/data:/app/data:Z" mensajesnequi
# o con docker: docker build / docker run (mismos flags, sin :Z en Windows/macOS)
```

```bash
podman compose up --build   # o: docker compose up --build
```

## Propuesta de infraestructura en AWS (IaC)

![Arquitectura de despliegue: Código + Docker + ECR + ECS Fargate + RDS](Mensajes-Arquitectura.jpg)

*Diagrama de despliegue propuesto — autoría: Christian Camilo Serna Gámez.
Referencia usada: [AWS Builder Center — Deploy a containerized application on ECS using ECR](https://builder.aws.com/content/2kWxLURWQxbU7JalfjyYkSgxqOs/deploy-containerized-apache-application-on-ecs-using-ecr).*

Se incluye en [`infra/`](infra/) una propuesta de despliegue en AWS con
**ECR + ECS Fargate + RDS PostgreSQL**, escrita como **AWS CDK (Python)** —
validada de verdad con `cdk synth` (sintetiza sin errores ni advertencias,
50 recursos de CloudFormation), aunque no desplegada contra una cuenta real.

Es una arquitectura distinta a la de la versión hexagonal (que propone
serverless con Lambda + DynamoDB) **a propósito**: esta app ya corre como un
contenedor persistente (tiene `Dockerfile`) y usa WebSocket con estado en
memoria (`MessageBroadcaster`) — Fargate es el destino natural para eso, no
Lambda. El flujo, tal como está en el diagrama: el código se conteneriza con
Docker, la imagen se sube (`push`) a Amazon ECR, y desde ahí ECS Fargate la
despliega en la subred pública de la VPC, conectada a Amazon RDS en la
subred privada.

Ver [`infra/README.md`](infra/README.md) para la justificación completa y
las limitaciones documentadas (la más importante: `DATABASE_URL` no se
compone automáticamente desde las credenciales generadas de RDS — hace
falta un ajuste chico en `app/core/config.py` antes de un despliegue real).

## Alcance: qué SÍ y qué NO tiene este proyecto

Incluido (lo obligatorio del PDF + extras): mensajes/consulta/búsqueda,
WebSocket en tiempo real, autenticación por API key, manejo de errores, rate
limiting, Docker/Podman, propuesta de infraestructura en AWS (IaC), tests
≥80%.

No incluido a propósito (para que la comparación sea limpia — está en la
versión hexagonal, agregada por fuera del alcance original del reto): la
preparación para migrar a PostgreSQL/DynamoDB en el propio código de la app
(la propuesta de IaC sí provisiona un RDS PostgreSQL real, pero conectar la
app a él requiere el ajuste manual documentado en
[`infra/README.md`](infra/README.md)).
