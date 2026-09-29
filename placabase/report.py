# -*- coding: utf-8 -*-
"""Reportes: imagen, hoja de calculo y memoria de calculo en Word."""
from __future__ import annotations
from pathlib import Path
import datetime
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .model import Project
from .solver import Results
from . import draw, geometry as G
from .units import U, UnitSet, float_to_frac


def _units(prj) -> UnitSet:
    return UnitSet(getattr(prj, "u_len", "in"), getattr(prj, "u_force", "kip"),
                   getattr(prj, "u_stress", "ksi"), getattr(prj, "u_moment", None))


def ck_vals(us: UnitSet, ch):
    """Demanda, capacidad y etiqueta de unidad de una verificacion, ya
    convertidas al sistema que eligio el usuario."""
    k = ch.kind
    if k == "-":
        return ch.demand, ch.capacity, ch.unit
    return us.out(k, ch.demand), us.out(k, ch.capacity), us.label(k)


# =================================================================== imagenes
def input_rows(prj: Project, us: UnitSet) -> list[tuple[str, str]]:
    """Tabla de datos de entrada, convertida a las unidades elegidas."""
    p, b, c, L = prj.plate, prj.bolts, prj.conc, prj.eloads
    q = us.q
    geo = (f"Ø{q('L', p.Dp)}" if p.shape == "Circular"
           else f"{q('L', p.N)} × {q('L', p.B)}")
    return [
        ("Perfil", f"{prj.section.label} ({prj.section.steel}), "
                   f"rotacion {prj.section.rotation:g}°"),
        ("Placa base", f"{geo} × {q('L', p.tp)}, {p.steel} "
                       f"(Fy = {q('S', p.mat().Fy)})"),
        ("Mortero", q("L", p.grout)),
        ("Anclajes", f"{b.n_total} Ø{b.size} in ({q('L', b.geom().db)}), {b.steel}, "
                     f"{b.atype}, hef = {q('L', b.hef)}"),
        ("Agujeros", f"{q('L', b.geom().dh)} — {b.hole_rule}"),
        ("Disposicion", f"{b.pattern} — {b.n_major} en eje mayor, "
                        f"{b.n_minor} en eje menor, ex = {q('L', b.ex)}, "
                        f"ey = {q('L', b.ey)}"),
        ("Concreto", f"f'c = {q('S', c.fc)}, pedestal {q('L', c.N2)} × {q('L', c.B2)}, "
                     f"ha = {q('L', c.ha)}, "
                     f"{'fisurado' if c.cracked else 'no fisurado'}, "
                     f"condicion {'A' if c.cond_A else 'B'}"),
        ("Llave de corte", (f"{q('L', prj.lug.W)} × {q('L', prj.lug.H)} × "
                            f"{q('L', prj.lug.t)}, {prj.lug.direction}"
                            if prj.lug.enabled else "No")),
        ("Rigidizadores", (f"{prj.stiff.count} pletinas {q('L', prj.stiff.t)} × "
                           f"{q('L', prj.stiff.h)}, proyeccion {q('L', prj.stiff.L)}, "
                           f"{prj.stiff.shape}, {prj.stiff.position}"
                           if prj.stiff.enabled else "No")),
        ("Soldadura ala", f"{prj.welds.flange.wtype} {q('L', prj.welds.flange.size)}, "
                          f"{prj.welds.flange.electrode}"),
        ("Soldadura alma", f"{prj.welds.web.wtype} {q('L', prj.welds.web.size)}, "
                           f"{prj.welds.web.electrode}"),
        ("Soldadura perimetral", f"{prj.welds.perimeter.wtype} "
                                 f"{q('L', prj.welds.perimeter.size)}, "
                                 f"{prj.welds.perimeter.electrode}"),
        ("Cargas (LRFD)" + (" en ejes de la placa" if prj.loads.tilted else ""),
         f"Pu = {q('F', L.Pu)}, Mux = {q('M', L.Mux)}, "
         f"Muy = {q('M', L.Muy)}, Vux = {q('F', L.Vux)}, "
         f"Vuy = {q('F', L.Vuy)}"),
        ("Columna inclinada", (f"giro X = {prj.loads.tilt_x:g}°, giro Y = {prj.loads.tilt_y:g}°; "
                               f"cargas en el eje: Pu = {q('F', prj.loads.Pu)}, "
                               f"Vux = {q('F', prj.loads.Vux)}, Vuy = {q('F', prj.loads.Vuy)}, "
                               f"Mux = {q('M', prj.loads.Mux)}, Muy = {q('M', prj.loads.Muy)}")
                              if prj.loads.tilted else "no (perpendicular a la placa)"),
    ]


def bolt_rows(res: Results, us: UnitSet):
    """(encabezados, filas) de la tabla de tensiones perno por perno."""
    fr = getattr(res, "fea", None)
    if fr is None or not fr.ok or not getattr(fr, "bolt_T", None):
        return None, []
    hdr = ["Perno", f"x ({us.L})", f"y ({us.L})", f"T ({us.F})",
           f"σt ({us.S})", "D/C"]
    orden = sorted(range(len(fr.bolt_T)), key=lambda i: -fr.bolt_T[i])
    filas = []
    for i in orden:
        x, y = fr.bolt_xy[i]
        filas.append([f"P{i + 1}", us.fmt("L", x), us.fmt("L", y),
                      us.fmt("F", fr.bolt_T[i]), us.fmt("S", fr.bolt_sig[i]),
                      f"{fr.bolt_ratio[i]:.3f}"])
    return hdr, filas


