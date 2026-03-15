# Variables de entorno

Referencia completa de las variables de entorno de SOSCuba Map. Copiar `.env.example` a `.env` y ajustar los valores.

## Obligatorias

| Variable       | Descripción                                  | Ejemplo                                                            |
|----------------|----------------------------------------------|--------------------------------------------------------------------|
| `SECRET_KEY`   | Clave secreta de Flask para firmar sesiones. Cambiar siempre en producción. | `openssl rand -hex 32`                                    |
| `DATABASE_URL` | URI de conexión a PostgreSQL.                | `postgresql+psycopg://user:pass@localhost:5432/soscubamap`         |

## Administrador

| Variable         | Descripción                                  | Default                |
|------------------|----------------------------------------------|------------------------|
| `ADMIN_EMAIL`    | Email del administrador. Se auto-crea al hacer login por primera vez. | `admin@soscuba.local` |
| `ADMIN_PASSWORD` | Contraseña del admin. Si está vacía, el login admin no funciona. | (vacío)               |

## Imágenes (Cloudinary)

| Variable                | Descripción                          | Default  |
|-------------------------|--------------------------------------|----------|
| `CLOUDINARY_CLOUD_NAME` | Nombre del cloud en Cloudinary.      | (vacío)  |
| `CLOUDINARY_API_KEY`    | API key de Cloudinary.               | (vacío)  |
| `CLOUDINARY_API_SECRET` | API secret de Cloudinary.            | (vacío)  |
| `IMAGE_MAX_MB`          | Tamaño máximo por imagen en MB.      | `2`      |
| `IMAGE_MAX_PER_SUBMIT`  | Máximo de imágenes por envío.        | `3`      |
| `IMAGE_ALLOWED_EXTENSIONS` | Extensiones permitidas (CSV).     | `jpg,jpeg,png,webp,heic` |

## Mapas (Google Maps)

Estos valores se usan opcionalmente para geocodificación y mapas avanzados. La app funciona sin ellos usando Leaflet/OSM.

| Variable              | Descripción                   | Default  |
|-----------------------|-------------------------------|----------|
| `GOOGLE_MAPS_API_KEY` | API key de Google Maps.       | (vacío)  |
| `GOOGLE_MAPS_MAP_ID`  | Map ID para estilos custom.   | (vacío)  |

## GeoJSON (datos geográficos de Cuba)

Rutas a archivos GeoJSON para la resolución automática de provincia/municipio a partir de coordenadas.

| Variable                         | Descripción                                              | Default  |
|----------------------------------|----------------------------------------------------------|----------|
| `GEOJSON_PROVINCES_PATH`         | Ruta al archivo GeoJSON de provincias.                   | (vacío)  |
| `GEOJSON_MUNICIPALITIES_PATH`    | Ruta al archivo GeoJSON de municipios.                   | (vacío)  |
| `GEOJSON_PROVINCE_KEYS`         | Nombres de propiedades en el GeoJSON para buscar provincia. | (vacío) |
| `GEOJSON_MUNICIPALITY_KEYS`     | Nombres de propiedades para buscar municipio.            | (vacío)  |
| `GEOJSON_MUNICIPALITY_PROVINCE_KEYS` | Propiedades que vinculan municipio con provincia.   | (vacío)  |

## Push Notifications (VAPID)

Para habilitar notificaciones push a los navegadores suscritos cuando se crean reportes urgentes o alertas de pánico.

| Variable            | Descripción                                     | Default                           |
|---------------------|-------------------------------------------------|-----------------------------------|
| `VAPID_PUBLIC_KEY`  | Clave pública VAPID (base64url).                | (vacío — push deshabilitado)      |
| `VAPID_PRIVATE_KEY` | Clave privada VAPID (base64url).                | (vacío — push deshabilitado)      |
| `VAPID_SUBJECT`     | Email de contacto para VAPID.                   | `mailto:soscubamap@proton.me`     |

Generar par de claves VAPID:

```bash
pip install pywebpush
python -c "from pywebpush import webpush; from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print('PUBLIC:', v.public_key); print('PRIVATE:', v.private_key)"
```

## reCAPTCHA

| Variable                  | Descripción                        | Default  |
|---------------------------|------------------------------------|----------|
| `RECAPTCHA_V2_SITE_KEY`   | Site key de reCAPTCHA v2.          | (vacío — reCAPTCHA deshabilitado) |
| `RECAPTCHA_V2_SECRET_KEY` | Secret key de reCAPTCHA v2.        | (vacío)  |

## Rate Limiting

| Variable                | Descripción                                        | Default    |
|-------------------------|----------------------------------------------------|------------|
| `RATELIMIT_STORAGE_URL` | Backend de almacenamiento para rate limits.         | `memory://` |

En producción con múltiples workers, usar Redis: `redis://localhost:6379/0`.

## Aplicación

| Variable              | Descripción                                      | Default  |
|-----------------------|--------------------------------------------------|----------|
| `CHAT_DISABLED`       | Deshabilitar el chat en vivo. `1` = deshabilitado. | `0`     |
| `ASSET_VERSION`       | Versión para cache-busting de assets estáticos.  | `1`      |
| `TRUST_PROXY_HEADERS` | Confiar en cabeceras de proxy (X-Forwarded-For). `1` = sí. | `1` |
