# -*- coding: utf-8 -*-
"""Parametros comunes del modelo 3D: brazo del cortante, modulo de balasto y rigidez axial del perno."""
from __future__ import annotations

from .model import Project
from .units import ES_KSI, Ec_ksi


def shear_arm(prj: Project) -> float:
    """Brazo e (in) entre donde el cortante entra en la placa (cara superior) y donde lo
    devuelven los pernos o la llave.  Manual si fea.shear_arm >= 0; si no:
      sin llave : tp/2 + mortero  (el perno apoya en el centro del espesor y, con mortero,
                  trabaja a esa altura sobre el concreto)
      con llave : tp + H/2        (la llave reacciona en el centro de su altura de apoyo)."""
    a = float(getattr(prj.fea, "shear_arm", -1.0))
    if a >= 0:
        return a
    p = prj.plate
    if prj.lug.enabled:
        return p.tp + 0.5 * prj.lug.H
    return 0.5 * p.tp + max(0.0, p.grout)


def foundation_ks(prj: Project) -> float:
    if prj.fea.ks_mode == "manual":
        return max(1.0, prj.fea.ks_manual)
    return Ec_ksi(prj.conc.fc) / max(6.0, prj.conc.ha)


def bolt_kb(prj: Project) -> float:
    g = prj.bolts.geom()
    Lb = prj.bolts.hef + prj.plate.tp + prj.plate.grout
    return ES_KSI * g.Ase / max(Lb, 1.0)
