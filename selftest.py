# -*- coding: utf-8 -*-
"""Autopruebas del motor de calculo (sin interfaz grafica)."""
import sys, math, traceback
sys.path.insert(0, ".")

from placabase.model import Project
from placabase.solver import solve
from placabase import geometry as G
from placabase.shapes import CATALOG, W_SHAPE, HSS_RECT, HSS_ROUND, PIPE

FAIL = []


def case(name, **mut):
    prj = Project()
    for path, val in mut.items():
        obj = prj
        parts = path.split(".")
        for q in parts[:-1]:
            obj = getattr(obj, q)
        setattr(obj, parts[-1], val)
    try:
        r = solve(prj)
    except Exception as e:
        FAIL.append(f"{name}: EXCEPCION {e}")
        traceback.print_exc()
        return None, None
    pos = G.bolt_positions(prj)
    feamsg = ""
    if r.fea is not None:
        if not r.fea.ok:
            FAIL.append(f"{name}: FEA fallo -> {r.fea.msg}")
        else:
            err = r.fea.R_found - r.fea.R_bolts - r.fea.sumF
            if abs(err) > 0.02 * max(1.0, abs(r.fea.sumF)):
                FAIL.append(f"{name}: equilibrio FEA fuera de tolerancia ({err:+.2f} kip)")
            feamsg = (f" | FEA vm={r.fea.vm_max:6.1f} ksi  p={r.fea.press_max:5.2f}  "
                      f"eq={err:+.3f}  it={r.fea.iters}")
    gov = r.governing.title[:38] if r.governing else "-"
    print(f"{name:34} n={len(pos):3d}  caso={r.br.case:13} Tu={r.br.Tu:7.1f}  "
          f"treq={r.treq:5.2f}  D/C={r.max_ratio:6.3f}  gob={gov:40}{feamsg}")
    for w in r.warnings:
        if w.startswith("**"):
            print(f"    AVISO CRITICO: {w}")
    return prj, r


print("=" * 150)
print("CASOS BASE")
print("=" * 150)
case("W14X90 base")
case("W14X90 rot 90", **{"section.rotation": 90.0})
case("W14X90 rot 30", **{"section.rotation": 30.0})
case("W14X90 M alto", **{"loads.Mux": 5200.0})
case("W14X90 traccion neta", **{"loads.Pu": -60.0, "loads.Mux": 900.0})
case("W14X90 sin momento", **{"loads.Mux": 0.0})

print()
print("PERFILES")
case("W36 grande", **{"section.label": "W24X162", "plate.N": 34.0, "plate.B": 30.0,
                      "plate.tp": 2.5, "loads.Pu": 900.0, "loads.Mux": 6000.0})
case("HSS12X12X1/2", **{"section.label": "HSS12X12X1/2", "section.steel": "ASTM A500 Gr.B (HSS rect.)"})
case("HSS8X4X1/2 rot90", **{"section.label": "HSS8X4X1/2", "section.rotation": 90.0,
                            "section.steel": "ASTM A500 Gr.B (HSS rect.)"})
case("HSS10.75X0.5 redondo", **{"section.label": "HSS10.75X0.5",
                                "section.steel": "ASTM A500 Gr.B (HSS red.)"})
case("Pipe 8 XS", **{"section.label": "Pipe 8 XS", "section.steel": "ASTM A53 Gr.B (Pipe)"})

print()
print("DISPOSICION DE PERNOS")
case("2 lados eje mayor", **{"bolts.pattern": "2 lados (eje mayor)"})
case("2 lados eje menor", **{"bolts.pattern": "2 lados (eje menor)"})
case("perim 4x2", **{"bolts.n_major": 4, "bolts.n_minor": 2})
case("perim 2x5", **{"bolts.n_major": 2, "bolts.n_minor": 5})
case("perim 5x5", **{"bolts.n_major": 5, "bolts.n_minor": 5})
case("placa circular 12 pernos", **{"plate.shape": "Circular", "plate.Dp": 30.0,
                                    "bolts.pattern": "Circular", "bolts.n_circ": 12,
                                    "section.label": "HSS10.75X0.5"})

print()
print("TIPOS DE PERNO")
for at in ["Con cabeza (hex pesada)", "Gancho en L", "Gancho en J", "Recto (sin cabeza)"]:
    case(f"anclaje {at[:22]}", **{"bolts.atype": at, "loads.Mux": 5200.0})

