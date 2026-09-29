# -*- coding: utf-8 -*-
"""Orquesta todas las verificaciones y devuelve un resultado unico."""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from .model import Project
from . import design as D
from . import anchors as A
from . import geometry as G
from . import materials as M
from .design import Check, Bearing
from .explain import Recorder
from .fea import run_fea, FEAResult


@dataclass
class Results:
    br: Bearing = None
    treq: float = 0.0
    tdet: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    fea: FEAResult = None
    warnings: list = field(default_factory=list)
    rec: Recorder = None

    @property
    def max_ratio(self) -> float:
        rs = [c.ratio for c in self.checks if not c.skip]
        return max(rs) if rs else 0.0

    @property
    def governing(self) -> Check | None:
        act = [c for c in self.checks if not c.skip]
        return max(act, key=lambda c: c.ratio) if act else None

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if not c.skip) and not self.warnings_fatal

    @property
    def warnings_fatal(self) -> bool:
        return any(w.startswith("**") for w in self.warnings)


def solve(prj: Project, with_fea: bool = True, detail: bool = True) -> Results:
    R = Results()
    R.rec = Recorder(prj.units()) if detail else None
    rec = R.rec
    if rec:
        rec.section("DATOS DE PARTIDA")
        u = prj.units()
        s_ = prj.section.shape()
        rec.add("Perfil", prj.section.label,
                f"{prj.section.steel}, rotacion {prj.section.rotation:g}°", None)
        rec.add("Placa", ("Ø" + rec.n('L', prj.plate.Dp)
                          if prj.plate.shape == "Circular"
                          else f"{rec.n('L', prj.plate.N)} × {rec.n('L', prj.plate.B)}")
                + f" × {rec.n('L', prj.plate.tp)} {u.L}", prj.plate.steel, None)
        rec.add("Pu", "axial factorizado (compresion +)", "", prj.loads.Pu, "F")
        rec.add("Mux", "momento respecto al eje fuerte", "", prj.loads.Mux, "M")
        rec.add("Muy", "momento respecto al eje debil", "", prj.loads.Muy, "M")
        rec.add("Vu", "cortante resultante",
                f"√({rec.n('F', prj.loads.Vux)}² + {rec.n('F', prj.loads.Vuy)}²)",
                prj.loads.Vu, "F")
        rec.add("f'c", "resistencia del concreto", "", prj.conc.fc, "S")
        rec.add("Fy placa", "", prj.plate.steel, prj.plate.mat().Fy, "S")
        rec.add("Anclajes", f"{prj.bolts.n_total} × Ø{prj.bolts.size} in",
                f"{prj.bolts.steel}, {prj.bolts.atype}, hef = "
                f"{rec.f('L', prj.bolts.hef)}", None)
    R.br = D.bearing(prj, rec)
    br = R.br
    p, b, c, L = prj.plate, prj.bolts, prj.conc, prj.loads

    # ------------------------------------------------------------ avisos
    if not br.feasible:
        R.warnings.append("** El discriminante del equilibrio es negativo: la placa no puede "
                          "equilibrar Pu y Mu. Aumente N, B o f'c, o acerque los pernos al borde. **")
    if b.atype.startswith("Recto") and br.Tu > 1e-6:
        R.warnings.append("** Varilla recta sin cabeza ni gancho con traccion en los pernos: "
                          "ACI 318-19 no le reconoce resistencia a la extraccion. **")
    if abs(prj.section.rotation) > 1e-6 and abs(abs(prj.section.rotation) - 90) > 1e-6:
        R.warnings.append("Rotacion del perfil distinta de 0° o 90°: las formulas cerradas de "
                          "DG1 usan el rectangulo envolvente del perfil (conservador). "
                          "El modelo de elementos finitos si usa la geometria real.")
    if p.shape == "Circular":
        R.warnings.append("Placa circular: las formulas cerradas usan el cuadrado equivalente de "
                          "igual area (Leq = 0.8862·Dp).")
    emin = M.min_edge_distance(b.size)
    if min(b.ex, b.ey) < emin - 1e-6:
        R.warnings.append(f"Distancia al borde menor que la minima recomendada "
                          f"({u.q('L', emin)} para perno de {b.size}\").")
    cl = G.bolt_clashes(prj)
    if cl:
        lst = ", ".join(f"#{k} ({x:.1f},{y:.1f})" for k, x, y, _ in cl[:6])
        R.warnings.append(f"** {len(cl)} perno(s) interfieren con el perfil o no dejan holgura "
                          f"para tuerca/llave: {lst}. Cambie la rotacion, ex/ey o la disposicion. **")
    bw, bh = G.profile_bbox(prj)
    if bw > p.Bc + 1e-6 or bh > p.Nc + 1e-6:
        R.warnings.append("** El perfil no cabe dentro de la placa. **")
    if c.seismic:
        R.warnings.append("Diseno sismico activo: se aplica el factor 0.75 a la resistencia del "
                          "concreto de los anclajes (ACI 17.10.5.2). Verifique ademas el requisito "
                          "de que el anclaje sea gobernado por la fluencia ductil del acero.")

    # ------------------------------------------------------------ chequeos
    ck: list[Check] = []

    ratio_brg = 0.0 if br.case == "TRACCION NETA" else (
        99.0 if not br.feasible else (br.fp / br.fp_max if br.fp_max > 0 else 99.0))
    ck.append(Check("brg", "Aplastamiento del concreto bajo la placa",
                    br.fp, br.fp_max, "ksi", "AISC J8 / DG1 §3.3",
                    {"CASO 1": "Presion uniforme sobre la longitud Y.",
                     "CASO 2": "La presion alcanza fp,max por definicion del metodo; "
                               "el equilibrio se logra con traccion en los pernos.",
                     "TRACCION NETA": "No hay aplastamiento: la placa esta en traccion neta."}
                    .get(br.case, "")))
    if not br.feasible:
        ck[-1].capacity = 0.0
        ck[-1].demand = 1.0

    if rec:
        rec.check("Aplastamiento del concreto", br.fp, br.fp_max, "S",
                  ratio_brg, ratio_brg <= 1.0, "AISC J8")
    R.treq, R.tdet = D.plate_thickness(prj, br, rec)
    ck.append(Check("tp", "Espesor de la placa  tp ≥ t requerido",
                    R.treq, p.tp, "in", "DG1 §3.1 y §3.3",
                    f"m={u.q('L', R.tdet['m_y'])}, n={u.q('L', R.tdet['m_x'])}, "
                    f"λn'={u.q('L', R.tdet['lam_n'])}"
                    + ("  (voladizos reducidos por los rigidizadores)" if prj.stiff.enabled else "")))

    if rec:
        rec.check("Espesor de la placa", R.treq, p.tp, "L",
                  R.treq / max(p.tp, 1e-9), R.treq <= p.tp, "DG1 §3.1")
    ck += A.anchor_checks(prj, br, rec)
    ck += D.welds(prj, br, rec)
    ck += D.shear_lug(prj, rec)
    ck += D.stiffeners(prj, br, rec)
    ck += D.column_base(prj)
    R.checks = ck

    # ------------------------------------------------------------ FEA
    if with_fea and prj.fea.enabled:
        R.fea = run_fea(prj)
        if R.fea.ok:
            Fy = p.mat().Fy
            R.checks.append(Check("fea_vm", "FEA — von Mises en la placa",
                                  R.fea.vm_max, 0.90 * Fy, "ksi",
                                  "AISC F11 / criterio de fluencia",
                                  f"malla {prj.fea.nx}×{prj.fea.ny}, {R.fea.msg}"))
            R.checks.append(Check("fea_press", "FEA — presion de contacto maxima",
                                  R.fea.press_max, br.fp_max, "ksi", "AISC J8",
                                  "Distribucion real obtenida del modelo, no el bloque rectangular."))
            g = b.geom()
            Tmax = max(R.fea.bolt_T) if R.fea.bolt_T else 0.0
            R.checks.append(Check("fea_bolt", "FEA — traccion maxima en un perno",
                                  Tmax, 0.75 * 0.75 * b.mat().Fu * g.Ab, "kip",
                                  "AISC J3", "Reparto real segun la rigidez de la placa."))
            if rec:
                uu = prj.units()
                rec.section("I.  ELEMENTOS FINITOS DE LA PLACA")
                rec.text("Placa de Mindlin-Reissner, elemento MITC4, sobre resortes "
                         "de Winkler solo a compresion; los pernos son resortes solo "
                         "a traccion repartidos en el anillo de apoyo de la tuerca.")
                rec.add("malla", f"{prj.fea.nx} × {prj.fea.ny}",
                        ("agujeros de perno mallados" if R.fea.holes_meshed
                         else "agujeros no mallados"), None)
                rec.add("w max", "deflexion maxima", "", R.fea.w_max, "L")
                rec.add("p max", "presion de contacto maxima", "", R.fea.press_max, "S")
                rec.add("σ von Mises max", "6·M/t² en la superficie", "",
                        R.fea.vm_max, "S")
                rec.add("equilibrio", "R concreto − R pernos − ΣF",
                        f"{rec.n('F', R.fea.R_found)} − {rec.n('F', R.fea.R_bolts)} − "
                        f"{rec.n('F', R.fea.sumF)}",
                        R.fea.R_found - R.fea.R_bolts - R.fea.sumF, "F",
                        "", "residuo de equilibrio del modelo")
    return R
