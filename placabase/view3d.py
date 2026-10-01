# -*- coding: utf-8 -*-
"""
Lectura de resultados de CalculiX (.frd) y dibujo 3D dentro del programa.

Del .frd se sacan los desplazamientos nodales y el tensor de esfuerzos; de la
malla (.inp de Gmsh) las coordenadas y los tetraedros.  Para dibujar no hace
falta el volumen completo: basta la PIEL del solido, es decir las caras de
tetraedro que pertenecen a un solo elemento.  Eso se colorea con el campo
elegido y se dibuja con matplotlib en 3D.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import math
import re

import numpy as np


@dataclass
class Result3D:
    ok: bool = False
    msg: str = ""
    nodes: dict = field(default_factory=dict)      # id -> (x, y, z)
    tris: list = field(default_factory=list)       # caras exteriores (n1,n2,n3)
    disp: dict = field(default_factory=dict)       # id -> (ux, uy, uz)
    vm: dict = field(default_factory=dict)         # id -> von Mises
    stress: dict = field(default_factory=dict)     # id -> (sx,sy,sz,sxy,syz,szx)
    forc: dict = field(default_factory=dict)       # id -> reaccion (RF)
    n_nodes: int = 0
    n_elems: int = 0
    umax: float = 0.0
    vmmax: float = 0.0
    rf_sum: tuple = (0.0, 0.0, 0.0)
    vm_avg: dict = None                             # ver smoothed_plate_vm


# ============================================================ malla (.inp)
def read_mesh_inp(path: str):
    """Devuelve (nodos, elementos) del .inp que escribe Gmsh."""
    nodes, elems = {}, []
    mode, etype = None, None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            t = ln.strip()
            if not t:
                continue
            up = t.upper()
            if up.startswith("*NODE"):
                mode = "N"; continue
            if up.startswith("*ELEMENT"):
                mode = "E"
                etype = ("C3D10" if "C3D10" in up else
                         ("C3D4" if "C3D4" in up else None))
                continue
            if t.startswith("*"):
                mode = None; continue
            v = [x.strip() for x in t.rstrip(",").split(",") if x.strip()]
            if mode == "N" and len(v) >= 4:
                nodes[int(v[0])] = (float(v[1]), float(v[2]), float(v[3]))
            elif mode == "E" and etype and len(v) >= 5:
                elems.append([int(x) for x in v[1:]])
    return nodes, elems


def skin(elems):
    """Caras exteriores: las que aparecen en un solo tetraedro.

    Con tetraedros de 10 nodos solo se usan los 4 vertices; para dibujar la
    piel eso es suficiente y evita triangulos curvos."""
    faces = {}
    for e in elems:
        a, b, c, d = e[0], e[1], e[2], e[3]
        for f in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            k = tuple(sorted(f))
            faces[k] = faces.get(k, 0) + 1
    return [k for k, n in faces.items() if n == 1]


# ============================================================ resultados (.frd)
def read_frd(path: str):
    """Devuelve (disp, stress) como dicts nodo -> tupla."""
    disp, stress, forc = {}, {}, {}
    block = None
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            s = ln.rstrip("\n")
            if len(s) > 5 and s[1:3] == "-4":
                name = s[5:13].strip().upper()
                block = ("U" if name.startswith("DISP") else
                         "S" if name.startswith("STRESS") else
                         "F" if name.startswith("FORC") else None)
                continue
            if s.startswith(" -3"):
                block = None
                continue
            if block and s.startswith(" -1"):
                try:
                    nid = int(s[3:13])
                except ValueError:
                    continue
                rest = s[13:]
                vals = []
                for i in range(0, len(rest), 12):
                    chunk = rest[i:i + 12].strip()
                    if not chunk:
                        continue
                    try:
                        vals.append(float(chunk))
                    except ValueError:
                        pass
                if block == "U" and len(vals) >= 3:
                    disp[nid] = tuple(vals[:3])
                elif block == "S" and len(vals) >= 6:
                    stress[nid] = tuple(vals[:6])
                elif block == "F" and len(vals) >= 3:
                    forc[nid] = tuple(vals[:3])
    return disp, stress, forc


def von_mises(sx, sy, sz, sxy, syz, szx):
    return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                     + 3.0 * (sxy ** 2 + syz ** 2 + szx ** 2))


def load_results(mesh_inp: str, frd: str) -> Result3D:
    r = Result3D()
    try:
        nodes, elems = read_mesh_inp(mesh_inp)
    except Exception as e:
        r.msg = f"No se pudo leer la malla: {e}"
        return r
    if not nodes or not elems:
        r.msg = "La malla no contiene nodos o elementos solidos."
        return r
    try:
        disp, stress, forc = read_frd(frd)
    except Exception as e:
        r.msg = f"No se pudo leer el .frd: {e}"
        return r
    if not disp:
        r.msg = ("El .frd no contiene desplazamientos. Revise que CalculiX haya "
                 "terminado sin errores (archivo .sta / .dat).")
        return r

    r.nodes = nodes
    r.tris = skin(elems)
    r.disp = disp
    r.vm = {n: von_mises(*s) for n, s in stress.items()}
    r.stress = stress
    r.forc = forc
    r.n_nodes, r.n_elems = len(nodes), len(elems)
    r.umax = max((math.sqrt(sum(c * c for c in u)) for u in disp.values()),
                 default=0.0)
    r.vmmax = max(r.vm.values(), default=0.0)
    if forc:
        r.rf_sum = tuple(sum(v[i] for v in forc.values()) for i in range(3))
    r.ok = True
    r.msg = (f"{r.n_nodes:,} nodos y {r.n_elems:,} tetraedros.  "
             f"|U| max = {r.umax:.5f} in ;  von Mises max = {r.vmmax:.2f} ksi")
    return r


# ==================================================================== dibujo
def set_aspect(ax, aspect, zoom=0.72):
    """Proporciones reales del modelo + zoom inicial conservador (luego se ajusta)."""
    ax._pb_aspect, ax._pb_zoom = aspect, zoom
    try:
        ax.set_box_aspect(aspect, zoom=zoom)
    except TypeError:
        ax.set_box_aspect(aspect)


def fit_to_axes(ax, margin=0.04):
    """Escala el modelo para que llene el area del grafico (ancho y alto) sin recortarse.
    Proyecta las 8 esquinas de la caja del modelo a pixeles y ajusta el zoom."""
    asp = getattr(ax, "_pb_aspect", None)
    if asp is None:
        return
    from mpl_toolkits.mplot3d import proj3d
    try:
        for _ in range(2):
            (x0, x1), (y0, y1), (z0, z1) = ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()
            cs = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
            X, Y, _z = proj3d.proj_transform([c[0] for c in cs], [c[1] for c in cs],
                                             [c[2] for c in cs], ax.get_proj())
            px = ax.transData.transform(np.column_stack([X, Y]))
            bb = ax.bbox
            w, h = px[:, 0].max() - px[:, 0].min(), px[:, 1].max() - px[:, 1].min()
            if w <= 1 or h <= 1 or bb.width <= 1 or bb.height <= 1:
                return
            k = min(bb.width * (1 - 2 * margin) / w, bb.height * (1 - 2 * margin) / h)
            ax._pb_zoom = float(np.clip(ax._pb_zoom * k, 0.2, 3.0))
            ax.set_box_aspect(asp, zoom=ax._pb_zoom)
    except Exception:
        pass


def _soft_cmap(diverging=False):
    """Paletas suaves para los resultados 3D (azul -> verde -> amarillo -> coral)."""
    from matplotlib.colors import LinearSegmentedColormap
    cols = (["#4a7fc1", "#f5f5f2", "#e2705f"] if diverging else
            ["#4a7fc1", "#63b7c4", "#9fd3a0", "#f1e08a", "#f4b26b", "#e2705f"])
    return LinearSegmentedColormap.from_list("pb_suave", cols, N=256)


def plot3d(ax, res: Result3D, prj, field="vm", scale=0.0, shrink_tris=12000, tag_max=True):
    """Dibuja la piel del solido coloreada por el campo elegido."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    ax.clear()
    if res is None or not res.ok:
        ax.text2D(0.5, 0.5, "Sin resultados 3D.\nUse  Calculo > Analisis 3D.",
                  ha="center", va="center", transform=ax.transAxes, fontsize=11,
                  color="#777777")
        ax.set_axis_off()
        return None

    u = prj.units()
    kl, ks = u.fl, u.fs

    ids = list(res.nodes.keys())
    idx = {n: i for i, n in enumerate(ids)}
    P = np.array([res.nodes[n] for n in ids], dtype=float)
    if scale > 0 and res.disp:
        D = np.array([res.disp.get(n, (0, 0, 0)) for n in ids], dtype=float)
        P = P + scale * D

    if field == "u":
        val = np.array([math.sqrt(sum(c * c for c in res.disp.get(n, (0, 0, 0))))
                        for n in ids])
        val = val / kl
        title, cmap, unit = "Desplazamiento |U|", _soft_cmap(), u.L
    elif field == "uz":
        val = np.array([res.disp.get(n, (0, 0, 0))[2] for n in ids]) / kl
        title, cmap, unit = "Desplazamiento vertical Uz", _soft_cmap(True), u.L
    else:
        val = np.array([res.vm.get(n, 0.0) for n in ids]) / ks
        title, cmap, unit = "Esfuerzo de von Mises", _soft_cmap(), u.S

    tris = res.tris
    if len(tris) > shrink_tris:                 # muestreo para que la vista fluya
        step = max(1, len(tris) // shrink_tris)
        tris = tris[::step]

    verts = [[P[idx[a]] / kl, P[idx[b]] / kl, P[idx[c]] / kl] for a, b, c in tris]
    face_val = np.array([(val[idx[a]] + val[idx[b]] + val[idx[c]]) / 3.0
                         for a, b, c in tris])

    import matplotlib.cm as cm
    from matplotlib.colors import Normalize
    vmin, vmax = float(np.min(face_val)), float(np.max(face_val))
    if abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0
    norm = Normalize(vmin=vmin, vmax=vmax)
    mapper = cm.ScalarMappable(norm=norm, cmap=cmap)

    coll = Poly3DCollection(verts, facecolors=mapper.to_rgba(face_val),
                            edgecolors=(0, 0, 0, 0.06), linewidths=0.1)
    ax.add_collection3d(coll)

    Pm = P / kl
    mins, maxs = Pm.min(axis=0), Pm.max(axis=0)
    # proporciones reales y margen minimo: el modelo llena el lienzo y queda
    # centrado; la rueda del mouse hace zoom sobre el centro
    spans = np.maximum(maxs - mins, 1e-6)
    pad = 0.03 * float(spans.max())
    ax.set_xlim(mins[0] - pad, maxs[0] + pad)
    ax.set_ylim(mins[1] - pad, maxs[1] + pad)
    ax.set_zlim(mins[2] - pad, maxs[2] + pad)
    set_aspect(ax, tuple(float(v) + 2 * pad for v in spans))
    if tag_max and len(val):
        try:
            ax.computed_zorder = False
        except Exception:
            pass
        k = int(np.argmax(val))
        mx, my_, mz = Pm[k]
        avg = res.vm_avg if (field == "vm" and getattr(res, "vm_avg", None)) else None
        if avg:                               # maximo PROMEDIADO (converge con la malla)
            mx, my_, mz = avg["x"] / kl, avg["y"] / kl, avg["z"] / kl
        ax.scatter([mx], [my_], [mz], s=170, color="#d62728", marker="*", edgecolors="black",
                   linewidths=0.8, depthshade=False, zorder=20)
        lbl = {"vm": "Esfuerzo maximo", "u": "Desplazamiento maximo",
               "uz": "Uz maximo"}.get(field, "Maximo")
        if avg:
            txt = (f"Esfuerzo maximo (promediado, r = {avg['radius'] / kl:.2g} {u.L}) = "
                   f"{avg['vm'] / ks:.4g} {unit}\npico puntual {avg['vm_point'] / ks:.4g} {unit} "
                   f"(depende de la malla)")
        else:
            txt = f"{lbl} = {val[k]:.4g} {unit}   (nodo {ids[k]})"
        ax.text2D(0.02, 0.93, txt,
                  transform=ax.transAxes, fontsize=9, color="#7a1010", fontweight="bold",
                  va="top", bbox=dict(boxstyle="round,pad=0.35", fc="#fff3e0", ec="#d62728", lw=1.0))
    ax.set_axis_off()                     # sin ejes ni reglas
    ax.set_title(f"{title}  ({unit})"
                 + (f"   —  deformada ×{scale:g}" if scale > 0 else ""),
                 fontsize=9, loc="left")
    mapper.set_array(face_val)
    return mapper


# ============================================================ solo geometria
def _clean_poly(poly):
    pts = list(poly)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts = pts[:-1]
    return pts


def _prism(poly, z0, z1, cap=True):
    """Caras (lista de poligonos 3D) de un prisma vertical sobre un poligono 2D."""
    pts = _clean_poly(poly)
    faces = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        faces.append([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)])
    if cap and n >= 3:
        faces.append([(x, y, z1) for x, y in pts])
        faces.append([(x, y, z0) for x, y in pts])
    return faces


