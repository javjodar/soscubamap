# Arquitectura del sistema

## Visión general

SOSCuba Map es una aplicación Flask monolítica con 7 blueprints, 19 modelos SQLAlchemy, y 15 servicios. Usa PostgreSQL como base de datos, Cloudinary para almacenamiento de imágenes, y Web Push (VAPID) para notificaciones.

```
                    ┌──────────────┐
                    │   Navegador  │
                    └──────┬───────┘
                           │
               ┌───────────▼───────────┐
               │    Gunicorn / Flask    │
               │   (ProxyFix si proxy) │
               └───────────┬───────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌─────▼─────┐     ┌──────▼──────┐
   │  Views  │      │    API    │     │  Static     │
   │ (HTML)  │      │  (JSON)   │     │  Assets     │
   └────┬────┘      └─────┬─────┘     └─────────────┘
        │                  │
        └────────┬─────────┘
                 │
        ┌────────▼────────┐
        │    Services     │
        │  (lógica neg.)  │
        └────────┬────────┘
                 │
        ┌────────▼────────┐       ┌──────────────┐
        │   SQLAlchemy    │───────│  PostgreSQL   │
        │     (ORM)       │       │     16        │
        └─────────────────┘       └──────────────┘
                                  ┌──────────────┐
                                  │  Cloudinary  │
                                  │  (imágenes)  │
                                  └──────────────┘
```

## Blueprints

Cada blueprint agrupa rutas por dominio funcional:

| Blueprint      | Prefijo URL     | Responsabilidad                                              |
|----------------|-----------------|--------------------------------------------------------------|
| `map`          | `/`             | Dashboard principal, mapa, crear/editar reportes, exportar, donar, analytics |
| `auth`         | `/`             | Registro (`/registro`), login (`/login`), logout             |
| `api`          | `/api`          | API REST JSON (posts, comments, votes, chat, push, analytics)|
| `admin`        | `/admin`        | Panel de admin: reportes, discusiones, donaciones, ajustes   |
| `moderation`   | `/moderacion`   | Cola de moderación: aprobar/rechazar reportes y ediciones    |
| `discussions`  | `/`             | Foro de discusiones (`/discusiones`)                          |
| `panic`        | `/`             | Botón de pánico (`/panic`, `/api/panic`)                      |

## Modelos de datos

### Reportes y contenido

- **Post** — Reporte geolocalizado. Campos principales: título, descripción, coordenadas, provincia, municipio, categoría, estado de moderación, fecha del evento (`movement_at`), nombre de represor, tipo personalizado, GeoJSON de polígono, links, contador de verificaciones.
- **Category** — Categorías de reportes (acción represiva, residencia de represor, movimiento de tropas, desconexión de internet, otros).
- **Media** — Imágenes asociadas a un post (URL de Cloudinary + caption).
- **PostRevision** — Historial de versiones de un post. Se crea antes de cada edición.
- **PostEditRequest** — Solicitudes de edición pendientes de moderación.
- **Comment** — Comentarios en reportes, con upvotes/downvotes.

### Discusiones

- **DiscussionPost** — Post del foro con markdown, imágenes y tags.
- **DiscussionComment** — Comentarios con soporte de hilos (parent_id para respuestas anidadas).
- **DiscussionTag** — Tags con slug para categorizar discusiones.

### Usuarios y roles

- **User** — Email, password hash, código anónimo (6 chars). Usa `Flask-Login`.
- **Role** — Roles: `colaborador`, `moderador`, `administrador`. Relación many-to-many con User.

### Sistema

- **VoteRecord** — Registro unificado de votos (verificaciones de posts, votos en comentarios, votos en discusiones). Usa `voter_hash` para deduplicación anónima.
- **ChatMessage** / **ChatPresence** — Chat en vivo con mensajes efímeros (48h) y presencia (10min TTL).
- **PushSubscription** — Suscripciones Web Push para notificaciones.
- **DonationLog** — Registro de donaciones recibidas (monto, vía, fecha, destino).
- **AuditLog** — Log de auditoría del sistema.
- **SiteSetting** — Configuraciones key-value (ej: `moderation_enabled`).
- **LocationReport** — Reportes de ubicación.

## Servicios

Los servicios encapsulan lógica de negocio reutilizable:

| Servicio              | Función                                                       |
|-----------------------|---------------------------------------------------------------|
| `authz`               | Decorador `@role_required` para autorización por roles        |
| `category_rules`      | Reglas por categoría (ej: si "otros" permite ciertos tipos)   |
| `category_sort`       | Ordenamiento de categorías para formularios                   |
| `content_quality`     | Validación de calidad de título y descripción                 |
| `cuba_locations`      | Datos de provincias y municipios de Cuba                      |
| `discussion_tags`     | Upsert y normalización de tags de discusión                   |
| `geo_lookup`          | Resolución de provincia/municipio a partir de lat/lng via GeoJSON |
| `input_safety`        | Detección de inputs maliciosos (XSS, injection)               |
| `markdown_utils`      | Renderizado seguro de Markdown (bleach + markdown)            |
| `media_upload`        | Validación y subida de imágenes a Cloudinary                  |
| `push_notifications`  | Envío de notificaciones Web Push via pywebpush                |
| `recaptcha`           | Verificación de tokens reCAPTCHA v2                           |
| `settings`            | Lectura/escritura de SiteSetting (key-value)                  |
| `text_sanitize`       | Sanitización de texto libre (trim, max length)                |
| `vote_identity`       | Generación de `voter_hash` para deduplicación anónima de votos|

## Flujo de moderación

```
Nuevo reporte/edición
        │
        ▼
┌─ moderation_enabled? ─┐
│                        │
│  SÍ              NO    │
│  │                │    │
│  ▼                ▼    │
│ status=pending  Publicación │
│  │              directa     │
│  ▼                          │
│ Cola de moderación          │
│ (/moderacion)               │
│  │                          │
│  ├── Aprobar ──► status=approved
│  │               + crear PostRevision
│  │
│  └── Rechazar ──► status=rejected
│                   + motivo obligatorio (ediciones)
└─────────────────────────────┘
```

Excepción: las categorías urgentes (`accion-represiva`, `movimiento-tropas`, `movimiento-militar`, `desconexion-internet`) y los reportes del botón de pánico se publican directamente sin moderación.

## Flujo de identidad anónima

Los usuarios pueden crear reportes y comentar sin registrarse. El sistema crea un `User` anónimo con email `anon+<hex>@local`, genera un `anon_code` de 6 caracteres, y lo muestra como `Anon-X3K9M2`. Para votos, se usa un `voter_hash` derivado del ID de usuario (si autenticado) o IP + User-Agent + SECRET_KEY (si anónimo) para prevenir duplicados.

## Stack de seguridad

- **CSRF:** Flask-WTF con WTF_CSRF_ENABLED para formularios HTML.
- **Rate limiting:** Flask-Limiter en todos los endpoints sensibles.
- **Input safety:** Detección de patrones maliciosos antes de guardar.
- **Sanitización:** Bleach para HTML, text_sanitize para texto libre.
- **reCAPTCHA v2:** Opcional en formularios de reportes, discusiones y comentarios.
- **Proxy fix:** ProxyFix para IP real detrás de reverse proxy.
