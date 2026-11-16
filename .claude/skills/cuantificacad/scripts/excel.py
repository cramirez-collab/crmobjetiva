import csv, json, re, sys, unicodedata
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

QJSON, CAPAS, LOGO, OUT = sys.argv[1:5]
data = json.load(open(QJSON))
PROY = data.get('proyecto') or 'Proyecto'
FECHA = data.get('fecha') or ''
AZUL, VERDE, GRIS, GRIS2, GRISC = '002C63', '02B381', '4A4A4A', '9E9E9E', 'E5E5E5'
F = 'Poppins'
ESPEC = {'01CIV': 'Civil / preliminares', '02TOP': 'Topografía', '04CIM': 'Cimentación', '05EST': 'Estructura de concreto',
         '07ALB': 'Albañilería', '08ARQ': 'Arquitectura', '09PIS': 'Acabados de piso', '09ACB': 'Acabados',
         '11PLA': 'Plafones', '13CAR': 'Carpintería', '14HER': 'Herrería', '15VID': 'Vidrio y aluminio',
         '16HID': 'Instalación hidráulica', '17SAN': 'Instalación sanitaria', '18PLU': 'Instalación pluvial',
         '19GAS': 'Instalación de gas', '20PCI': 'Protección contra incendio', '21ELE': 'Instalación eléctrica',
         '22HVA': 'HVAC y extracción', '23ESP': 'Instalaciones especiales', '25MUE': 'Muebles y equipos'}
ORDEN = ['CIM', 'ROD', 'CIS', 'S05', 'S04', 'S03', 'S02', 'S01', 'N01', 'N02', 'N02A'] + \
        [f'N{i:02d}' for i in range(3, 25)] + ['AZ', 'SOB']


