"""cuantificacad · consolidador de planos DWG/DXF de Revit para LibreCAD y cuantificación.

Uso:
  python3 -I consolidar.py <carpeta_dxf> <salida.dxf> <cantidades.json> [solo_federado|solo_laminas] [config.json]

<carpeta_dxf> contiene una subcarpeta por disciplina (p. ej. "03 ESTRUCTURA", "05.3 PLUVIAL") con los .dxf.
Zona FEDERADO (y >= 0): una planta por nivel, alineada a la retícula de la disciplina de referencia
(origen = eje vertical y eje horizontal mínimos), todas las disciplinas encimadas.
Zona LAMINAS (y < 0): cada lámina completa, separada.
Capa = <PREFIJO>-<ELEMENTO>[-M2|-ML|-PZA]_<NIVEL>. Sufijo de unidad = capa medible.
Lecciones integradas (4 rondas de revisión, proyecto piloto Nashira): ver references/lecciones.md
"""
import json, re, sys, unicodedata
from collections import defaultdict, Counter
from pathlib import Path

import ezdxf
from ezdxf import recover, xref, path as ezpath
from ezdxf.math import Matrix44
from shapely.geometry import Polygon, LineString, MultiLineString
from shapely.ops import linemerge

# Retícula de referencia: se calcula en main() desde la disciplina de referencia (config 'referencia')
REFX, REFY = {}, {}
LETRA = re.compile(r'[A-Z]{1,2}')
NUM = re.compile(r'\d{1,2}')

DPREF = {'00 TOPOGRAFIA': '02TOP', '01 CIVIL': '01CIV', '02 ARQUITECTURA': '08ARQ', '03 ESTRUCTURA': '05EST',
         '05.1 HIDRAULICA': '16HID', '05.2 SANITARIA': '17SAN', '05.3 PLUVIAL': '18PLU',
         '05.4 ELECTRICA Y ESPECIALES': '21ELE', '05.5 GAS': '19GAS', '05.6 PCI': '20PCI', '05.7 HVAC': '22HVA',
         '06 ACABADOS': '09ACB', '09 VIDRIO Y ALUMINIO': '15VID', '10 HERRERIA': '14HER', '11 CARPINTERIA': '13CAR'}
COLOR = {'02TOP': 9, '01CIV': 8, '08ARQ': 7, '05EST': 4, '04CIM': 5, '07ALB': 32, '16HID': 170, '17SAN': 30,
         '18PLU': 140, '21ELE': 1, '23ESP': 200, '19GAS': 50, '20PCI': 10, '22HVA': 130, '09ACB': 40, '09PIS': 40,
         '11PLA': 60, '15VID': 150, '14HER': 250, '13CAR': 34, '25MUE': 90, '00GEN': 8}

ANOT = re.compile(r'ANNO|DIMS|COTA|NOTA|TEXTO|ETIQUETA|LLAMADA|SIMB|SYMB|IDEN|TTLB|NPLT|KEYNOTE|REFR|TAG|'
                  r'ANOTACION|LEVL|SECCION|ALZADO|VISTA|REVC|TITULO|BLOQUES DE T', re.I)
GRID = re.compile(r'GRID|REJILLA|^_EJE_', re.I)

# categorías de Revit (español / AIA) -> (capa estándar, disciplinas dueñas)
CAT = [
    (r'^MUROS? CORTINA|MONTANTES|PANELES DE MURO|^A-GLAZ-CWMG', '15VID-CANCEL', {'08ARQ', '15VID'}),
    (r'^MUROS|^A-WALL', '08ARQ-MUROS', {'08ARQ'}),
    (r'BARANDAL|BALAUSTRE|BARANDILLA|^A-FLOR-HRAL', '14HER-BARANDAL', {'08ARQ', '14HER'}),
    (r'^PUERTAS|^A-DOOR', '13CAR-PUERTA-PZA', {'08ARQ'}),
    (r'^VENTANAS|^A-GLAZ', '15VID-VENTANA-PZA', {'08ARQ'}),
    (r'MUEBLES DE OBRA|CASEWORK', '13CAR-MUEBLE-PZA', {'08ARQ'}),
    (r'MOBILIARIO|^A-FURN', '25MUE-MOBILIARIO-PZA', {'08ARQ'}),
    (r'APARATOS SANITARIOS|^P-.*FIXT', '25MUE-SANITARIO-PZA', {'08ARQ'}),
    (r'^TECHOS|PLAFON|^A-CLNG', '11PLA-PLAFON', {'08ARQ', '09ACB'}),
    (r'^SUELOS|^A-FLOR', '08ARQ-PISO', {'08ARQ', '09ACB', '01CIV'}),
    (r'^ESCALERAS|^A-FLOR-STRS', '08ARQ-ESCALERA', {'08ARQ'}),
    (r'^HABITACIONES|^AREAS|^ÁREAS|^A-AREA', '08ARQ-AREAS', {'08ARQ'}),
    (r'^TOPOGRAF|^C-TOPO|CURVA', '02TOP-TERRENO', {'02TOP', '01CIV'}),
]
EST = [  # sólo para láminas estructurales (AIA de Revit)
    (r'^S-COLS-IDEN', '05EST-COLUMNA-ETIQ'), (r'^S-COLS-HDLN', '05EST-COLUMNA-OCULTO'), (r'^S-COLS', '05EST-COLUMNA-PZA'),
    (r'^S-BEAM-IDEN', '05EST-TRABE-ETIQ'), (r'^S-BEAM-HDLN', '05EST-TRABE-OCULTO'), (r'^S-BEAM', '05EST-TRABE-LOSA'),
    (r'^S-(SLAB|FLOR)', '05EST-LOSA-M2'), (r'^S-WALL', '05EST-MURO-M2'), (r'^S-STRS', '05EST-RAMPA-ESC'),
    (r'^S-FNDN', '04CIM-CIMENTACION-M2'), (r'^S-', '05EST-OTROS'), (r'^A-WALL', '07ALB-MURO-M2'),
]
MEP_ML = re.compile(r'PIPE|CNDT|DUCT|TUB|CHAROLA|TRAY|CABLE|CONDUIT|DRAN|SANR|DOMW|STRM|GAS|SPRN|FIRE', re.I)
MEP_PZA = re.compile(r'FIXT|EQPM|EQUIP|DEVC|LITE|LUMIN|DIFF|GRILL|VALV|ACCS|SPRK|HEAD', re.I)