print()
print("DIAMETROS Y MATERIALES")
for sz in ["3/4", "1", "1-1/2", "2", "3"]:
    case(f"perno {sz}\"", **{"bolts.size": sz, "bolts.ex": 3.5, "bolts.ey": 3.5})
for st in ["ASTM F1554 Gr.36", "ASTM F1554 Gr.105", "ASTM F3125 Gr.A490"]:
    case(f"{st[5:]}", **{"bolts.steel": st, "loads.Mux": 5200.0})

print()
print("LLAVE DE CORTE Y RIGIDIZADORES")
case("llave X", **{"lug.enabled": True, "loads.Vux": 90.0})
case("llave ambos ejes", **{"lug.enabled": True, "lug.direction": "Ambos ejes",
                            "loads.Vux": 70.0, "loads.Vuy": 70.0})
case("rigidizadores alas", **{"stiff.enabled": True, "stiff.position": "Alas (paralelo a Y)"})
case("rigidizadores ambos", **{"stiff.enabled": True, "stiff.position": "Ambos", "stiff.count": 8})
case("rigid HSS perimetro", **{"section.label": "HSS12X12X1/2", "stiff.enabled": True,
                               "stiff.position": "Perimetro HSS (4 caras)", "stiff.count": 8,
                               "section.steel": "ASTM A500 Gr.B (HSS rect.)"})
case("llave + rigidizadores", **{"lug.enabled": True, "stiff.enabled": True,
                                 "loads.Vux": 90.0, "loads.Mux": 4200.0})

print()
print("SOLDADURA")
case("CJP alas", **{"welds.flange": __import__("placabase.model", fromlist=["WeldSpec"]).WeldSpec(
    "CJP (penetracion completa)", 0.0, "E70XX", True)})
case("filete chico", **{"welds.flange": __import__("placabase.model", fromlist=["WeldSpec"]).WeldSpec(
    "Filete", 0.1875, "E70XX", True), "loads.Mux": 5200.0})

print()
print("CONCRETO / SISMO")
case("no fisurado", **{"conc.cracked": False, "loads.Mux": 5200.0})
case("condicion A", **{"conc.cond_A": True, "loads.Mux": 5200.0})
case("sismico", **{"conc.seismic": True, "loads.Mux": 5200.0})
case("pedestal chico", **{"conc.N2": 26.0, "conc.B2": 26.0, "loads.Mux": 5200.0})
case("f'c 6 ksi", **{"conc.fc": 6.0, "loads.Mux": 5200.0})

print()
print("FAMILIAS AISC, SECCIONES DOBLES, PERSONALIZADAS Y LLAVES DE PERFIL")
case("L6X6X1/2", **{"section.label": "L6X6X1/2", "section.steel": "ASTM A36"})
case("2L6X6X1/2 espalda con espalda", **{"section.label": "L6X6X1/2", "section.double": True,
                                        "section.gap": 0.75})
case("2C10X15.3 rot 90", **{"section.label": "C10X15.3", "section.double": True,
                            "section.rotation": 90.0})
case("WT9X25", **{"section.label": "WT9X25"})
case("MC12X31", **{"section.label": "MC12X31"})
case("HP12X53", **{"section.label": "HP12X53"})
case("S12X35", **{"section.label": "S12X35"})
case("llave W8X31", **{"lug.enabled": True, "lug.ltype": "Perfil (cualquier seccion)",
                       "lug.label": "W8X31", "loads.Vux": 40.0})
case("llave HSS6X6X1/2 girada", **{"lug.enabled": True, "lug.ltype": "Perfil (cualquier seccion)",
                                   "lug.label": "HSS6X6X1/2", "lug.rotation": 90.0,
                                   "loads.Vuy": 30.0})
case("llave Pipe6STD", **{"lug.enabled": True, "lug.ltype": "Perfil (cualquier seccion)",
                          "lug.label": "Pipe6STD", "loads.Vux": 25.0})
case("adhesivo + coord. manuales", **{"bolts.atype": "Recto (sin cabeza)",
                                      "bolts.install": "Postinstalado adhesivo (epoxico)",
                                      "bolts.pattern": "Coordenadas manuales",
                                      "bolts.coords": [[-8.5, -8.5], [8.5, -8.5], [8.5, 8.5],
                                                       [-8.5, 8.5], [0.0, 8.5]]})

