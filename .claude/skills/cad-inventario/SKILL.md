---
name: cad-inventario
description: Recorre una carpeta de Google Drive de un proyecto de construcción y arma el inventario completo de DWG, RVT, PDF y XLSX, eligiendo la versión más reciente de cada lámina por disciplina. Parte de /cuantificacad; también sirve sola para "qué planos son los vigentes".
---

# cad-inventario (solo lectura en Drive)

1. Cargar `mcp__Google_Drive__search_files`.
2. Recorrer el árbol completo:
   - BFS con `parentId = 'a' or parentId = 'b' …`, hasta unos 25 padres por consulta;
   - `excludeContentSnippets: true`, `pageSize: 200`, y seguir `nextPageToken`;
   - los resultados grandes se guardan en un archivo: procesarlos con `jq`.
   - No entrar a Renders ni Moodboards.
3. Escribir `inventario.tsv` (full_path, title, id, mimeType, fileSize, modifiedTime) y `carpetas.tsv`.
4. Elegir la última versión por disciplina con las reglas de `cuantificacad/SKILL.md`:
   - la fecha de la carpeta o del nombre manda;
   - fuera las rutas con ARCHIVO, ANTERIORES u OBSOLETO;
   - fuera los archivos de otro proyecto;
   - las láminas que falten en el juego nuevo se toman de su última versión anterior.
5. Escribir `seleccion.tsv` (disciplina, id, title, size, path).
   - La disciplina usa nombres de carpeta numerados: "00 TOPOGRAFIA", "01 CIVIL", "02 ARQUITECTURA", "03 ESTRUCTURA", "05.1 HIDRAULICA", "05.2 SANITARIA", "05.3 PLUVIAL", "05.4 ELECTRICA Y ESPECIALES", "05.5 GAS", "05.6 PCI", "05.7 HVAC", "06 ACABADOS", "09 VIDRIO Y ALUMINIO", "10 HERRERIA", "11 CARPINTERIA". Agregar las que falten.
6. Reportar en tabla, por disciplina:
   - carpeta elegida y su fecha;
   - número de láminas;
   - versiones anteriores descartadas;
   - archivos de más de 10 MB, que no se podrán descargar desde la sesión.
