# -*- coding: utf-8 -*-
"""
Fuerza en cada perno por DISTRIBUCION LINEAL (placa rigida, secciones planas).

Es el calculo "a mano" del metodo elastico de placa base: la placa es rigida, de modo que su
desplazamiento vertical es un plano

        w(x, y) = a + b·x + c·y                (w > 0 hacia el concreto)

y todo lo demas sigue de la compatibilidad y el equilibrio:

  concreto  (Winkler, solo compresion)   p(x, y) = ks · max(w, 0)
  perno i   (resorte axial, solo tracc.)  T_i     = kb · max(−w_i, 0)          w_i = w(x_i, y_i)

  equilibrio de la placa (Pu comprimiendo; Mx' tracciona +Y; My' tracciona −X):
        ∫p dA  − ΣT_i             = Pu
        ∫p·y dA − ΣT_i·y_i        = −Mx'
        ∫p·x dA − ΣT_i·x_i        = +My'
  con  Mx' = |Mux| − e·Vuy ,  My' = Muy + e·Vux   (par del cortante, mismo brazo e del 2D).

La fuerza de cada perno es entonces LINEAL en su distancia al eje neutro (w = 0).  Los tres
parametros (a, b, c) salen de un Newton con Jacobiano exacto: es el minimo de una energia
convexa, asi que converge siempre.  Las integrales sobre la zona comprimida (placa recortada por
w > 0, menos los agujeros) son exactas: momentos de poligonos.

ks y kb son los mismos del modelo 2D y del solido 3D (Ec/hped y E·Ase/(hef + tp + mortero)), asi
los tres modelos comparten las mismas hipotesis de rigidez y la unica diferencia es la flexibilidad
de la placa.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

import numpy as np

from .model import Project
from . import geometry as G
from .units import ES_KSI, Ec_ksi


# ------------------------------------------------------------ poligonos
def _clip_halfplane(poly, a, b, c):
    """Recorta un poligono CONVEXO por el semiplano  a + b·x + c·y >= 0 (Sutherland-Hodgman)."""
    out = []
    n = len(poly)
    if n == 0:
        return out
    vals = [a + b * x + c * y for x, y in poly]
    for i in range(n):
        j = (i + 1) % n
        p, q = poly[i], poly[j]
        vp, vq = vals[i], vals[j]
        if vp >= 0:
            out.append(p)
        if (vp >= 0) != (vq >= 0):
            t = vp / (vp - vq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _moments(poly):
    """(A, Sx, Sy, Sxx, Sxy, Syy) de un poligono simple, antihorario:
    A = ∫dA, Sx = ∫x dA, Sy = ∫y dA, Sxx = ∫x² dA, Sxy = ∫xy dA, Syy = ∫y² dA."""
    n = len(poly)
    if n < 3:
        return (0.0,) * 6
    A = Sx = Sy = Sxx = Sxy = Syy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        A += cr
        Sx += (x0 + x1) * cr
        Sy += (y0 + y1) * cr
        Sxx += (x0 * x0 + x0 * x1 + x1 * x1) * cr
        Syy += (y0 * y0 + y0 * y1 + y1 * y1) * cr
        Sxy += (x0 * y1 + 2 * x0 * y0 + 2 * x1 * y1 + x1 * y0) * cr
    return (A / 2.0, Sx / 6.0, Sy / 6.0, Sxx / 12.0, Sxy / 24.0, Syy / 12.0)


def _circle_poly(cx, cy, r, n):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def _open_ccw(poly):
    pts = list(poly)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts = pts[:-1]
    if _moments(pts)[0] < 0:
        pts = pts[::-1]
    return pts


def _convex_clip(subject, clipper):
    """Interseccion de dos poligonos convexos antihorarios."""
    out = subject
    n = len(clipper)
    for i in range(n):
        x0, y0 = clipper[i]
        x1, y1 = clipper[(i + 1) % n]
        out = _clip_halfplane(out, (y1 - y0) * x0 - (x1 - x0) * y0, -(y1 - y0), (x1 - x0))
        if not out:
            break
    return out


def lug_pieces(prj: Project) -> list:
    """Huella de la llave de corte bajo la placa como [(signo, poligono)] por inclusion-exclusion:
    ahi no hay contacto placa-concreto (igual que en el modelo solido 3D, donde la cara superior de
    la llave queda pegada a la placa)."""
    if not prj.lug.enabled:
        return []
    rs, rnd, ro, tr = G.lug_rects(prj)
    if rnd:                                       # tubo redondo: corona
        return [(+1, _circle_poly(0.0, 0.0, ro, 72)), (-1, _circle_poly(0.0, 0.0, max(ro - tr, 1e-6), 72))]
    polys = [_open_ccw(q) for q in rs if len(q) >= 3]
    out = [(+1, q) for q in polys]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            inter = _convex_clip(polys[i], polys[j])
            if len(inter) >= 3 and _moments(inter)[0] > 1e-9:
                out.append((-1, inter))
    return out


def lug_contains(prj: Project):
    """Funcion (x, y) -> True si el punto queda bajo la llave (sin contacto)."""
    pcs = lug_pieces(prj)
    if not pcs:
        return lambda x, y: False
    polys = [(s_, q) for s_, q in pcs if s_ > 0]
    holes = [q for s_, q in pcs if s_ < 0 and len(q) >= 3] if pcs and pcs[-1][0] < 0 else []

    def inside(x, y):
        return any(G._inside(x, y, q) for _, q in polys)
    if any(s_ < 0 for s_, _ in pcs) and prj.lug.enabled and G.lug_rects(prj)[1]:
        ring_in = [q for s_, q in pcs if s_ < 0][0]
        return lambda x, y: inside(x, y) and not G._inside(x, y, ring_in)
    return inside


# ------------------------------------------------------------ resultado
@dataclass
class LinearResult:
    ok: bool = False
    msg: str = ""
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    ks: float = 0.0
    kb: float = 0.0
    arm: float = 0.0
    Mx: float = 0.0                 # Mx' y My' con el par del cortante
    My: float = 0.0
    bolt_xy: list = field(default_factory=list)
    bolt_T: list = field(default_factory=list)          # kip
    bolt_dw: list = field(default_factory=list)         # alargamiento (−w_i) de cada perno, in
    T_sum: float = 0.0
    T_max: float = 0.0
    R_conc: float = 0.0             # reaccion del concreto, kip
    p_max: float = 0.0              # presion maxima, ksi
    A_plate: float = 0.0
    A_comp: float = 0.0             # area de contacto (comprimida), in²
    xc: float = 0.0                 # centroide de la presion
    yc: float = 0.0
    na: tuple = None                # eje neutro: (nx, ny, d)  con  nx·x + ny·y = d   (w = 0)
    iters: int = 0
    resid: float = 0.0              # residuo de equilibrio, kip


def foundation_ks(prj: Project) -> float:
    if prj.fea.ks_mode == "manual":
        return max(1.0, prj.fea.ks_manual)
    return Ec_ksi(prj.conc.fc) / max(6.0, prj.conc.ha)


def bolt_kb(prj: Project) -> float:
    g = prj.bolts.geom()
    Lb = prj.bolts.hef + prj.plate.tp + prj.plate.grout
    return ES_KSI * g.Ase / max(Lb, 1.0)


def linear_bolt_forces(prj: Project) -> LinearResult:
    """Fuerza de cada perno con la distribucion lineal de la placa rigida."""
    from .fea import shear_arm
    r = LinearResult()
    p, L = prj.plate, prj.eloads
    circ = (p.shape == "Circular")
    bolts = G.bolt_positions(prj)
    if not bolts:
        r.msg = "No hay pernos."
        return r
    g = prj.bolts.geom()
    r_hole = g.dh / 2.0
    ks, kb = foundation_ks(prj), bolt_kb(prj)
    arm = shear_arm(prj)
    Mx = abs(L.Mux) - arm * L.Vuy
    My = L.Muy + arm * L.Vux
    Pu = L.Pu

    if circ:
        plate = _circle_poly(0.0, 0.0, p.Dp / 2.0, 360)
    else:
        plate = [(-p.B / 2, -p.N / 2), (p.B / 2, -p.N / 2), (p.B / 2, p.N / 2), (-p.B / 2, p.N / 2)]
    holes = [_circle_poly(bx, by, r_hole, 36) for (bx, by) in bolts] if r_hole > 1e-6 else []
    lugs = lug_pieces(prj)
    A0 = _moments(plate)[0] - sum(_moments(h)[0] for h in holes) - sum(s_ * _moments(q)[0] for s_, q in lugs)
    r.A_plate = A0
    xb = np.array([q[0] for q in bolts])
    yb = np.array([q[1] for q in bolts])

    def region(a, b, c):
        M = np.array(_moments(_clip_halfplane(plate, a, b, c)))
        if M[0] > 0:
            for h in holes:
                M -= np.array(_moments(_clip_halfplane(h, a, b, c)))
            for s_, q in lugs:
                M -= s_ * np.array(_moments(_clip_halfplane(q, a, b, c)))
        return M                                            # A, Sx, Sy, Sxx, Sxy, Syy

    def evaluate(x):
        a, b, c = x
        A, Sx, Sy, Sxx, Sxy, Syy = region(a, b, c)
        wi = a + b * xb + c * yb
        T = kb * np.maximum(-wi, 0.0)
        C = ks * (a * A + b * Sx + c * Sy)
        Cy = ks * (a * Sy + b * Sxy + c * Syy)
        Cx = ks * (a * Sx + b * Sxx + c * Sxy)
        # residuos (= gradiente de la energia)
        gres = np.array([C - T.sum() - Pu,
                         Cx - (T * xb).sum() - My,
                         Cy - (T * yb).sum() + Mx])
        # energia:  ½ks∫(w+)² + ½kbΣ(w_i−)² − Pu·a − My·b + Mx·c
        w2 = a * a * A + b * b * Sxx + c * c * Syy + 2 * a * b * Sx + 2 * a * c * Sy + 2 * b * c * Sxy
        Pi = 0.5 * ks * w2 + 0.5 * kb * float((np.maximum(-wi, 0.0) ** 2).sum()) \
            - Pu * a - My * b + Mx * c
        # Jacobiano (matriz de rigidez de la placa rigida)
        K = ks * np.array([[A, Sx, Sy], [Sx, Sxx, Sxy], [Sy, Sxy, Syy]])
        act = (wi < 0)
        if act.any():
            ph = np.stack([np.ones(act.sum()), xb[act], yb[act]])      # 3×n
            K = K + kb * ph @ ph.T
        return gres, Pi, K

    # arranque: solucion lineal con TODA la placa en contacto (sin levantamiento)
    Ix = _moments(plate)[5] - sum(_moments(h)[5] for h in holes) - sum(s_ * _moments(q)[5] for s_, q in lugs)
    Iy = _moments(plate)[3] - sum(_moments(h)[3] for h in holes) - sum(s_ * _moments(q)[3] for s_, q in lugs)
    a0 = Pu / (ks * max(A0, 1e-9))
    x = np.array([a0 + 1e-6, My / (ks * max(Iy, 1e-9)), -Mx / (ks * max(Ix, 1e-9))])
    gres, Pi, K = evaluate(x)
    it = 0
    for it in range(1, 201):
        if float(np.linalg.norm(gres)) < 1e-9 * max(1.0, abs(Pu) + abs(Mx) + abs(My)):
            break
        try:
            d = np.linalg.solve(K + 1e-12 * np.eye(3) * max(1.0, float(np.trace(K))), -gres)
        except np.linalg.LinAlgError:
            d = -gres / max(float(np.trace(K)), 1e-9)
        # busqueda de linea sobre la energia convexa
        t = 1.0
        for _ in range(40):
            g2, Pi2, K2 = evaluate(x + t * d)
            if Pi2 <= Pi + 1e-4 * t * float(gres @ d) + 1e-12 * abs(Pi):
                break
            t *= 0.5
        x = x + t * d
        gres, Pi, K = g2, Pi2, K2
    a, b, c = (float(v) for v in x)
    r.a, r.b, r.c, r.ks, r.kb, r.arm, r.Mx, r.My, r.iters = a, b, c, ks, kb, arm, Mx, My, it
    r.resid = float(np.linalg.norm(gres))

    wi = a + b * xb + c * yb
    T = kb * np.maximum(-wi, 0.0)
    r.bolt_xy = [(float(u), float(v)) for u, v in zip(xb, yb)]
    r.bolt_T = [float(t_) for t_ in T]
    r.bolt_dw = [float(max(-w_, 0.0)) for w_ in wi]
    r.T_sum, r.T_max = float(T.sum()), float(T.max())
    Mm = region(a, b, c)
    r.A_comp = float(Mm[0])
    r.R_conc = float(ks * (a * Mm[0] + b * Mm[1] + c * Mm[2]))
    if Mm[0] > 1e-9:
        # centroide de la presion  p = ks·w  (w lineal)
        num_x = ks * (a * Mm[1] + b * Mm[3] + c * Mm[4])
        num_y = ks * (a * Mm[2] + b * Mm[4] + c * Mm[5])
        if r.R_conc > 1e-9:
            r.xc, r.yc = float(num_x / r.R_conc), float(num_y / r.R_conc)
    pv = plate if not circ else plate[::10]
    r.p_max = float(ks * max(0.0, max(a + b * x_ + c * y_ for x_, y_ in pv)))
    nrm = math.hypot(b, c)
    if nrm > 1e-12:
        r.na = (b / nrm, c / nrm, -a / nrm)                  # nx·x + ny·y = d
    r.ok = r.resid < 1e-4 * max(1.0, abs(Pu) + abs(Mx) + abs(My)) and np.isfinite(r.T_sum)
    r.msg = (f"Distribucion lineal: {it} iteraciones, residuo {r.resid:.2e} kip; "
             f"ΣT = {r.T_sum:.2f} kip, T max = {r.T_max:.2f} kip, "
             f"presion max = {r.p_max:.3f} ksi, area comprimida = {r.A_comp:.1f} in²")
    return r
