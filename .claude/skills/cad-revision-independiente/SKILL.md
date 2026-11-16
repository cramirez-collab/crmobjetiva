---
name: cad-revision-independiente
description: Segunda revisión independiente de cantidades sacadas de un DXF federado (áreas, longitudes, piezas por capa y nivel). Escribe su propio código, sin leer el del productor, y da veredicto APTO / APTO CON OBSERVACIONES / NO APTO. Parte de /cuantificacad; regla de Carlos: toda cifra con segunda revisión.
---

# cad-revision-independiente

**Prohibido** leer `.claude/skills/cuantificacad/scripts/` o cualquier script del productor. El código va en `rev<N>/`, y se pueden reusar las rondas anteriores del propio revisor.

## Checklist (cada ronda completa)
1. **Aritmética:**
   - por (capa, nivel): polilíneas cerradas (piezas y área por fórmula de Gauss) y abiertas (longitud);
   - INSERT por tipo en capas `-PZA`, excluyendo bloques vacíos;
   - comparar contra `cantidades.json`: tolerancia 0.5 % o 1 unidad.
2. **Geometría sin medir:**
   - LINE, ARC o SPLINE que queden en capas `-ML`;
   - `-ML` + `-PAR` ≈ total crudo;
   - `-PAR` siempre con gemela a 0.3 m o menos (muestrear 10).
3. **Duplicados y traslapes:**
   - polilíneas y bloques idénticos o cercanos (menos de 0.15–0.25 m, mismo tipo y tamaño);
   - traslape colineal en `-ML`.
4. **Bordes contra eje:** capas `X-ML` con hermana `X-CNTR-ML`. ¿Son orillas (±0.15 m) o fragmentos encima del eje? ¿El eje está medido?
5. **Verosimilitud:**
   - área por capa menor que la planta;
   - columnas, puertas, muebles y sanitarios consistentes entre niveles tipo;
   - longitudes de 0 o de más de 3,000 m por capa y nivel;
   - niveles que faltan;
   - láminas tipo copiadas a todos sus niveles.
6. **Muestreo manual:** 3 partidas contra la geometría.

## Salida
- `revision_independiente_<N>.md` en español:
  - tabla con partida, productor, revisor, diferencia y OK / OBSERVACIÓN / ERROR;
  - lista de observaciones para el cliente;
  - última línea con el veredicto.
- No inventar números: lo no revisado es "sin verificar".
- Se itera hasta que no quede ningún ERROR. Los límites documentados (losas sin contorno, láminas sin retícula) son OBSERVACIÓN.
