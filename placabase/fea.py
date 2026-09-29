# -*- coding: utf-8 -*-
"""
Elementos finitos de la placa base.

Elemento : cuadrilatero de 4 nodos, placa de Mindlin-Reissner con integracion
           reducida selectiva (2x2 en flexion, 1x1 en cortante) - evita el
           bloqueo por cortante en placas gruesas y delgadas.
GDL      : [w, bx, by] por nodo.  w positivo HACIA ABAJO (hacia el concreto).
Apoyo    : resortes de Winkler nodo a nodo, SOLO COMPRESION (iterativo).
Pernos   : resortes axiales en la posicion del perno, SOLO TRACCION.
Carga    : Pu, Mux y Muy repartidos sobre la huella del perfil (paredes y
           alas), que es por donde el perfil realmente entrega la carga.
Extra    : los rigidizadores se introducen como apoyos elasticos en linea con
           la rigidez de mensula  k = 3·E·I/L³  repartida en su longitud.

Salidas  : deflexion, presion de contacto, fuerza por perno, momentos de placa
           Mx/My/Mxy, esfuerzo de von Mises en la superficie y la demanda de
           soldadura por pulgada en la linea de contacto perfil-placa.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np

from .model import Project
from . import geometry as G
from .units import ES_KSI, NU_STEEL, Ec_ksi, UnitSet

try:
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    HAVE_SCIPY = True
except Exception:                                    # pragma: no cover
    HAVE_SCIPY = False


GP2 = [(-1 / math.sqrt(3), -1 / math.sqrt(3)), (1 / math.sqrt(3), -1 / math.sqrt(3)),
       (1 / math.sqrt(3), 1 / math.sqrt(3)), (-1 / math.sqrt(3), 1 / math.sqrt(3))]


@dataclass
class FEAResult:
    ok: bool = False
    msg: str = ""
    X: np.ndarray = None
    Y: np.ndarray = None
    w: np.ndarray = None            # deflexion nodal, in (positivo hacia abajo)
    press: np.ndarray = None        # presion de contacto nodal, ksi
    vm_top: np.ndarray = None       # von Mises en la cara superior, ksi
    vm_bot: np.ndarray = None
    Mx: np.ndarray = None
    My: np.ndarray = None
    Mxy: np.ndarray = None
    active: np.ndarray = None       # mascara de elementos dentro de la placa
    used: np.ndarray = None         # mascara de nodos con material
    bolt_xy: list = field(default_factory=list)
    bolt_T: list = field(default_factory=list)       # traccion por perno, kip
    bolt_sig: list = field(default_factory=list)     # esfuerzo de traccion, ksi
    bolt_ratio: list = field(default_factory=list)   # D/C frente a AISC J3
    bolt_nodes: list = field(default_factory=list)   # nodos del anillo de apoyo
    holes_meshed: bool = False
    n_holes: int = 0
    w_max: float = 0.0
    press_max: float = 0.0
    vm_max: float = 0.0
    weld_line_max: float = 0.0      # kip/in en la interfaz perfil-placa
    iters: int = 0
    sumF: float = 0.0
    R_found: float = 0.0
    R_bolts: float = 0.0


def _shape(xi, eta):
    N = np.array([(1 - xi) * (1 - eta), (1 + xi) * (1 - eta),
                  (1 + xi) * (1 + eta), (1 - xi) * (1 + eta)]) * 0.25
    dN = np.array([[-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)],
                   [-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)]]) * 0.25
    return N, dN


def _elem_k(xe, ye, t, E, nu):
    """Rigidez del elemento MITC4 (Bathe-Dvorkin).

    Flexion  : integracion completa 2x2.
    Cortante : deformaciones transversales SUPUESTAS, ligadas en los puntos
               medios de los bordes e interpoladas.  Elimina a la vez el
               bloqueo por cortante y los modos de energia nula (hourglass)
               que aparecen con integracion reducida de 1 punto.
    """
    D = E * t ** 3 / (12.0 * (1 - nu ** 2))
    Db = D * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2.0]])
    Gm = E / (2 * (1 + nu))
    Ds = (5.0 / 6.0) * Gm * t * np.eye(2)
    K = np.zeros((12, 12))

    # --- filas de deformacion por cortante covariante en los puntos de ligadura
    def tie_row(n1, n2):
        r = np.zeros(12)
        hx = (xe[n2] - xe[n1]) / 2.0
        hy = (ye[n2] - ye[n1]) / 2.0
        r[3 * n2] += 0.5
        r[3 * n1] -= 0.5
        for n in (n1, n2):
            r[3 * n + 1] -= 0.5 * hx
            r[3 * n + 2] -= 0.5 * hy
        return r

    gA = tie_row(0, 1)      # gamma_xi  en (0,-1)
    gC = tie_row(3, 2)      # gamma_xi  en (0,+1)
    gB = tie_row(1, 2)      # gamma_eta en (+1,0)
    gD = tie_row(0, 3)      # gamma_eta en (-1,0)

    for xi, eta in GP2:
        N, dN = _shape(xi, eta)
        J = np.array([[dN[0] @ xe, dN[0] @ ye], [dN[1] @ xe, dN[1] @ ye]])
        detJ = np.linalg.det(J)
        if detJ <= 0:
            return None
        g = np.linalg.solve(J, dN)                      # dN/dx , dN/dy

        Bb = np.zeros((3, 12))
        for i in range(4):
            Bb[0, 3 * i + 1] = g[0, i]
            Bb[1, 3 * i + 2] = g[1, i]
            Bb[2, 3 * i + 1] = g[1, i]
            Bb[2, 3 * i + 2] = g[0, i]
        K += Bb.T @ Db @ Bb * detJ

        Bnat = np.vstack([0.5 * (1 - eta) * gA + 0.5 * (1 + eta) * gC,
                          0.5 * (1 - xi) * gD + 0.5 * (1 + xi) * gB])
        Bs = np.linalg.solve(J, Bnat)                   # a cartesianas
        K += Bs.T @ Ds @ Bs * detJ
    return K


def run_fea(prj: Project) -> FEAResult:
    r = FEAResult()
    if not HAVE_SCIPY:
        r.msg = "SciPy no disponible: el modulo de elementos finitos requiere scipy."
        return r

    p, c, L = prj.plate, prj.conc, prj.eloads
    circ = (p.shape == "Circular")
    Bx = p.Dp if circ else p.B
    Ny = p.Dp if circ else p.N
    nx = max(6, min(60, prj.fea.nx))
    ny = max(6, min(60, prj.fea.ny))

    xs = np.linspace(-Bx / 2, Bx / 2, nx + 1)
    ys = np.linspace(-Ny / 2, Ny / 2, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    nnod = (nx + 1) * (ny + 1)

    def nid(i, j):
        return i * (ny + 1) + j

    # ---- posicion de los pernos y radios de agujero / arandela
    bolts = G.bolt_positions(prj)
    g = prj.bolts.geom()
    r_hole = g.dh / 2.0
    r_wash = max(g.Fhex, 2.2 * g.db) / 2.0

    # ---- elementos activos (recorte circular y agujeros de perno)
    act = np.ones((nx, ny), dtype=bool)
    dxe, dye = Bx / nx, Ny / ny
    if circ:
        R = p.Dp / 2
        for i in range(nx):
            for j in range(ny):
                cx = 0.5 * (xs[i] + xs[i + 1])
                cy = 0.5 * (ys[j] + ys[j + 1])
                act[i, j] = (cx * cx + cy * cy) <= R * R

    carve = bool(getattr(prj.fea, "holes", True)) and r_hole > 0.9 * max(dxe, dye)
    n_carved = 0
    if carve:
        for (bx_, by_) in bolts:
            for i in range(nx):
                cx = 0.5 * (xs[i] + xs[i + 1])
                if abs(cx - bx_) > r_hole + dxe:
                    continue
                for j in range(ny):
                    cy = 0.5 * (ys[j] + ys[j + 1])
                    if act[i, j] and (cx - bx_) ** 2 + (cy - by_) ** 2 <= r_hole ** 2:
                        act[i, j] = False
                        n_carved += 1
    r.active = act
    r.holes_meshed = carve
    r.n_holes = len(bolts) if carve else 0

    # ---- espesor efectivo por elemento (los rigidizadores se introducen como
    #      una banda de espesor equivalente, NO como apoyos a tierra: la
    #      pletina rigidiza la placa, no la sostiene contra el suelo)
    dx = Bx / nx
    dy = Ny / ny
    t_el = np.full((nx, ny), p.tp)
    if prj.stiff.enabled:
        Ist = prj.stiff.t * prj.stiff.h ** 3 / 12.0
        for (x1, y1, x2, y2) in G.stiffener_lines(prj):
            horiz = abs(x2 - x1) > abs(y2 - y1)
            band = dy if horiz else dx
            t_eq = (p.tp ** 3 + 12.0 * Ist / max(band, 1e-6)) ** (1.0 / 3.0)
            npts = 24
            for k_ in range(npts + 1):
                uu = k_ / npts
                xx, yy = x1 + (x2 - x1) * uu, y1 + (y2 - y1) * uu
                ii = int(np.clip(math.floor((xx + Bx / 2) / dx), 0, nx - 1))
                jj = int(np.clip(math.floor((yy + Ny / 2) / dy), 0, ny - 1))
                t_el[ii, jj] = max(t_el[ii, jj], t_eq)

    # ---- calibracion: la pared del perfil rigidiza la placa bajo su huella
    fpf = float(getattr(prj.fea, "fp_factor", 1.0))
    if fpf > 1.0 + 1e-9:
        from .geometry import _seg_dist
        polys = G.section_polys(prj)
        segs = [(a, b) for poly in polys for a, b in zip(poly[:-1], poly[1:])]
        tol = 0.75 * max(dx, dy)
        for i in range(nx):
            for j in range(ny):
                cx = 0.5 * (xs[i] + xs[i + 1]); cy = 0.5 * (ys[j] + ys[j + 1])
                if any(_seg_dist(cx, cy, a[0], a[1], b[0], b[1]) <= tol for a, b in segs):
                    t_el[i, j] = max(t_el[i, j], p.tp * fpf)

    # ---- rigidez global
    ndof = 3 * nnod
    rows, cols, vals = [], [], []
    xe0 = np.array([0.0, dx, dx, 0.0])
    ye0 = np.array([0.0, 0.0, dy, dy])
    Kcache = {}
    used_nodes = np.zeros(nnod, dtype=bool)
    trib = np.zeros(nnod)
    for i in range(nx):
        for j in range(ny):
            if not act[i, j]:
                continue
            kt = round(float(t_el[i, j]), 5)
            Ke = Kcache.get(kt)
            if Ke is None:
                Ke = _elem_k(xe0, ye0, kt, ES_KSI, NU_STEEL)
                Kcache[kt] = Ke
            nds = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            used_nodes[nds] = True
            for n_ in nds:
                trib[n_] += dx * dy / 4.0
            dofs = np.array([[3 * n, 3 * n + 1, 3 * n + 2] for n in nds]).ravel()
            for a in range(12):
                for b in range(12):
                    v = Ke[a, b]
                    if v != 0.0:
                        rows.append(dofs[a]); cols.append(dofs[b]); vals.append(v)

    Kbase = sp.coo_matrix((vals, (rows, cols)), shape=(ndof, ndof)).tocsr()

    # ---- modulo de balasto
    if prj.fea.ks_mode == "manual":
        ks = max(1.0, prj.fea.ks_manual)
    else:
        Ec = Ec_ksi(c.fc)
        ks = Ec / max(6.0, c.ha)                        # kip/in^3
    ks *= float(getattr(prj.fea, "ks_factor", 1.0))
    kf_node = ks * trib                                  # kip/in

    # ---- resortes de perno
    #      La tuerca/arandela apoya sobre un ANILLO alrededor del agujero, no
    #      sobre un punto: la rigidez del perno se reparte entre los nodos de
    #      ese anillo.  Asi el modelo sigue siendo valido con el agujero
    #      recortado de la malla.
    Lb = prj.bolts.hef + p.tp + p.grout
    kb = ES_KSI * g.Ase / max(Lb, 1.0) * float(getattr(prj.fea, "bolt_factor", 1.0))
    bolt_groups = []                     # [(lista_nodos, x, y)]
    for (bx, by) in bolts:
        ring = []
        i0 = int(np.clip(math.floor((bx - r_wash + Bx / 2) / dx), 0, nx))
        i1 = int(np.clip(math.ceil((bx + r_wash + Bx / 2) / dx), 0, nx))
        j0 = int(np.clip(math.floor((by - r_wash + Ny / 2) / dy), 0, ny))
        j1 = int(np.clip(math.ceil((by + r_wash + Ny / 2) / dy), 0, ny))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                n_ = nid(i, j)
                if not used_nodes[n_]:
                    continue
                rr = math.hypot(xs[i] - bx, ys[j] - by)
                if rr <= r_wash + 1e-9 and (not carve or rr >= r_hole - 0.5 * max(dx, dy)):
                    ring.append(n_)
        if not ring:                      # malla gruesa: vuelve al nodo mas cercano
            i = int(np.clip(round((bx + Bx / 2) / dx), 0, nx))
            j = int(np.clip(round((by + Ny / 2) / dy), 0, ny))
            n_ = nid(i, j)
            if used_nodes[n_]:
                ring = [n_]
        if ring:
            bolt_groups.append((ring, bx, by))
    bolt_nodes = [(n_, bx, by) for ring, bx, by in bolt_groups for n_ in ring]
    r.bolt_xy = [(b, c) for _, b, c in bolt_groups]
    r.bolt_nodes = [ring for ring, _, _ in bolt_groups]

    # ---- cargas sobre la huella del perfil
    F = np.zeros(ndof)
    fp = G.profile_footprint(prj)
    fp = [q for q in fp if abs(q[0]) < Bx / 2 - 1e-9 and abs(q[1]) < Ny / 2 - 1e-9]
    if not fp:
        fp = [(0.0, 0.0)]
    m = len(fp)
    wj = 1.0 / m
    Iyy = sum(wj * q[1] ** 2 for q in fp)
    Ixx = sum(wj * q[0] ** 2 for q in fp)
    for (qx, qy) in fp:
        fz = wj * L.Pu
        if Iyy > 1e-9:
            fz -= abs(L.Mux) * wj * qy / Iyy
        if Ixx > 1e-9:
            fz -= L.Muy * wj * qx / Ixx
        # reparto bilineal al elemento contenedor
        fi = (qx + Bx / 2) / dx
        fj = (qy + Ny / 2) / dy
        i0 = int(np.clip(math.floor(fi), 0, nx - 1))
        j0 = int(np.clip(math.floor(fj), 0, ny - 1))
        a, b = fi - i0, fj - j0
        for (di, dj, wgt) in ((0, 0, (1 - a) * (1 - b)), (1, 0, a * (1 - b)),
                              (1, 1, a * b), (0, 1, (1 - a) * b)):
            n_ = nid(i0 + di, j0 + dj)
            if used_nodes[n_]:
                F[3 * n_] += fz * wgt
    r.sumF = float(sum(F[0::3]))

    # ---- iteracion de contacto (resortes unilaterales)
    found_on = np.ones(nnod, dtype=bool)
    bolt_on = {n_: True for n_, _, _ in bolt_nodes}
    u = np.zeros(ndof)
    for it in range(1, max(3, prj.fea.max_iter) + 1):
        diag = np.zeros(ndof)
        for n_ in range(nnod):
            if not used_nodes[n_]:
                diag[3 * n_:3 * n_ + 3] = 1.0           # nodo inactivo: fija
                continue
            k = 1e-6
            if found_on[n_]:
                k += kf_node[n_]
            diag[3 * n_] += k
            diag[3 * n_ + 1] += 1e-6
            diag[3 * n_ + 2] += 1e-6
        for ring, _, _ in bolt_groups:
            kn = kb / len(ring)
            for n_ in ring:
                if bolt_on[n_]:
                    diag[3 * n_] += kn
        K = Kbase + sp.diags(diag)
        try:
            u = spl.spsolve(K.tocsc(), F)
        except Exception as e:                          # pragma: no cover
            r.msg = f"Fallo en la solucion del sistema: {e}"
            return r
        w = u[0::3]

        new_f = np.array([(w[n_] > 0) if used_nodes[n_] else False for n_ in range(nnod)])
        new_b = {n_: (w[n_] < 0) for n_, _, _ in bolt_nodes}
        if np.array_equal(new_f, found_on) and new_b == bolt_on:
            r.iters = it
            break
        found_on, bolt_on = new_f, new_b
    else:
        r.iters = prj.fea.max_iter

    w = u[0::3]
    press = np.where((w > 0) & used_nodes, ks * np.maximum(w, 0.0), 0.0)
    r.R_found = float(np.sum(press * trib))
    r.bolt_T = [float(sum(max(0.0, -w[n_]) * kb / len(ring) for n_ in ring))
                for ring, _, _ in bolt_groups]
    r.R_bolts = float(sum(r.bolt_T))
    Ase_ = g.Ase if g.Ase > 0 else 1e-9
    phiRnt = 0.75 * 0.75 * prj.bolts.mat().Fu * g.Ab
    r.bolt_sig = [T / Ase_ for T in r.bolt_T]
    r.bolt_ratio = [T / phiRnt if phiRnt > 0 else 0.0 for T in r.bolt_T]

    # ---- momentos y von Mises en el centro de cada elemento -> a nodos
    Mx = np.zeros(nnod); My = np.zeros(nnod); Mxy = np.zeros(nnod); cnt = np.zeros(nnod)
    tn = np.zeros(nnod)
    _, dN0 = _shape(0.0, 0.0)
    Je = np.array([[dx / 2 * 2 / 2, 0], [0, dy / 2 * 2 / 2]])
    for i in range(nx):
        for j in range(ny):
            if not act[i, j]:
                continue
            nds = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            xe = np.array([xs[i], xs[i + 1], xs[i + 1], xs[i]])
            ye = np.array([ys[j], ys[j], ys[j + 1], ys[j + 1]])
            J = np.array([[dN0[0] @ xe, dN0[0] @ ye], [dN0[1] @ xe, dN0[1] @ ye]])
            gg = np.linalg.solve(J, dN0)
            bx = np.array([u[3 * n_ + 1] for n_ in nds])
            by = np.array([u[3 * n_ + 2] for n_ in nds])
            kap = np.array([gg[0] @ bx, gg[1] @ by, gg[1] @ bx + gg[0] @ by])
            te = float(t_el[i, j])
            De = ES_KSI * te ** 3 / (12.0 * (1 - NU_STEEL ** 2))
            Db = De * np.array([[1, NU_STEEL, 0], [NU_STEEL, 1, 0],
                                [0, 0, (1 - NU_STEEL) / 2]])
            m_ = Db @ kap
            for n_ in nds:
                Mx[n_] += m_[0]; My[n_] += m_[1]; Mxy[n_] += m_[2]
                cnt[n_] += 1; tn[n_] += te
    cnt[cnt == 0] = 1
    Mx /= cnt; My /= cnt; Mxy /= cnt
    tn = np.where(cnt > 0, tn / cnt, p.tp)

    z = 6.0 / np.maximum(tn, 1e-6) ** 2
    sx, sy, sxy = Mx * z, My * z, Mxy * z
    vm = np.sqrt(sx ** 2 - sx * sy + sy ** 2 + 3 * sxy ** 2)
    vm[~used_nodes] = 0.0

    sh = (nx + 1, ny + 1)
    r.X, r.Y = X, Y
    r.w = w.reshape(sh)
    r.press = press.reshape(sh)
    r.Mx, r.My, r.Mxy = Mx.reshape(sh), My.reshape(sh), Mxy.reshape(sh)
    r.used = used_nodes.reshape(sh)
    r.vm_top = vm.reshape(sh)
    r.vm_bot = r.vm_top
    r.w_max = float(np.max(np.abs(w[used_nodes]))) if used_nodes.any() else 0.0
    r.press_max = float(np.max(press))
    r.vm_max = float(np.max(vm))

    # ---- demanda de soldadura en la interfaz perfil-placa (kip/in)
    try:
        per = 0.0
        s = prj.section.shape()
        per = s.perimeter_weld_len() if s.is_hollow else 2 * s.bf * 2 + 2 * (s.d - 2 * s.tf)
        if per > 0:
            Ften = max(0.0, r.R_bolts)
            r.weld_line_max = (abs(prj.eloads.Mux) / max(s.Sx, 1e-9) * s.A / 2.0 + Ften) / per
    except Exception:
        r.weld_line_max = 0.0

    r.ok = True
    _u = UnitSet(prj.u_len, prj.u_force, prj.u_stress, prj.u_moment)
    r.msg = (f"Convergio en {r.iters} iteraciones.  "
             f"ΣF aplicada = {_u.q('F', r.sumF)} ;  "
             f"reaccion del concreto = {_u.q('F', r.R_found)} ;  "
             f"traccion en pernos = {_u.q('F', r.R_bolts)} ;  "
             f"equilibrio = {_u.fmt('F', r.R_found - r.R_bolts - r.sumF)} {_u.F}"
             + (f" ;  {n_carved} elementos recortados por los {len(bolts)} agujeros"
                if carve else " ;  agujeros no mallados (malla insuficiente)"))
    return r
