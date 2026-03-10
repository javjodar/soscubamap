# Runbook de despliegue y operaciones

## Prerrequisitos

- Python 3.12+
- PostgreSQL 16+
- (Opcional) Docker y Docker Compose
- Acceso SSH al servidor (para baremetal)
- Cuenta de Cloudinary (para subida de imágenes)

## Despliegue con Docker Compose (recomendado)

### Primera vez

```bash
cp .env.example .env
# Editar .env (ver docs/ENV.md)
docker compose up --build -d
```

El `entrypoint.sh` se encarga automáticamente de:
1. Esperar a que PostgreSQL esté listo
2. Ejecutar migraciones (`flask db upgrade heads`)
3. Sembrar roles y categorías
4. Iniciar Gunicorn en el puerto 8000

### Verificar que está corriendo

```bash
docker compose ps
curl http://localhost:8000/api/health
# Debe devolver: {"status": "ok"}
```

### Ver logs

```bash
docker compose logs -f web
docker compose logs -f db
```

### Actualizar a nueva versión

```bash
git pull
docker compose up --build -d
```

Las migraciones se ejecutan automáticamente al iniciar el contenedor.

### Parar

```bash
docker compose down          # Parar servicios (datos persisten en volumen)
docker compose down -v       # Parar y eliminar volumen de datos (DESTRUCTIVO)
```

## Despliegue baremetal (systemd)

### Configuración inicial

```bash
# Como root o con sudo
useradd -m -s /bin/bash soscuba
su - soscuba

git clone <repo-url> /home/soscuba/soscubamap
cd /home/soscuba/soscubamap
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env
```

### Crear base de datos

```bash
sudo -u postgres createdb soscubamap
# O ajustar DATABASE_URL si usas otro usuario/host
```

### Migraciones y datos iniciales

```bash
source .venv/bin/activate
flask --app run.py db upgrade
python -m scripts.seed_roles
python -m scripts.seed_categories
```

### Servicio systemd

Crear `/etc/systemd/system/soscuba.service`:

```ini
[Unit]
Description=SOSCuba Map
After=network.target postgresql.service

[Service]
User=soscuba
WorkingDirectory=/home/soscuba/soscubamap
EnvironmentFile=/home/soscuba/soscubamap/.env
ExecStart=/home/soscuba/soscubamap/.venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 120 "run:app"
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable soscuba
sudo systemctl start soscuba
```

### Actualizar (script incluido)

```bash
sudo bash deploy.sh
```

El script `deploy.sh` hace: `git pull` → `flask db upgrade` → `systemctl restart soscuba`.

## Migraciones

### Aplicar migraciones pendientes

```bash
flask --app run.py db upgrade
```

### Crear nueva migración

```bash
flask --app run.py db migrate -m "descripción del cambio"
# Revisar el archivo generado en migrations/versions/
flask --app run.py db upgrade
```

### Revertir última migración

```bash
flask --app run.py db downgrade -1
```

### Ver estado

```bash
flask --app run.py db current
flask --app run.py db history
```

## Scripts de datos

| Script                          | Función                                       |
|---------------------------------|-----------------------------------------------|
| `python -m scripts.seed_roles`         | Crear roles: colaborador, moderador, administrador |
| `python -m scripts.seed_categories`    | Crear categorías de reportes                  |
| `python -m scripts.seed_discussion_tags` | Crear tags de discusión                     |
| `python -m scripts.backfill_locations` | Rellenar provincia/municipio en posts existentes |
| `python -m scripts.reverse_geocode_posts` | Geocodificación inversa de posts           |

## Self-hosted maps

Para servir tiles OSM localmente, usar el compose adicional:

```bash
docker compose -f docker-compose.maps.yml up -d
```

Ver [`README.maps-selfhosted.es.md`](../README.maps-selfhosted.es.md) para el proceso completo de importación de datos OSM.

## Monitoreo

### Health check

```bash
curl http://localhost:8000/api/health
```

### Logs (systemd)

```bash
sudo journalctl -u soscuba -f
```

### Logs (Docker)

```bash
docker compose logs -f web
```

### Base de datos

```bash
# Verificar conexión
docker compose exec db pg_isready -U postgres

# Conectar a psql
docker compose exec db psql -U postgres -d soscubamap
```

## Problemas comunes

### La app no arranca: "DB not ready"

El entrypoint espera a que PostgreSQL esté listo. Si falla repetidamente, verificar que el servicio de base de datos está corriendo y que `DATABASE_URL` es correcto.

### Migraciones fallan

Si una migración falla, revisar el estado actual con `flask db current` y comparar con los archivos en `migrations/versions/`. Si hay conflictos, puede ser necesario revertir con `flask db downgrade` y volver a aplicar.

### Rate limiting no funciona con múltiples workers

Por defecto, Flask-Limiter usa almacenamiento en memoria, que no se comparte entre workers de Gunicorn. Para producción, configurar `RATELIMIT_STORAGE_URL=redis://localhost:6379/0`.

### Imágenes no se suben

Verificar que las variables `CLOUDINARY_*` están configuradas correctamente. Sin Cloudinary, la subida de imágenes no funciona.

## Rollback

### Rollback de código

```bash
git log --oneline -5          # Identificar commit anterior
git checkout <commit-hash>
# Docker: docker compose up --build -d
# Systemd: sudo systemctl restart soscuba
```

### Rollback de migración

```bash
flask --app run.py db downgrade -1
# Repetir según cuántas migraciones revertir
```

### Rollback de un reporte editado

La app guarda `PostRevision` antes de cada edición. Los administradores pueden restaurar versiones anteriores desde la interfaz web en el historial del reporte (`/admin/reportes/<id>/revisiones/<rev_id>/restaurar`).