def clean(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]+', '-', s).strip('-')[:28] or 'X'


def std_layer(src, P, codigo=''):
    u = src.upper()
    if codigo.startswith('G-') and P == '08ARQ' and not re.search(r'AREA|ÁREA|HABITACION', u, re.I) and not GRID.search(u):
        return '08ARQ-ANOT' if ANOT.search(u) else '08ARQ-FONDO-AREAS'
    if GRID.search(u) and not ANOT.search(u.replace('GRID-IDEN', '')):
        return f'{P}-EJES'
    if P == '05EST':
        if re.match(r'^S-GRID-IDEN', u): return '05EST-EJES-ETIQ'
        for rx, n in EST:
            if re.search(rx, u): return n
    if re.search(r'DIMS|^COTAS', u): return f'{P}-COTAS'
    if ANOT.search(u): return f'{P}-ANOT'
    if P in ('16HID', '17SAN', '18PLU', '19GAS', '20PCI', '21ELE', '22HVA', '23ESP') and re.match(r'^(P|M|E|F|FP|T|EL)-', u):
        base = f'{P}-' + clean(re.sub(r'^(P|M|E|F|FP|T|EL)-', '', u))
        if MEP_PZA.search(u): return base + '-PZA'
        if MEP_ML.search(u): return base + '-ML'
        return base
    for rx, n, owners in CAT:
        if re.search(rx, u, re.I):
            if P in owners:
                if n == '08ARQ-PISO' and P == '09ACB': return '09PIS-PISO-M2'
                if n == '08ARQ-PISO' and P == '01CIV': return '01CIV-LOSA-M2'
                if n == '08ARQ-AREAS': return '08ARQ-AREAS-M2'
                return n
            break
    return f'{P}-FONDO'

# ---------------------------------------------------------------- niveles
ORDEN = ['CIM', 'ROD', 'CIS', 'S05', 'S04', 'S03', 'S02', 'S01', 'N00', 'N01', 'N02', 'N02A'] + \
        [f'N{i:02d}' for i in range(3, 25)] + ['AZ', 'SOB']


