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
_rw = solve(_w)
_cp = [c for c in _rw.checks if c.key == "weld_part"]
print(f"{'W soldado solo en el alma':34} weld_part D/C = {_cp[0].ratio if _cp else float('nan'):.2f}")
if not _cp or not any("NO esta soldada" in w for w in _rw.warnings):
    FAIL.append("soldadura parcial: falta la verificacion o el aviso")

# ---- el veredicto final lo da el analisis 3D
import types
from placabase.fem_checks import Fem3D
_m = Project(); _m.loads.Mux = 4200.0
_rm = solve(_m)
if not (_rm.pending and _rm.verdict == "PENDIENTE"):
    FAIL.append("sin 3D: el veredicto debe ser PENDIENTE (realizar analisis 3D)")
if not any("REALIZAR ANALISIS 3D" in w for w in _rm.warnings):
    FAIL.append("sin 3D: falta el aviso de realizar el analisis 3D")


def _mock_fem(prj, Ts, umax=0.1):
    """Paquete 3D simulado con la traccion `Ts` de cada perno."""
    pos = G.bolt_positions(prj)
    post = types.SimpleNamespace(
        bolts=[(k + 1, x, y, T) for k, ((x, y), T) in enumerate(zip(pos, Ts))],
        p_max=1.0, R_conc=sum(Ts) + prj.eloads.Pu, T_bolts=sum(Ts), zones=[], msg="simulado")
    return Fem3D(post=post, vm_avg=dict(vm=20.0, radius=1.0, x=0, y=0, z=0), rep={}, fast=True,
                 n_nodes=1000, n_elems=500, umax=umax, vmmax=90.0, sig=prj.sig3d())


_n = len(G.bolt_positions(_m))
_Ts = [0.0] * _n; _Ts[1] = 30.0; _Ts[3] = 20.0
_r3 = solve(_m, fem=_mock_fem(_m, _Ts))
_bt = [c for c in _r3.checks if c.key == "blt_t"][0]
print(f"{'con 3D simulado':34} veredicto = {_r3.verdict}  blt_t demanda = {_bt.demand:.1f} (esperado 30.0)  "
      f"filas fem_ = {[c.key for c in _r3.checks if c.key.startswith('fem_')]}")
if _r3.pending or abs(_bt.demand - 30.0) > 1e-6:
    FAIL.append("con 3D: la fuerza del perno de diseno debe salir del 3D y el veredicto dejar de ser PENDIENTE")
if not {"fem_bolt", "fem_press", "fem_vm"} <= {c.key for c in _r3.checks}:
    FAIL.append("con 3D: faltan las filas de verificacion FEM")
if any(c.key.startswith("lin_") for c in _r3.checks) or any("lineal" in w.lower() for w in _r3.warnings):
    FAIL.append("no debe quedar nada del reparto lineal en el veredicto")
# un 3D con un perno sobrecargado debe dar NO CUMPLE
_Ts2 = [0.0] * _n; _Ts2[0] = 500.0
if solve(_m, fem=_mock_fem(_m, _Ts2)).verdict != "NO CUMPLE":
    FAIL.append("con 3D sobrecargado el veredicto debe ser NO CUMPLE")
# la firma del 3D ignora datos cosmeticos y cambia con la geometria
_q1, _q2 = Project(), Project(); _q2.name = "otro"; _q2.author = "x"
_q3 = Project(); _q3.plate.tp = 2.5
if not (_q1.sig3d() == _q2.sig3d() and _q1.sig3d() != _q3.sig3d()):
    FAIL.append("firma del 3D: debe ignorar nombre/autor y detectar cambios de geometria")
print(f"{'firma del modelo 3D':34} ok")

# vista 3D: el modelo cabe completo (sin tocar los bordes) en ventanas anchas, altas y chicas
import matplotlib
matplotlib.use("Agg")
import numpy as np
from matplotlib.figure import Figure
from PIL import Image
import io
from placabase import view3d
_vp = Project()
_ok_view = True
for _w, _h in ((10.2, 5.0), (7, 6), (4, 8), (3, 2.5)):
    _fig = Figure(figsize=(_w, _h), dpi=100)
    _ax = _fig.add_axes([0, 0, 1, 1], projection="3d")
    view3d.plot_geometry(_ax, _vp)
    _ax.set_title("", loc="left")
    _ax.view_init(elev=24, azim=-58)
    view3d.fit_to_axes(_ax)
    _buf = io.BytesIO(); _fig.savefig(_buf, format="png"); _buf.seek(0)
    _im = np.array(Image.open(_buf).convert("L"))
    _ys, _xs = np.where(_im < 245)
    _ok = _xs.min() > 1 and _ys.min() > 1 and _xs.max() < _im.shape[1] - 2 and _ys.max() < _im.shape[0] - 2
    _fill = max((_xs.max() - _xs.min()) / _im.shape[1], (_ys.max() - _ys.min()) / _im.shape[0])
    _ok_view &= _ok and _fill > 0.7
    print(f"{'vista 3D ' + str((_w, _h)):34} cabe = {_ok}   ocupa {100 * _fill:.0f} % del lado limitante")