# grupo de soldadura contra calculo a mano
from placabase.shapes import CATALOG, make_custom, PLATE
from placabase.model import WeldSpec
from placabase import design as _D
CATALOG.shapes["_PLT"] = make_custom("_PLT", PLATE, 12.0, 1.0, 1.0)
_p = Project(); _p.section.label = "_PLT"
_g = _D.weld_group(_p, G.section_rects(_p), WeldSpec(size=0.5), P=-100.0)
_g2 = _D.weld_group(_p, G.section_rects(_p), WeldSpec(size=0.5), Mx=360.0)
print(f"{'grupo de soldadura (a mano)':34} traccion f={_g['fmax']:.3f} (3.846)  "
      f"momento f={_g2['fmax']:.3f} (6.000)")
if abs(_g["fmax"] - 100 / 26) > 0.01 or abs(_g2["fmax"] - 6.0) > 0.02:
    FAIL.append("grupo de soldadura: no coincide con el calculo a mano")
# seccion doble contra la tabla AISC (2L4X4X1/2, s = 3/8: Iy = 25.1 in4)
_q = Project(); _q.section.label = "L4X4X1/2"; _q.section.double = True; _q.section.gap = 0.375
_e = _q.section.eff()
print(f"{'2L4X4X1/2 s=3/8 contra AISC':34} Iy={_e.Iy:.2f} (25.1)  Ix={_e.Ix:.2f} (11.0)")
if abs(_e.Iy - 25.1) > 0.5:
    FAIL.append("seccion doble: Iy no coincide con AISC")

# columna inclinada: la proyeccion conserva la magnitud de fuerza y momento
_t = Project(); _t.loads.tilt_x = 15.0; _t.loads.tilt_y = 20.0
_e = _t.eloads
_f0 = math.hypot(_t.loads.Pu, _t.loads.Vux, _t.loads.Vuy)
_f1 = math.hypot(_e.Pu, _e.Vux, _e.Vuy)
_m1 = math.hypot(_e.Mux, _e.Muy, _e.Tz)
print(f"{'columna inclinada (15°, 20°)':34} |F| {_f0:.3f} -> {_f1:.3f}   |M| 1800 -> {_m1:.3f}")
if abs(_f0 - _f1) > 1e-6 or abs(_m1 - 1800.0) > 1e-6:
    FAIL.append("columna inclinada: la rotacion de cargas no conserva la magnitud")
_t = Project(); _t.loads.tilt_x = 30.0; _t.loads.Vux = 0.0
if abs(_t.eloads.Pu - 400 * math.cos(math.radians(30))) > 1e-6 or abs(_t.eloads.Vuy - 400 * 0.5) > 1e-6:
    FAIL.append("columna inclinada: componentes normal/tangencial incorrectas")
case("columna inclinada 20°", **{"loads.tilt_y": 20.0})

# perfil W soldado solo en el alma: la soldadura parcial debe tomar el momento
_w = Project(); _w.welds.flange.wtype = "Sin soldadura"
_rw = solve(_w, with_fea=False)
_cp = [c for c in _rw.checks if c.key == "weld_part"]
print(f"{'W soldado solo en el alma':34} weld_part D/C = {_cp[0].ratio if _cp else float('nan'):.2f}")
if not _cp or not any("NO esta soldada" in w for w in _rw.warnings):
    FAIL.append("soldadura parcial: falta la verificacion o el aviso")

# 2D: signo de Muy (mano derecha, como el 3D) y asimetria por cortante
from placabase.fea import run_fea
_f = Project(); _f.loads.Mux = 0.0; _f.loads.Vux = 0.0; _f.loads.Muy = 3000.0
_r = run_fea(_f)
_tm = sum(T for (x, y), T in zip(_r.bolt_xy, _r.bolt_T) if x < 0)
_tp_ = sum(T for (x, y), T in zip(_r.bolt_xy, _r.bolt_T) if x > 0)
print(f"{'2D Muy>0 tracciona -X':34} T(-X) = {_tm:.1f}  T(+X) = {_tp_:.1f}")
if not (_tm > 5.0 and _tp_ < 0.5):
    FAIL.append("2D: Muy > 0 debe traccionar el lado -X (convencion del 3D)")