def _rot_matrix(tilt_x, tilt_y):
    """Misma matriz que Loads.eff(): R = Ry(tilt_y)·Rx(tilt_x)."""
    cx, sx = math.cos(math.radians(tilt_x)), math.sin(math.radians(tilt_x))
    cy, sy = math.cos(math.radians(tilt_y)), math.sin(math.radians(tilt_y))
    return np.array([[cy, sy * sx, sy * cx], [0.0, cx, -sx], [-sy, cy * sx, cy * cx]])


def _tilted_prism(poly, H, R, cap=True):
    """Prisma de altura axial H sobre `poly` (en el plano de la seccion), inclinado
    con la matriz R y CORTADO al ras de la placa (z = 0): la base de la columna es
    un corte a bisel que apoya plano sobre la placa."""
    pts = _clean_poly(poly)
    n = len(pts)
    bot, top = [], []
    for (x, y) in pts:
        v0 = R @ np.array([x, y, 0.0])
        t0 = -v0[2] / R[2, 2]                      # eje de la columna donde z = 0
        bot.append(tuple(R @ np.array([x, y, t0])))
        top.append(tuple(R @ np.array([x, y, H])))
    faces = [[bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]] for i in range(n)]
    if cap and n >= 3:
        faces.append(list(top))
        faces.append(list(bot))
    return faces


