# API Reference

SOSCuba Map expone una API REST JSON bajo los prefijos `/api` y `/api/v1`. Todas las respuestas usan `Content-Type: application/json`. Los errores devuelven `{"error": "mensaje"}` o `{"ok": false, "error": "mensaje"}`.

Rate limiting está habilitado en todos los endpoints. Las cabeceras `X-RateLimit-*` indican límites y uso restante.

## Autenticación

La mayoría de endpoints son públicos. Los que requieren autenticación usan sesiones Flask (cookie `session`). Los endpoints de administración requieren el rol `administrador`.

---

## Endpoints públicos

### `GET /api/health`

Health check.

**Respuesta:** `200`

```json
{"status": "ok"}
```

---

### `GET /api/categories`

Lista todas las categorías de reportes.

**Respuesta:** `200`

```json
[
  {
    "id": 1,
    "name": "Acción represiva",
    "slug": "accion-represiva",
    "description": "Acciones represivas documentadas"
  }
]
```

---

### `GET /api/posts`

Lista reportes aprobados para el mapa.

**Parámetros query:**

| Parámetro     | Tipo   | Descripción                        |
|---------------|--------|------------------------------------|
| `category_id` | int    | Filtrar por categoría              |
| `limit`       | int    | Máximo de resultados               |

**Respuesta:** `200` — Array de objetos post con campos: `id`, `title`, `description`, `latitude`, `longitude`, `address`, `province`, `municipality`, `movement_at`, `repressor_name`, `other_type`, `created_at`, `anon`, `polygon_geojson`, `links`, `media`, `verify_count`, `verified_by_me`, `category`.

---

### `GET /api/v1/reports`

Versión paginada de reportes con filtros avanzados. Rate limit: 120/minuto.

**Parámetros query:**

| Parámetro      | Tipo   | Default     | Descripción                                       |
|----------------|--------|-------------|---------------------------------------------------|
| `category_id`  | int    | —           | Filtrar por categoría                              |
| `province`     | string | —           | Filtrar por provincia (case-insensitive)           |
| `municipality` | string | —           | Filtrar por municipio (case-insensitive)           |
| `status`       | string | `approved`  | Estado del reporte (solo admin puede ver otros)    |
| `page`         | int    | `1`         | Página actual                                      |
| `per_page`     | int    | `50`        | Resultados por página (máx 100)                    |

**Respuesta:** `200`

```json
{
  "page": 1,
  "per_page": 50,
  "total": 142,
  "pages": 3,
  "has_next": true,
  "has_prev": false,
  "items": [
    {
      "id": 1,
      "title": "Título del reporte",
      "description": "Descripción detallada...",
      "latitude": 23.1136,
      "longitude": -82.3666,
      "address": "Calle 23, Vedado",
      "province": "La Habana",
      "municipality": "Plaza de la Revolución",
      "movement_at": "2025-07-11T14:00:00",
      "repressor_name": null,
      "other_type": null,
      "status": "approved",
      "polygon_geojson": null,
      "links": ["https://example.com/evidence"],
      "media": [{"url": "https://res.cloudinary.com/...", "caption": "Foto"}],
      "verify_count": 5,
      "created_at": "2025-07-12T10:30:00",
      "updated_at": "2025-07-12T12:00:00",
      "anon": "Anon-X3K9M2",
      "category": {"id": 1, "name": "Acción represiva", "slug": "accion-represiva"}
    }
  ]
}
```

---

### `GET /api/v1/reports/<post_id>`

Detalle de un reporte específico. Rate limit: 120/minuto.

**Respuesta:** `200` — Objeto post individual (misma estructura que items de `/api/v1/reports`).

**Errores:** `403` si el reporte no está aprobado y el usuario no es admin. `404` si no existe.

---

### `GET /api/v1/categories`

Alias de `/api/categories`.

---

### `GET /api/v1/analytics`

Estadísticas agregadas de reportes. Rate limit: 60/minuto.

**Parámetros query:**

| Parámetro     | Tipo   | Default         | Descripción                              |
|---------------|--------|-----------------|------------------------------------------|
| `start`       | string | 90 días atrás   | Fecha inicio (YYYY-MM-DD)                |
| `end`         | string | hoy             | Fecha fin (YYYY-MM-DD)                   |
| `category_id` | int    | —               | Filtrar por categoría                     |
| `province`    | string | —               | Filtrar por provincia                     |

**Respuesta:** `200`

```json
{
  "range": {"start": "2025-04-01", "end": "2025-07-01"},
  "reports_over_time": [{"date": "2025-04-15", "count": 3}],
  "category_distribution": [{"id": 1, "name": "Acción represiva", "count": 45}],
  "province_distribution": [{"name": "La Habana", "count": 30}],
  "municipality_distribution": [{"name": "Centro Habana", "count": 12}],
  "moderation_status": {"approved": 100, "pending": 5, "rejected": 2, "hidden": 1},
  "top_verified": [{"id": 42, "title": "...", "verify_count": 15}],
  "comments_over_time": {
    "labels": ["2025-04-15", "2025-04-16"],
    "report_counts": [2, 5],
    "discussion_counts": [1, 3]
  },
  "edit_status": {"pending": 2, "approved": 10, "rejected": 1}
}
```

