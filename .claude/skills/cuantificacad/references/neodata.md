# Carga a NeoData

- La hoja **NEODATA** del Excel trae las columnas Partida (especialidad), Nivel, Clave, Descripción, Unidad (M2, ML, PZA), Cantidad y la capa del DXF de donde sale cada cantidad.
- **Clave:** `<PROY>-<PREFIJO>-<ELEMENTO>-<NIVEL>[-TIPO]`. Se puede remplazar por la clave del catálogo del proyecto: S.SAN, H.CPVC, PL.SAN, G.GAL, etc. (en Nashira: "13. Catálogos de conceptos").
- Importación directa desde DWG o capas en NeoData: **sin verificar**. Lo seguro es importar desde Excel (Clave, Descripción, Unidad, Cantidad).
- La columna "Tipo de dato" separa "Medido en DXF" de "Referencia (etiquetas)". Lo de referencia no se carga como cantidad.
