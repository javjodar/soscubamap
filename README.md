# #SOSCuba Map

Dashboard colaborativo para documentar y visualizar lugares y acciones represivas en Cuba.

## Stack

- Python Flask
- PostgreSQL
- Leaflet + OpenStreetMap

## Instalacion principal (baremetal)

Esta es la opcion recomendada para desarrollo y control directo del entorno.

1. Crear entorno virtual e instalar dependencias.

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
cp .env.example .env
```

1. Configurar base de datos y migraciones.

```bash
flask --app run.py db upgrade
```

1. Sembrar datos base.

```bash
python -m scripts.seed_roles
python -m scripts.seed_categories
```

1. Configurar admin (opcional, recomendado).

```bash
ADMIN_EMAIL=admin@soscuba.local
ADMIN_PASSWORD=tu_password_seguro
```

1. Ejecutar la app.

```bash
flask --app run.py run
```

## Opcion alternativa: Docker Compose

Si prefieres entorno containerizado:

```bash
docker compose up --build -d
```

Logs:

```bash
docker compose logs -f web
```

Parar:

```bash
docker compose down
```

## Self-hosted maps (opcional)

Existe soporte para mapas self-hosted con un compose adicional.
Para configuracion completa e import de datos OSM, ver:

- `README.maps-selfhosted.es.md`

## Roles

- colaborador: cuenta estandar
- moderador: revisa reportes
- administrador: gestiona usuarios y ajustes

## Proveedor de mapas por vista

Desde `Admin` puedes elegir proveedor por separado:

- Vista principal (`/`): `OSM + Leaflet` o `Google Maps`
- Formularios de creación/edición (`/nuevo`, edición de reporte): `OSM + Leaflet` o `Google Maps`

Si `GOOGLE_MAPS_API_KEY` no está configurada, el sistema usa `Leaflet` como fallback.

## Nota

Los reportes se muestran como anonimos por defecto y pueden pasar por moderacion segun la configuracion.

## Capa de conectividad (Cloudflare Radar)

Variables necesarias en `.env`:

```bash
CF_API_TOKEN=tu_token
GEOJSON_PROVINCES_PATH=/ruta/absoluta/o/relativa/al/repo/data/geo/cuba_provinces.geojson
# opcional si tu archivo usa otra propiedad para nombre de provincia (ej. shapeName)
GEOJSON_PROVINCE_KEYS=province,provincia,name,shapeName
CLOUDFLARE_RADAR_HTTP_TIMESERIES_URL=https://api.cloudflare.com/client/v4/radar/http/timeseries?name=main&name=previous&geoId=3556965&geoId=3556965&dateRange=1d&dateRange=1dControl
CONNECTIVITY_FETCH_DELAY_SECONDS=120
CONNECTIVITY_FETCH_TIMEOUT_SECONDS=30
CONNECTIVITY_STALE_AFTER_HOURS=8
CONNECTIVITY_FRONTEND_REFRESH_SECONDS=300
```

Ejecutar ingesta manual:

```bash
python -m scripts.fetch_connectivity
```

Cron recomendado (UTC, cada 2 horas):

```cron
CRON_TZ=UTC
0 */2 * * * cd /ruta/soscubamap && /ruta/.venv/bin/python -m scripts.fetch_connectivity >> /var/log/soscubamap-connectivity.log 2>&1
```

En el mapa, la capa `Conectividad` permite alternar ventana de análisis (`24h`, `6h`, `2h`) para recalcular colores por provincia usando snapshots recientes.

Debug (solo admin autenticado):

```bash
curl -s http://127.0.0.1:8000/api/connectivity/debug
curl -s "http://127.0.0.1:8000/api/connectivity/debug?probe=1"
```