def strip(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()


def nivel_txt(t, plano_requerido=False):
    t = strip(t)
    if plano_requerido and not re.search(r'PLANTA|ESTRUCTURACION DE LOSA|INSTALACION|NIVEL|SOTANO|AZOTEA', t):
        return None
    if re.search(r'DETALLE|ISOMETRIC|CUADRO|CORTE|SECCION|ALZADO|DEPTO|DEPARTAMENTO|CUARTO DE M|ISO-|ISO -|^ISO', t):
        return None
    if 'CIMENTACION' in t: return 'CIM'
    if 'RODAMIENTO' in t: return 'ROD'
    if 'CISTERNA' in t: return 'CIS'
    if 'SOBREPASO' in t: return 'SOB'
    if 'AZOTEA' in t and not re.search(r'NIVEL\s*\d', t): return 'AZ'
    m = re.search(r'SOTANO\s*S?0?(\d)', t)
    if m: return f'S0{m.group(1)}'
    if re.search(r'NIVEL\s*0\b', t): return 'N00'
    if 'PLANTA BAJA' in t: return 'N01'
    m = re.search(r'NIVEL\s+(?:LOSA\s+)?N?(\d{1,2})(A?)\b', t) or re.search(r'\bN(\d{1,2})(A?)\b', t)
    if m: return f'N{int(m.group(1)):02d}{m.group(2)}'
    return None


def codigo_de(titulo):
    t = strip(titulo)
    m = re.search(r'\b((?:EST|IE|ISE|AI|AC|AE|[ACGHVW])-\d{2,4}[A-Z]?)\b', t)
    if m: return m.group(1)
    m = re.search(r'_V2_(\d+)|_(\d{2}) -|PLANO - (\d{2})', t)
    return Path(titulo).stem[:24]

# ---------------------------------------------------------------- geometría


def ref_point(e):
    t = e.dxftype()
    try:
        if t == 'LINE': return e.dxf.start
        if t in ('CIRCLE', 'ARC'): return e.dxf.center
        if t in ('INSERT', 'MTEXT', 'TEXT'): return e.dxf.insert
        if t == 'DIMENSION': return e.dxf.defpoint
        if t in ('LWPOLYLINE',): return next(iter(e.vertices()))
        if t == 'HATCH':
            for p in ezpath.from_hatch(e): return p.start
        if t == 'SPLINE': return e.control_points[0]
    except Exception:
        return None
    return None


def merge_axis(segs):
    """une segmentos colineales (ejes punteados) -> [(coord, min, max)]; corta si hay hueco > 1.5 m"""
    by = defaultdict(list)
    for c, a, b in segs: by[round(c, 3)].append((a, b))
    out = []
    for c, ab in by.items():
        ab.sort()
        ca, cb = ab[0]
        for a, b in ab[1:]:
            if a - cb > 1.5:
                out.append((c, ca, cb)); ca, cb = a, b
            else:
                cb = max(cb, b)
        out.append((c, ca, cb))
    return out


def grid_entities(msp):
    ents = list(msp.query('LINE MTEXT TEXT'))
    if not any(GRID.search(e.dxf.layer) for e in ents):
        for ins in msp.query('INSERT'):
            if 'RVT' in ins.dxf.name.upper():
                try:
                    ents += [v for v in ins.virtual_entities() if v.dxftype() in ('LINE', 'MTEXT', 'TEXT')]
                except Exception:
                    pass
    return ents


def grid_planes(msp):
    """Detecta cada planta (conjunto de ejes etiquetados que se cruzan). Devuelve lista de (X, Y, region)."""
    ents = grid_entities(msp)
    vs, hs = [], []
    for e in ents:
        if e.dxftype() != 'LINE' or not GRID.search(e.dxf.layer) or 'IDEN' in e.dxf.layer.upper(): continue
        s, f = e.dxf.start, e.dxf.end
        if abs(s.x - f.x) < 1e-3 and abs(s.y - f.y) > 0.05: vs.append((s.x, min(s.y, f.y), max(s.y, f.y)))
        elif abs(s.y - f.y) < 1e-3 and abs(s.x - f.x) > 0.05: hs.append((s.y, min(s.x, f.x), max(s.x, f.x)))
    vert = [g for g in merge_axis(vs) if g[2] - g[1] > 3]
    hor = [g for g in merge_axis(hs) if g[2] - g[1] > 3]
    labs = []
    for e in ents:
        if e.dxftype() == 'LINE': continue
        L = e.dxf.layer.upper()
        if not (('GRID' in L and 'IDEN' in L) or L == 'REJILLAS' or L.startswith('REJILLAS')): continue
        t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip().upper()
        labs.append((t, e.dxf.insert))
    X, Y = [], []
    for t, p in labs:
        if LETRA.fullmatch(t):
            c = [g for g in vert if abs(g[0] - p.x) < 1.0 and (abs(p.y - g[1]) < 3 or abs(p.y - g[2]) < 3)]
            if c: X.append((t, min(c, key=lambda g: abs(g[0] - p.x))))
        elif NUM.fullmatch(t):
            c = [g for g in hor if abs(g[0] - p.y) < 1.0 and (abs(p.x - g[1]) < 3 or abs(p.x - g[2]) < 3)]
            if c: Y.append((t, min(c, key=lambda g: abs(g[0] - p.y))))
    X = list({(t, g) for t, g in X}); Y = list({(t, g) for t, g in Y})
    # componentes conexas: eje vertical y horizontal conectados si se cruzan
    nodes = [('X',) + x for x in X] + [('Y',) + y for y in Y]
    par = list(range(len(nodes)))
    def find(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i, a in enumerate(nodes):
        if a[0] != 'X': continue
        for j, b in enumerate(nodes):
            if b[0] != 'Y': continue
            gx, gy = a[2], b[2]
            if gy[1] - 0.5 <= gx[0] <= gy[2] + 0.5 and gx[1] - 0.5 <= gy[0] <= gx[2] + 0.5:
                par[find(i)] = find(j)
    comp = defaultdict(list)
    for i, n in enumerate(nodes): comp[find(i)].append(n)
    planos = []
    for c in comp.values():
        Xd, Yd = defaultdict(list), defaultdict(list)
        for n in c:
            (Xd if n[0] == 'X' else Yd)[n[1]].append(n[2][0])
        if len(Xd) < 2 or len(Yd) < 2: continue
        Xd = {k: sum(v) / len(v) for k, v in Xd.items()}; Yd = {k: sum(v) / len(v) for k, v in Yd.items()}
        gx = [n[2] for n in c if n[0] == 'X']; gy = [n[2] for n in c if n[0] == 'Y']
        x0 = min([g[0] for g in gx] + [g[1] for g in gy]); x1 = max([g[0] for g in gx] + [g[2] for g in gy])
        y0 = min([g[0] for g in gy] + [g[1] for g in gx]); y1 = max([g[0] for g in gy] + [g[2] for g in gx])
        planos.append((Xd, Yd, (x0 - 3, y0 - 3, x1 + 3, y1 + 3)))
    return planos


def _offset(vals, ref, labels):
    """Desplazamiento que empata más ejes con la retícula de referencia (por espaciamiento, no por nombre)."""
    best = None
    for v in vals:
        for r in ref.values():
            o = v - r
            res = [min(abs(w - o - rr) for rr in ref.values()) for w in vals]
            k = sum(1 for d in res if d < 0.03)
            lab = sum(1 for name, w in labels.items() if name in ref and abs(w - o - ref[name]) < 0.03)
            err = max([d for d in res if d < 0.03], default=9)
            key = (k, lab, -err)
            if best is None or key > best[0]:
                best = (key, o, k, err, lab)
    return best


def anclar(X, Y):
    bx = _offset(list(X.values()), REFX, X)
    by = _offset(list(Y.values()), REFY, Y)
    if not bx or not by or bx[2] < 2 or by[2] < 2: return None
    ren = (bx[4] < bx[2]) or (by[4] < by[2])  # nombres de ejes distintos a estructura
    return bx[1], by[1], max(bx[3], by[3]), bx[2] + by[2], ren


def nivel_region(msp, region, ents_region):
    """Nivel de una planta según los nombres de vista de Revit en bloques y títulos dentro/debajo de la planta."""
    votos = Counter()
    x0, y0, x1, y1 = region
    for e in msp.query('INSERT'):
        p = e.dxf.insert
        if x0 <= p.x <= x1 and y0 <= p.y <= y1:
            n = nivel_txt(e.dxf.name.rsplit('-', 1)[-1])
            if n: votos[n] += 1
    for e in msp.query('MTEXT TEXT'):
        p = e.dxf.insert
        if x0 - 2 <= p.x <= x1 + 2 and y0 - 10 <= p.y <= y0 + 3:
            t = e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text
            if re.match(r'\s*(PLANTA|NIVEL|S[OÓ]TANO|AZOTEA)', t, re.I):
                n = nivel_txt(t)
                if n: votos[n] += 5
    return votos.most_common(1)[0][0] if votos else None


def hatch_polys(h):
    out = []
    try:
        for p in ezpath.from_hatch(h):
            pts = [(v.x, v.y) for v in p.flattening(0.005)]
            if len(pts) >= 4:
                pg = Polygon(pts)
                if not pg.is_valid: pg = pg.buffer(0)
                if pg.area > 1e-4: out.append(pg)
    except Exception:
        pass
    return out


def robust_bbox(msp):
    xs, ys = [], []
    for e in msp:
        p = ref_point(e)
        if p is not None: xs.append(p[0]); ys.append(p[1])
    if not xs: return (0, 0, 1, 1)
    xs.sort(); ys.sort(); n = len(xs)
    lo, hi = int(n * 0.005), max(int(n * 0.995) - 1, 0)
    return xs[lo], ys[lo], xs[hi], ys[hi]


def inside(p, r):
    return p is not None and r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]

# ---------------------------------------------------------------- proceso por lámina


def a_metros(sdoc):
    if sdoc.header.get('$INSUNITS', 6) == 4:
        m = Matrix44.scale(0.001)
        for e in list(sdoc.modelspace()):
            try: e.transform(m)
            except Exception: pass
        sdoc.header['$INSUNITS'] = 6
        return True
    return False


def prep(sdoc, P, planos_niv, codigo=''):
    """planos_niv: [(region, nivel)]. Renombra capas, sufijo de nivel por región, polilíneas medibles."""
    msp = sdoc.modelspace()
    # contenido de bloques a capa 0 (hereda la capa del bloque -> se prende/apaga con él)
    for b in sdoc.blocks:
        if b.name.upper().startswith(('*PAPER', '*MODEL')): continue
        for e in b:
            try: e.dxf.layer = '0'
            except Exception: pass

    nivs = {n for _, n in planos_niv}

    def suf(e):
        if e.dxftype() == 'INSERT' and len(nivs) > 1:
            nv = nivel_txt(e.dxf.name.rsplit('-', 1)[-1])
            if nv in nivs: return nv
        p = ref_point(e)
        c = [(((p[0] - (r[0] + r[2]) / 2) ** 2 + (p[1] - (r[1] + r[3]) / 2) ** 2), n) for r, n in planos_niv if inside(p, r)]
        return min(c)[1] if c else 'DET'
    nuevas = []
    for e in list(msp):
        try: src = e.dxf.layer
        except Exception: continue
        base = std_layer(src, P, codigo)
        s = suf(e)
        if e.dxftype() == 'HATCH' and base.endswith(('-M2', '-PZA')):
            for pg in hatch_polys(e): nuevas.append((f'{base}_{s}', pg))
        e.dxf.layer = f'{base}_{s}'
    vistos = set()
    for lay, pg in nuevas:
        c = pg.representative_point()
        k = (lay, round(c.x, 2), round(c.y, 2), round(pg.area, 3))
        if k in vistos: continue
        vistos.add(k)
        for poly in ([pg] if pg.geom_type == 'Polygon' else list(pg.geoms)):
            msp.add_lwpolyline(list(poly.exterior.coords)[:-1], close=True, dxfattribs={'layer': lay})
    # líneas de tubería / canalización -> polilíneas continuas (para medir longitud)
    grupos = defaultdict(list)
    for e in list(msp.query('LINE ARC LWPOLYLINE SPLINE')):
        lay = e.dxf.layer
        if '-ML_' not in lay: continue
        try:
            if e.dxftype() == 'LINE':
                grupos[lay].append(LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]))
            elif e.dxftype() in ('ARC', 'SPLINE'):
                grupos[lay].append(LineString([(v.x, v.y) for v in e.flattening(0.01)]))
            else:
                if e.closed: continue
                grupos[lay].append(LineString([(v[0], v[1]) for v in e.get_points('xy')]))
            msp.delete_entity(e)
        except Exception:
            pass
    for lay, ls in grupos.items():
        uniq, vistos = [], set()
        for l in ls:
            if l.length <= 0: continue
            k = tuple(sorted([tuple(round(c, 2) for c in l.coords[0]), tuple(round(c, 2) for c in l.coords[-1])]))
            if k in vistos: continue
            vistos.add(k); uniq.append(l)
        if not uniq: continue
        from shapely.ops import unary_union
        merged = linemerge(MultiLineString(uniq))
        gs = [merged] if merged.geom_type == 'LineString' else list(merged.geoms)
        # tubería dibujada a doble línea: el par paralelo (sep. <= 0.25 m) se mueve a capa -PAR (no medible)
        from shapely.strtree import STRtree
        tree = STRtree(gs); par = set()
        for i, g in enumerate(gs):
            if i in par: continue
            for j in tree.query(g.buffer(0.25)):
                j = int(j)
                if j <= i or j in par: continue
                h = gs[j]
                if min(g.length, h.length) / max(g.length, h.length) > 0.7 and g.hausdorff_distance(h) <= 0.3:
                    par.add(j); break
        base, niv = lay.rsplit('_', 1)
        for i in par:
            msp.add_lwpolyline(list(gs[i].coords), dxfattribs={'layer': f'{base[:-3]}-PAR_{niv}'})
        # eje: se disuelven traslapes colineales sólo entre las líneas que quedan como eje
        ejes = [g for i, g in enumerate(gs) if i not in par]
        if ejes:
            import shapely
            u = unary_union([shapely.set_precision(g, 0.005) for g in ejes])
            u = linemerge(u) if u.geom_type == 'MultiLineString' else u
            for g in ([u] if u.geom_type == 'LineString' else [x for x in getattr(u, 'geoms', []) if x.geom_type == 'LineString']):
                msp.add_lwpolyline(list(g.coords), dxfattribs={'layer': lay})
    for name in {e.dxf.layer for e in msp}:
        if name not in sdoc.layers: sdoc.layers.add(name)
        sdoc.layers.get(name).color = COLOR.get(name[:5], 7)


