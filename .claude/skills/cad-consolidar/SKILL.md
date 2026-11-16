---
name: cad-consolidar
description: Convierte DWG de Revit/AutoCAD a DXF y los consolida en un DXF federado para LibreCAD, con capas ESPECIALIDAD-ELEMENTO-UNIDAD_NIVEL, alineado por retícula, con polilíneas medibles y cantidades. Parte de /cuantificacad.
---

# cad-consolidar

Scripts en `.claude/skills/cuantificacad/scripts/`. Antes de tocar nada, leer `references/lecciones.md`.

## 1. DWG → DXF
`node scripts/dwg2dxf.mjs a.dwg a.dxf b.dwg b.dxf …`, desde la carpeta `scripts/`, después de `npm install`.
- Convertir por disciplina: `dwg/<disc>/*.dwg` → `dxf/<disc>/*.dxf`.
- Debe salir "OK" en todos.

## 2. Federado (todas las disciplinas, por nivel)
```bash
python3 -I scripts/consolidar.py dxf/ entrega/<PROY>_FEDERADO.dxf cantidades.json solo_federado config.json
```
- **Pasada 1:** retícula de referencia desde las plantas de `config.referencia`. Se imprime `RETICULA X/Y`; revisar que tenga los ejes esperados.
- **Bitácora por lámina:** `FEDERADO Nxx (ejes n, dif 0 mm)` o `solo LAMINAS: motivo`.
  - Si una dif es mayor a 50 mm hay un error de alineación: detenerse y revisar.
- **Al final** se ve "duplicados eliminados" y "capas no medibles por eje hermano".
- **Memoria:** el federado de unas 320 láminas usa unos 6 GB. NO correr el modo completo (federado + láminas) en un solo proceso: se cae por memoria.

## 3. Láminas separadas (una por disciplina)
Para cada disciplina: carpeta `lam/<disc>/<disc>` (symlink a `dxf/<disc>`), y luego
`python3 -I scripts/consolidar.py lam/<disc> entrega/<PROY>_LAMINAS_<disc>.dxf lam_<disc>.json solo_laminas config.json`
- Se pueden correr 2 en paralelo con `xargs -P 2`.

## 4. Validación
- `QT_QPA_PLATFORM=offscreen librecad dxf2pdf -a -t <dir> <archivo.dxf>` debe terminar en "DONE".
- Vista rápida de un nivel: `python3 -I scripts/preview.py <dxf> out.png x0 y0 x1 y1`. El nivel i ocupa x ≈ i × slot_m; el slot_m viene en el json.

## 5. Cantidades
- `cantidades.json` sale del DXF final, o sea lo mismo que se mide en LibreCAD.
- No editar números a mano: corregir el script y volver a correr.
