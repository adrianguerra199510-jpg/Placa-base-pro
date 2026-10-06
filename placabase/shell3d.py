# -*- coding: utf-8 -*-
"""
Motor de PLACAS (elementos shell S6 de CalculiX) de la conexion — alternativa al solido 3D.

Cada pieza de acero se modela por su superficie media con un elemento de placa (triangulo cuadratico S6,
Reissner-Mindlin):

  · placa base   en z = tp/2   (espesor tp, agujeros taladrados, sin arandelas),
  · paredes del perfil (alas y alma, caras de un HSS, cuerdas de un tubo, rectangulos de una seccion generica)
    como superficies verticales por su linea media, desde z = tp/2 hasta el tope,
  · rigidizadores como placas verticales (su contorno real) unidas a la placa y a la pared,
  · llave de corte como resortes horizontales en los nodos de la placa bajo su huella.

El concreto son resortes de Winkler solo a compresion (rigidez por area tributaria) y cada perno un resorte
solo a traccion (mas los horizontales) en la corona de apoyo de la tuerca, igual que en el solido.  Las cargas
entran por un nodo de referencia acoplado al tope del perfil.

HUELLA BAJO EL PERFIL.  La union paredes-placa comparte los nodos de la linea media, pero un shell no tiene el
espesor del ala: la placa bajo el ala (y la bajo la pletina) trabaja solida con ella.  Por eso los nodos de la
placa dentro de la huella del perfil / de la pletina se ligan (*EQUATION, traslaciones) al nodo mas cercano de la
linea media de la pared.  Sin esa ligadura el shell sobrestima la traccion de los pernos en ~30 %; con ella
queda a -12 ... +5 % del solido en los casos de comparacion (ver LEEME).

Resultados: el .frd de CalculiX trae los nodos EXPANDIDOS de cada shell (cara superior, media e inferior); sus
esfuerzos dan el von Mises de cada cara de la placa, de modo que el resto del programa (von Mises promediado,
mapas en planta, soldadura, pernos, memoria) funciona igual que con el solido.
"""
from __future__ import annotations
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from .model import Project
from . import geometry as G
from .units import ES_KSI, NU_STEEL, Ec_ksi
from .params3d import shear_arm, foundation_ks, bolt_kb, washer_radius

CANCELADO = "Analisis cancelado por el usuario."


# ============================================================================ geometria
def profile_walls(prj: Project):
    """Paredes del perfil: [(nombre, (x1,y1), (x2,y2), espesor)] en coordenadas de la placa."""
    from .weld3d import _walls
    return [(n, a, b, t) for (n, a, b, t, _spec) in _walls(prj)]


def _inside(x, y, poly):
    return G._inside(x, y, poly)


def stiffener_plates(prj: Project, walls):
    """Rigidizadores como placas verticales.  -> [dict(pts3d, base=((x,y),(x,y)), t, rect=[4 pts])]
    El borde que toca el perfil se prolonga hasta la linea media de la pared para que quede unido a ella."""
    st = prj.stiff
    if not (st.enabled and st.count > 0) or prj.section.generic:
        return []
    out = []
    tpm = prj.plate.tp / 2.0
    outline = st.outline()[:-1]
    c = max(0.0, min(st.clip_root, 0.45 * min(st.L, st.h)))
    for (x1, y1, x2, y2) in G.stiffener_lines(prj):
        Ls = math.hypot(x2 - x1, y2 - y1)
        if Ls < 1e-6:
            continue
        ux, uy = (x2 - x1) / Ls, (y2 - y1) / Ls
        # espesor de la pared a la que se pega: la mas cercana a (x1, y1)
        best, tw = 1e18, 0.5
        for (_n, (ax, ay), (bx, by), t) in walls:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            tt = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x1 - ax) * dx + (y1 - ay) * dy) / L2))
            d = math.hypot(x1 - ax - tt * dx, y1 - ay - tt * dy)
            if d < best:
                best, tw = d, t
        d_in = min(tw / 2.0, 0.9 * max(st.L, 0.1))
        pts = []
        for (xl, yl) in outline:
            xe = -d_in if abs(xl) < 1e-9 else xl
            pts.append((x1 + ux * xe, y1 + uy * xe, tpm + yl))
        nx, ny = -uy, ux
        h = st.t / 2.0
        rect = [(x1 + ux * c + nx * h, y1 + uy * c + ny * h), (x2 + nx * h, y2 + ny * h),
                (x2 - nx * h, y2 - ny * h), (x1 + ux * c - nx * h, y1 + uy * c - ny * h)]
        out.append(dict(pts3d=pts, base=((x1 + ux * c, y1 + uy * c), (x2, y2)), t=st.t, rect=rect))
    return out