def save_figures(prj: Project, res: Results, folder: str) -> list[str]:
    f = Path(folder)
    f.mkdir(parents=True, exist_ok=True)
    paths = []

    fig, ax = plt.subplots(figsize=(7.0, 7.0), dpi=150)
    draw.plan_view(ax, prj)
    fig.tight_layout()
    p1 = f / "planta.png"; fig.savefig(p1); plt.close(fig); paths.append(str(p1))

    fig, ax = plt.subplots(figsize=(7.0, 5.0), dpi=150)
    draw.elevation_view(ax, prj)
    fig.tight_layout()
    p2 = f / "elevacion.png"; fig.savefig(p2); plt.close(fig); paths.append(str(p2))

    if res.fea is not None and res.fea.ok:
        for key, name in (("vm", "fea_vonmises"), ("p", "fea_presion"), ("w", "fea_deflexion")):
            fig, ax = plt.subplots(figsize=(6.5, 6.0), dpi=150)
            cs = draw.fea_view(ax, prj, res.fea, key)
            if cs is not None:
                fig.colorbar(cs, ax=ax, shrink=0.85)
            fig.tight_layout()
            pp = f / f"{name}.png"; fig.savefig(pp); plt.close(fig); paths.append(str(pp))
    return paths


# ==================================================================== XLSX
def export_xlsx(prj: Project, res: Results, path: str,
                figs: list[str] | None = None, detail: bool = True) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image as XLImage

    u = U(prj.metric)
    F = "Arial"
    B = Font(name=F, size=10, bold=True)
    N = Font(name=F, size=10)
    S = Font(name=F, size=8, italic=True, color="595959")
    HD = Font(name=F, size=10, bold=True, color="FFFFFF")
    FH = PatternFill("solid", fgColor="2E75B6")
    OKF = PatternFill("solid", fgColor="C6EFCE")
    NOF = PatternFill("solid", fgColor="FFC7CE")
    thin = Side(style="thin", color="BFBFBF")
    BX = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = Workbook()
    ws = wb.active
    ws.title = "RESUMEN"
    for col, w in zip("ABCDEFG", (3, 54, 14, 14, 10, 11, 74)):
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False

    def band(r, t):
        ws.merge_cells(f"B{r}:G{r}")
        ws[f"B{r}"] = t
        for c in "BCDEFG":
            ws[f"{c}{r}"].fill = FH
            ws[f"{c}{r}"].font = HD
        ws[f"B{r}"].alignment = Alignment(horizontal="left", indent=1)

    ws["B1"] = "PLACA BASE — RESUMEN DE VERIFICACIONES"
    ws["B1"].font = Font(name=F, size=14, bold=True)
    ws["B2"] = (f"{prj.name}   |   Elemento {prj.element}   |   {prj.author}   |   "
                f"{prj.date or datetime.date.today().isoformat()}")
    ws["B2"].font = S

    r = 4
    band(r, "1.  DATOS PRINCIPALES"); r += 1
    p, b, c, L = prj.plate, prj.bolts, prj.conc, prj.eloads
    geo = (f"Ø{u.l(p.Dp):.4g}" if p.shape == "Circular"
           else f"{u.l(p.N):.4g} × {u.l(p.B):.4g}")
    datos = [
        ("Perfil", f"{prj.section.label}  ({prj.section.steel}, rotacion {prj.section.rotation:g}°)"),
        ("Placa", f"{geo} × {u.l(p.tp):.4g} {u.L}  —  {p.steel}"),
        ("Mortero de nivelacion", f"{u.l(p.grout):.4g} {u.L}"),
        ("Pernos", f"{b.n_total} × Ø{b.size}\"  {b.steel}  —  {b.atype}"),
        ("Disposicion", f"{b.pattern};  eje mayor {b.n_major} / eje menor {b.n_minor};  "
                        f"hef = {u.l(b.hef):.4g} {u.L}"),
        ("Concreto", f"f'c = {u.s(c.fc):.4g} {u.S};  pedestal {u.l(c.N2):.4g} × {u.l(c.B2):.4g} {u.L};  "
                     f"{'fisurado' if c.cracked else 'no fisurado'}"),
        ("Llave de corte", (f"{u.l(prj.lug.W):.4g} × {u.l(prj.lug.H):.4g} × {u.l(prj.lug.t):.4g} {u.L}"
                            if prj.lug.enabled else "no")),
        ("Rigidizadores", (f"{prj.stiff.count} pletinas {u.l(prj.stiff.t):.4g} {u.L}, "
                           f"L = {u.l(prj.stiff.L):.4g} {u.L}" if prj.stiff.enabled else "no")),
        ("Soldadura", f"ala: {prj.welds.flange.wtype} {float_to_frac(prj.welds.flange.size)}\" · "
                      f"alma: {prj.welds.web.wtype} {float_to_frac(prj.welds.web.size)}\" · "
                      f"perim.: {prj.welds.perimeter.wtype} {float_to_frac(prj.welds.perimeter.size)}\""),
        ("Columna inclinada", (f"giro X = {prj.loads.tilt_x:g}°, giro Y = {prj.loads.tilt_y:g}° "
                               f"(cargas ingresadas en el eje de la columna)"
                               if prj.loads.tilted else "no")),
        ("Cargas factorizadas" + (" (ejes de la placa)" if prj.loads.tilted else ""),
         f"Pu = {u.f(L.Pu):.4g} {u.F};  Mux = {u.m(L.Mux):.4g} {u.M};  "
                                f"Muy = {u.m(L.Muy):.4g} {u.M};  Vu = {u.f(L.Vu):.4g} {u.F}"),
    ]
    for k, v in datos:
        ws[f"B{r}"] = k; ws[f"B{r}"].font = N
        ws.merge_cells(f"C{r}:G{r}")
        ws[f"C{r}"] = v; ws[f"C{r}"].font = N
        r += 1

    r += 1
    band(r, "2.  ESTADO DE APLASTAMIENTO"); r += 1
    br = res.br
    for k, v in [("Caso", br.case),
                 ("Excentricidad e = Mu/Pu", f"{u.l(br.e):.4g} {u.L}" if br.e != float('inf') else "∞"),
                 ("e critica", f"{u.l(br.ecrit):.4g} {u.L}"),
                 ("Longitud de aplastamiento Y", f"{u.l(br.Y):.4g} {u.L}"),
                 ("Presion de contacto fp", f"{u.s(br.fp):.4g} / {u.s(br.fp_max):.4g} {u.S}"),
                 ("Traccion total en pernos Tu", f"{u.f(br.Tu):.4g} {u.F}  en {br.n_t} pernos"),
                 ("Brazo del grupo traccionado f", f"{u.l(br.f_arm):.4g} {u.L}"),
                 ("Espesor requerido", f"{u.l(res.treq):.4g} / {u.l(p.tp):.4g} {u.L}")]:
        ws[f"B{r}"] = k; ws[f"B{r}"].font = N
        ws.merge_cells(f"C{r}:G{r}"); ws[f"C{r}"] = v; ws[f"C{r}"].font = N
        r += 1

    r += 1
    band(r, "3.  VERIFICACIONES"); r += 1
    hdr = ["Verificacion", "Demanda", "Capacidad", "Unid.", "D/C", "Referencia y observaciones"]
    for i, h in enumerate(hdr):
        cell = ws.cell(row=r, column=2 + i, value=h)
        cell.font = B; cell.border = BX
        cell.fill = PatternFill("solid", fgColor="F2F2F2")
    r += 1
    first = r
    usx = _units(prj)
    for ch in res.checks:
        dv, cv, ul = ck_vals(usx, ch)
        ws.cell(row=r, column=2, value=ch.title).font = N
        ws.cell(row=r, column=3, value=round(dv, 4)).font = N
        ws.cell(row=r, column=4, value=round(cv, 4)).font = N
        ws.cell(row=r, column=5, value=ul).font = N
        cr = ws.cell(row=r, column=6, value=("—" if ch.skip else round(ch.ratio, 3)))
        cr.font = B
        cr.fill = OKF if ch.ok else NOF
        cr.alignment = Alignment(horizontal="center")
        ws.cell(row=r, column=7, value=(ch.ref + ("  —  " + ch.note if ch.note else ""))).font = S
        for cc in range(2, 8):
            ws.cell(row=r, column=cc).border = BX
        r += 1

    r += 1
    ws[f"B{r}"] = "VEREDICTO"
    ws[f"B{r}"].font = Font(name=F, size=12, bold=True)
    gov = res.governing
    ws[f"C{r}"] = "CUMPLE" if res.ok else "NO CUMPLE"
    ws[f"C{r}"].font = Font(name=F, size=12, bold=True)
    ws[f"C{r}"].fill = OKF if res.ok else NOF
    ws.merge_cells(f"D{r}:G{r}")
    ws[f"D{r}"] = (f"D/C maximo = {res.max_ratio:.3f}" +
                   (f"  —  gobierna: {gov.title}" if gov else ""))
    ws[f"D{r}"].font = N
    r += 2
    if res.warnings:
        band(r, "4.  AVISOS"); r += 1
        for wmsg in res.warnings:
            ws.merge_cells(f"B{r}:G{r}")
            ws[f"B{r}"] = wmsg
            ws[f"B{r}"].font = Font(name=F, size=9, bold=wmsg.startswith("**"),
                                    color="9C0006" if wmsg.startswith("**") else "595959")
            r += 1

    # --- hoja de dibujos
    if figs:
        ws2 = wb.create_sheet("DIBUJOS")
        ws2.sheet_view.showGridLines = False
        row = 2
        for fp in figs:
            try:
                img = XLImage(fp)
                img.width = int(img.width * 0.55)
                img.height = int(img.height * 0.55)
                ws2.add_image(img, f"B{row}")
                row += 32
            except Exception:
                pass

    # --- hoja FEA
    if res.fea is not None and res.fea.ok:
        ws3 = wb.create_sheet("FEA")
        ws3.sheet_view.showGridLines = False
        ws3.column_dimensions["B"].width = 46
        ws3.column_dimensions["C"].width = 18
        rows = [("Malla", f"{prj.fea.nx} × {prj.fea.ny}"),
                ("Iteraciones de contacto", res.fea.iters),
                (f"Deflexion maxima ({usx.L})", usx.out("L", res.fea.w_max)),
                (f"Presion de contacto maxima ({usx.S})", usx.out("S", res.fea.press_max)),
                (f"von Mises maximo ({usx.S})", usx.out("S", res.fea.vm_max)),
                (f"Reaccion del concreto ({usx.F})", usx.out("F", res.fea.R_found)),
                (f"Traccion total en pernos ({usx.F})", usx.out("F", res.fea.R_bolts)),
                (f"Carga aplicada ΣF ({usx.F})", usx.out("F", res.fea.sumF)),
                (f"Demanda de soldadura ({usx.F}/{usx.L})",
                 usx.out("LF", res.fea.weld_line_max))]
        rr = 2
        ws3["B1"] = "ELEMENTOS FINITOS — RESULTADOS"; ws3["B1"].font = Font(name=F, size=12, bold=True)
        for k, v in rows:
            ws3[f"B{rr}"] = k; ws3[f"B{rr}"].font = N
            ws3[f"C{rr}"] = v; ws3[f"C{rr}"].font = B
            rr += 1
        rr += 1
        ws3[f"B{rr}"] = "TENSIONES PERNO POR PERNO"; ws3[f"B{rr}"].font = B
        rr += 1
        hdr, filas = bolt_rows(res, usx)
        if hdr:
            for j, htxt in enumerate(hdr):
                cc = ws3.cell(row=rr, column=2 + j, value=htxt); cc.font = B
                cc.fill = PatternFill("solid", fgColor="DDDDDD")
            rr += 1
            red = PatternFill("solid", fgColor="FFC7CE")
            grn = PatternFill("solid", fgColor="C6EFCE")
            for fila in filas:
                for j, vtxt in enumerate(fila):
                    try:
                        val = float(str(vtxt).replace(",", ""))
                    except ValueError:
                        val = vtxt
                    cc = ws3.cell(row=rr, column=2 + j, value=val)
                    cc.font = N
                    if j == 5:
                        cc.font = B
                        cc.fill = grn if float(fila[5]) <= 1.0 else red
                rr += 1

    if detail and res.rec is not None:
        ws4 = wb.create_sheet("MEMORIA")
        ws4.sheet_view.showGridLines = False
        ws4.column_dimensions["B"].width = 130
        ws4["B1"] = "DESARROLLO DE LAS ECUACIONES"
        ws4["B1"].font = Font(name=F, size=12, bold=True)
        rr = 3
        for kind, txt in res.rec.to_lines():
            c = ws4.cell(row=rr, column=2, value=txt)
            if kind == "sec":
                c.font = HD; c.fill = FH
            elif kind == "chk":
                c.font = B
            elif kind == "txt":
                c.font = S
            else:
                c.font = N
            rr += 1

    wb.save(path)
    return path