def cargar(sdoc, tdoc, dx, dy, region=None, ren=None, nivel=None):
    tmsp = tdoc.modelspace()
    antes = {e.dxf.handle for e in tmsp}

    def filtro(e):
        if e.dxftype() == 'VIEWPORT': return False
        if region is None: return True
        if e.dxftype() == 'INSERT':
            n = e.dxf.name.upper()
            if 'RVT' in n or n.startswith('FP_'): return False  # fondo vinculado repetido / patrón de relleno
        if nivel is not None:
            try: return e.dxf.layer.endswith('_' + nivel)
            except Exception: return False
        return inside(ref_point(e), region)
    ld = xref.Loader(sdoc, tdoc, conflict_policy=xref.ConflictPolicy.KEEP)
    ld.load_modelspace(filter_fn=filtro)
    ld.execute()
    for e in tmsp:
        if e.dxf.handle not in antes:
            try: e.translate(dx, dy, 0)
            except Exception: pass
            if ren and e.dxf.layer.endswith('_' + ren[0]):
                nuevo = e.dxf.layer[:-len(ren[0])] + ren[1]
                if nuevo not in tdoc.layers:
                    tdoc.layers.add(nuevo, color=tdoc.layers.get(e.dxf.layer).color)
                e.dxf.layer = nuevo