def footprints(prj: Project, stiff):
    """Poligonos cerrados de la huella (para insertar sus bordes en la malla de la placa y ligar sus nodos):
    la del perfil (exterior, interior) y las bases de las pletinas.  -> [(poly, hueco|None)]"""
    out = []
    if prj.section.generic:
        for poly in G.section_rects(prj):
            out.append((poly[:-1], None))
    else:
        ext, inn = G.profile_outline(prj)
        out.append((ext[:-1] if ext[0] == ext[-1] else ext, (inn[:-1] if inn and inn[0] == inn[-1] else inn)))
    for s in stiff:
        out.append((s["rect"], None))
    return out


def on_footprint_edges(x, y, fps, tol=1e-5):
    """True si (x, y) esta sobre un borde de la huella (los nodos que la malla coloca a lo largo de las
    lineas insertadas).  Solo esos nodos se ligan: los interiores de una franja angosta no existen o sobrerrigidizan."""
    for poly, hole in fps:
        for pl in ([poly] + ([hole] if hole else [])):
            n = len(pl)
            for i in range(n):
                a, b = pl[i], pl[(i + 1) % n]
                if _seg_dist(x, y, a[0], a[1], b[0], b[1]) < tol:
                    return True
    return False


def make_spec(prj: Project, lc: float) -> dict:
    """Descripcion JSON de la geometria para el mallador (se ejecuta en un proceso hijo)."""
    p, b = prj.plate, prj.bolts
    s = prj.section.shape()
    g = b.geom()
    H = max(3.0 * s.d, 12.0)
    walls = profile_walls(prj)
    stiff = stiffener_plates(prj, walls)
    fps = footprints(prj, stiff)
    tmin = min([w[3] for w in walls] + [st["t"] for st in stiff] + [p.tp])
    rw = washer_radius(prj)
    return dict(
        lc=lc, tp=p.tp, circ=(p.shape == "Circular"), Dp=p.Dp, N=p.N, B=p.B,
        bolts=[list(q) for q in G.bolt_positions(prj)], rh=g.dh / 2.0, rw=rw,
        H=H, walls=[dict(name=n, p1=list(a), p2=list(c), t=t) for (n, a, c, t) in walls],
        stiff=[dict(pts3d=[list(q) for q in st["pts3d"]], base=[list(q) for q in st["base"]], t=st["t"])
               for st in stiff],
        foot=[[list(q) for q in poly] for poly, hole in fps]
             + [[list(q) for q in hole] for poly, hole in fps if hole],
        tmin=tmin)


