---
name: cuantificacad
description: Junta los planos DWG de un proyecto (arquitectura, estructura, MEP y todas las especialidades) en un DXF federado para LibreCAD, con capas por especialidad, nivel y unidad, y saca la cuantificación lista para NeoData con revisión independiente. Usar cuando pidan "cuantifica los planos", "junta los DWG", "plano federado", "capas para cuantificar", "/cuantificacad" o "@cuantificacad", con una carpeta de Drive de un proyecto.
---

# /cuantificacad

Orquestador. Recibe la carpeta de Drive del proyecto y entrega en `CR PLANOS`:
- copia de los DWG más recientes;
- el DXF federado (LibreCAD) y las láminas por disciplina;
- el Excel para NeoData;
- la revisión independiente.

**Candados (manual de Carlos):**
- Nunca se modifican, mueven ni borran los originales del Drive; solo se trabaja sobre copias.
- Toda cifra pasa por revisión independiente antes de entregarse.
- Lo no comprobado se marca "sin verificar".
- Respuesta en español de México, breve.

## Flujo (en orden; cada paso tiene su agente o skill)

| # | Paso | Quién | Salida |
|---|------|-------|--------|
| 0 | Leer el manual "01 Manual Como trabaja Claude" en Drive | este orquestador | reglas del usuario |
| 1 | Inventario del árbol de Drive y elección de la **última versión por lámina y disciplina** | agente `cad-inventario` (skill `cad-inventario`) | `inventario.tsv`, `seleccion.tsv` |
| 2 | Crear `CR PLANOS/01 DWG ULTIMA VERSION/<disciplina>` y copiar | agente `cad-copiador` | `copias_drive.tsv` |
| 3 | Descargar los DWG seleccionados | agente `cad-descargador` | `dwg/<disciplina>/*.dwg` |
| 4 | Convertir DWG → DXF, consolidar, cuantificar | agente `cad-consolidador` (skill `cad-consolidar`) | `<PROY>_FEDERADO.dxf`, láminas, `cantidades.json` |
| 5 | Revisión independiente, iterar hasta "APTO" o "APTO CON OBSERVACIONES" | agente `cad-revisor` (skill `cad-revision-independiente`) | `revision_independiente.md` |
| 6 | Excel NeoData, 7z por volúmenes, subir a Drive, avisar | skill `cad-entrega` | carpeta `CR PLANOS/02 CONSOLIDADO LIBRECAD` |

- Los pasos 2 y 3 corren en paralelo.
- El paso 5 **nunca** lo hace el mismo agente que produjo los números, y no lee `scripts/`. Si da "NO APTO", se corrige en el paso 4 y se vuelve a revisar.

## Arranque rápido (sesión en la nube)

```bash
bash .claude/skills/cuantificacad/scripts/instalar.sh
cp .claude/skills/cuantificacad/references/config_ejemplo.json $SCRATCH/config.json   # editar "proyecto" y "prefijos"
```

**Estructura de trabajo** (en el scratchpad, nunca en el repo):
- `dwg/<disciplina>/` → `dxf/<disciplina>/`
- `entrega/`
- `subir/`

**Nombres de carpeta de disciplina:** "03 ESTRUCTURA", "05.3 PLUVIAL", etc. El prefijo de capa se toma del config.

## Reglas para elegir la "última versión"
- Manda la fecha de la **carpeta de entrega o del nombre** (20260804, 260820…), no `modifiedTime`. Las carpetas "Apto para construcción" son copias con fecha de copia.
- Se descartan las rutas con ARCHIVO, ANTERIORES u OBSOLETO.
- Si una lámina no viene en el juego más reciente, se toma su última versión anterior y se anota (en Nashira: A-109 de 260226).
- Se excluyen los archivos de **otro proyecto** que aparezcan en la búsqueda (en Nashira aparecieron DWG de "La Fortuna").

## Qué reportar al final (en este orden)
1. Resultado y ligas de Drive.
2. Totales por especialidad (ML, M2, PZA).
3. Lo que **no** quedó: láminas sin retícula, archivos que no bajaron (más de 10 MB), límites.
4. Observaciones de la revisión para arquitectura, estructura e ingenierías.
5. Lo que falta que haga el usuario, numerado.

Las lecciones del piloto están en `references/lecciones.md`: **leer antes de tocar el script**. La carga a NeoData está en `references/neodata.md`.