# ==================================================================== DOCX
def export_docx(prj: Project, res: Results, path: str,
                figs: list[str] | None = None, detail: bool = True) -> str:
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    u = U(prj.metric)
    us = _units(prj)
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(9)

    doc.add_heading("MEMORIA DE CALCULO — PLACA BASE", level=0)
    p0 = doc.add_paragraph()
    p0.add_run(f"{prj.name}\n").bold = True
    p0.add_run(f"Elemento: {prj.element}     Calculo: {prj.author}     "
               f"Fecha: {prj.date or datetime.date.today().isoformat()}\n")
    p0.add_run("Normas: AISC 360-22, AISC Design Guide 1 (2ª Ed.), ACI 318-19 Cap. 17.")

    doc.add_heading("1. Datos de entrada", level=1)
    p, b, c, L = prj.plate, prj.bolts, prj.conc, prj.eloads
    rows = input_rows(prj, us)
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for k, v in rows:
        cells = t.add_row().cells
        cells[0].text = k
        cells[1].text = v

    doc.add_heading("2. Aplastamiento y equilibrio (DG1 §3.3)", level=1)
    br = res.br
    doc.add_paragraph(
        f"A1 = {br.A1:.1f} in²;  A2 = {br.A2:.1f} in²;  √(A2/A1) = {br.sqrt_ratio:.3f};  "
        f"φcPp = {us.q('F', br.phiPp)};  fp,max = {us.q('S', br.fp_max)};  "
        f"qmax = {us.q('LF', br.qmax)}.")
    doc.add_paragraph(
        f"e = Mu/Pu = {br.e:.2f} in;  ecrit = {br.ecrit:.2f} in  →  {br.case}.  "
        f"Y = {us.q('L', br.Y)};  fp = {us.q('S', br.fp)};  Tu = {us.q('F', br.Tu)} repartidos en "
        f"{br.n_t} pernos con brazo f = {br.f_arm:.2f} in.")
    d = res.tdet
    doc.add_paragraph(
        f"Voladizos: m = {d['m_y']:.2f} in, n = {d['m_x']:.2f} in, λ = {d['lam']:.3f}, "
        f"λn' = {d['lam_n']:.2f} in.  Espesor requerido t = {res.treq:.3f} in "
        f"(propuesto {p.tp:g} in).")

    doc.add_heading("3. Verificaciones", level=1)
    t = doc.add_table(rows=1, cols=5)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(["Verificacion", "Demanda", "Capacidad", "Un.", "D/C"]):
        t.rows[0].cells[i].text = h
        for pr in t.rows[0].cells[i].paragraphs:
            for rr in pr.runs:
                rr.bold = True
    us = _units(prj)
    for ch in res.checks:
        dv, cv, ul = ck_vals(us, ch)
        cells = t.add_row().cells
        cells[0].text = ch.title
        cells[1].text = f"{dv:,.3f}"
        cells[2].text = f"{cv:,.3f}"
        cells[3].text = ul
        cells[4].text = "—" if ch.skip else f"{ch.ratio:.3f}"
        if not ch.ok:
            for pr in cells[4].paragraphs:
                for rr in pr.runs:
                    rr.bold = True
                    rr.font.color.rgb = RGBColor(0x9C, 0x00, 0x06)

    pv = doc.add_paragraph()
    pv.add_run("VEREDICTO: ").bold = True
    rr = pv.add_run("CUMPLE" if res.ok else "NO CUMPLE")
    rr.bold = True
    rr.font.color.rgb = RGBColor(0x00, 0x61, 0x00) if res.ok else RGBColor(0x9C, 0x00, 0x06)
    gov = res.governing
    pv.add_run(f"   D/C maximo = {res.max_ratio:.3f}" +
               (f"   (gobierna: {gov.title})" if gov else ""))

    if res.warnings:
        doc.add_heading("4. Avisos", level=1)
        for wmsg in res.warnings:
            doc.add_paragraph(wmsg, style="List Bullet")

    if res.fea is not None and res.fea.ok:
        doc.add_heading("5. Elementos finitos", level=1)
        doc.add_paragraph(
            f"Placa de Mindlin-Reissner (cuadrilateros de 4 nodos, integracion reducida "
            f"selectiva) sobre fundacion elastica de Winkler solo a compresion, con resortes "
            f"de perno solo a traccion.  Malla {prj.fea.nx}×{prj.fea.ny}.  {res.fea.msg}")
        doc.add_paragraph(
            f"Deflexion maxima = {us.q('L', res.fea.w_max)};  presion de contacto maxima = "
            f"{us.q('S', res.fea.press_max)};  von Mises maximo = {us.q('S', res.fea.vm_max)};  "
            f"traccion maxima en un perno = "
            f"{us.q('F', max(res.fea.bolt_T) if res.fea.bolt_T else 0.0)}.")

        hdr, filas = bolt_rows(res, us)
        if hdr:
            doc.add_paragraph().add_run("Tensiones perno por perno").bold = True
            tb = doc.add_table(rows=1, cols=len(hdr))
            tb.style = "Light Grid Accent 1"
            for j, htxt in enumerate(hdr):
                cel = tb.rows[0].cells[j]
                cel.text = ""
                cel.paragraphs[0].add_run(htxt).bold = True
            for fila in filas:
                cel = tb.add_row().cells
                for j, vtxt in enumerate(fila):
                    cel[j].text = ""
                    run = cel[j].paragraphs[0].add_run(vtxt)
                    run.font.size = Pt(8)
                    if j == 5:
                        run.bold = True

    post = getattr(res, "post3d", None)
    if post is not None:
        from .weld3d import summary_rows
        doc.add_heading("6. Modelo solido 3D — soldadura y pernos", level=1)
        doc.add_paragraph("Modelo solido de tetraedros cuadraticos (Gmsh + CalculiX): placa con los agujeros "
            "taladrados, perfil, rigidizadores y llave; concreto como resortes solo a "
            "compresion y pernos solo a traccion (paso no lineal). La fuerza en la "
            "soldadura se obtiene integrando en el espesor de cada pared los esfuerzos "
            "del perfil justo por encima del pie del cordon. La compresion se transmite "
            "por contacto (DG1); el cordon se verifica a traccion y cortante con el "
            "metodo vectorial de AISC J2.4. D/C pico = punto mas cargado (concentracion "
            "elastica local); D/C media = fuerza de la pared repartida en su longitud.")
        doc.add_paragraph(f"Equilibrio: {post.msg}.")
        for titulo, rows in zip(("Soldadura perfil-placa", "Traccion por perno"),
                                summary_rows(prj, post)):
            doc.add_paragraph().add_run(titulo).bold = True
            tb = doc.add_table(rows=0, cols=len(rows[0]))
            tb.style = "Light Grid Accent 1"
            for i, r in enumerate(rows):
                cel = tb.add_row().cells
                for j, v in enumerate(r):
                    cel[j].text = ""
                    run = cel[j].paragraphs[0].add_run(str(v))
                    run.font.size = Pt(8)
                    run.bold = (i == 0)

    if detail and res.rec is not None:
        doc.add_page_break()
        doc.add_heading("Anexo A — Desarrollo de las ecuaciones", level=1)
        doc.add_paragraph(
            "Cada linea muestra el simbolo, la formula, la sustitucion numerica y "
            "el resultado, en las unidades de trabajo del proyecto.")
        for kind, txt in res.rec.to_lines():
            par = doc.add_paragraph()
            run = par.add_run(txt)
            run.font.size = Pt(7.5)
            if kind == "sec":
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
            elif kind == "chk":
                run.bold = True
            elif kind == "txt":
                run.italic = True
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    if figs:
        doc.add_page_break()
        doc.add_heading("Anexo B — Dibujos y resultados graficos", level=1)
        for fp in figs:
            try:
                doc.add_picture(fp, width=Inches(6.0))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:
                pass

    doc.save(path)
    return path


