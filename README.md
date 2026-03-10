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

## Tests

El proyecto incluye una suite de tests unitarios con pytest.

```bash
# Ejecutar todos los tests
pytest

# Con reporte de coverage
pytest tests/unit/ -v --cov=app/services --cov-report=term-missing
```

## Roles

- colaborador: cuenta estandar
- moderador: revisa reportes
- administrador: gestiona usuarios y ajustes

## Nota

Los reportes se muestran como anonimos por defecto y pueden pasar por moderacion segun la configuracion.
