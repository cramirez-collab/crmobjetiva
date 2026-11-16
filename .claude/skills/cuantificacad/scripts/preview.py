import sys, ezdxf
from ezdxf import recover
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
src, out, x0, y0, x1, y1 = sys.argv[1], sys.argv[2], *map(float, sys.argv[3:7])
only = sys.argv[7] if len(sys.argv) > 7 else None
doc = ezdxf.readfile(src)
msp = doc.modelspace()
def inside(e):
    try:
        b = ezdxf.bbox.extents([e], fast=True)
        return b.has_data and b.extmin.x < x1 and b.extmax.x > x0 and b.extmin.y < y1 and b.extmax.y > y0 and (only is None or only in e.dxf.layer)
    except Exception: return False
ents = [e for e in msp if inside(e)]
fig = plt.figure(figsize=(14, 14 * (y1 - y0) / (x1 - x0))); ax = fig.add_axes([0, 0, 1, 1])
cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)
Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_entities(ents)
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); fig.savefig(out, dpi=90)
print(len(ents))