---

## Verificación de reportes

### `POST /api/posts/<post_id>/verify`

Verificar (confirmar) un reporte. Un usuario solo puede verificar cada reporte una vez (basado en hash de identidad + cookie). Rate limit: 10/min, 200/día.

**Respuesta:** `200`

```json
{"ok": true, "verify_count": 6}
```

Si ya verificó: `{"ok": false, "verify_count": 5}`.

---

## Comentarios

### `GET /api/posts/<post_id>/comments`

Lista comentarios de un reporte, ordenados por fecha descendente.

**Respuesta:** `200`

```json
[
  {
    "id": 1,
    "author": "Anon-X3K9M2",
    "body": "Puedo confirmar esto.",
    "created_at": "2025-07-12T11:00:00",
    "upvotes": 3,
    "downvotes": 0,
    "score": 3
  }
]
```

### `POST /api/posts/<post_id>/comments`

Crear un comentario. Rate limit: 10/min, 200/día.

**Body (JSON):**

```json
{
  "body": "Texto del comentario",
  "recaptcha": "token-opcional"
}
```

**Respuesta:** `200` — Devuelve la lista completa de comentarios actualizada.

---

### `POST /api/comments/<comment_id>/vote`

Votar un comentario. Rate limit: 10/min, 200/día.

**Body (JSON):**

```json
{"value": 1}
```

`value` debe ser `1` (upvote) o `-1` (downvote).

**Respuesta:** `200`

```json
{"ok": true, "upvotes": 4, "downvotes": 0, "score": 4}
```

---

### `DELETE /api/comments/<comment_id>` (Admin)

Eliminar un comentario. Requiere rol `administrador`. Rate limit: 10/min, 100/día.

**Respuesta:** `200` — `{"ok": true}`

---

## Estado de reportes (Admin)

### `POST /api/posts/<post_id>/status`

Cambiar el estado de un reporte. Requiere rol `administrador`.

**Body (JSON):**

```json
{"status": "approved"}
```

Valores válidos: `pending`, `approved`, `rejected`, `hidden`, `deleted`.

**Respuesta:** `200` — `{"ok": true, "status": "approved"}`

---

## Media

### `POST /api/posts/<post_id>/media`

Subir imágenes a un reporte existente. Rate limit: 6/hora, 30/día.

**Body:** `multipart/form-data`

| Campo              | Tipo     | Descripción                    |
|--------------------|----------|--------------------------------|
| `images`           | file[]   | Archivos de imagen             |
| `image_captions[]` | string[] | Leyendas para cada imagen      |

Si la moderación está habilitada, se crea una solicitud de edición (`status: "pending"`). Si no, las imágenes se añaden directamente.

**Respuesta:** `200`

```json
{"ok": true, "status": "approved", "media": [...]}
```

---

## Botón de pánico

### `POST /api/panic`

Envía un reporte de emergencia desde el botón de pánico. Se aprueba automáticamente. Rate limit: 1/hora, 3/día.

**Body (JSON):**

```json
{
  "latitude": 23.1136,
  "longitude": -82.3666,
  "description": "Descripción opcional"
}
```

**Respuesta:** `201`

```json
{"ok": true, "id": 42}
```

---

## Push Notifications

### `POST /api/push/subscribe`

Suscribir un navegador para recibir push notifications. Rate limit: 5/min, 60/día.

**Body (JSON):**

```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}
```

**Respuesta:** `200` — `{"status": "ok"}`

### `POST /api/push/unsubscribe`

Cancelar suscripción push. Rate limit: 10/min, 120/día.

**Body (JSON):**

```json
{"endpoint": "https://fcm.googleapis.com/fcm/send/..."}
```

**Respuesta:** `200` — `{"status": "ok"}`

---

## Chat (si habilitado)

### `GET /api/chat`

Obtener mensajes del chat (últimas 24h) y count de usuarios online. Rate limit: 60/min.

### `POST /api/chat`

Enviar mensaje al chat. Rate limit: 6/min, 120/día.

**Body (JSON):**

```json
{
  "body": "Hola a todos",
  "nickname": "MiNick"
}
```

**Respuesta:** `200`

```json
{
  "items": [
    {"id": 1, "author": "Anon-XYZ", "body": "Hola", "created_at": "..."}
  ],
  "online_count": 5
}
```

---

## Votación en discusiones

### `POST /api/discusiones/<post_id>/vote`

Votar un post de discusión. Rate limit: 12/min, 240/día. Body: `{"value": 1}` o `{"value": -1}`.

### `POST /api/discusiones/comentarios/<comment_id>/vote`

Votar un comentario de discusión. Rate limit: 10/min, 200/día. Body: `{"value": 1}` o `{"value": -1}`.

Ambos devuelven: `{"ok": true, "upvotes": N, "downvotes": N, "score": N}`.

---

## Códigos de error comunes

| Código | Significado                                    |
|--------|------------------------------------------------|
| `400`  | Datos inválidos o faltantes                    |
| `403`  | No autorizado (falta rol requerido)            |
| `404`  | Recurso no encontrado                          |
| `429`  | Rate limit excedido                            |
| `500`  | Error interno del servidor                     |
| `503`  | Funcionalidad deshabilitada (ej: push off)     |