if not _ok_view:
    FAIL.append("vista 3D: el modelo debe caber completo y ocupar ~90 % del lado limitante")

# tamano de malla 3D automatico: sube con el area de la placa (costo acotado) y respeta el manual
from placabase import mesh3d
_a = Project(); _b = Project(); _b.plate.N = _b.plate.B = 80.0
_c = Project(); _c.fea.mesh3d = 1.5
_la, _lb, _lc = mesh3d.mesh_size_for(_a), mesh3d.mesh_size_for(_b), mesh3d.mesh_size_for(_c)
print(f"{'malla 3D automatica':34} placa 22 in: {_la:.2f} in   placa 80 in: {_lb:.2f} in   manual 1.5: {_lc:.2f} in")
if not (_lb > _la and abs(_lc - 1.5) < 1e-9):
    FAIL.append("malla 3D: el tamano automatico debe crecer con la placa y el manual tener prioridad")
_tok = mesh3d.CancelToken(); _tok.cancel()
if mesh3d.full_3d(Project(), __import__("tempfile").mkdtemp(), cancel=_tok)[1] != mesh3d.CANCELADO:
    FAIL.append("cancelar antes de empezar debe devolver 'cancelado'")

print()
print("CASOS LIMITE")
case("placa insuficiente", **{"loads.Mux": 26000.0})
case("perfil mas grande que placa", **{"section.label": "W14X730", "plate.N": 14.0, "plate.B": 14.0})

# ---------------------------------------------------- combinaciones de carga y flexion del perno
from placabase.model import LoadCombo
_cb = Project()
_cb.combos = [LoadCombo("A", 400, 1800, 0, 30, 0), LoadCombo("B", -100, 0, 0, 10, 0)]
_q0, _q1 = _cb.with_combo(0), _cb.with_combo(1)
if not (_q0.loads.Pu == 400 and _q1.loads.Pu == -100 and _cb.loads.Pu == 400 and _q0.sig3d() != _q1.sig3d()):
    FAIL.append("combinaciones: with_combo no aplica las cargas de la combinacion")
_rt = Project.from_json(_cb.to_json())
if [c.name for c in _rt.combos] != ["A", "B"]:
    FAIL.append("combinaciones: no sobreviven al guardar/abrir")
_so = Project(); _so.bolts.standoff = 2.0
_Rso = solve(_so)
_k = {c.key: c for c in _Rso.checks}
if "blt_m" not in _k or "blt_tm" not in _k or _k["blt_m"].ratio <= 0:
    FAIL.append("flexion del perno: faltan las verificaciones con stand-off")
_cant = Project(); _cant.bolts.standoff = 2.0; _cant.bolts.fixity = "Voladizo (placa libre de girar)"
_kc = {c.key: c for c in solve(_cant).checks}
if abs(_kc["blt_m"].demand / _k["blt_m"].demand - 2.0) > 1e-6:
    FAIL.append("flexion del perno: voladizo debe duplicar el momento del doble empotramiento")
if "blt_m" in {c.key for c in solve(Project()).checks}:
    FAIL.append("flexion del perno: sin stand-off no debe verificarse")
print(f"{'flexion del perno (stand-off 2 in)':34} M/φMn = {_k['blt_m'].ratio:.3f}   voladizo = {_kc['blt_m'].ratio:.3f}")