def _plate_top_mesh(prj, holes, zt):
    """Triangulos de la cara superior de la placa con los agujeros REALMENTE vacios:
    Delaunay sobre contorno, aros de agujero y una rejilla interior; se descartan los
    triangulos cuyo centro cae dentro de un agujero."""
    from scipy.spatial import Delaunay
    from . import geometry as G
    p = prj.plate
    outer = _clean_poly(G.plate_outline(prj))
    pts = [tuple(q) for q in outer]
    xs = [q[0] for q in outer]; ys = [q[1] for q in outer]
    # refina el contorno
    if p.shape != "Circular":
        m = 10
        pts = []
        for i in range(len(outer)):
            a, b = outer[i], outer[(i + 1) % len(outer)]
            pts += [(a[0] + (b[0] - a[0]) * k / m, a[1] + (b[1] - a[1]) * k / m) for k in range(m)]
    step = max(max(xs) - min(xs), max(ys) - min(ys)) / 14.0
    circ = p.shape == "Circular"
    R = p.Dp / 2 if circ else 0
    gx = np.arange(min(xs) + step / 2, max(xs), step)
    gy = np.arange(min(ys) + step / 2, max(ys), step)
    for x in gx:
        for y in gy:
            if circ and x * x + y * y > (R - step * 0.4) ** 2:
                continue
            pts.append((float(x), float(y)))
    for (cx, cy, r) in holes:
        for a in np.linspace(0, 2 * math.pi, 25)[:-1]:
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    P = np.array(pts)
    # descarta puntos interiores demasiado cerca de un agujero (dentro del hueco)
    keep = np.ones(len(P), bool)
    for (cx, cy, r) in holes:
        d = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
        keep &= ~(d < r * 0.98)
    P = P[keep]
    tri = Delaunay(P)
    out = []
    for s_ in tri.simplices:
        c = P[s_].mean(axis=0)
        if any(math.hypot(c[0] - cx, c[1] - cy) < r for (cx, cy, r) in holes):
            continue
        if circ and math.hypot(c[0], c[1]) > R:
            continue
        out.append([(P[k][0], P[k][1], zt) for k in s_])
    return out