# ===================================================================== PDF
def export_pdf(prj: Project, res: Results, path: str,
               figs: list[str] | None = None, detail: bool = True) -> str:
    """Memoria de calculo en PDF (reportlab, sin depender de Word)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image as RLImage, PageBreak)

    u = U(prj.metric)
    us = _units(prj)
    ss = getSampleStyleSheet()
    H0 = ParagraphStyle("H0", parent=ss["Title"], fontName="Helvetica-Bold",
                        fontSize=15, spaceAfter=2)
    H1 = ParagraphStyle("H1", parent=ss["Heading2"], fontName="Helvetica-Bold",
                        fontSize=11, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor("#1F3864"))
    BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontName="Helvetica",
                          fontSize=8, leading=10.5)
    SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=6.6, leading=8.2,
                           textColor=colors.HexColor("#444444"))
    CEN = ParagraphStyle("CEN", parent=BODY, alignment=TA_CENTER)

    story = []
    story.append(Paragraph("MEMORIA DE CALCULO — PLACA BASE", H0))
    story.append(Paragraph(
        f"<b>{prj.name}</b> &nbsp;|&nbsp; Elemento: {prj.element} &nbsp;|&nbsp; "
        f"Calculo: {prj.author or '-'} &nbsp;|&nbsp; "
        f"Fecha: {prj.date or datetime.date.today().isoformat()}", CEN))
    story.append(Paragraph(
        "Normas: AISC 360-22 · AISC Design Guide 1 (2ª Ed.) · ACI 318-19 Cap. 17"
        f" &nbsp;|&nbsp; Unidades: {us.L}, {us.F}, {us.S}", CEN))
    story.append(Spacer(1, 8))

    def tbl(data, widths, style_extra=None, hdr=True):
        t = Table(data, colWidths=widths, repeatRows=1 if hdr else 0)
        st = [("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
              ("FONTSIZE", (0, 0), (-1, -1), 7),
              ("LEADING", (0, 0), (-1, -1), 8.6),
              ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        if hdr:
            st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6")),
                   ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        t.setStyle(TableStyle(st + (style_extra or [])))
        return t

    # ------------------------------------------------------- 1. entrada
    story.append(Paragraph("1. Datos de entrada", H1))
    p, b, c, L = prj.plate, prj.bolts, prj.conc, prj.eloads
    geo = (f"Ø{us.q('L', p.Dp)}" if p.shape == "Circular"
           else f"{us.q('L', p.N)} × {us.q('L', p.B)}")
    rows = [["Concepto", "Descripcion"]]
    rows += [
        ["Perfil", f"{prj.section.label} ({prj.section.steel}), rotacion "
                   f"{prj.section.rotation:g}°"],
        ["Placa base", f"{geo} × {us.q('L', p.tp)} — {p.steel} "
                       f"(Fy = {us.q('S', p.mat().Fy)})"],
        ["Mortero de nivelacion", us.q("L", p.grout)],
        ["Anclajes", f"{b.n_total} Ø{b.size} in ({us.q('L', b.geom().db)}) — {b.steel} "
                     f"— {b.atype}, hef = {us.q('L', b.hef)}"],
        ["Agujeros en la placa", f"{us.q('L', b.geom().dh)} — {b.hole_rule}"],
        ["Disposicion", f"{b.pattern}; {b.n_major} en eje mayor, {b.n_minor} en eje "
                        f"menor; ex = {us.q('L', b.ex)}, ey = {us.q('L', b.ey)}"],
        ["Concreto", f"f'c = {us.q('S', c.fc)}; pedestal {us.q('L', c.N2)} × "
                     f"{us.q('L', c.B2)}; ha = {us.q('L', c.ha)}; "
                     f"{'fisurado' if c.cracked else 'no fisurado'}; "
                     f"condicion {'A' if c.cond_A else 'B'}"],
        ["Llave de corte", (f"{us.q('L', prj.lug.W)} × {us.q('L', prj.lug.H)} × "
                            f"{us.q('L', prj.lug.t)} — {prj.lug.direction}"
                            if prj.lug.enabled else "No")],
        ["Rigidizadores", (f"{prj.stiff.count} pletinas {prj.stiff.shape.lower()}, "
                           f"t = {us.q('L', prj.stiff.t)}, L = {us.q('L', prj.stiff.L)}, "
                           f"h = {us.q('L', prj.stiff.h)}; {prj.stiff.position}; "
                           f"{prj.stiff.spacing_mode}"
                           + (f", separacion {us.q('L', prj.stiff.spacing)}"
                              if prj.stiff.spacing_mode.startswith("Separacion") else "")
                           if prj.stiff.enabled else "No")],
        ["Soldadura", f"ala: {prj.welds.flange.wtype} "
                      f"{us.q('L', prj.welds.flange.size)} "
                      f"({prj.welds.flange.electrode}) · alma: {prj.welds.web.wtype} "
                      f"{us.q('L', prj.welds.web.size)} · perimetral: "
                      f"{prj.welds.perimeter.wtype} "
                      f"{us.q('L', prj.welds.perimeter.size)}"],
        ["Cargas (LRFD)", f"Pu = {us.q('F', L.Pu)}; Mux = {us.q('M', L.Mux)}; "
                          f"Muy = {us.q('M', L.Muy)}; Vux = {us.q('F', L.Vux)}; "
                          f"Vuy = {us.q('F', L.Vuy)}"],
    ]
    rows = [[Paragraph(str(a), BODY), Paragraph(str(bq), BODY)] for a, bq in rows]
    story.append(tbl(rows, [1.5 * inch, 5.2 * inch]))

    # --------------------------------------------- 2. equilibrio
    story.append(Paragraph("2. Aplastamiento y equilibrio (DG1 §3.3)", H1))
    br = res.br
    story.append(Paragraph(
        f"A1 = {us.fmt('A', br.A1)} {us.A}; A2 = {us.fmt('A', br.A2)} {us.A}; "
        f"√(A2/A1) = {br.sqrt_ratio:.3f}; φcPp = {us.q('F', br.phiPp)}; "
        f"fp,max = {us.q('S', br.fp_max)}; qmax = {us.q('LF', br.qmax)}.", BODY))
    ee = "∞" if br.e == float("inf") else us.q("L", br.e)
    story.append(Paragraph(
        f"e = Mu/Pu = {ee}; ecrit = {us.q('L', br.ecrit)} → <b>{br.case}</b>. "
        f"Y = {us.q('L', br.Y)}; fp = {us.q('S', br.fp)}; Tu = {us.q('F', br.Tu)} "
        f"repartidos en {br.n_t} pernos con brazo f = {us.q('L', br.f_arm)}.", BODY))
    d = res.tdet
    story.append(Paragraph(
        f"Voladizos: m = {us.q('L', d['m_y'])}, n = {us.q('L', d['m_x'])}, "
        f"λ = {d['lam']:.3f}, λn' = {us.q('L', d['lam_n'])}. "
        f"Espesor requerido t = <b>{us.q('L', res.treq)}</b> "
        f"(propuesto {us.q('L', p.tp)}).", BODY))

    # --------------------------------------------- 3. verificaciones
    story.append(Paragraph("3. Verificaciones", H1))
    data = [["Verificacion", "Demanda", "Capacidad", "Un.", "D/C"]]
    style = []
    for i, ch in enumerate(res.checks, start=1):
        dv, cv, ul = ck_vals(us, ch)
        data.append([Paragraph(ch.title, BODY), f"{dv:,.3f}", f"{cv:,.3f}",
                     ul, "—" if ch.skip else f"{ch.ratio:.3f}"])
        col = colors.HexColor("#EEEEEE") if ch.skip else (
            colors.HexColor("#C6EFCE") if ch.ok else colors.HexColor("#FFC7CE"))
        style.append(("BACKGROUND", (4, i), (4, i), col))
    style += [("ALIGN", (1, 1), (-1, -1), "RIGHT"),
              ("FONTNAME", (4, 1), (4, -1), "Helvetica-Bold")]
    story.append(tbl(data, [3.5 * inch, 0.85 * inch, 0.95 * inch, 0.5 * inch,
                            0.6 * inch], style))

    gov = res.governing
    vcol = "#006100" if res.ok else "#9C0006"
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f'<b>VEREDICTO: <font color="{vcol}">'
        f'{"CUMPLE" if res.ok else "NO CUMPLE"}</font></b> &nbsp;&nbsp; '
        f"D/C maximo = {res.max_ratio:.3f}"
        + (f" &nbsp;(gobierna: {gov.title})" if gov else ""), BODY))

    if res.warnings:
        story.append(Paragraph("4. Avisos", H1))
        for wmsg in res.warnings:
            col = "9C0006" if wmsg.startswith("**") else "7F6000"
            story.append(Paragraph(f'<font color="#{col}">• {wmsg}</font>', BODY))

    # --------------------------------------------- 5. FEA
    if res.fea is not None and res.fea.ok:
        fr = res.fea
        story.append(Paragraph("5. Elementos finitos", H1))
        story.append(Paragraph(
            "Placa de Mindlin-Reissner con elemento MITC4 sobre fundacion elastica de "
            "Winkler solo a compresion; pernos como resortes solo a traccion repartidos "
            "en el anillo de apoyo de la tuerca; rigidizadores como banda de espesor "
            f"equivalente. Malla {prj.fea.nx}×{prj.fea.ny}"
            + (f", con los {fr.n_holes} agujeros de perno recortados de la malla."
               if fr.holes_meshed else ", sin mallar los agujeros.") + f" {fr.msg}", BODY))
        story.append(Paragraph(
            f"Deflexion maxima = {us.q('L', fr.w_max)}; presion de contacto maxima = "
            f"{us.q('S', fr.press_max)}; von Mises maximo = {us.q('S', fr.vm_max)}.", BODY))
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>Tensiones por perno</b>", BODY))
        story.append(_bolt_table_pdf(prj, res, tbl, BODY, inch, colors))

    post = getattr(res, "post3d", None)
    if post is not None:
        from .weld3d import summary_rows
        import math as _m
        story.append(Paragraph("6. Modelo solido 3D — soldadura y pernos", H1))
        story.append(Paragraph("Modelo solido de tetraedros cuadraticos (Gmsh + CalculiX): placa con los agujeros "
            "taladrados, perfil, rigidizadores y llave; concreto como resortes solo a "
            "compresion y pernos solo a traccion (paso no lineal). La fuerza en la "
            "soldadura se obtiene integrando en el espesor de cada pared los esfuerzos "
            "del perfil justo por encima del pie del cordon. La compresion se transmite "
            "por contacto (DG1); el cordon se verifica a traccion y cortante con el "
            "metodo vectorial de AISC J2.4. D/C pico = punto mas cargado (concentracion "
            "elastica local); D/C media = fuerza de la pared repartida en su longitud.", BODY))
        story.append(Paragraph(f"Equilibrio: {post.msg}.", BODY))
        wr, br_ = summary_rows(prj, post)
        st = []
        for i, r in enumerate(wr[1:], start=1):
            for j in (5, 6):
                try:
                    ok = float(r[j]) <= 1.0
                except ValueError:
                    ok = False
                st.append(("BACKGROUND", (j, i), (j, i),
                           colors.HexColor("#C6EFCE" if ok else "#FFC7CE")))
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>Soldadura perfil-placa</b>", BODY))
        story.append(tbl([[Paragraph(str(c), BODY) for c in r] for r in wr],
                         [0.8 * inch, 1.9 * inch] + [0.8 * inch] * 5, st))
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>Traccion por perno (3D)</b>", BODY))
        story.append(tbl(br_, [0.6 * inch] + [1.0 * inch] * 3,
                         [("ALIGN", (1, 1), (-1, -1), "RIGHT")]))

    # ------------------------------------- desarrollo de las ecuaciones
    if detail and res.rec is not None:
        story.append(PageBreak())
        story.append(Paragraph("Anexo A — Desarrollo de las ecuaciones", H1))
        story.append(Paragraph(
            "Cada linea muestra el simbolo, la formula, la sustitucion numerica y "
            "el resultado, en las unidades de trabajo del proyecto.", SMALL))
        EQ = ParagraphStyle("EQ", parent=BODY, fontName="Helvetica",
                            fontSize=7.4, leading=9.6, leftIndent=8)
        SEC = ParagraphStyle("SEC", parent=BODY, fontName="Helvetica-Bold",
                             fontSize=8.4, leading=11, spaceBefore=7, spaceAfter=2,
                             textColor=colors.white,
                             backColor=colors.HexColor("#1F3864"),
                             leftIndent=2, rightIndent=2, borderPadding=3)
        NT = ParagraphStyle("NT", parent=EQ, textColor=colors.HexColor("#555555"),
                            fontName="Helvetica-Oblique", leftIndent=16)
        CH = ParagraphStyle("CH", parent=EQ, fontName="Helvetica-Bold",
                            textColor=colors.HexColor("#1F3864"))
        from xml.sax.saxutils import escape as _esc
        for kind, txt in res.rec.to_lines():
            st = {"sec": SEC, "txt": NT, "chk": CH}.get(kind, EQ)
            story.append(Paragraph(_esc(txt), st))

    # --------------------------------------------- anexo grafico
    if figs:
        story.append(PageBreak())
        story.append(Paragraph("Anexo — Dibujos y resultados graficos", H1))
        for fp in figs:
            try:
                from PIL import Image as PILImage
                iw, ih = PILImage.open(fp).size
                w = 6.1 * inch
                story.append(RLImage(fp, width=w, height=w * ih / iw))
                story.append(Spacer(1, 6))
            except Exception:
                pass

    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.55 * inch,
                            title=f"Memoria placa base {prj.element}",
                            author=prj.author or "PlacaBasePro")

    def _footer(canvas, docu):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(0.6 * inch, 0.32 * inch,
                          f"{prj.name} — {prj.element} — PlacaBasePro 1.1")
        canvas.drawRightString(letter[0] - 0.6 * inch, 0.32 * inch,
                               f"Pagina {docu.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def _bolt_table_pdf(prj, res, tbl, BODY, inch, colors):
    us = _units(prj)
    fr = res.fea
    data = [["#", f"x ({us.L})", f"y ({us.L})", f"T ({us.F})",
             f"σt ({us.S})", "D/C"]]
    style = []
    order = sorted(range(len(fr.bolt_T)), key=lambda i: -fr.bolt_T[i])
    for k, i in enumerate(order, start=1):
        x, y = fr.bolt_xy[i]
        data.append([f"P{i + 1}", us.fmt("L", x), us.fmt("L", y),
                     us.fmt("F", fr.bolt_T[i]), us.fmt("S", fr.bolt_sig[i]),
                     f"{fr.bolt_ratio[i]:.3f}"])
        col = colors.HexColor("#C6EFCE") if fr.bolt_ratio[i] <= 1 else colors.HexColor("#FFC7CE")
        style.append(("BACKGROUND", (5, k), (5, k), col))
    style.append(("ALIGN", (1, 1), (-1, -1), "RIGHT"))
    return tbl(data, [0.4 * inch] + [0.85 * inch] * 5, style)