if "--3d" in sys.argv:
    # prueba de extremo a extremo con Gmsh + CalculiX (~30 s con la malla rapida)
    import tempfile
    from placabase import mesh3d
    from placabase.rep3d import make_fem
    print()
    from placabase.model import ENGINES
    print("ANALISIS SOLIDO 3D (--3d)")
    _p3 = Project(); _p3.fea.engine = ENGINES[0]
    _res, _msg = mesh3d.full_3d(_p3, tempfile.mkdtemp(prefix="pb3d_"))
    if _res is None:
        FAIL.append(f"3D: no corrio: {_msg[-300:]}")
    else:
        _fem = make_fem(_p3, _res)
        _R = solve(_p3, fem=_fem)
        _ks = [c.key for c in _R.checks if c.key.startswith("fem_")]
        _post = _fem.post
        _eq = _post.R_conc - _post.T_bolts - _p3.eloads.Pu
        print(f"{'3D PB-01':34} nodos={_fem.n_nodes:,}  R−ΣT−Pu = {_eq:+.3f} kip  filas: {_ks}")
        if abs(_eq) > 0.02 * max(1.0, abs(_p3.eloads.Pu)):
            FAIL.append(f"3D: equilibrio fuera de tolerancia ({_eq:+.2f} kip)")
        if not {"fem_bolt", "fem_press", "fem_vm"} <= set(_ks):
            FAIL.append("3D: faltan filas de verificacion FEM")
        if any("pendientes" in w for w in _R.warnings):
            FAIL.append("3D: no debe quedar el aviso de pendiente")
        if not (_fem.rep or {}).get("plan", {}).get("top"):
            FAIL.append("3D: no se generaron las vistas en planta")
        # soldadura con conectores: equilibrio vertical (contacto − cordones = Pu) y de cortante
        _eqw = _post.F_bear - _post.Fz_weld - _p3.eloads.Pu
        print(f"{'  soldadura: contacto − cordones − Pu':34} {_eqw:+.3f} kip   (modelo {_post.weld_model}, "
              f"contacto {_post.F_bear:.1f}, cordones {_post.Fz_weld:.1f})")
        if _post.weld_model != "conectores" or abs(_eqw) > 0.02 * abs(_p3.eloads.Pu):
            FAIL.append("3D: equilibrio vertical del cordon con conectores")
        # traccion pura: todo el axial pasa por los cordones y por los pernos
        _pt = Project(); _pt.fea.engine = ENGINES[0]; _pt.loads.Pu = -100.0; _pt.loads.Mux = 0.0; _pt.loads.Vux = 0.0
        _rt, _mt = mesh3d.full_3d(_pt, tempfile.mkdtemp(prefix="pb3d_"))
        if _rt is None:
            FAIL.append(f"3D traccion pura: no corrio: {_mt[-200:]}")
        else:
            _pp = _rt.post
            print(f"{'  traccion pura 100 kip':34} cordones {_pp.Fz_weld:.2f} kip  contacto {_pp.F_bear:.3f}  "
                  f"pernos {_pp.T_bolts:.2f}")
            if not (abs(_pp.Fz_weld - 100.0) < 2.0 and _pp.F_bear < 1.0 and abs(_pp.T_bolts - 100.0) < 2.0):
                FAIL.append("3D traccion pura: el axial debe pasar por cordones y pernos")
        # respaldo fusionado: corre y entrega zonas
        _pf = Project(); _pf.fea.engine = ENGINES[0]; _pf.fea.weld_model = "Fusionado (union monolitica, equivale a CJP)"
        _rf, _mf = mesh3d.full_3d(_pf, tempfile.mkdtemp(prefix="pb3d_"))
        if _rf is None or not _rf.post or not _rf.post.zones or _rf.post.weld_model != "fusionado":
            FAIL.append("3D fusionado: no entrego zonas de soldadura")
        else:
            print(f"{'  modelo fusionado (respaldo)':34} zonas = {[z.name for z in _rf.post.zones]}")

    # motor de placas (shell): corre, equilibra y entrega vistas y filas
    print()
    print("ANALISIS CON PLACAS (--3d)")
    _ps = Project(); _ps.fea.engine = ENGINES[1]
    _rs, _ms = mesh3d.full_3d(_ps, tempfile.mkdtemp(prefix="pbsh_"))
    if _rs is None:
        FAIL.append(f"placas: no corrio: {_ms[-300:]}")
    else:
        _fs = make_fem(_ps, _rs)
        _Rs = solve(_ps, fem=_fs)
        _ps_ = _fs.post
        _eqs = _ps_.R_conc - _ps_.T_bolts - _ps.eloads.Pu
        _ks = [c.key for c in _Rs.checks if c.key.startswith("fem_")]
        print(f"{'placas PB-01':34} nodos={_fs.n_nodes:,}  R−ΣT−Pu = {_eqs:+.3f} kip  filas: {_ks}")
        if abs(_eqs) > 0.02 * max(1.0, abs(_ps.eloads.Pu)):
            FAIL.append(f"placas: equilibrio fuera de tolerancia ({_eqs:+.2f} kip)")
        if not {"fem_bolt", "fem_press", "fem_vm"} <= set(_ks):
            FAIL.append("placas: faltan filas de verificacion FEM")
        if not (_fs.rep or {}).get("plan", {}).get("top"):
            FAIL.append("placas: no se generaron las vistas en planta")

print()
print("=" * 150)
if FAIL:
    print(f"FALLAS ({len(FAIL)}):")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("TODAS LAS PRUEBAS DEL MOTOR PASARON")