def geometry_faces(prj):
    """Piezas de la conexion como caras 3D (pulgadas).
    -> lista de (grupo, caras, color, alfa); grupo: 'conc' | 'below' | 'plate' | 'above'.
    No requiere Gmsh ni CalculiX."""
    from . import geometry as G
    p, b, st, lug = prj.plate, prj.bolts, prj.stiff, prj.lug
    s = prj.section.shape()
    g = b.geom()
    parts = []
    bpos = G.bolt_positions(prj)

    # ---- placa con agujeros
    holes = [(bx, by, g.dh / 2) for bx, by in bpos]
    top = _plate_top_mesh(prj, holes, p.tp)
    bot = [[(x, y, 0.0) for x, y, _ in t] for t in top]
    side = _prism(G.plate_outline(prj), 0.0, p.tp, cap=False)
    wall = []
    for (cx, cy, r) in holes:
        ring = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 25)[:-1]]
        wall += _prism(ring, 0.0, p.tp, cap=False)
    parts.append(("plate", top + bot, "#9aa5b1", 1.0, "flat"))
    parts.append(("plate", side, "#9aa5b1", 1.0))
    parts.append(("plate", wall, "#3b434b", 1.0))

    # ---- pernos (vastago inferior / parte sobre la placa) y tuercas
    low, up, nuts, ends = [], [], [], []
    hef = max(float(b.hef), 1.0)
    eh = float(b.eh) if b.eh and b.eh > 0 else 3.0 * g.db
    kind = ("gancho_L" if "en L" in b.atype else "gancho_J" if "en J" in b.atype
            else "recto" if b.atype.startswith("Recto") else "cabeza")
    for (bx, by) in bpos:
        r = g.db / 2
        c = [(bx + r * math.cos(a), by + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 17)[:-1]]
        low += _prism(c, -hef, 0.0, cap=True)
        # extremo embebido segun el tipo de anclaje
        if kind == "cabeza":                       # cabeza hexagonal pesada
            F = max(g.Fhex, 1.5 * g.db)
            hr = F / math.sqrt(3.0)
            hx = [(bx + hr * math.cos(math.radians(60 * k)), by + hr * math.sin(math.radians(60 * k)))
                  for k in range(6)]
            ends += _prism(hx, -hef - 0.7 * g.db, -hef)
        elif kind in ("gancho_L", "gancho_J"):     # doblez hacia el exterior (radial)
            n = math.hypot(bx, by)
            ux, uy = (bx / n, by / n) if n > 1e-6 else (1.0, 0.0)
            px, py = -uy, ux
            L = eh

            # pata horizontal como prisma rectangular de seccion db x db
            def q(s, t, z):
                return (bx + ux * s + px * t, by + uy * s + py * t, z)
            s0, s1, t0, t1 = -r, L, -r, r
            z0, z1 = -hef - r, -hef + r
            ends += [[q(s0, t0, z0), q(s1, t0, z0), q(s1, t1, z0), q(s0, t1, z0)],
                     [q(s0, t0, z1), q(s1, t0, z1), q(s1, t1, z1), q(s0, t1, z1)],
                     [q(s0, t0, z0), q(s1, t0, z0), q(s1, t0, z1), q(s0, t0, z1)],
                     [q(s0, t1, z0), q(s1, t1, z0), q(s1, t1, z1), q(s0, t1, z1)],
                     [q(s1, t0, z0), q(s1, t1, z0), q(s1, t1, z1), q(s1, t0, z1)],
                     [q(s0, t0, z0), q(s0, t1, z0), q(s0, t1, z1), q(s0, t0, z1)]]
            if kind == "gancho_J":                  # pata corta hacia arriba en el extremo
                h = min(1.5 * g.db + eh * 0.5, 0.5 * hef)
                ends += [[q(s1 - 2 * r, t0, z1), q(s1, t0, z1), q(s1, t0, z1 + h), q(s1 - 2 * r, t0, z1 + h)],
                         [q(s1 - 2 * r, t1, z1), q(s1, t1, z1), q(s1, t1, z1 + h), q(s1 - 2 * r, t1, z1 + h)],
                         [q(s1 - 2 * r, t0, z1), q(s1 - 2 * r, t1, z1), q(s1 - 2 * r, t1, z1 + h), q(s1 - 2 * r, t0, z1 + h)],
                         [q(s1, t0, z1), q(s1, t1, z1), q(s1, t1, z1 + h), q(s1, t0, z1 + h)],
                         [q(s1 - 2 * r, t0, z1 + h), q(s1, t0, z1 + h), q(s1, t1, z1 + h), q(s1 - 2 * r, t1, z1 + h)]]
        up += _prism(c, 0.0, p.tp + 1.25 * g.db, cap=True)
        hexr = 0.9 * g.db
        hx = [(bx + hexr * math.cos(math.radians(60 * k)), by + hexr * math.sin(math.radians(60 * k)))
              for k in range(6)]
        nuts += _prism(hx, p.tp, p.tp + 0.875 * g.db)
    parts.append(("below", low, "#c9a227", 1.0))
    parts.append(("below", ends, "#a8861c", 1.0))
    parts.append(("above", up, "#c9a227", 1.0))
    parts.append(("above", nuts, "#8d7514", 1.0))

    # ---- columna (inclinada y con la base cortada a bisel sobre la placa)
    H = max(3.0 * s.d, 12.0)
    R = _rot_matrix(prj.loads.tilt_x, prj.loads.tilt_y)
    col = []
    if prj.section.generic:
        for poly in G.section_rects(prj):
            col += _tilted_prism(poly, H, R)
    else:
        ext, inn = G.profile_outline(prj)
        col += _tilted_prism(ext, H, R, cap=not inn)
        if inn:
            col += _tilted_prism(inn, H, R, cap=False)
            e, i_ = _clean_poly(ext), _clean_poly(inn)
            if len(e) == len(i_):                    # corona superior del tubo
                for k in range(len(e)):
                    k2 = (k + 1) % len(e)
                    q = [tuple(R @ np.array([x, y, H])) for x, y in (e[k], e[k2], i_[k2], i_[k])]
                    col.append(q)
    col = [[(x, y, z + p.tp) for x, y, z in f] for f in col]
    parts.append(("above", col, "#4c78a8", 1.0))

    # ---- rigidizadores (solo columna vertical)
    if st.enabled and st.count > 0 and not prj.loads.tilted:
        prof2d = st.outline()[:-1]
        faces = []
        for (x1, y1, x2, y2) in G.stiffener_lines(prj):
            ang = math.atan2(y2 - y1, x2 - x1)
            ca, sa = math.cos(ang), math.sin(ang)

            def T(u, v, w):
                return (x1 + u * ca - w * sa, y1 + u * sa + w * ca, p.tp + v)
            w = st.t / 2
            for i, (u0, v0) in enumerate(prof2d):
                u1, v1 = prof2d[(i + 1) % len(prof2d)]
                faces.append([T(u0, v0, -w), T(u1, v1, -w), T(u1, v1, w), T(u0, v0, w)])
            faces.append([T(u, v, w) for u, v in prof2d])
            faces.append([T(u, v, -w) for u, v in prof2d])
        parts.append(("above", faces, "#59a14f", 1.0))

    # ---- llave de corte (bajo la placa)
    if lug.enabled:
        faces = []
        for poly in G.lug_outline(prj):
            faces += _prism(poly, -lug.H, 0.0)
        parts.append(("below", faces, "#e15759", 1.0))

    # ---- pedestal de concreto (transparente)
    c = prj.conc
    ped = [(-c.B2 / 2, -c.N2 / 2), (c.B2 / 2, -c.N2 / 2), (c.B2 / 2, c.N2 / 2), (-c.B2 / 2, c.N2 / 2)]
    zc = -min(c.ha, max(b.hef * 1.15, 12.0))
    conc = _prism(ped, zc, 0.0, cap=False)                 # caras laterales
    conc.append([(x, y, zc) for x, y in ped])              # fondo (sin tapa: apoya la placa)
    parts.append(("conc", conc, "#a9b4bd", 0.16))          # UNICO elemento translucido
    return parts