def cuantificar(sdoc, region, nivel, codigo, disc):
    msp = sdoc.modelspace()
    q = []
    acc = defaultdict(lambda: [0, 0.0, 0.0])
    for e in msp.query('LWPOLYLINE'):
        lay = e.dxf.layer
        m = re.search(r'-(M2|PZA|ML)_', lay)
        if not m: continue
        pts = [(v[0], v[1]) for v in e.get_points('xy')]
        if len(pts) < 2: continue
        a = acc[lay.rsplit('_', 1)[0]]
        if e.closed and len(pts) >= 3:
            pg = Polygon(pts)
            if not inside(pg.representative_point().coords[0], region): continue
            a[0] += 1; a[1] += abs(pg.area)
        else:
            ls = LineString(pts)
            if not inside(ls.interpolate(0.5, normalized=True).coords[0], region): continue
            a[0] += 1; a[2] += ls.length
    for lay, (n, area, lon) in acc.items():
        q.append(dict(nivel=nivel, lamina=codigo, disciplina=disc, capa=lay, tipo='POLILINEAS',
                      piezas=n, area_m2=round(area, 3), longitud_m=round(lon, 3)))
    cnt = defaultdict(int)
    for e in msp.query('INSERT'):
        if '-PZA_' not in e.dxf.layer or not inside(e.dxf.insert, region): continue
        tipo = re.split(r'-\d{5,}|-V\d+-', e.dxf.name)[0][:50]
        cnt[(e.dxf.layer.rsplit('_', 1)[0], 'BLOQUE ' + tipo)] += 1
    for e in msp.query('MTEXT TEXT'):
        if not e.dxf.layer.startswith(('05EST-COLUMNA-ETIQ', '05EST-TRABE-ETIQ')): continue
        if not inside(e.dxf.insert, region): continue
        t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip().upper()
        if re.fullmatch(r'[A-Z]{1,3}-\d{1,3}[A-Z]?', t):
            cnt[(e.dxf.layer.rsplit('_', 1)[0], 'ETIQUETA ' + t)] += 1
    for (lay, t), n in sorted(cnt.items()):
        q.append(dict(nivel=nivel, lamina=codigo, disciplina=disc, capa=lay, tipo=t, piezas=n,
                      area_m2=None, longitud_m=None))
    return q


