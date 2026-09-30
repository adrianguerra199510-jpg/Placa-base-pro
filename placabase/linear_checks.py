# -*- coding: utf-8 -*-
"""
Verificaciones de la fuerza por perno con distribucion LINEAL (placa rigida) y comprobacion de que
esa distribucion es aplicable.

  · Resistencia de cada perno (AISC 360 J3.6 y J3.7) con la fuerza del perno mas cargado.
  · Aplastamiento del concreto (AISC J8) con la presion maxima de la distribucion lineal.
  · Espesor de la placa (AISC DG1 §3.1 y §3.3) con esa presion y esa traccion.
  · Validez de la hipotesis de placa rigida: el reparto lineal (secciones planas) solo es correcto si
    la placa es lo bastante rigida; ni AISC ni ACI 318 dan un limite numerico, asi que se comprueba
    contra el analisis de la placa FLEXIBLE del propio programa (2D de Mindlin): la fuerza del perno
    mas cargado y la traccion total del 2D no deben exceder a las lineales en mas de 10 % (o en mas
    de 5 % de φRnt cuando la traccion es pequena).  `rigid_thickness` busca el espesor con el que
    se cumple.
"""
from __future__ import annotations
import copy
import dataclasses
import math

from .model import Project
from . import geometry as G
from .design import Check, Bearing, plate_thickness
from .linear import LinearResult, linear_bolt_forces

TOL_REL = 0.10          # desviacion relativa admisible flexible/lineal
TOL_ABS = 0.05          # ... o 5 % de φRnt (traccion pequena)


def bolt_phiRnt(prj: Project) -> float:
    g, mat = prj.bolts.geom(), prj.bolts.mat()
    return 0.75 * 0.75 * mat.Fu * g.Ab                       # AISC J3-1: φ·Fnt·Ab, Fnt = 0.75·Fu


def rigid_deviation(lin: LinearResult, fea, phiRnt: float) -> dict:
    """Compara la placa flexible (2D) con la distribucion lineal."""
    pos2 = {(round(x, 2), round(y, 2)): T for (x, y), T in zip(fea.bolt_xy, fea.bolt_T)}
    t2 = [pos2.get((round(x, 2), round(y, 2)), 0.0) for (x, y) in lin.bolt_xy]
    T2max, T2sum = (max(t2) if t2 else 0.0), sum(t2)
    Tlmax, Tlsum = lin.T_max, lin.T_sum
    cap_max = max((1 + TOL_REL) * Tlmax, Tlmax + TOL_ABS * phiRnt)
    cap_sum = max((1 + TOL_REL) * Tlsum, Tlsum + TOL_ABS * phiRnt)
    ok = (T2max <= cap_max + 1e-9) and (T2sum <= cap_sum + 1e-9)
    return dict(T2max=T2max, T2sum=T2sum, cap_max=cap_max, cap_sum=cap_sum, ok=ok,
                dev_max=(T2max / Tlmax - 1.0) if Tlmax > 1e-9 else float("inf"),
                dev_sum=(T2sum / Tlsum - 1.0) if Tlsum > 1e-9 else float("inf"),
                per_bolt=t2, significant=max(T2max, Tlmax) >= TOL_ABS * phiRnt)


def rigid_thickness(prj: Project, max_factor: float = 8.0) -> dict:
    """Menor espesor de placa con el que la distribucion lineal es aplicable (ver el criterio
    de rigid_deviation).  Corre el 2D varias veces (unos segundos).
    -> dict(tp, ok_actual, dev_actual, applicable)  ·  tp = None si no hay traccion significativa."""
    from .fea import run_fea

    def evalu(tp):
        q = copy.deepcopy(prj)
        q.plate.tp = tp
        lin = linear_bolt_forces(q)
        fea = run_fea(q)
        if not (lin.ok and fea.ok):
            return None
        return rigid_deviation(lin, fea, bolt_phiRnt(q))

    d0 = evalu(prj.plate.tp)
    if d0 is None:
        return dict(tp=None, ok_actual=False, dev_actual=None, applicable=False)
    if not d0["significant"]:
        return dict(tp=None, ok_actual=True, dev_actual=d0["dev_max"], applicable=False)
    if d0["ok"]:
        return dict(tp=prj.plate.tp, ok_actual=True, dev_actual=d0["dev_max"], applicable=True)
    lo, hi = prj.plate.tp, None
    t = prj.plate.tp
    while t < max_factor * prj.plate.tp:
        t *= 1.25
        d = evalu(t)
        if d is not None and d["ok"]:
            hi = t
            break
        lo = t
    if hi is None:
        return dict(tp=None, ok_actual=False, dev_actual=d0["dev_max"], applicable=True)
    for _ in range(6):
        mid = 0.5 * (lo + hi)
        d = evalu(mid)
        if d is not None and d["ok"]:
            hi = mid
        else:
            lo = mid
    return dict(tp=hi, ok_actual=False, dev_actual=d0["dev_max"], applicable=True)


