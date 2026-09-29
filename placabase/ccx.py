# -*- coding: utf-8 -*-
"""
Exportacion a CalculiX (.inp) del conjunto PLACA + PERFIL + SOLDADURA.

Modelo:
  - Placa : cascaras S4 en z = 0, espesor tp.
  - Perfil: cascaras S4 extruidas desde la huella real del perfil hasta una
            altura h (por defecto 3·d), con el espesor de cada pared/ala.
  - Union : cada nodo de la base del perfil se liga a los 4 nodos de placa que
            lo rodean mediante *EQUATION con pesos bilineales.  Esa reaccion
            nodal es, fisicamente, la fuerza que debe transmitir la soldadura.
  - Apoyo : resortes a tierra SPRING1 en cada nodo de placa (modulo de
            balasto).  Es un apoyo bilateral: revise el signo de la reaccion,
            porque las zonas con reaccion de traccion no son reales.
  - Carga : Pu, Mux, Muy y Vu aplicados en un nodo de referencia en el tope
            del perfil, ligado al borde superior con *DISTRIBUTING COUPLING.

El archivo se resuelve con   ccx -i modelo   y se visualiza en PrePoMax o
CalculiX GraphiX.
"""
from __future__ import annotations
from pathlib import Path
import math
import subprocess

from .model import Project
from . import geometry as G
from .units import ES_KSI, NU_STEEL, Ec_ksi
from .shapes import W_SHAPE, HSS_RECT


def export_inp(prj: Project, path: str, height: float | None = None) -> str:
    p = prj.plate
    s = prj.section.shape()
    circ = (p.shape == "Circular")
    Bx = p.Dp if circ else p.B
    Ny = p.Dp if circ else p.N
    nx, ny = max(8, prj.fea.nx), max(8, prj.fea.ny)
    dx, dy = Bx / nx, Ny / ny
    H = height if height else 3.0 * s.d

    L: list[str] = []
    nodes: dict[int, tuple] = {}
    nid = 1

    def add_node(x, y, z):
        nonlocal nid
        nodes[nid] = (x, y, z)
        nid += 1
        return nid - 1

    # ---------------------------------------------------------------- placa
    grid = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            x = -Bx / 2 + i * dx
            y = -Ny / 2 + j * dy
            if circ and (x * x + y * y) > (p.Dp / 2) ** 2 * 1.0001:
                continue
            grid[(i, j)] = add_node(x, y, 0.0)

    plate_el = []
    eid = 1
    for i in range(nx):
        for j in range(ny):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if not all(k in grid for k in q):
                continue
            plate_el.append((eid, [grid[k] for k in q]))
            eid += 1

    # --------------------------------------------------------------- perfil
    fp = G.profile_footprint(prj)
    nz = max(4, int(H / max(dx, dy)))
    prof_rows = []
    for k in range(nz + 1):
        z = H * k / nz
        prof_rows.append([add_node(x, y, z) for (x, y) in fp])

    prof_el = []
    m = len(fp)
    closed = s.is_hollow
    for k in range(nz):
        for a in range(m if closed else m - 1):
            b = (a + 1) % m
            prof_el.append((eid, [prof_rows[k][a], prof_rows[k][b],
                                  prof_rows[k + 1][b], prof_rows[k + 1][a]]))
            eid += 1

    ref = add_node(0.0, 0.0, H)

    # ------------------------------------------------------------- escritura
    L.append("** Modelo generado por PlacaBasePro")
    L.append(f"** Proyecto: {prj.name} - Elemento: {prj.element}")
    L.append("** Unidades: in, kip, ksi")
    L.append("*NODE, NSET=NALL")
    for n, (x, y, z) in nodes.items():
        L.append(f"{n}, {x:.6f}, {y:.6f}, {z:.6f}")

    L.append("*ELEMENT, TYPE=S4, ELSET=EPLACA")
    for e, nds in plate_el:
        L.append(f"{e}, " + ", ".join(str(n) for n in nds))
    L.append("*ELEMENT, TYPE=S4, ELSET=EPERFIL")
    for e, nds in prof_el:
        L.append(f"{e}, " + ", ".join(str(n) for n in nds))

    L.append("*MATERIAL, NAME=ACERO")
    L.append("*ELASTIC")
    L.append(f"{ES_KSI:.1f}, {NU_STEEL}")
    L.append("*SHELL SECTION, ELSET=EPLACA, MATERIAL=ACERO")
    L.append(f"{p.tp:.4f}")
    t_wall = s.tf if s.kind == W_SHAPE else s.tw
    L.append("*SHELL SECTION, ELSET=EPERFIL, MATERIAL=ACERO")
    L.append(f"{t_wall:.4f}")

    # --- resortes a tierra (balasto)
    if prj.fea.ks_mode == "manual":
        ks = max(1.0, prj.fea.ks_manual)
    else:
        ks = Ec_ksi(prj.conc.fc) / max(6.0, prj.conc.ha)
    L.append("*ELEMENT, TYPE=SPRING1, ELSET=ERESORTE")
    for (i, j), n in grid.items():
        wgt = dx * dy
        if i in (0, nx):
            wgt *= 0.5
        if j in (0, ny):
            wgt *= 0.5
        L.append(f"{eid}, {n}")
        eid += 1
    L.append("*SPRING, ELSET=ERESORTE")
    L.append("3")
    L.append(f"{ks * dx * dy:.6f}")
    L.append("** NOTA: rigidez promedio por nodo; el resorte es BILATERAL.")

    # --- union soldada perfil -> placa  (*EQUATION bilineal)
    L.append("** ---- UNION SOLDADA PERFIL-PLACA (equivale a soldadura de resistencia total)")
    base = prof_rows[0]
    for idx, (x, y) in enumerate(fp):
        fi = (x + Bx / 2) / dx
        fj = (y + Ny / 2) / dy
        i0 = min(max(int(math.floor(fi)), 0), nx - 1)
        j0 = min(max(int(math.floor(fj)), 0), ny - 1)
        a, b = fi - i0, fj - j0
        wts = [((i0, j0), (1 - a) * (1 - b)), ((i0 + 1, j0), a * (1 - b)),
               ((i0 + 1, j0 + 1), a * b), ((i0, j0 + 1), (1 - a) * b)]
        wts = [(k, w) for k, w in wts if k in grid and w > 1e-9]
        if not wts:
            continue
        tot = sum(w for _, w in wts)
        for dofn in (1, 2, 3):
            terms = [f"{base[idx]}, {dofn}, 1.0"]
            for k, w in wts:
                terms.append(f"{grid[k]}, {dofn}, {-w/tot:.6f}")
            L.append("*EQUATION")
            L.append(str(len(terms)))
            L.append(", ".join(terms))

    # --- acople rigido del nodo de carga al tope del perfil
    L.append(f"*NSET, NSET=NTOPE")
    L.append(", ".join(str(n) for n in prof_rows[-1]))
    L.append(f"*NSET, NSET=NREF")
    L.append(str(ref))
    L.append("*SURFACE, NAME=STOPE, TYPE=NODE")
    L.append("NTOPE")
    L.append("*DISTRIBUTING COUPLING, ELSET=ECPL")
    L.append("** (si su version de ccx no soporta DISTRIBUTING COUPLING, sustituya por *RIGID BODY)")
    L.append("*RIGID BODY, NSET=NTOPE, REF NODE=" + str(ref))

    # --- restriccion minima de estabilidad (giro alrededor de z)
    L.append("*BOUNDARY")
    L.append(f"{ref}, 6, 6")

    # --- paso de carga
    ld = prj.eloads
    L.append("*STEP")
    L.append("*STATIC")
    L.append("*CLOAD")
    L.append(f"{ref}, 3, {-ld.Pu:.4f}")
    if abs(ld.Vux) > 0:
        L.append(f"{ref}, 1, {ld.Vux:.4f}")
    if abs(ld.Vuy) > 0:
        L.append(f"{ref}, 2, {ld.Vuy:.4f}")
    if abs(ld.Mux) > 0:
        L.append(f"{ref}, 4, {ld.Mux:.4f}")
    if abs(ld.Muy) > 0:
        L.append(f"{ref}, 5, {ld.Muy:.4f}")
    L.append("*NODE FILE")
    L.append("U, RF")
    L.append("*EL FILE")
    L.append("S, E")
    L.append("*END STEP")

    out = Path(path)
    out.write_text("\n".join(L), encoding="utf-8")
    return str(out)


