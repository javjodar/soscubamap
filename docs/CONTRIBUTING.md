# Guía de contribución

Gracias por tu interés en contribuir a SOSCuba Map. Esta guía explica cómo configurar el entorno de desarrollo y enviar cambios.

## Configurar entorno de desarrollo

### 1. Clonar y crear entorno virtual

```bash
git clone <repo-url> && cd soscubamap
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 2. Base de datos local

Opción A — Docker (solo la BD):

```bash
docker run -d --name soscuba-db \
  -e POSTGRES_DB=soscubamap \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16-alpine
```

Opción B — PostgreSQL local:

```bash
createdb soscubamap
```

### 3. Configurar variables

```bash
cp .env.example .env
# Los valores por defecto funcionan para desarrollo local
```

### 4. Inicializar datos

```bash
flask --app run.py db upgrade
python -m scripts.seed_roles
python -m scripts.seed_categories
```

### 5. Ejecutar

```bash
flask --app run.py run
# Abrir http://localhost:5000
```

Para crear un usuario admin, configurar `ADMIN_EMAIL` y `ADMIN_PASSWORD` en `.env` y hacer login.

## Estructura del proyecto

```
soscubamap/
├── app/
│   ├── __init__.py          # create_app(), registro de blueprints
│   ├── extensions.py        # db, migrate, login_manager, limiter
│   ├── blueprints/
│   │   ├── api/             # API REST JSON
│   │   ├── auth/            # Registro y login
│   │   ├── map/             # Dashboard, reportes, mapa
│   │   ├── admin/           # Panel de administración
│   │   ├── moderation/      # Cola de moderación
│   │   ├── discussions/     # Foro de discusiones
│   │   └── panic/           # Botón de pánico
│   ├── models/              # 18 modelos SQLAlchemy
│   ├── services/            # 15 servicios de lógica de negocio
│   ├── templates/           # Templates Jinja2
│   └── static/              # CSS, JS, imágenes
├── config/
│   └── settings.py          # Configuración desde variables de entorno
├── migrations/              # Alembic (Flask-Migrate)
├── scripts/                 # Scripts de seed y mantenimiento
├── docs/                    # Documentación
├── docker-compose.yml
├── Dockerfile
├── deploy.sh
├── entrypoint.sh
├── requirements.txt
└── run.py                   # Punto de entrada
```

## Convenciones de código

### Python

- El proyecto usa Flask y sigue las convenciones estándar de Python.
- Las rutas usan URLs en español (ej: `/registro`, `/moderacion`, `/discusiones`).
- Los mensajes de error y flash también están en español.
- Las funciones privadas se prefijan con `_` (ej: `_get_chat_nick()`).
- Los servicios encapsulan lógica reutilizable. No poner lógica compleja directamente en las rutas.

### Base de datos

- Cada cambio de esquema requiere una migración Alembic.
- Nombrar migraciones descriptivamente: `flask --app run.py db migrate -m "add_rejection_reason_to_post_edit_requests"`.
- Revisar siempre el archivo de migración generado antes de aplicar.

### Templates

- Extender siempre de `shared/base.html`.
- Organizar templates en carpetas por blueprint.

## Flujo de trabajo

### 1. Crear una rama

```bash
git checkout -b feature/mi-cambio
```

### 2. Hacer cambios

- Escribir código siguiendo las convenciones anteriores.
- Si cambias modelos, crear migración.
- Probar manualmente que la funcionalidad funciona.

### 3. Commit

```bash
git add <archivos-específicos>
git commit -m "Descripción clara del cambio"
```

Formato de mensajes de commit:
- Usar español o inglés, pero ser consistente dentro del commit.
- Ser descriptivo: "Agregar validación de longitud mínima en descripción" en vez de "fix bug".

### 4. Pull request

- Describir qué cambia y por qué.
- Incluir pasos para probar el cambio.
- Si hay cambios de BD, mencionar la migración.

## Áreas donde se necesita ayuda

- Tests automatizados (actualmente no hay suite de tests).
- Internacionalización (i18n) para soportar inglés.
- Mejoras de accesibilidad en la interfaz.
- Documentación de las categorías y su significado.
