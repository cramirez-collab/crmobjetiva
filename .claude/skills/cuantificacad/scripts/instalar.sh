#!/bin/bash
# Instala lo necesario para cuantificacad (Linux / sesión en la nube). Uso: bash instalar.sh
set -e
cd "$(dirname "$0")"
npm install --silent                       # lector DWG -> DXF (LibreDWG en WebAssembly)
pip install -q ezdxf shapely openpyxl matplotlib pillow
command -v 7z >/dev/null || apt-get install -y -q p7zip-full >/dev/null
command -v librecad >/dev/null || apt-get install -y -q librecad >/dev/null   # validación con dxf2pdf
echo "cuantificacad listo"
