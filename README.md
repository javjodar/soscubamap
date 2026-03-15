# #SOSCuba Map

Dashboard colaborativo para documentar y visualizar lugares y acciones represivas en Cuba.

Construido con Flask, PostgreSQL, Leaflet y OpenStreetMap. Los reportes se muestran como anónimos por defecto y pueden pasar por moderación según la configuración.

## Stack

- **Backend:** Python 3.12, Flask 3, SQLAlchemy, Alembic
- **Base de datos:** PostgreSQL 16
- **Mapas:** Leaflet + OpenStreetMap (con soporte para tiles self-hosted)
- **Imágenes:** Cloudinary
- **Push notifications:** Web Push (VAPID)

## Quick start

### 1. Clonar y crear entorno virtual

```bash
git clone <repo-url> && cd soscubamap
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

### 2. Instalar dependencias y configurar

```bash
pip install -r requirements.txt
cp .env.example .env
# Editar .env con tus valores (ver docs/ENV.md para referencia completa)
```

### 3. Base de datos y migraciones

```bash
flask --app run.py db upgrade
```

### 4. Sembrar datos base

```bash
python -m scripts.seed_roles
python -m scripts.seed_categories
```

### 5. Configurar admin (opcional, recomendado)

Editar `.env`:

```
ADMIN_EMAIL=admin@soscuba.local
ADMIN_PASSWORD=tu_password_seguro
```

### 6. Ejecutar la app

```bash
flask --app run.py run
```

La app estará disponible en `http://localhost:5000`.

## Docker Compose (alternativa)

```bash
docker compose up --build -d
```

La app estará en `http://localhost:8000`. Logs: `docker compose logs -f web`. Parar: `docker compose down`.

## Self-hosted maps (opcional)

Para mapas self-hosted con tiles locales, ver [`README.maps-selfhosted.es.md`](README.maps-selfhosted.es.md).

## Tests

El proyecto incluye una suite de tests unitarios con pytest.

```bash
# Ejecutar todos los tests
pytest

# Con reporte de coverage
pytest tests/unit/ -v --cov=app/services --cov-report=term-missing
```

## Roles

- **colaborador:** cuenta estándar, puede crear y editar reportes
- **moderador:** revisa reportes pendientes y solicitudes de edición
- **administrador:** gestiona usuarios, ajustes, donaciones, y tiene acceso completo

## Contribuir

1. Hacer fork del repositorio.
2. Crear una rama para tu cambio: `git checkout -b feature/mi-cambio`.
3. Hacer commit de tus cambios: `git commit -m "Descripción del cambio"`.
4. Push a tu fork: `git push origin feature/mi-cambio`.
5. Abrir un Pull Request contra la rama principal.

Para más detalles sobre el entorno de desarrollo, convenciones de código y estructura del proyecto, ver la [Guía de contribución](docs/CONTRIBUTING.md).

## Documentación

- [Referencia de variables de entorno](docs/ENV.md)
- [Referencia de la API](docs/API.md)
- [Arquitectura del sistema](docs/ARCHITECTURE.md)
- [Runbook de despliegue y operaciones](docs/RUNBOOK.md)
- [Guía de contribución](docs/CONTRIBUTING.md)

## Proveedor de mapas por vista

Desde `Admin` puedes elegir proveedor por separado:

- Vista principal (`/`): `OSM + Leaflet` o `Google Maps`
- Formularios de creación/edición (`/nuevo`, edición de reporte): `OSM + Leaflet` o `Google Maps`

Si `GOOGLE_MAPS_API_KEY` no está configurada, el sistema usa `Leaflet` como fallback.

## Nota

Los reportes se muestran como anónimos por defecto y pueden pasar por moderación según la configuración.

## Licencia

Ver [LICENSE](LICENSE).