SLOT_M = 90.0


def solo_referencia_lista(ROOT, ref_disc, cfg):
    """Pasada 1: retícula de referencia desde las plantas de la disciplina de referencia."""
    global SLOT_M
    infos = []
    for f in sorted((ROOT / ref_disc).glob('*.dxf')):
        if not nivel_txt(f.stem, plano_requerido=True): continue
        try:
            d, _ = recover.readfile(str(f))
        except Exception:
            continue
        a_metros(d)
        infos += grid_planes(d.modelspace())
    if not infos: return False
    X, Y, _ = max(infos, key=lambda g: len(g[0]) + len(g[1]))
    ox, oy = min(X.values()), min(Y.values())
    REFX.update({k: v - ox for k, v in X.items()}); REFY.update({k: v - oy for k, v in Y.items()})
    for X2, Y2, _ in infos:
        a = anclar(X2, Y2)
        if not a or a[2] > 0.05: continue
        for k, v in X2.items(): REFX.setdefault(k, v - a[0])
        for k, v in Y2.items(): REFY.setdefault(k, v - a[1])
    span = max(max(REFX.values()) - min(REFX.values()), max(REFY.values()) - min(REFY.values()))
    SLOT_M = float(max(60, round(span * 2.5 / 10) * 10))
    print('RETICULA X', {k: round(v, 3) for k, v in sorted(REFX.items())})
    print('RETICULA Y', {k: round(v, 3) for k, v in sorted(REFY.items(), key=lambda t: int(t[0]))}, 'slot', SLOT_M)
    return True


def rango(titulo):
    t = strip(titulo)
    if re.search(r'DEPTO|DEPARTAMENTO|DETALLE|ISOMETRIC', t): return None
    m = re.search(r'NIVEL\s*(\d{1,2})\s*-\s*(\d{1,2})\b', t) or re.search(r'\bN(\d{1,2})\s*Y\s*N(\d{1,2})\b', t)
    if m and int(m.group(2)) > int(m.group(1)):
        return [f'N{i:02d}' for i in range(int(m.group(1)), int(m.group(2)) + 1)]
    return None


def r2(v, q=0.01):
    return round(v / q)


_TAM = {}


def tam_bloque(doc, name):
    if doc is None: return None
    if name not in _TAM:
        try:
            from ezdxf import bbox
            b = bbox.extents(doc.blocks.get(name), fast=True)
            _TAM[name] = (round(b.size.x, 2), round(b.size.y, 2)) if b.has_data else None
        except Exception:
            _TAM[name] = None
    return _TAM[name]


def bordes_y_segmentos(tdoc):
    """Capa X-ML con hermana X-CNTR-ML en el mismo nivel: si sus líneas están desplazadas del eje (> 5 cm) son
    BORDES (charola dibujada por sus orillas); si están encima del eje son SEGMENTOS. Ninguna se mide."""
    msp = tdoc.modelspace()
    capas = {e.dxf.layer for e in msp}
    ren = {}
    for L in capas:
        m = re.match(r'(.+?)-ML_([A-Z0-9]+)$', L)
        if not m or m.group(1).endswith('-CNTR'): continue
        her = f'{m.group(1)}-CNTR-ML_{m.group(2)}'
        if her not in capas: continue
        eje = [LineString(e.get_points('xy')) for e in msp.query(f'LWPOLYLINE[layer=="{her}"]')]
        pts = []
        for e in msp.query(f'LWPOLYLINE[layer=="{L}"]'):
            pts += [p for p in e.get_points('xy')][:3]
        if not eje or not pts: continue
        from shapely.ops import unary_union
        from shapely.geometry import Point
        u = unary_union(eje)
        d = sorted(u.distance(Point(p)) for p in pts)
        ren[L] = f'{m.group(1)}-{"BORDE" if d[len(d) // 2] > 0.05 else "SEGMENTOS"}_{m.group(2)}'
    for L, N in ren.items():
        if N not in tdoc.layers: tdoc.layers.add(N, color=tdoc.layers.get(L).color)
    for e in msp:
        if e.dxf.layer in ren: e.dxf.layer = ren[e.dxf.layer]
    return ren


