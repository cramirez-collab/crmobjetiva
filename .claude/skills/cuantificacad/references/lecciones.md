# Lecciones del piloto (Nashira, 16-nov-2026)

Cada punto es un error real que la revisión independiente encontró y que el script ya corrige. No quitar estas reglas.

## Lectura y unidades
- Los DWG de Revit 2018+ (AC1032) se leen con `@mlightcad/libredwg-web` (`dwg_write_dxf`). No hace falta AutoCAD ni ODA.
- Eléctrica y HVAC pueden venir en **milímetros** (`$INSUNITS = 4`): se escala a metros antes de todo.
- Revit exporta todo en **líneas sueltas**, no polilíneas. Para medir hay que reconstruir:
  - áreas y piezas: contorno de los achurados (HATCH) de cada categoría;
  - longitudes: unir líneas, arcos y **splines** (el eje de algunas tuberías eléctricas viene en SPLINE).

## Alineación
- Cada lámina trae su propio origen. Se alinea por la **retícula**, con estas reglas:
  - Se empata por **espaciamiento entre ejes** (tolerancia 3 cm), no por el nombre del eje: arquitectura y las ingenierías nombran algunos ejes distinto que estructura.
  - Los ejes punteados vienen en segmentos: se unen, y se cortan si hay un hueco mayor a 1.5 m (dos plantas en la misma lámina).
  - Una lámina puede traer 2 plantas; cada una es un componente de ejes que se cruzan.
  - El nivel de cada planta sale del **nombre de vista de Revit** que trae cada bloque ("...-PLANTA NIVEL 3"). El punto de inserción NO sirve: muchos bloques se insertan lejos de su planta.
- "NIVEL 0" es un nivel propio (N00). No mezclarlo con N01.
- Las láminas tipo ("NIVEL 2 - 7", "N3 Y N4") se copian a **cada nivel** que cubren.
- Las láminas sin retícula reconocible (departamentos tipo, isométricos, detalles) quedan solo en la zona de LÁMINAS y se reportan en la bitácora.

## Medición
- Tubería a doble línea: el par paralelo (separación ≤ 0.25 m, Hausdorff ≤ 0.3 m) va a la capa `-PAR` (no medible).
- **Emparejar ANTES de disolver traslapes.** Disolver primero rompe los pares y cuenta las dos paredes (+15 %).
- Los traslapes colineales del eje se disuelven con precisión de 5 mm (`set_precision 0.005`).
- Si una capa `X-ML` tiene hermana `X-CNTR-ML` en el mismo nivel:
  - si sus líneas están a más de 5 cm del eje, son **bordes** (charola) → capa `-BORDE`;
  - si están encima del eje, son **fragmentos** → capa `-SEGMENTOS`.
  - Ninguna de las dos se suma.
- Bloques duplicados: solo si son del mismo tipo, mismo tamaño y escala, y están a 25 cm o menos. Ojo: sin el criterio de tamaño se borraron rellenos de gabinete de 10 cm.
- Los bloques vacíos (sin geometría) no son piezas.
- Puertas, ventanas, muebles y sanitarios se cuentan **solo desde arquitectura**. Si se cuentan desde las láminas de áreas o de carpintería, se duplican.
- Las láminas de áreas (G-) no aportan piezas.
- Los fondos vinculados de Revit (bloques `*_rvt-*`) y los patrones de relleno (`FP_*`) no se federan: pesan cientos de MB y se repiten en cada ingeniería.

## Límites conocidos (documentar, no son errores)
- Losas y pisos: sin contorno cerrado no se mide su área. Usar el modelo Revit (cuantificaobjetiva).
- Los conteos por etiqueta (C-1, T-12) son referencia, no se cobran.
- Los diámetros de tubería no vienen separados en capas; se reporta la longitud por sistema.

## Entrega
- La herramienta de Drive de esta sesión: descarga hasta 10 MB y sube hasta unos 3.1 MB por archivo.
  - El DXF federado se entrega en 7z por volúmenes de 3,000 KB (`7z a -t7z -mx=9 -v3000k`).
  - Los DWG de más de 10 MB no bajan: pedírselos al usuario.
- Archivos de más de unos 250 MB no caben bien en LibreCAD. Por eso se separa así:
  - **FEDERADO**: un archivo con todo, por nivel;
  - **LÁMINAS**: un archivo por disciplina.
- Validar siempre con `librecad dxf2pdf -a` (QT_QPA_PLATFORM=offscreen).
