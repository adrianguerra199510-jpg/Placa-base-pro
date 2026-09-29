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
def plot3d(ax, res: Result3D, prj, field="vm", scale=0.0, shrink_tris=12000):
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
        title, cmap, unit = "Desplazamiento |U|", "viridis", u.L
    elif field == "uz":
        val = np.array([res.disp.get(n, (0, 0, 0))[2] for n in ids]) / kl
        title, cmap, unit = "Desplazamiento vertical Uz", "coolwarm", u.L
    else:
        val = np.array([res.vm.get(n, 0.0) for n in ids]) / ks
        title, cmap, unit = "Esfuerzo de von Mises", "inferno", u.S

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
                            edgecolors=(0, 0, 0, 0.10), linewidths=0.12)
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
    try:
        ax.set_box_aspect(tuple(float(v) + 2 * pad for v in spans), zoom=0.92)
    except TypeError:
        ax.set_box_aspect(tuple(float(v) + 2 * pad for v in spans))
    except Exception:
        pass
    ax.set_xlabel(f"X ({u.L})"); ax.set_ylabel(f"Y ({u.L})")
    ax.set_zlabel(f"Z ({u.L})")
    ax.set_title(f"{title}  ({unit})"
                 + (f"   —  deformada ×{scale:g}" if scale > 0 else ""),
                 fontsize=9, loc="left")
    mapper.set_array(face_val)
    return mapper