# ============================================================================ mallador (proceso hijo)
def mesh_child(spec_path: str, out_path: str) -> int:
    """Malla la superficie media con la API de Gmsh y escribe un JSON con nodos y elementos S6 por grupo."""
    import gmsh
    sp = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    tp, tpm, lc = sp["tp"], sp["tp"] / 2.0, sp["lc"]
    gmsh.initialize(["gmsh", "-nopopup"], interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", max(1, (os.cpu_count() or 2) - 1))
        occ = gmsh.model.occ
        gmsh.model.add("shell")
        inputs, names = [], []
        # ---- placa
        if sp["circ"]:
            pl = occ.addDisk(0, 0, tpm, sp["Dp"] / 2, sp["Dp"] / 2)
        else:
            pl = occ.addRectangle(-sp["B"] / 2, -sp["N"] / 2, tpm, sp["B"], sp["N"])
        holes = [occ.addDisk(x, y, tpm, sp["rh"], sp["rh"]) for (x, y) in sp["bolts"]]
        if holes:
            res, _ = occ.cut([(2, pl)], [(2, h) for h in holes])
            plate = res
        else:
            plate = [(2, pl)]
        inputs += plate
        names += ["plate"] * len(plate)
        # ---- paredes del perfil
        ztop = tp + sp["H"]
        for i, w in enumerate(sp["walls"]):
            (x1, y1), (x2, y2) = w["p1"], w["p2"]
            pts = [occ.addPoint(x1, y1, tpm), occ.addPoint(x2, y2, tpm),
                   occ.addPoint(x2, y2, ztop), occ.addPoint(x1, y1, ztop)]
            ls = [occ.addLine(pts[k], pts[(k + 1) % 4]) for k in range(4)]
            inputs.append((2, occ.addPlaneSurface([occ.addCurveLoop(ls)])))
            names.append(f"wall{i}")
        # ---- rigidizadores
        for j, st in enumerate(sp["stiff"]):
            pts = [occ.addPoint(*q) for q in st["pts3d"]]
            ls = [occ.addLine(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))]
            inputs.append((2, occ.addPlaneSurface([occ.addCurveLoop(ls)])))
            names.append(f"stiff{j}")
        # ---- bordes de la huella embebidos en la placa
        nplate_inputs = len(inputs)
        for poly in sp["foot"]:
            pts = [occ.addPoint(x, y, tpm) for (x, y) in poly]
            for k in range(len(pts)):
                inputs.append((1, occ.addLine(pts[k], pts[(k + 1) % len(pts)])))
                names.append("foot")
        occ.synchronize()
        out, outmap = occ.fragment(inputs[:nplate_inputs], inputs[nplate_inputs:])
        occ.synchronize()
        part_of = {}
        for (dt, nm) in zip(inputs[:nplate_inputs], names[:nplate_inputs]):
            pass
        for k, nm in enumerate(names[:nplate_inputs]):
            for (d, t) in outmap[k]:
                if d == 2:
                    part_of[t] = nm
        # ---- tamano de malla
        hh = max(0.06, (sp["rw"] - sp["rh"]) / 2.5)
        tb = sp["tmin"]
        f = 0
        curves_h = []
        for (x, y) in sp["bolts"]:
            r = sp["rw"] + 0.05
            for (d, t) in gmsh.model.getEntitiesInBoundingBox(x - r, y - r, tpm - 1e-3, x + r, y + r, tpm + 1e-3, 1):
                curves_h.append(t)
        fields = []
        if curves_h:
            f += 1; gmsh.model.mesh.field.add("Distance", f)
            gmsh.model.mesh.field.setNumbers(f, "CurvesList", curves_h)
            gmsh.model.mesh.field.setNumber(f, "Sampling", 40)
            f += 1; gmsh.model.mesh.field.add("Threshold", f)
            gmsh.model.mesh.field.setNumber(f, "InField", f - 1)
            gmsh.model.mesh.field.setNumber(f, "SizeMin", hh)
            gmsh.model.mesh.field.setNumber(f, "SizeMax", lc)
            gmsh.model.mesh.field.setNumber(f, "DistMin", 0.1)
            gmsh.model.mesh.field.setNumber(f, "DistMax", 0.1 + 4 * hh)
            fields.append(f)
        # lineas de union paredes-placa: elementos de ~lc/3 (al menos 1.2 veces el espesor)
        base_curves = []
        for (d, t) in gmsh.model.getEntities(1):
            bb = gmsh.model.getBoundingBox(d, t)
            if abs(bb[2] - tpm) < 1e-6 and abs(bb[5] - tpm) < 1e-6:
                base_curves.append(t)
        if base_curves:
            f += 1; gmsh.model.mesh.field.add("Distance", f)
            gmsh.model.mesh.field.setNumbers(f, "CurvesList", base_curves)
            gmsh.model.mesh.field.setNumber(f, "Sampling", 40)
            f += 1; gmsh.model.mesh.field.add("Threshold", f)
            gmsh.model.mesh.field.setNumber(f, "InField", f - 1)
            gmsh.model.mesh.field.setNumber(f, "SizeMin", max(1.2 * tb, lc / 3.0))
            gmsh.model.mesh.field.setNumber(f, "SizeMax", lc)
            gmsh.model.mesh.field.setNumber(f, "DistMin", 1.5 * tb)
            gmsh.model.mesh.field.setNumber(f, "DistMax", 1.5 * tb + 2.0 * lc)
            fields.append(f)
        if fields:
            f += 1; gmsh.model.mesh.field.add("Min", f)
            gmsh.model.mesh.field.setNumbers(f, "FieldsList", fields)
            gmsh.model.mesh.field.setAsBackgroundMesh(f)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", lc)
        gmsh.option.setNumber("Mesh.MeshSizeMin", min(hh, lc / 3.0) * 0.8)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.mesh.generate(2)
        nt, nc, _ = gmsh.model.mesh.getNodes()
        nodes = {int(i): [float(nc[3 * k]), float(nc[3 * k + 1]), float(nc[3 * k + 2])] for k, i in enumerate(nt)}
        groups = {}
        for (d, t) in gmsh.model.getEntities(2):
            et, en, enn = gmsh.model.mesh.getElements(2, t)
            if not len(et):
                continue
            if et[0] != 9:
                raise RuntimeError(f"tipo de elemento inesperado {et[0]}")
            nm = part_of.get(t)
            if nm is None:
                bb = gmsh.model.getBoundingBox(d, t)
                nm = "plate" if abs(bb[2] - tpm) < 1e-6 and abs(bb[5] - tpm) < 1e-6 else "plate?"
            arr = [int(x) for x in enn[0]]
            groups.setdefault(nm, []).extend([arr[6 * k:6 * k + 6] for k in range(len(arr) // 6)])
    finally:
        gmsh.finalize()
    Path(out_path).write_text(json.dumps(dict(nodes=nodes, groups=groups)), encoding="utf-8")
    return 0 if Path(out_path).exists() else 3


# ============================================================================ modelo de CalculiX
def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def build_inp(prj: Project, mesh: dict, out_inp: str, spec: dict) -> dict:
    """Escribe el .inp (shells S6, resortes, ligaduras y paso estatico) y devuelve el `meta` del postproceso."""
    p, b = prj.plate, prj.bolts
    g = b.geom()
    tp, tpm = p.tp, p.tp / 2.0
    ztop = tp + spec["H"]
    nodes = {int(k): tuple(v) for k, v in mesh["nodes"].items()}
    groups = {k: v for k, v in mesh["groups"].items()}
    if "plate?" in groups:
        groups.setdefault("plate", []).extend(groups.pop("plate?"))
    plate_el = groups.get("plate", [])
    used = set()
    for lst in groups.values():
        for c in lst:
            used.update(c)
    nodes = {n: nodes[n] for n in used}
    plate_nodes = set(n for c in plate_el for n in c)

    ks = foundation_ks(prj)
    kb = bolt_kb(prj)
    Lb = max(b.hef + tp + p.grout, 1.0)
    kbh = ES_KSI / (2.0 * (1.0 + NU_STEEL)) * g.Ase / Lb
    Ec = Ec_ksi(prj.conc.fc)

    # ---- area tributaria de cada nodo de la placa (regla del punto medio: A/3 en los nodos de lado)
    wts = {}
    for c in plate_el:
        a, bq, cc = nodes[c[0]], nodes[c[1]], nodes[c[2]]
        A = 0.5 * abs((bq[0] - a[0]) * (cc[1] - a[1]) - (bq[1] - a[1]) * (cc[0] - a[0]))
        for n in c[3:6]:
            wts[n] = wts.get(n, 0.0) + A / 3.0

    # ---- llave de corte: resortes horizontales en la huella (el concreto no apoya bajo ella)
    lug_polys = G.lug_outline(prj)
    lug_nodes = []
    if lug_polys:
        for n in plate_nodes:
            x, y, _z = nodes[n]
            if any(_inside(x, y, poly) for poly in lug_polys):
                lug_nodes.append(n)
        for n in lug_nodes:
            wts.pop(n, None)

    # ---- coronas de apoyo de la tuerca
    r_h, r_w = g.dh / 2.0, washer_radius(prj)
    pos = G.bolt_positions(prj)
    rings = {}
    for k, (bx, by) in enumerate(pos, start=1):
        d = sorted((math.hypot(nodes[n][0] - bx, nodes[n][1] - by), n) for n in plate_nodes)
        d = [(r_, n) for r_, n in d if r_ >= r_h - 1e-6]
        ring = [n for r_, n in d if r_ <= r_w + 1e-6]
        if len(ring) < 4:
            ring = [n for _, n in d[:4]]
        rings[k] = sorted(ring)

    # ---- nodos de la linea media (union pared-placa) y ligadura de la huella
    segs = [(w["p1"], w["p2"]) for w in spec["walls"]] + [(tuple(s_["base"][0]), tuple(s_["base"][1]))
                                                         for s_ in spec["stiff"]]
    centers = []
    for n in plate_nodes:
        x, y, _z = nodes[n]
        if any(_seg_dist(x, y, a[0], a[1], c[0], c[1]) < 1e-5 for a, c in segs):
            centers.append(n)
    cset = set(centers)
    fps = footprints(prj, stiffener_plates(prj, profile_walls(prj)))
    eqs = []
    if centers:
        from scipy.spatial import cKDTree
        cxy = np.array([nodes[n][:2] for n in centers])
        tree = cKDTree(cxy)
        for n in plate_nodes:
            if n in cset:
                continue
            x, y, _z = nodes[n]
            if on_footprint_edges(x, y, fps):
                _, j = tree.query([x, y])
                for dof in (1, 2, 3):
                    eqs.append((n, centers[j], dof))

    # ---- tope del perfil
    wall_nodes = set(n for k, lst in groups.items() if k.startswith("wall") for c in lst for n in c)
    tope = [n for n in wall_nodes if abs(nodes[n][2] - ztop) < 1e-6]

    ref = max(nodes) + 1
    gid = max(nodes) + 20
    gnodes = []

    def ground(n):
        nonlocal gid
        x, y, z = nodes[n]
        gnodes.append((gid, x, y, z - 1.0))
        gid += 1
        return gid - 1

    conc_pairs = [(n, ground(n)) for n in plate_nodes if n in wts]
    ring_pairs = {k: [(n, ground(n)) for n in ring] for k, ring in rings.items()}
    z_arm = shear_arm(prj) - (0.5 * prj.lug.H if prj.lug.enabled else 0.0)
    D = 50.0
    ld = prj.eloads
    L = ["** PlacaBasePro - modelo de placas (shell S6)", f"** {prj.name} / {prj.element}", "*NODE"]
    for n, (x, y, z) in nodes.items():
        L.append(f"{n}, {x:.6f}, {y:.6f}, {z:.6f}")
    L += [f"{ref}, 0.0, 0.0, {z_arm:.6f}", f"{ref + 1}, 0.0, 0.0, {z_arm:.6f}"]
    eid = 1
    names = {}
    for gname, lst in groups.items():
        es = "EPLATE" if gname == "plate" else ("E" + gname.upper())
        names[gname] = es
        L.append(f"*ELEMENT, TYPE=S6, ELSET={es}")
        for c in lst:
            L.append(f"{eid}, " + ", ".join(map(str, c)))
            eid += 1
    L += ["*MATERIAL, NAME=ACERO", "*ELASTIC", f"{ES_KSI:.1f}, {NU_STEEL:.3f}"]
    plastic = bool(getattr(prj.fea, "plastic", False))
    if plastic:
        # placa elasto-plastica perfecta con limite φ·Fy (igual que en el modelo solido); el resto, elastico
        fy = 0.9 * prj.plate.mat().Fy
        L += ["*MATERIAL, NAME=PLACA", "*ELASTIC", f"{ES_KSI:.1f}, {NU_STEEL:.3f}",
              "*PLASTIC", f"{fy:.4f}, 0.0", f"{fy * 1.0005:.4f}, 0.25"]
    for gname, es in names.items():
        if gname == "plate":
            th = tp
        elif gname.startswith("wall"):
            th = spec["walls"][int(gname[4:])]["t"]
        else:
            th = spec["stiff"][int(gname[5:])]["t"]
        L += [f"*SHELL SECTION, ELSET={es}, MATERIAL={'PLACA' if (plastic and gname == 'plate') else 'ACERO'}", f"{th:.6f}"]

    # ---- ligadura de la huella
    if eqs:
        L.append("*EQUATION")
        for n, c, dof in eqs:
            L += ["2", f"{n},{dof},1.0,{c},{dof},-1.0"]
    # ---- acople rigido del tope (pequenos giros) con ecuaciones lineales
    if tope:
        L.append("*EQUATION")
        for n in tope:
            x, y, z = nodes[n]
            rz = z - z_arm
            L += ["4", f"{n},1,1.0,{ref},1,-1.0,{ref + 1},2,{-rz:.6f},{ref + 1},3,{y:.6f}",
                  "4", f"{n},2,1.0,{ref},2,-1.0,{ref + 1},3,{-x:.6f},{ref + 1},1,{rz:.6f}",
                  "4", f"{n},3,1.0,{ref},3,-1.0,{ref + 1},1,{-y:.6f},{ref + 1},2,{x:.6f}"]
    L.append("*NODE, NSET=NTIERRA")
    for (i, x, y, z) in gnodes:
        L.append(f"{i}, {x:.6f}, {y:.6f}, {z:.6f}")
    eid = max(eid, 1) + 1

    classes = {}
    for (n, gn) in conc_pairs:
        classes.setdefault(int(round(math.log(max(wts[n], 1e-9)) / math.log(1.08))), []).append((n, gn))
    for ci, lst in sorted(classes.items()):
        kc = ks * sum(wts[n] for n, _ in lst) / len(lst)
        L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET=ECONC{ci + 200}")
        for (n, gn) in lst:
            L.append(f"{eid}, {n}, {gn}"); eid += 1
        L += [f"*SPRING, ELSET=ECONC{ci + 200}, NONLINEAR",
              f"{-kc * D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kc * 1e-5 * D:.6e}, {D:.1f}"]
    for k, ring in rings.items():
        kr = kb / len(ring)
        L.append(f"*ELEMENT, TYPE=SPRINGA, ELSET=EPERNO{k}")
        for (n, gn) in ring_pairs[k]:
            L.append(f"{eid}, {n}, {gn}"); eid += 1
        L += [f"*SPRING, ELSET=EPERNO{k}, NONLINEAR",
              f"{-kr * 1e-5 * D:.6e}, {-D:.1f}", "0.0, 0.0", f"{kr * D:.6e}, {D:.1f}"]
        for dof in (1, 2):
            L.append(f"*ELEMENT, TYPE=SPRING1, ELSET=EPERNO{k}H{dof}")
            for n in ring:
                L.append(f"{eid}, {n}"); eid += 1
            L += [f"*SPRING, ELSET=EPERNO{k}H{dof}", str(dof), f"{kbh / len(ring):.6f}"]
    if lug_nodes:
        Wl = max(max(max(q[0] for q in poly) - min(q[0] for q in poly),
                     max(q[1] for q in poly) - min(q[1] for q in poly)) for poly in lug_polys)
        kl = Ec * Wl / len(lug_nodes)               # rigidez horizontal total Ec·W repartida en la huella
        for dof in (1, 2):
            L.append(f"*ELEMENT, TYPE=SPRING1, ELSET=ELLAVE{dof}")
            for n in lug_nodes:
                L.append(f"{eid}, {n}"); eid += 1
            L += [f"*SPRING, ELSET=ELLAVE{dof}", str(dof), f"{kl:.6f}"]
    kfric = max(1e-3, 0.05 * kbh * max(len(rings), 1) / max(len(plate_nodes), 1))
    for dof in (1, 2):
        L.append(f"*ELEMENT, TYPE=SPRING1, ELSET=EFRIC{dof}")
        for n in plate_nodes:
            L.append(f"{eid}, {n}"); eid += 1
        L += [f"*SPRING, ELSET=EFRIC{dof}", str(dof), f"{kfric:.8f}"]

    L += ["*BOUNDARY", "NTIERRA, 1, 3", f"{ref + 1}, 3, 3",
          # con plasticidad se resuelve en pequenas deformaciones (sin NLGEOM): converge en mas casos
          ("*STEP, INC=60" if plastic else "*STEP, NLGEOM, INC=300"), "*STATIC",
          # el intento plastico falla rapido (incremento minimo mayor) para pasar pronto al criterio elastico
          ("0.5, 1.0, 0.02, 1.0" if plastic else "0.5, 1.0, 1e-3, 1.0"), "*CLOAD", f"{ref}, 3, {-ld.Pu:.5f}"]
    if abs(ld.Vux) > 0:
        L.append(f"{ref}, 1, {ld.Vux:.5f}")
    if abs(ld.Vuy) > 0:
        L.append(f"{ref}, 2, {ld.Vuy:.5f}")
    if abs(ld.Mux) > 0:
        L.append(f"{ref + 1}, 1, {ld.Mux:.5f}")
    if abs(ld.Muy) > 0:
        L.append(f"{ref + 1}, 2, {ld.Muy:.5f}")
    L += ["*NODE FILE", "U, RF", "*EL FILE", "S" + (", PEEQ" if plastic else ""), "*END STEP"]
    Path(out_inp).write_text("\n".join(L), encoding="utf-8")
    meta = {"ks": ks, "kb": kb, "tp": tp, "z_wall": tpm, "ztop": ztop, "shell": True,
            "base": sorted(plate_nodes), "base_ground": [gg for _, gg in conc_pairs],
            "ring_ground": {str(k): [gg for _, gg in v] for k, v in ring_pairs.items()},
            "n_bolts": len(pos), "n_ties": len(eqs) // 3, "n_lug": len(lug_nodes)}
    Path(out_inp).with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


# ============================================================================ resultados
def read_frd_nodes(path: str) -> dict:
    """Coordenadas de TODOS los nodos del .frd (incluye los nodos expandidos de cada shell)."""
    nodes = {}
    inblock = False
    with open(path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if ln.startswith("    2C"):
                inblock = True
                continue
            if inblock:
                if ln.startswith(" -3"):
                    break
                if ln.startswith(" -1"):
                    try:
                        nid = int(ln[3:13])
                        nodes[nid] = (float(ln[13:25]), float(ln[25:37]), float(ln[37:49]))
                    except ValueError:
                        continue
    return nodes


def load_shell_results(frd: str, mesh: dict, prj: Project, spec: dict):
    """Result3D con los nodos expandidos del .frd (caras superior e inferior de cada shell).
    Los triangulos son los de la superficie media; el von Mises de cada nodo medio es el MAYOR de las fibras
    (cara superior / inferior) de su espesor."""
    from .view3d import Result3D, read_frd, von_mises
    r = Result3D()
    nodes = read_frd_nodes(frd)
    disp, stress, forc = read_frd(frd)
    if not disp or not nodes:
        r.msg = ("El .frd no contiene desplazamientos. Revise que CalculiX haya terminado sin errores "
                 "(archivo .sta / .dat).")
        return r
    groups = {k: v for k, v in mesh["groups"].items()}
    if "plate?" in groups:
        groups.setdefault("plate", []).extend(groups.pop("plate?"))
    mesh_xyz = {int(k): tuple(v) for k, v in mesh["nodes"].items()}
    r.nodes = nodes
    r.disp = disp
    r.stress = stress
    r.forc = forc
    vm = {n: von_mises(*s_) for n, s_ in stress.items()}
    thick = {"plate": prj.plate.tp}
    for gname in groups:
        if gname.startswith("wall"):
            thick[gname] = spec["walls"][int(gname[4:])]["t"]
        elif gname.startswith("stiff"):
            thick[gname] = spec["stiff"][int(gname[5:])]["t"]
    ids = np.array(list(nodes.keys()))
    xyz = np.array([nodes[i] for i in ids])
    from scipy.spatial import cKDTree
    tree = cKDTree(xyz)
    mid_vm = {}
    for gname, lst in groups.items():
        th = thick[gname]
        mids = sorted({n for c in lst for n in c})
        for n in mids:
            # los nodos de union (varias placas con distinta normal) pierden su numero original en el .frd:
            # CalculiX crea nodos expandidos nuevos.  Su posicion sale de la malla y sus resultados del
            # entorno de nodos expandidos que quedan dentro del espesor.
            x0, y0, z0 = nodes[n] if n in nodes else mesh_xyz[n]
            idxs = tree.query_ball_point((x0, y0, z0), th / 2.0 + 1e-3)
            best = mid_vm.get(n, 0.0)
            ds = []
            for k in idxs:
                nid = int(ids[k])
                if nid not in vm:
                    continue
                if gname == "plate":
                    xk, yk, _zk = nodes[nid]
                    if abs(xk - x0) > 1e-3 or abs(yk - y0) > 1e-3:
                        continue
                best = max(best, vm[nid])
                if nid in disp:
                    ds.append(disp[nid])
            mid_vm[n] = best
            if n not in nodes:
                nodes[n] = (x0, y0, z0)
            if n not in disp and ds:
                disp[n] = tuple(float(sum(d[q] for d in ds) / len(ds)) for q in range(3))
    vm.update(mid_vm)
    r.vm = vm
    if getattr(prj.fea, "plastic", False):
        from .view3d import read_peeq
        pe_all = read_peeq(frd)
        pe_mid = {}
        for n in sorted({n for c in groups.get("plate", []) for n in c}):
            x0, y0, z0 = nodes[n] if n in nodes else mesh_xyz[n]
            best = 0.0
            for k in tree.query_ball_point((x0, y0, z0), prj.plate.tp / 2.0 + 1e-3):
                nid = int(ids[k])
                xk, yk, _zk = nodes[nid]
                if abs(xk - x0) > 1e-3 or abs(yk - y0) > 1e-3:
                    continue
                best = max(best, pe_all.get(nid, 0.0))
            pe_mid[n] = best
        r.peeq = pe_mid
    tris_all, parts = [], {"plate": [], "column": [], "stiff": []}
    for gname, lst in groups.items():
        key = "plate" if gname == "plate" else ("column" if gname.startswith("wall") else "stiff")
        for c in lst:
            tr = (c[0], c[1], c[2])
            tris_all.append(tr)
            parts[key].append(tr)
    r.tris = tris_all
    r.parts = {k: v for k, v in parts.items() if v}
    mids_all = {n for lst in groups.values() for c in lst for n in c}
    r.n_nodes = len(mids_all)
    r.n_elems = len(tris_all)
    r.umax = max((math.sqrt(sum(c * c for c in disp[n])) for n in mids_all if n in disp), default=0.0)
    r.vmmax = max((vm[n] for n in vm if n in stress), default=0.0)
    if forc:
        r.rf_sum = tuple(sum(v[i] for v in forc.values()) for i in range(3))
    r.ok = True
    r.msg = (f"{r.n_nodes:,} nodos y {r.n_elems:,} placas (S6).  |U| max = {r.umax:.5f} in ;  "
             f"von Mises max = {r.vmmax:.2f} ksi")
    return r


# ============================================================================ flujo completo
def full_shell(prj: Project, folder: str, stem: str = "modelo_placas", progress=None, cancel=None, lc=None):
    """Geometria -> malla de superficies (Gmsh) -> .inp -> CalculiX -> resultados, con cancelacion y reintentos
    con malla mas gruesa si algo falla."""
    from . import mesh3d

    def say(m):
        if progress:
            progress(m)

    lc0 = lc if lc else mesh3d.mesh_size_for(prj)
    last = "No se pudo completar el analisis."
    import copy
    elastic = copy.deepcopy(prj)
    elastic.fea.plastic = False
    # con plasticidad primero un intento; si CalculiX no converge se pasa al criterio elastico (mallas 1.0, 1.35, 1.8)
    plan = ([(prj, 1.0, "")] if getattr(prj.fea, "plastic", False) else []) + \
           [(elastic if getattr(prj.fea, "plastic", False) else prj, f, "") for f in (1.0, 1.35, 1.8)]
    for k, (pj, f, _) in enumerate(plan):
        if cancel is not None and cancel.cancelled:
            return None, CANCELADO
        fallback = pj is elastic
        tag = "" if k == 0 else (f"  (la plasticidad no convergio: criterio elastico)" if (fallback and f == 1.0 and k == 1)
                                 else f"  (reintento con malla mas gruesa x{f:g})")
        res, msg = _full_shell_once(pj, folder, stem, lc0 * f, say, cancel, tag)
        if res is not None or msg == CANCELADO or (cancel is not None and cancel.cancelled):
            if res is not None and fallback:
                res.msg += "   (La plasticidad no convergio en este caso: se uso el criterio elastico de von Mises promediado.)"
            return res, (CANCELADO if (cancel is not None and cancel.cancelled) else (res.msg if res is not None else msg))
        last = msg
    return None, last + "\n\n(Se probaron varios tamanos de malla; revise la geometria o aumente el tamano manual.)"


def _full_shell_once(prj, folder, stem, lc, say, cancel, tag=""):
    from . import mesh3d
    Path(folder).mkdir(parents=True, exist_ok=True)
    spec = make_spec(prj, lc)
    spec_path = str(Path(folder) / f"{stem}_geo.json")
    mesh_path = str(Path(folder) / f"{stem}_malla.json")
    Path(spec_path).write_text(json.dumps(spec), encoding="utf-8")
    if Path(mesh_path).exists():
        Path(mesh_path).unlink()
    say(f"1/3  Mallando las placas con Gmsh (elemento de {lc * 25.4:.0f} mm = {lc:.2f} in) ...{tag}")
    rc, out, state = mesh3d._run_proc(mesh3d._self_cmd() + ["--shell", spec_path, mesh_path], cancel, 1800)
    if state == "cancelado" or (cancel is not None and cancel.cancelled):
        return None, CANCELADO
    if not Path(mesh_path).exists():
        return None, f"Gmsh no genero la malla de placas.\n\n{out[-3000:]}"
    mesh = json.loads(Path(mesh_path).read_text(encoding="utf-8"))
    say(f"2/3  Armando el modelo de CalculiX ...{tag}")
    inp = str(Path(folder) / f"{stem}_ccx.inp")
    try:
        meta = build_inp(prj, mesh, inp, spec)
    except Exception as e:
        import traceback
        return None, f"No se pudo armar el .inp: {e}\n{traceback.format_exc()[-800:]}"
    say(f"3/3  Resolviendo con CalculiX ...{tag}")
    ok, out, frd = mesh3d.run_ccx(inp, prj.fea.ccx_path, cancel=cancel)
    if cancel is not None and cancel.cancelled:
        return None, CANCELADO
    if not ok:
        return None, f"CalculiX no genero resultados.\n\n{out[-3000:]}"
    sta = Path(inp).with_suffix(".sta")
    try:
        last = [ln.split() for ln in sta.read_text().splitlines() if ln.strip() and ln.split()[0].isdigit()]
        frac = float(last[-1][4]) if last else 0.0
    except Exception:
        frac = 1.0
    if frac < 0.999:
        return None, (f"CalculiX no convergio: se detuvo al {100*frac:.0f} % de la carga "
                      f"(resultado parcial descartado).\n\n{out[-1500:]}")
    say("Leyendo resultados ...")
    res = load_shell_results(frd, mesh, prj, spec)
    if not res.ok:
        err = [ln for ln in out.splitlines() if "*ERROR" in ln][:3]
        return None, res.msg + ("\n" + "\n".join(err) if err else "")
    res.lc = lc
    res.folder = folder
    res.engine = "placas"
    from .weld3d import postprocess
    try:
        res.post = postprocess(prj, res, str(Path(inp).with_suffix(".meta.json")))
    except Exception as e:
        res.post = None
        res.msg += f"   (postproceso de soldadura fallido: {e})"
    try:
        from .view3d import smoothed_plate_vm
        r_avg = max(prj.fea.vm_avg_factor * prj.plate.tp, lc / 1.2)
        res.vm_avg = smoothed_plate_vm(res, prj, r_avg)
        if res.vm_avg:
            res.msg += (f"   Von Mises PROMEDIADO en la placa (r = {res.vm_avg['radius']:.2f} in) = "
                        f"{res.vm_avg['vm']:.1f} ksi")
    except Exception as e:
        res.vm_avg = None
        res.msg += f"   (promedio de von Mises no disponible: {e})"
    res.part_avg = {}
    return res, res.msg