def linear_checks(prj: Project, br: Bearing, fea=None, rec=None):
    """-> (LinearResult, [Check]).  `fea` es el resultado del 2D (o None)."""
    u = prj.units()
    lin = linear_bolt_forces(prj)
    out: list[Check] = []
    p, b = prj.plate, prj.bolts
    g, mat = b.geom(), b.mat()
    phiRnt = bolt_phiRnt(prj)
    if rec:
        rec.section("J.  FUERZA POR PERNO — DISTRIBUCION LINEAL (PLACA RIGIDA)")
        rec.text("Hipotesis: la placa es rigida y sus secciones permanecen planas, w = a + b·x + c·y. "
                 "El concreto reacciona como resorte de Winkler solo a compresion (p = ks·w⁺) y cada "
                 "perno como resorte axial solo a traccion (Ti = kb·(−wi)⁺); por eso la fuerza del "
                 "perno es proporcional a su distancia al eje neutro (w = 0). El equilibrio de Pu, "
                 "Mx' y My' da a, b y c.")
    if not lin.ok:
        out.append(Check("lin_t", "Distribucion lineal — no convergio", 1.0, 0.0, "-", "",
                         lin.msg, skip=False))
        return lin, out

    if rec:
        rec.add("ks", "Ec / max(6 in ; hped)", "", lin.ks, "K", "", "modulo de balasto (igual al del 2D y el 3D)")
        rec.add("kb", "Es·Ase / (hef + tp + mortero)", "", lin.kb, "LF", "", "rigidez axial de un perno")
        rec.add("e", "brazo del cortante", "", lin.arm, "L")
        rec.add("Mx'", "|Mux| − e·Vuy", "", lin.Mx, "M")
        rec.add("My'", "Muy + e·Vux", "", lin.My, "M")
        rec.add("a , b , c", "w = a + b·x + c·y",
                f"{lin.a:.5g} , {lin.b:.5g} , {lin.c:.5g}", None, "-", "",
                f"{lin.iters} iteraciones; residuo de equilibrio {lin.resid:.1e} kip")
        rec.add("A comprimida", "region con w > 0", "", lin.A_comp, "A", "",
                f"{100 * lin.A_comp / max(lin.A_plate, 1e-9):.0f} % del area de la placa")
        rec.add("ΣT", "Σ kb·(−wi)⁺", "", lin.T_sum, "F")
        rec.add("Tmax", "perno mas cargado", "", lin.T_max, "F")
        rec.add("pmax", "ks·wmax", "", lin.p_max, "S")
        for i, (xy, T) in enumerate(zip(lin.bolt_xy, lin.bolt_T)):
            if T > 1e-6:
                rec.add(f"T(P{i + 1})", "kb·(−wi)",
                        f"x = {rec.n('L', xy[0])} , y = {rec.n('L', xy[1])}", T, "F")

    # ---- resistencia del perno (AISC J3)
    Vua = 0.0 if prj.lug.enabled else prj.eloads.Vu
    if prj.eloads.friction and not prj.lug.enabled and prj.eloads.Pu > 0:
        Vua = max(0.0, Vua - prj.eloads.mu_fric * prj.eloads.Pu)
    n_tot = max(1, len(lin.bolt_xy))
    Vua_b = Vua / n_tot
    Fnt, Fnv = 0.75 * mat.Fu, 0.45 * mat.Fu
    phiRnv = 0.75 * Fnv * g.Ab
    no_ten = lin.T_max <= 1e-6
    out.append(Check("lin_t", "Perno — traccion maxima, distribucion lineal (AISC J3)",
                     lin.T_max, phiRnt, "kip", "AISC Ec. J3-1",
                     f"ΣT = {u.q('F', lin.T_sum)}; perno mas cargado en "
                     f"({u.fmt('L', lin.bolt_xy[lin.bolt_T.index(lin.T_max)][0])}, "
                     f"{u.fmt('L', lin.bolt_xy[lin.bolt_T.index(lin.T_max)][1])})",
                     skip=no_ten))
    rt = lin.T_max / phiRnt if phiRnt > 0 else 0.0
    rv = Vua_b / phiRnv if phiRnv > 0 else 0.0
    if not no_ten and rt > 0.30 and rv > 0.30:
        frv = Vua_b / g.Ab if g.Ab > 0 else 0.0
        Fnt_p = max(0.0, min(1.3 * Fnt - (Fnt / (0.75 * Fnv)) * frv, Fnt))
        out.append(Check("lin_tv", "Perno — interaccion traccion-cortante, distribucion lineal",
                         lin.T_max, 0.75 * Fnt_p * g.Ab, "kip", "AISC Ec. J3-3a",
                         f"F'nt = {u.q('S', Fnt_p)} con frv = {u.q('S', frv)}"))

    # ---- aplastamiento (AISC J8)
    out.append(Check("lin_brg", "Aplastamiento — presion maxima, distribucion lineal (AISC J8)",
                     lin.p_max, br.fp_max, "ksi", "AISC Ec. J8-2",
                     "Presion triangular/trapezoidal de la placa rigida sobre el concreto."))

    # ---- espesor de la placa con la presion y la traccion lineales (DG1)
    try:
        Ycomp = p.Nc
        if abs(lin.c) > 1e-9:
            yna = -lin.a / lin.c                       # y donde w = 0 (en x = 0)
            Ycomp = min(max(yna + (p.Dp if p.shape == "Circular" else p.N) / 2.0, 0.0), p.Nc)
        Tsum = lin.T_sum
        farm = (sum(T * xy[1] for xy, T in zip(lin.bolt_xy, lin.bolt_T)) / Tsum) if Tsum > 1e-9 else br.f_arm
        br_l = dataclasses.replace(br, fp=lin.p_max, Y=Ycomp, Tu=Tsum, f_arm=max(farm, 1e-6),
                                   n_t=max(1, sum(1 for t in lin.bolt_T if t > 1e-9)),
                                   case="CASO 2" if Tsum > 1e-9 else "CASO 1", feasible=True)
        treq_l, _ = plate_thickness(prj, br_l, None)
        out.append(Check("lin_tp", "Espesor de la placa con la distribucion lineal (DG1)",
                         treq_l, p.tp, "in", "DG1 §3.1 y §3.3",
                         f"pmax = {u.q('S', lin.p_max)}, Y = {u.q('L', Ycomp)}, ΣT = {u.q('F', Tsum)}"))
    except Exception as e:                              # pragma: no cover
        out.append(Check("lin_tp", "Espesor de la placa con la distribucion lineal (DG1)", 0.0, 1.0,
                         "in", "DG1", f"no evaluado: {e}", skip=True))

    # ---- validez de la hipotesis de placa rigida
    if fea is not None and getattr(fea, "ok", False):
        d = rigid_deviation(lin, fea, phiRnt)
        note = (f"Placa flexible (2D): perno max {u.q('F', d['T2max'])} contra {u.q('F', lin.T_max)} "
                f"lineal ({100 * d['dev_max']:+.0f} %), ΣT {u.q('F', d['T2sum'])} contra "
                f"{u.q('F', lin.T_sum)} ({100 * d['dev_sum']:+.0f} %). Admisible: ≤ 10 % "
                f"(o ≤ 5 % de φRnt con traccion pequena). Si no se cumple, la placa no es rigida y "
                f"la distribucion lineal SUBESTIMA la traccion: use la del 2D/3D o aumente tp.")
        out.append(Check("lin_rigid", "Validez de la distribucion lineal — placa rigida",
                         d["T2max"], d["cap_max"], "kip", "criterio del programa (ACI 318 Cap. 17 / "
                         "EN 1992-4: distribucion plana solo con placa rigida)", note,
                         skip=not d["significant"]))
        if rec:
            rec.add("Tmax placa flexible", "analisis 2D de Mindlin", "", d["T2max"], "F")
            rec.add("Desviacion", "Tmax,2D / Tmax,lineal − 1",
                    f"{100 * d['dev_max']:+.1f} %", None, "-", "",
                    "placa rigida si ≤ 10 % (o ≤ 5 % de φRnt)")
            rec.check("Distribucion lineal aplicable (placa rigida)", d["T2max"], d["cap_max"],
                      "F", d["T2max"] / max(d["cap_max"], 1e-9), d["ok"], "criterio del programa")
    if rec:
        rec.check("Perno en traccion (distribucion lineal)", lin.T_max, phiRnt, "F",
                  lin.T_max / phiRnt if phiRnt > 0 else 0, lin.T_max <= phiRnt, "AISC J3.6")
        rec.check("Aplastamiento (distribucion lineal)", lin.p_max, br.fp_max, "S",
                  lin.p_max / br.fp_max if br.fp_max > 0 else 0, lin.p_max <= br.fp_max, "AISC J8")
    return lin, out
