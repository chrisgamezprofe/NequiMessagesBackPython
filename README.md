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
- [Seguridad adicional en inputs](#seguridad-adicional-en-inputs)
- [Pruebas](#pruebas)
- [Docker / Podman](#docker--podman)
- [Propuesta de infraestructura en AWS (IaC)](#propuesta-de-infraestructura-en-aws-iac)
- [Alcance: qué SÍ y qué NO tiene este proyecto](#alcance-qué-sí-y-qué-no-tiene-este-proyecto)

## Descripción general

El servicio expone:

1. **`POST /api/v1/messages`**: valida el formato del mensaje, filtra contenido
   inapropiado (censura simple por lista de palabras) y calcula metadatos
   (`word_count`, `character_count`, `processed_at`) antes de almacenarlo.
2. **`GET /api/v1/messages/{session_id}`**: mensajes de una sesión, con
   paginación (`limit`/`offset`) y filtro opcional por remitente (`sender`).
3. **`GET /api/v1/messages/search`** (punto extra): búsqueda de mensajes por
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
(ver `.env.example`), **todos** los endpoints de `/api/v1/messages*` (no
`/health`) exigen el header `X-API-Key` con ese valor exacto, o responden
`401` con `error.code = "INVALID_API_KEY"`. El WebSocket usa el mismo
mecanismo pero vía query param (`?api_key=...`), ya que un cliente WebSocket
de navegador no puede fijar headers custom en el *handshake*.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{ ... }'
```

### `POST /api/v1/messages`

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
| 413         | `PAYLOAD_TOO_LARGE`      | El body de la request supera el tamaño máximo permitido (ver [Seguridad adicional en inputs](#seguridad-adicional-en-inputs)) |
| 429         | `RATE_LIMIT_EXCEEDED`    | Se superó el límite de solicitudes             |
| 500         | `INTERNAL_SERVER_ERROR`  | Error inesperado del servidor                  |

### `GET /api/v1/messages/{session_id}`

| Parámetro | Tipo   | Default | Notas                          |
|-----------|--------|---------|----------------------------------|
| session_id (path) | string | — | 1-100 caracteres                |
| limit     | int    | 20      | 1-100                            |
| offset    | int    | 0       | ≥ 0                               |
| sender    | string | (todos) | `"user"` o `"system"`            |
| order     | string | `"desc"` | `"desc"`: el último mensaje enviado primero. `"asc"`: el más antiguo primero. |

El orden se aplica sobre `timestamp` (cuándo se envió el mensaje), no sobre
`message_id`: este último es un string arbitrario que entrega quien llama, sin
ninguna garantía de orden, así que no sirve para "el último enviado primero".

Si la sesión no existe, devuelve `200` con una lista vacía.

### `GET /api/v1/messages/search` (punto extra)

Busca mensajes cuyo texto contenga lo dado (`q`, 1-200 caracteres), sin
distinguir mayúsculas/minúsculas. Acepta `limit`/`offset`.

Busca sobre `original_content` (el texto real), no sobre `content` (la
versión censurada): si buscara sobre `content`, una palabra prohibida jamás
podría encontrarse, porque ya no existe ahí. La respuesta sigue devolviendo
`content` censurado como siempre — buscar por la palabra prohibida no la
"destapa" en el resultado.

`q` se trata siempre como texto literal, aunque contenga `%` o `_` (los
comodines de `LIKE` en SQL) — ver
[Seguridad adicional en inputs](#seguridad-adicional-en-inputs).

### `WS /ws/messages/{session_id}` (punto extra)

Notifica en tiempo real los mensajes nuevos de una sesión. Cada
`POST /api/v1/messages` exitoso con ese `session_id` se reenvía como un frame
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

## Seguridad adicional en inputs

Más allá de la validación de formato de Pydantic, se agregaron protecciones
puntuales contra abusos concretos que no son teóricos — cada una responde a
algo que sí puede pasar con este código y este despliegue (ECS detrás de un
ALB, ver [Propuesta de infraestructura en AWS](#propuesta-de-infraestructura-en-aws-iac)):

- **Comparación de API key en tiempo constante** (`app/core/api_key_auth.py`).
  `hmac.compare_digest` en vez de `==`: con `==`, Python deja de comparar en
  el primer carácter distinto, así que el tiempo de respuesta varía según
  cuántos caracteres iniciales acierte quien ataca (*timing attack*) — con
  suficientes intentos medidos, eso permite reconstruir la key carácter a
  carácter.
- **Comodines de `LIKE` escapados en la búsqueda** (`app/repositories/message_repository.py`,
  método `search`). `q` se envuelve en `%...%` para el `ILIKE` de SQL, pero
  `%` y `_` ya son comodines de SQL: sin escaparlos, `GET /api/v1/messages/search?q=%25`
  (`%` sin escapar en la URL) haría match con *todos* los mensajes —una fuga
  del contenido completo a través del buscador— y `q=_` con cualquier mensaje
  de un solo carácter. Ahora se tratan siempre como texto literal.
- **Límites de tamaño en `session_id` (path) y `q` (búsqueda)**. `session_id`
  ya se limitaba a 100 caracteres al crear un mensaje
  (`MessageCreate.session_id`), pero el path param de
  `GET /api/v1/messages/{session_id}` no tenía el mismo tope; `q` tampoco
  tenía límite superior. Ambos ahora rechazan con `422` un valor
  desproporcionadamente largo, antes de llegar a la base de datos.
- **Límite de tamaño del body** (`app/core/body_size_limit.py`,
  `BodySizeLimitMiddleware`). Sin esto, un body de varios MB se lee completo
  en memoria aunque `MessageCreate.content` (máx. 5000 caracteres) lo termine
  rechazando de todas formas — la validación de Pydantic corre después de que
  Starlette ya cargó el body entero. El middleware corta por `Content-Length`
  antes de eso (`413 PAYLOAD_TOO_LARGE`, tope configurable vía
  `Settings.max_body_bytes`, 50 KiB por defecto).
- **Rate limiting resistente al proxy de la infraestructura propuesta**
  (`app/core/rate_limit.py`). Detrás de un Application Load Balancer (el de
  `infra/`), `request.client.host` deja de identificar al cliente real: a la
  app le llega la IP interna del ALB, así que todo el tráfico externo se
  agruparía en un solo balde. Ahora se usa el último valor de
  `X-Forwarded-For` (el que el ALB —el único proxy de confianza delante de la
  app— añade él mismo al final, sin importar qué valor propio haya mandado el
  cliente).

Cada punto tiene su prueba dedicada en `tests/unit/` (`test_api_key_auth.py`,
`test_message_repository.py`, `test_rate_limit.py`) y `tests/integration/`
(`test_messages_api.py`).

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
