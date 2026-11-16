---
name: cad-entrega
description: Arma y publica los entregables de /cuantificacad - Excel para NeoData con logo y colores Objetiva, DXF en 7z por volúmenes y reporte de revisión - en la carpeta CR PLANOS del proyecto en Drive.
---

# cad-entrega

1. **Logo:** buscar "Logo Objetiva" en Drive (imagen PNG) y descargarlo a `logo.png`.
2. **Excel:**
   ```bash
   python3 -I scripts/excel.py cantidades.json references/estandar_capas.csv logo.png "entrega/AAAA-MM-DD <PROY> CUANTIFICACION NEODATA.xlsx"
   ```
   - Para la hoja "CAPAS EN DXF", generar antes `capas_dxf.json` junto a `cantidades.json`: una lista de [prefijo, capa_base, nivel, unidad, medible, color, entidades] leída del DXF federado.
   - Hojas: LEEME, NEODATA, RESUMEN, GENERADOR, BITACORA, CAPAS, CAPAS EN DXF.
   - Letra Poppins; azul #002C63, verde #02B381 y grises.
3. **DXF:**
   ```bash
   7z a -t7z -mx=9 -v3000k "subir/AAAA-MM-DD <PROY> FEDERADO LIBRECAD.7z" <PROY>_FEDERADO.dxf
   ```
   - Luego `7z t` sobre la parte .001.
   - Las partes de 3 MB caben en el límite de subida (unos 3.1 MB por archivo).
4. **Drive:**
   - Crear `CR PLANOS/02 CONSOLIDADO LIBRECAD`.
   - Subir con `create_file`, `base64Content: "sha256:<hash>:<ruta absoluta>"` y `disableConversionToGoogleType: true`.
   - Antes de subir muchas partes (cada una requiere aprobación), preguntar al usuario.
   - Nunca sobrescribir: una versión anterior se renombra con "(version previa)"; no se borra.
5. **Entrega al usuario:** mandar el Excel con SendUserFile y dar las ligas.
   - Nombres de archivo: `AAAA-MM-DD HHMMSS Proyecto Tema`, hora de Guadalajara.