_g = Project(); _g.loads.Vux = 30.0
_rg = run_fea(_g)
_a = sum(T for (x, y), T in zip(_rg.bolt_xy, _rg.bolt_T) if x < 0)
_b = sum(T for (x, y), T in zip(_rg.bolt_xy, _rg.bolt_T) if x > 0)
_g.loads.Vux = 0.0
_r0 = run_fea(_g)
_s0 = [T for (x, y), T in zip(_r0.bolt_xy, _r0.bolt_T) if x < 0]
_s1 = [T for (x, y), T in zip(_r0.bolt_xy, _r0.bolt_T) if x > 0]
print(f"{'2D cortante Vux>0':34} T(-X) = {_a:.2f}  T(+X) = {_b:.2f}   (Vux=0: {sum(_s0):.2f} / {sum(_s1):.2f})")
if not (_a > _b + 0.1 and abs(sum(_s0) - sum(_s1)) < 1e-6):
    FAIL.append("2D: el cortante debe cargar mas el lado -X y sin cortante debe ser simetrico")

# ---- fuerza por perno con distribucion lineal (placa rigida)
from placabase.linear import linear_bolt_forces
from placabase.model import BOLT_FORCE_METHODS
_l = Project(); _l.lug.enabled = False
_l.loads.Mux = 0.0; _l.loads.Muy = 0.0; _l.loads.Vux = 0.0; _l.loads.Vuy = 0.0; _l.loads.Pu = 400.0
_r = linear_bolt_forces(_l)
print(f"{'lineal: axial puro':34} T = {_r.T_sum:.4f}  p = {_r.p_max:.4f}  (Pu/A = {400 / _r.A_plate:.4f})")
if not (_r.ok and _r.T_sum < 1e-9 and abs(_r.p_max - 400 / _r.A_plate) < 1e-6):
    FAIL.append("lineal: axial puro debe dar T = 0 y p = Pu/A")
_l.loads.Mux = 4200.0
_r = linear_bolt_forces(_l)
_mchk = sum(T * y for (x, y), T in zip(_r.bolt_xy, _r.bolt_T)) - _r.R_conc * _r.yc
print(f"{'lineal: equilibrio (Mux 4200)':34} ΣT = {_r.T_sum:.2f}  R−ΣT−Pu = {_r.R_conc - _r.T_sum - 400:+.2e}  M = {_mchk:.2f}")
if not (_r.ok and abs(_r.R_conc - _r.T_sum - 400) < 1e-6 and abs(_mchk - 4200) < 1e-3 and _r.T_sum > 10):
    FAIL.append("lineal: equilibrio de fuerzas y momentos")
# limite de placa rigida: el 2D con una placa muy gruesa debe coincidir con la distribucion lineal
_t = Project(); _t.lug.enabled = False; _t.loads.Mux = 4200.0; _t.loads.Vux = 0.0; _t.plate.tp = 12.0
_rl, _rf = linear_bolt_forces(_t), run_fea(_t)
_dif = abs(sum(_rf.bolt_T) - _rl.T_sum) / _rl.T_sum
print(f"{'placa rigida: 2D contra lineal':34} ΣT lineal {_rl.T_sum:.2f}  2D {sum(_rf.bolt_T):.2f}  ({100 * _dif:.1f} %)")
if _dif > 0.05:
    FAIL.append("placa rigida: el 2D no converge a la distribucion lineal")
_m = Project(); _m.bolts.force_method = BOLT_FORCE_METHODS[1]
_rm = solve(_m, with_fea=True)
if not any(c.key == "lin_rigid" for c in _rm.checks):
    FAIL.append("metodo lineal: falta la verificacion de placa rigida")
# validacion de la placa rigida contra el 3D (simulado con las mismas fuerzas: debe cumplir)
import types
from placabase.linear_checks import apply_3d_validation
_rm.post3d = types.SimpleNamespace(bolts=[(k + 1, x, y, T) for k, ((x, y), T) in enumerate(zip(_rm.lin.bolt_xy, _rm.lin.bolt_T))])
_ok3d = apply_3d_validation(_m, _rm)
_row = [c for c in _rm.checks if c.key == "lin_rigid"]
if not (_ok3d and _row and _row[0].ok and "3D" in _row[0].title):
    FAIL.append("validacion de placa rigida contra el 3D")
print(f"{'metodo lineal en el solver':34} D/C max = {_rm.max_ratio:.2f}  filas lin_ = {[c.key for c in _rm.checks if c.key.startswith('lin_')]}")

print()
print("CASOS LIMITE")
case("placa insuficiente", **{"loads.Mux": 26000.0})
case("perfil mas grande que placa", **{"section.label": "W14X730", "plate.N": 14.0, "plate.B": 14.0})
case("malla fina", **{"fea.nx": 44, "fea.ny": 44})
case("sin FEA", **{"fea.enabled": False})

print()
print("=" * 150)
if FAIL:
    print(f"FALLAS ({len(FAIL)}):")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DEL MOTOR PASARON")