def run_ccx(inp_path: str, ccx_exe: str = "ccx", timeout: int = 600):
    """Ejecuta CalculiX.  Devuelve (ok, salida)."""
    p = Path(inp_path)
    stem = str(p.with_suffix(""))
    try:
        r = subprocess.run([ccx_exe, "-i", stem], capture_output=True, text=True,
                           timeout=timeout, cwd=str(p.parent))
        ok = Path(stem + ".frd").exists()
        return ok, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return False, (f"No se encontro el ejecutable '{ccx_exe}'. Indique la ruta completa "
                       f"de ccx.exe en la pestana de Elementos Finitos.")
    except subprocess.TimeoutExpired:
        return False, "CalculiX excedio el tiempo limite."


def read_frd_max(frd_path: str):
    """Lee el .frd y devuelve (|U|max, von Mises max) de forma aproximada."""
    umax, smax = 0.0, 0.0
    try:
        block = None
        with open(frd_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "DISP" in line:
                    block = "U"; continue
                if "STRESS" in line:
                    block = "S"; continue
                if line.startswith(" -3"):
                    block = None; continue
                if block and line.startswith(" -1"):
                    parts = line[13:].split()
                    try:
                        v = [float(x) for x in parts]
                    except ValueError:
                        continue
                    if block == "U" and len(v) >= 3:
                        umax = max(umax, math.sqrt(sum(c * c for c in v[:3])))
                    elif block == "S" and len(v) >= 6:
                        sx, sy, sz, sxy, syz, szx = v[:6]
                        vm = math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                                       + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))
                        smax = max(smax, vm)
    except Exception:
        pass
    return umax, smax