def strip(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()


# niveles tipo: lámina "NIVEL 2 - 7", "N3 Y N4", "NIVEL 9 - 10"
tipo = {}  # las láminas tipo ya se copian a cada nivel en el DXF; sin factor
for b in []:
    t = strip(b.get('archivo', ''))
    m = re.search(r'NIVEL\s*(\d{1,2})\s*-\s*(\d{1,2})\b', t) or re.search(r'\bN(\d{1,2})\s*Y\s*N(\d{1,2})\b', t)
    if m and 'DEPTO' not in t:
        a, z = int(m.group(1)), int(m.group(2))
        if z > a: tipo[b.get('codigo')] = (z - a + 1, f'N{a:02d} a N{z:02d}')

agg = defaultdict(lambda: dict(piezas=0, area=0.0, lon=0.0, laminas=set()))
for r in data['cantidades']:
    k = (r['capa'], r['nivel'], r['tipo'])
    a = agg[k]
    a['piezas'] += r['piezas'] or 0
    a['area'] += r['area_m2'] or 0
    a['lon'] += r['longitud_m'] or 0
    a['laminas'].add(r['lamina'])

filas = []
for (capa, nivel, tp), a in agg.items():
    pref = capa[:5]
    elem = capa[6:]
    unidad = 'ML' if capa.endswith('-ML') else 'M2' if capa.endswith('-M2') else 'PZA'
    fac, rango = 1, ''
    for l in a['laminas']:
        if l in tipo: fac, rango = tipo[l]
    def add(u, cant, desc):
        clave = f'NSH-{pref}-{re.sub(r"-(M2|ML|PZA)$", "", elem)}-{nivel}'
        if tp.startswith(('BLOQUE', 'ETIQUETA')):
            clave += '-' + re.sub(r'[^A-Z0-9]+', '', strip(tp.split(' ', 1)[1]))[:16]
        filas.append(dict(esp=ESPEC.get(pref, pref), pref=pref, nivel=nivel, clave=clave, desc=desc, unidad=u,
                          cant=round(cant, 2), fac=fac, total=round(cant * fac, 2), rango=rango, capa=f'{capa}_{nivel}',
                          laminas=', '.join(sorted(a['laminas'])), ref=tp.startswith('ETIQUETA')))
    nombre = elem.replace('-', ' ').lower()
    if tp == 'POLILINEAS':
        if unidad == 'ML' or a['lon'] > 0:
            add('ML', a['lon'], f'{ESPEC.get(pref, pref)}: {nombre} (longitud de polilíneas)')
        if a['area'] > 0:
            add('M2', a['area'], f'{ESPEC.get(pref, pref)}: {nombre} (área de polilíneas cerradas)')
        if unidad == 'PZA':
            add('PZA', a['piezas'], f'{ESPEC.get(pref, pref)}: {nombre} (piezas = polilíneas cerradas)')
    else:
        add('PZA', a['piezas'], f'{ESPEC.get(pref, pref)}: {nombre} - {tp.split(" ", 1)[1].lower()}'
            + (' (conteo de etiquetas, referencia)' if tp.startswith('ETIQUETA') else ''))
filas = [f for f in filas if f['cant'] > 0]
filas.sort(key=lambda f: (f['pref'], ORDEN.index(f['nivel']) if f['nivel'] in ORDEN else 99, f['clave']))

wb = Workbook()
thin = Side(style='thin', color=GRISC)


def hoja(ws, titulo, cols, rows, widths):
    ws.sheet_view.showGridLines = False
    img = Image(LOGO); img.width, img.height = 240, 52; ws.add_image(img, 'A1')
    ws['A4'] = titulo; ws['A4'].font = Font(name=F, size=14, bold=True, color=AZUL)
    ws['A5'] = f'Proyecto {PROY} | Fuente: últimas versiones DWG (copias en CR PLANOS) | {FECHA}'
    ws['A5'].font = Font(name=F, size=9, color=GRIS2)
    for j, c in enumerate(cols, 1):
        cell = ws.cell(row=7, column=j, value=c)
        cell.font = Font(name=F, bold=True, color='FFFFFF', size=10)
        cell.fill = PatternFill('solid', fgColor=AZUL)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for i, r in enumerate(rows, 8):
        for j, v in enumerate(r, 1):
            cell = ws.cell(row=i, column=j, value=v)
            cell.font = Font(name=F, size=9, color=GRIS)
            cell.border = Border(bottom=thin)
            if isinstance(v, float): cell.number_format = '#,##0.00'
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = 'A8'
    ws.auto_filter.ref = f'A7:{get_column_letter(len(cols))}{7 + len(rows)}'
    ws.row_dimensions[7].height = 30


ws = wb.active; ws.title = 'NEODATA'
hoja(ws, 'Cuantificación por especialidad y nivel (formato de importación NeoData)',
     ['Partida', 'Nivel', 'Clave', 'Descripción', 'Unidad', 'Cantidad por planta', 'Factor niveles tipo',
      'Cantidad total', 'Niveles tipo', 'Capa en DXF (LibreCAD)', 'Láminas fuente', 'Tipo de dato'],
     [[f['esp'], f['nivel'], f['clave'], f['desc'], f['unidad'], float(f['cant']), f['fac'], float(f['total']),
       f['rango'], f['capa'], f['laminas'], 'Referencia (etiquetas)' if f['ref'] else 'Medido en DXF'] for f in filas],
     [24, 7, 34, 60, 7, 13, 10, 13, 13, 34, 26, 18])
for i in range(8, 8 + len(filas)):
    ws.cell(row=i, column=8).font = Font(name=F, size=9, bold=True, color=VERDE)

# resumen por especialidad
res = defaultdict(lambda: defaultdict(float))
for f in filas:
    if not f['ref']: res[f['esp']][f['unidad']] += f['total']
ws2 = wb.create_sheet('RESUMEN')
hoja(ws2, 'Resumen por especialidad (solo medido, con niveles tipo)', ['Especialidad', 'M2', 'ML', 'PZA'],
     [[k, round(v.get('M2', 0), 2), round(v.get('ML', 0), 2), round(v.get('PZA', 0), 2)] for k, v in sorted(res.items())],
     [32, 14, 14, 14])

ws3 = wb.create_sheet('GENERADOR')
hoja(ws3, 'Generador por lámina (detalle sin agrupar)',
     ['Nivel', 'Lámina', 'Disciplina', 'Capa', 'Tipo', 'Piezas', 'Área m2', 'Longitud m'],
     [[r['nivel'], r['lamina'], r['disciplina'], r['capa'], r['tipo'], r['piezas'], r['area_m2'], r['longitud_m']]
      for r in data['cantidades']], [7, 14, 24, 34, 40, 9, 11, 11])

ws4 = wb.create_sheet('BITACORA')
hoja(ws4, 'Bitácora de procesamiento por plano', ['Disciplina', 'Código', 'Archivo', 'Estado', 'mm→m', 'Plantas detectadas',
                                                 'Entidades', 'Arreglos DXF'],
     [[b.get('disciplina'), b.get('codigo'), b.get('archivo'), b.get('estado'), 'sí' if b.get('mm_a_m') else '',
       b.get('planos_detectados'), b.get('entidades'), b.get('arreglos_dxf')] for b in data['bitacora']],
     [24, 12, 60, 70, 7, 10, 10, 10])

ws5 = wb.create_sheet('CAPAS')
rows = list(csv.reader(open(CAPAS)))
hoja(ws5, 'Estándar objetivo de capas (referencia de diseño). Las capas reales están en la hoja CAPAS EN DXF', rows[0], rows[1:],
     [5, 26, 8, 30, 34, 24, 10, 26, 8])

import os
cj = os.path.join(os.path.dirname(QJSON) or '.', 'capas_dxf.json')
if os.path.exists(cj):
    rr = sorted(json.load(open(cj)), key=lambda r: (r[1], ORDEN.index(r[2]) if r[2] in ORDEN else 99))
    ws7 = wb.create_sheet('CAPAS EN DXF')
    hoja(ws7, 'Capas reales del DXF federado (filtrar por nivel o especialidad en LibreCAD)',
         ['Prefijo', 'Capa base', 'Nivel', 'Unidad', 'Medible', 'Color ACI', 'Entidades'], rr, [9, 40, 8, 8, 9, 10, 11])
ws6 = wb.create_sheet('LEEME')
texto = [
    'CÓMO USAR EL DXF EN LIBRECAD',
    '1. Abrir <PROYECTO>_FEDERADO.dxf (todas las disciplinas por nivel). Las láminas separadas están en <PROYECTO>_LAMINAS_<disciplina>.dxf.',
    '2. Zona FEDERADO (y > 0): cada nivel en su columna; origen = cruce de los ejes mínimos de la retícula de referencia; disciplinas encimadas.',
    '3. Zona LAMINAS (abajo, y < 0): cada plano completo y separado, con su título.',
    '4. Capas: PREFIJO-ELEMENTO[-UNIDAD]_NIVEL. Ej. 05EST-COLUMNA-PZA_N05, 18PLU-PIPE-ML_N08.',
    '   - Filtrar en la Lista de capas por "_N05" muestra un nivel; por "17SAN" una especialidad; por "-M2", "-ML", "-PZA" lo medible.',
    '   - Ojo (lápiz) prende/apaga; candado bloquea. Capas *-FONDO = fondo arquitectónico/estructural de cada ingeniería.',
    '5. Medir: seleccionar polilíneas de una capa medible y usar Info > Área / Longitud total.',
    '6. Las capas -M2 son polilíneas cerradas reconstruidas de los achurados de Revit; -ML son tuberías/canalizaciones unidas.',
    '7. LibreCAD no guarda DWG: para DWG, abrir el DXF en AutoCAD/ODA y Guardar como DWG.',
    '',
    'LÍMITES (lo que no está medido)',
    '- Tuberías: longitud total por capa/sistema y nivel; el diámetro no viene separado en capas (Revit lo pone en etiquetas).',
    '- Losas y trabes: sólo las zonas que Revit achuró; losa total por nivel requiere el modelo Revit (cuantificaobjetiva).',
    '- Conteos "Referencia (etiquetas)" cuentan etiquetas de vista, no elementos; usar para validar, no para cobrar.',
    '- Láminas sin retícula A-F/1-6 o sin nivel (detalles, isométricos, departamentos tipo) sólo están en zona LAMINAS.',
    '- Charola S01: se mide sólo el eje (23ESP-CABL-TRAY-CNTR). Los bordes están en capa -BORDE y NO se suman.',
    '- Accesorios eléctricos sin geometría (cajas, tapas, interruptores) no se cuentan como pieza.',
    '- Observaciones específicas del proyecto: ver la revisión independiente (archivo REVISION INDEPENDIENTE).',
    '- NeoData: la hoja NEODATA tiene Clave, Descripción, Unidad, Cantidad. Importación directa desde DWG en NeoData: sin verificar.',
]
ws6.sheet_view.showGridLines = False
img = Image(LOGO); img.width, img.height = 240, 52; ws6.add_image(img, 'A1')
for i, t in enumerate(texto, 4):
    c = ws6.cell(row=i, column=1, value=t)
    c.font = Font(name=F, size=11 if t.isupper() else 10, bold=t.isupper(), color=AZUL if t.isupper() else GRIS)
ws6.column_dimensions['A'].width = 130
wb.move_sheet('LEEME', offset=-(len(wb.sheetnames) - 1))
wb.save(OUT)
print('filas', len(filas), 'tipo', tipo)