def depurar(tmsp, doc=None):
    vistos, borrar, ins_idx = set(), [], {}
    for e in tmsp:
        t = e.dxftype()
        try:
            if t == 'INSERT':
                p = e.dxf.insert
                if p.y < -100: continue
                k = (t, e.dxf.layer, re.split(r'-\d{5,}|-V\d+-', e.dxf.name)[0], r2(p.x, 0.15), r2(p.y, 0.15), r2(e.dxf.rotation, 1))
            elif t == 'LINE':
                a, b = e.dxf.start, e.dxf.end
                if a.y < -100: continue
                k = (t, e.dxf.layer) + tuple(sorted([(r2(a.x), r2(a.y)), (r2(b.x), r2(b.y))]))
            elif t == 'LWPOLYLINE':
                pts = [(r2(x), r2(y)) for x, y in e.get_points('xy')]
                if not pts or e.get_points('xy')[0][1] < -100: continue
                k = (t, e.dxf.layer, e.closed, tuple(pts))
            elif t in ('MTEXT', 'TEXT'):
                p = e.dxf.insert
                if p.y < -100: continue
                k = (t, e.dxf.layer, e.plain_text() if t == 'MTEXT' else e.dxf.text, r2(p.x, 0.05), r2(p.y, 0.05))
            elif t in ('CIRCLE', 'ARC'):
                c = e.dxf.center
                if c.y < -100: continue
                k = (t, e.dxf.layer, r2(c.x), r2(c.y), r2(e.dxf.radius), r2(getattr(e.dxf, 'start_angle', 0), 1))
            else:
                continue
        except Exception:
            continue
        if t == 'INSERT':
            kk = k[:3] + (k[5], tam_bloque(doc, e.dxf.name), round(e.dxf.xscale, 3), round(e.dxf.yscale, 3))
            px, py = e.dxf.insert.x, e.dxf.insert.y
            cel = (int(px // 0.25), int(py // 0.25))
            dup = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for qx, qy in ins_idx.get(kk + (cel[0] + dx, cel[1] + dy), ()):
                        if abs(qx - px) <= 0.25 and abs(qy - py) <= 0.25: dup = True
            if dup: borrar.append(e)
            else: ins_idx.setdefault(kk + cel, []).append((px, py))
            continue
        if k in vistos: borrar.append(e)
        else: vistos.add(k)
    for e in borrar: tmsp.delete_entity(e)
    return len(borrar)


def cuantificar_final(tmsp, fuentes):
    acc = defaultdict(lambda: [0, 0.0, 0.0])
    cnt = defaultdict(int)
    for e in tmsp.query('LWPOLYLINE'):
        lay = e.dxf.layer
        m = re.search(r'-(M2|PZA|ML)_([A-Z0-9]+)$', lay)
        if not m or m.group(2) in ('DET',): continue
        pts = [(x, y) for x, y in e.get_points('xy')]
        if len(pts) < 2 or pts[0][1] < -100: continue
        a = acc[(lay.rsplit('_', 1)[0], m.group(2))]
        if e.closed and len(pts) >= 3:
            a[0] += 1; a[1] += abs(Polygon(pts).area)
        else:
            a[0] += 1; a[2] += LineString(pts).length
    for e in tmsp.query('INSERT'):
        lay = e.dxf.layer
        m = re.search(r'-PZA_([A-Z0-9]+)$', lay)
        if not m or e.dxf.insert.y < -100: continue
        blk = e.block()
        if blk is None or len(blk) == 0: continue  # bloque vacío: no es pieza
        tipo = re.split(r'-\d{5,}|-V\d+-', e.dxf.name)[0][:50]
        cnt[(lay.rsplit('_', 1)[0], m.group(1), 'BLOQUE ' + tipo)] += 1
    for e in tmsp.query('MTEXT TEXT'):
        lay = e.dxf.layer
        if not lay.startswith(('05EST-COLUMNA-ETIQ', '05EST-TRABE-ETIQ')) or e.dxf.insert.y < -100: continue
        t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip().upper()
        if re.fullmatch(r'[A-Z]{1,3}-\d{1,3}[A-Z]?', t):
            cnt[(lay.rsplit('_', 1)[0], lay.rsplit('_', 1)[1], 'ETIQUETA ' + t)] += 1
    q = []
    for (capa, niv), (n, area, lon) in acc.items():
        q.append(dict(nivel=niv, lamina=', '.join(sorted(fuentes.get((niv, capa[:5]), []))), disciplina=capa[:5],
                      capa=capa, tipo='POLILINEAS', piezas=n, area_m2=round(area, 3), longitud_m=round(lon, 3)))
    for (capa, niv, t), n in cnt.items():
        q.append(dict(nivel=niv, lamina=', '.join(sorted(fuentes.get((niv, capa[:5]), []))), disciplina=capa[:5],
                      capa=capa, tipo=t, piezas=n, area_m2=None, longitud_m=None))
    return q


def main():
    global SLOT_M
    ROOT, OUT, QJSON = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    modo = sys.argv[4] if len(sys.argv) > 4 else ''
    cfg = json.loads(Path(sys.argv[5]).read_text()) if len(sys.argv) > 5 else {}
    DPREF.update(cfg.get('prefijos', {}))
    ref_disc = cfg.get('referencia', '03 ESTRUCTURA')
    if not solo_referencia_lista(ROOT, ref_disc, cfg):
        print('ERROR: no se pudo calcular la retícula de referencia en', ref_disc); sys.exit(2)
    SLOT_M = cfg.get('slot_m') or SLOT_M
    solo_fed = modo == 'solo_federado'
    solo_lam = modo == 'solo_laminas'
    tdoc = ezdxf.new('R2018', setup=True)
    tdoc.header['$INSUNITS'] = 6; tdoc.header['$MEASUREMENT'] = 1
    tmsp = tdoc.modelspace()
    tdoc.layers.add('00GEN-TITULO', color=5); tdoc.layers.add('00GEN-MARCO-ZONA', color=8)
    hojas = sorted(ROOT.glob('*/*.dxf'))
    SLOT = {n: i for i, n in enumerate(ORDEN)}
    usados = set()
    lam_x, lam_y, fila_h = 0.0, -150.0, 0.0
    cantidades, bitacora = [], []
    fuentes = defaultdict(set)
    for f in hojas:
        disc = f.parent.name
        P = DPREF.get(disc, '00GEN')
        titulo = f.stem
        if P == '21ELE' and strip(titulo).startswith('ISE'): P = '23ESP'
        codigo = codigo_de(titulo)
        try:
            sdoc, aud = recover.readfile(str(f))
        except Exception as ex:
            bitacora.append(dict(archivo=f.name, disciplina=disc, estado='ERROR lectura: ' + str(ex)[:150])); continue
        mm = a_metros(sdoc)
        msp = sdoc.modelspace()
        nivel_arch = nivel_txt(titulo, plano_requerido=True)
        planos = grid_planes(msp)
        asign = []
        for X, Y, region in planos:
            n = nivel_region(msp, region, None) if len(planos) > 1 else (nivel_arch or nivel_region(msp, region, None))
            anc = anclar(X, Y)
            if n and anc: asign.append((region, n, anc))
        # niveles repetidos en la misma lámina: quedarse con la planta de más ejes
        uniq = {}
        for r, n, a in asign:
            if n not in uniq or a[3] > uniq[n][1][3]: uniq[n] = (r, a)
        prep(sdoc, P, [(r, n) for n, (r, a) in uniq.items()], codigo)
        if not solo_fed:
            x0, y0, x1, y1 = robust_bbox(msp)
            w, h = x1 - x0, y1 - y0
            if lam_x + w > 1500:
                lam_x, lam_y, fila_h = 0.0, lam_y - fila_h - 40, 0.0
            cargar(sdoc, tdoc, lam_x - x0, lam_y - y1, None)
            tmsp.add_mtext(f'{codigo}  |  {disc}  |  {titulo}', dxfattribs={
                'layer': '00GEN-TITULO', 'char_height': 1.2, 'insert': (lam_x, lam_y + 4)})
            tmsp.add_lwpolyline([(lam_x - 2, lam_y + 2), (lam_x + w + 2, lam_y + 2), (lam_x + w + 2, lam_y - h - 2),
                                 (lam_x - 2, lam_y - h - 2)], close=True, dxfattribs={'layer': '00GEN-MARCO-ZONA'})
            lam_x += w + 30; fila_h = max(fila_h, h)
        est = []
        rg = rango(titulo) if len(uniq) == 1 else None
        for n, (r, (ax, ay, err, k, ren)) in ({} if solo_lam else uniq).items():
            destinos = rg if (rg and rg[0] == n) else [n]
            for d in destinos:
                ox = SLOT.get(d, len(ORDEN)) * SLOT_M
                cargar(sdoc, tdoc, ox - ax, -ay, r, None if d == n else (n, d), nivel=n)
                usados.add(d)
                fuentes[(d, P)].add(codigo)
                if P == '05EST': fuentes[(d, '04CIM')].add(codigo); fuentes[(d, '07ALB')].add(codigo)
            if len(destinos) > 1: n = f'{destinos[0]}..{destinos[-1]}'
            est.append(f'{n}(ejes {k}, dif {err * 1000:.0f} mm' + (', ejes con otra nomenclatura' if ren else '') + ')')
        estado = ('FEDERADO ' + ', '.join(est)) if est else ('solo LAMINAS: ' + (
            'sin retícula reconocible' if not planos else 'sin nivel identificable' if not asign else ''))
        bitacora.append(dict(archivo=f.name, disciplina=disc, codigo=codigo, estado=estado, mm_a_m=mm,
                             planos_detectados=len(planos), entidades=len(msp), arreglos_dxf=len(aud.fixes)))
        print(f'{disc[:14]:14s} {codigo:12s} {estado}', flush=True)
    if solo_lam:
        tmsp.add_mtext('LAMINAS: cada plano completo y separado.', dxfattribs={
            'layer': '00GEN-TITULO', 'char_height': 4.0, 'insert': (0, -130)})
        tdoc.saveas(OUT); print('capas', len(tdoc.layers), 'entidades', len(tmsp)); return
    for n in usados:
        tmsp.add_mtext(f'NIVEL {n}', dxfattribs={'layer': '00GEN-TITULO', 'char_height': 2.5,
                                                  'insert': (SLOT.get(n, len(ORDEN)) * SLOT_M, 40)})
    tmsp.add_mtext('ZONA FEDERADO: todas las disciplinas encimadas por nivel. Origen = cruce de los ejes mínimos de la retícula de referencia.',
                   dxfattribs={'layer': '00GEN-TITULO', 'char_height': 4.0, 'insert': (0, 60)})
    if not solo_fed:
        tmsp.add_mtext('ZONA LAMINAS: cada plano completo y separado.', dxfattribs={
            'layer': '00GEN-TITULO', 'char_height': 4.0, 'insert': (0, -130)})
    ren = bordes_y_segmentos(tdoc)
    quitados = depurar(tmsp, tdoc)
    print('duplicados eliminados', quitados, flush=True)
    cantidades = cuantificar_final(tmsp, fuentes)
    bitacora.append(dict(archivo='(federado)', estado=f'duplicados eliminados: {quitados}; capas no medibles por eje hermano: {ren}'))
    tdoc.saveas(OUT)
    import datetime
    QJSON.write_text(json.dumps(dict(proyecto=cfg.get('proyecto', ''), fecha=str(datetime.date.today()), reticula=dict(X=REFX, Y=REFY), slot_m=SLOT_M, cantidades=cantidades, bitacora=bitacora), ensure_ascii=False, indent=1))
    print('capas', len(tdoc.layers), 'entidades', len(tmsp))


if __name__ == '__main__':
    main()