_GROUP_ORDER_ABOVE = {"conc": 10, "below": 2, "plate": 3, "above": 4}


def update_order(ax):
    """Ordena el dibujo segun la camara: vista desde arriba -> lo de abajo se pinta
    primero y la placa lo tapa; desde abajo, al reves."""
    colls = getattr(ax, "_pb_groups", None)
    if not colls:
        return
    from_above = ax.elev >= 0
    for grp, coll in colls:
        z = _GROUP_ORDER_ABOVE[grp]          # el concreto (translucido) va siempre al final
        if not from_above and grp in ("below", "above"):
            z = 6 - z                                   # above <-> below invertidos
        coll.set_zorder(z)


def plot_geometry(ax, prj, show_concrete=True):
    """Dibuja el conjunto de la conexion (solo geometria) en un eje 3D."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.colors import to_rgb

    ax.clear()
    try:
        ax.computed_zorder = False           # respeta el orden de los grupos
    except Exception:
        pass
    u = prj.units()
    kl = u.fl
    groups = []
    allp = []
    for part in geometry_faces(prj):
        grp, faces, color, alpha = part[:4]
        flat = len(part) > 4 and part[4] == "flat"
        if not faces or (grp == "conc" and not show_concrete):
            continue
        v = [[(x / kl, y / kl, z / kl) for x, y, z in f] for f in faces]
        allp += [pt for f in v for pt in f]      # incluye el concreto: si no, queda fuera del encuadre
        rgb = to_rgb(color)
        # los triangulos de la malla de la placa no llevan aristas
        edge = (*rgb, 1.0) if flat else ((0, 0, 0, 0.35) if alpha > 0.5 else (0.3, 0.35, 0.4, 0.35))
        coll = Poly3DCollection(v, facecolors=(*rgb, alpha), edgecolors=edge,
                                linewidths=0.35)
        ax.add_collection3d(coll)
        groups.append((grp, coll))
    ax._pb_groups = groups
    update_order(ax)

    P = np.array(allp, dtype=float)
    mins, maxs = P.min(axis=0), P.max(axis=0)
    spans = np.maximum(maxs - mins, 1e-6)
    pad = 0.03 * float(spans.max())
    ax.set_xlim(mins[0] - pad, maxs[0] + pad)
    ax.set_ylim(mins[1] - pad, maxs[1] + pad)
    ax.set_zlim(mins[2] - pad, maxs[2] + pad)
    set_aspect(ax, tuple(float(v) + 2 * pad for v in spans))
    ax.set_axis_off()                     # sin ejes ni reglas
    tl = prj.loads
    ax.set_title("Geometria de la conexion"
                 + (f"   —   columna inclinada  X {tl.tilt_x:g}°, Y {tl.tilt_y:g}°"
                    if tl.tilted else ""), fontsize=9, loc="left")


def render_result_png(res: Result3D, prj, field: str, path: str, scale: float = 0.0,
                      size=(7.0, 4.6), dpi=150):
    """Imagen de un campo de resultados 3D con la etiqueta del maximo (para el reporte).
    -> (ruta, valor_maximo, nodo) o (None, 0, 0)."""
    import matplotlib
    from matplotlib.figure import Figure
    try:
        fig = Figure(figsize=size, dpi=dpi)
        ax = fig.add_axes([0.0, 0.0, 0.87, 0.93], projection="3d")
        m = plot3d(ax, res, prj, field, scale, tag_max=True)
        ax.view_init(elev=24, azim=-58)
        fit_to_axes(ax)
        if m is not None:
            cax = fig.add_axes([0.90, 0.16, 0.02, 0.66])
            fig.colorbar(m, cax=cax)
        fig.savefig(path)
        return path
    except Exception:
        return None


# ====================================== esfuerzo promediado en la placa (convergente)
def _covered_by_profile(prj, x, y):
    """True si (x, y) esta bajo el metal del perfil (union placa-perfil)."""
    from . import geometry as G
    if prj.section.generic:
        return any(G._inside(x, y, poly) for poly in G.section_rects(prj))
    ext, inn = G.profile_outline(prj)
    if not G._inside(x, y, ext):
        return False
    return not (inn and G._inside(x, y, inn))


def smoothed_face_fields(res: "Result3D", prj, radius: float = 0.0):
    """Campo de von Mises PROMEDIADO nodo a nodo en cada cara de la placa (ver smoothed_plate_vm).
    -> dict(radius, top=dict(xy, vm, vm_point, z), bot=dict(...)); una cara ausente no aparece.
    xy: (n,2) nodos usados; vm: von Mises del tensor promediado en el circulo de radio r alrededor de
    cada nodo; vm_point: von Mises puntual del nodo."""
    import numpy as np
    from scipy.spatial import Delaunay, cKDTree
    from . import geometry as G

    tp = prj.plate.tp
    r = radius if radius and radius > 0 else tp
    g = prj.bolts.geom()
    bolts = np.array(G.bolt_positions(prj), dtype=float).reshape(-1, 2)
    r_hole = g.dh / 2.0
    tol = 1e-4

    ids = [n for n in res.nodes if n in res.stress]
    out = dict(radius=float(r))
    if not ids:
        return out
    P = np.array([res.nodes[n] for n in ids], dtype=float)
    S = np.array([res.stress[n] for n in ids], dtype=float)

    def in_hole(x, y):
        return bolts.size > 0 and bool(np.any(np.hypot(bolts[:, 0] - x, bolts[:, 1] - y) < r_hole - 1e-6))

    for name, zl, is_top in (("bot", 0.0, False), ("top", tp, True)):
        sel = np.where(np.abs(P[:, 2] - zl) < tol)[0]
        if is_top:
            sel = np.array([k for k in sel if not _covered_by_profile(prj, P[k, 0], P[k, 1])], dtype=int)
        if len(sel) < 4:
            continue
        xy = P[sel, :2]
        tri = Delaunay(xy)
        w = np.zeros(len(sel))
        for s_ in tri.simplices:
            a, b, c = xy[s_[0]], xy[s_[1]], xy[s_[2]]
            cen = (a + b + c) / 3.0
            if in_hole(cen[0], cen[1]):
                continue
            if is_top and _covered_by_profile(prj, cen[0], cen[1]):
                continue
            ar = 0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if ar > 50.0 * (r * r):                # triangulo espurio que cruza vacios grandes
                continue
            w[s_] += ar / 3.0
        keep = w > 0
        if keep.sum() < 4:
            continue
        idx = sel[keep]; xyk = xy[keep]; wk = w[keep]; Sk = S[idx]
        tree = cKDTree(xyk)
        vm_pt = np.array([von_mises(*s) for s in Sk])
        vm_sm = np.empty(len(idx))
        for i in range(len(idx)):
            nb = tree.query_ball_point(xyk[i], r)
            ww = wk[nb]
            vm_sm[i] = von_mises(*((Sk[nb] * ww[:, None]).sum(axis=0) / ww.sum()))
        out[name] = dict(xy=xyk, vm=vm_sm, vm_point=vm_pt, z=float(zl))
    return out


def smoothed_plate_vm(res: "Result3D", prj, radius: float = 0.0):
    """Esfuerzo de von Mises PROMEDIADO en la placa, para leer un maximo que no dependa
    de la malla.  El von Mises puntual crece sin limite al refinar en las aristas vivas
    (borde de agujero, pie del perfil); en cambio el promedio ponderado por area sobre
    un circulo de radio fijo (por defecto el espesor de la placa) SI converge.

    Se promedia el TENSOR de esfuerzos (no el von Mises) y solo entre nodos de la misma
    cara (superior o inferior de la placa), para no anular la flexion a traves del
    espesor.  La cara superior excluye lo cubierto por el perfil.  Los pesos son el area
    tributaria de cada nodo (triangulacion de la cara), asi la densidad de la malla no
    sesga el promedio.

    -> dict(vm=maximo promediado, x, y, z, radius, vm_point=maximo puntual de la misma
    zona, n=nodos) o None."""
    import numpy as np
    F = smoothed_face_fields(res, prj, radius)
    best = None
    for name in ("bot", "top"):
        f = F.get(name)
        if f is None:
            continue
        i = int(np.argmax(f["vm"]))
        if best is None or f["vm"][i] > best["vm"]:
            best = dict(vm=float(f["vm"][i]), x=float(f["xy"][i][0]), y=float(f["xy"][i][1]),
                        z=f["z"], radius=F["radius"], vm_point=0.0, n=0)
    if best is not None:
        for name in ("bot", "top"):
            f = F.get(name)
            if f is not None:
                best["vm_point"] = max(best["vm_point"], float(f["vm_point"].max()))
                best["n"] += int(len(f["vm"]))
    return best
