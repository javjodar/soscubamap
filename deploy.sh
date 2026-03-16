#!/usr/bin/env bash
set -euo pipefail

APP_USER="soscuba"
APP_DIR="/home/${APP_USER}/soscubamap"
SERVICE_NAME="soscuba"
FLASK_APP_PATH="${APP_DIR}/run.py"

run_as_app_user() {
  if [[ $EUID -eq 0 ]]; then
    sudo -u "${APP_USER}" "$@"
  else
    "$@"
  fi
}

if [[ ! -d "${APP_DIR}" ]]; then
  echo "No existe el repo en ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -x "${APP_DIR}/.venv/bin/flask" ]]; then
  echo "No existe .venv o Flask no esta instalado en ${APP_DIR}" >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/requirements.txt" ]]; then
  echo "No existe requirements.txt en ${APP_DIR}" >&2
  exit 1
fi

echo "[1/4] Git pull"
run_as_app_user git -C "${APP_DIR}" pull

echo "[2/4] Dependencias"
run_as_app_user "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

echo "[3/4] Migraciones"
run_as_app_user "${APP_DIR}/.venv/bin/flask" --app "${FLASK_APP_PATH}" db upgrade

echo "[4/4] Reinicio de servicio"
if [[ $EUID -eq 0 ]]; then
  systemctl restart "${SERVICE_NAME}"
else
  sudo systemctl restart "${SERVICE_NAME}"
fi

echo "Listo. Logs: sudo journalctl -u ${SERVICE_NAME} -f"
