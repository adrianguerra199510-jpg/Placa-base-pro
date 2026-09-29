# -*- coding: utf-8 -*-
"""Ventana principal de PlacaBasePro (PySide6)."""
from __future__ import annotations
import os
import sys
import datetime
import tempfile
import traceback
from pathlib import Path

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject
from PySide6.QtGui import QAction, QKeySequence, QColor, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QTabWidget, QSplitter,
                               QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
                               QComboBox, QPushButton, QTextEdit, QToolBar, QCheckBox,
                               QStatusBar, QDoubleSpinBox, QProgressDialog, QSizePolicy)

from . import __version__
from .model import (INSTALL_TYPES, ADH_ENV, ADH_CATEGORY)
from .model import (Project, PATTERNS, ANCHOR_TYPES, WELD_TYPES, PLATE_SHAPES,
                    LUG_DIRS, STIFF_POSITIONS, STIFF_SHAPES, STIFF_SPACING)
from . import materials as M
from .shapes import CATALOG, W_SHAPE, HSS_RECT, HSS_ROUND, PIPE, KIND_LABELS
from .model import LUG_TYPES, save_book, load_book
from .dialogs import SectionDialog, MaterialsDialog
from PySide6.QtWidgets import QListWidget, QInputDialog
from .solver import solve
from .units import parse_xy_clipboard
from . import draw, report, ccx, mesh3d, view3d
from .ui_widgets import Form, scroll, PasteTable
from .units import (UnitSet, LEN_UNITS, FORCE_UNITS, STRESS_UNITS, MOMENT_UNITS,
                    DEFAULT_SETS, KIP_TO_KN, IN_TO_MM, KIPIN_TO_KNM)

KIND_NAMES = {W_SHAPE: "W (ala ancha)", HSS_RECT: "HSS cuadrado/rectangular",
              HSS_ROUND: "HSS circular", PIPE: "Pipe (tuberia)"}
KIND_BY_NAME = {v: k for k, v in KIND_NAMES.items()}
FIELDS_FEA = [("Von Mises", "vm"), ("Presion de contacto", "p"), ("Deflexion", "w"),
              ("Momento Mx", "mx"), ("Momento My", "my")]


FAMILY_DESC = {"W": "W — ala ancha", "M": "M — perfil I liviano", "S": "S — I americano",
               "HP": "HP — pilote", "C": "C — canal", "MC": "MC — canal miscelaneo",
               "L": "L — angulo", "WT": "WT — te de W", "MT": "MT — te de M",
               "ST": "ST — te de S", "HSS": "HSS — rectangular / cuadrado",
               "HSS circular": "HSS — circular", "Pipe": "Pipe — tuberia",
               "Personalizado": "Secciones personalizadas", "Importado": "Importados"}
FAMILY_STEEL = {"W": "ASTM A992", "M": "ASTM A36", "S": "ASTM A36", "HP": "ASTM A572 Gr.50",
                "C": "ASTM A36", "MC": "ASTM A36", "L": "ASTM A36", "WT": "ASTM A992",
                "MT": "ASTM A36", "ST": "ASTM A36", "HSS": "ASTM A500 Gr.B (HSS rect.)",
                "HSS circular": "ASTM A500 Gr.B (HSS red.)", "Pipe": "ASTM A53 Gr.B (Pipe)"}


def fam_label(f):
    return FAMILY_DESC.get(f, f)


def fam_from_label(t):
    for k, v in FAMILY_DESC.items():
        if v == t:
            return k
    return t


def _wheel_zoom(canvas, ax_getter, three_d=False):
    """Zoom con la rueda del mouse (centrado en el cursor en 2D)."""
    def on_scroll(ev):
        ax = ax_getter()
        if ax is None:
            return
        k = 0.85 if ev.button == "up" else 1 / 0.85
        if three_d:
            for get, set_ in ((ax.get_xlim3d, ax.set_xlim3d), (ax.get_ylim3d, ax.set_ylim3d),
                              (ax.get_zlim3d, ax.set_zlim3d)):
                a, b = get()
                c = (a + b) / 2
                set_(c - (b - a) / 2 * k, c + (b - a) / 2 * k)
        else:
            if ev.inaxes is not ax or ev.xdata is None:
                return
            for get, set_, c in ((ax.get_xlim, ax.set_xlim, ev.xdata),
                                 (ax.get_ylim, ax.set_ylim, ev.ydata)):
                a, b = get()
                set_(c - (c - a) * k, c + (b - c) * k)
        canvas.draw_idle()
    canvas.mpl_connect("scroll_event", on_scroll)


class Canvas(QWidget):
    def __init__(self, parent=None, size=(6, 6)):
        super().__init__(parent)
        self.fig = Figure(figsize=size, dpi=100, tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        self.cv = FigureCanvasQTAgg(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(self.cv, self))
        lay.addWidget(self.cv)
        self.cbar = None
        _wheel_zoom(self.cv, lambda: self.ax)

    def reset(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.cbar = None


class Canvas3D(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(figsize=(7, 6), dpi=100)
        self.ax = self.fig.add_axes([0.0, 0.0, 0.88, 0.95], projection="3d")
        self.cv = FigureCanvasQTAgg(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(self.cv, self))
        lay.addWidget(self.cv)
        self.cbar = None
        _wheel_zoom(self.cv, lambda: self.ax, three_d=True)
        self.cv.mpl_connect("motion_notify_event", self._on_rotate)
        self.cv.mpl_connect("resize_event", self._on_resize)
        self.cv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _on_resize(self, ev):
        # el modelo se re-ajusta al ancho/alto disponibles
        from . import view3d as _v
        if getattr(self.ax, "_pb_aspect", None) is not None:
            _v.fit_to_axes(self.ax)
            self.cv.draw_idle()

    def _on_rotate(self, ev):
        # al girar la camara, reordena el dibujo (arriba/abajo de la placa)
        if ev.button is not None and getattr(self.ax, "_pb_groups", None):
            from . import view3d as _v
            _v.update_order(self.ax)

    def reset(self, cbar=True):
        self.fig.clf()
        # el eje ocupa todo el lienzo (menos la franja de la barra de colores si la hay),
        # asi el modelo queda centrado
        self.ax = self.fig.add_axes([0.0, 0.0, 0.88 if cbar else 1.0, 0.95], projection="3d")
        self.cbar = None


class Worker3D(QThread):
    """Corre el ciclo geometria -> Gmsh -> CalculiX en segundo plano para que
    la ventana siga respondiendo."""
    progress = Signal(str)
    done = Signal(object, str)

    def __init__(self, prj, folder):
        super().__init__()
        self.prj, self.folder = prj, folder

    def run(self):
        try:
            res, msg = mesh3d.full_3d(self.prj, self.folder, "modelo3d",
                                      progress=self.progress.emit)
        except Exception as e:
            res, msg = None, f"{type(e).__name__}: {e}"
        self.done.emit(res, msg)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.prj = Project()
        self.prj.date = datetime.date.today().isoformat()
        self.book = [self.prj]
        self.cur = 0
        self.cache3d = {}            # id(conexion) -> (firma, post3d)
        self.rep3d = None            # imagenes/resumen 3D para el reporte
        self.rep3d_cache = {}        # id(conexion) -> (firma, rep3d)
        self.res = None
        self.res3d = None
        self.post3d = None
        self._sig3d = None
        self.worker = None
        self.path = None
        self._loading = False
        self.us = UnitSet(self.prj.u_len, self.prj.u_force,
                          self.prj.u_stress, self.prj.u_moment)

        self.setWindowTitle(f"PlacaBasePro {__version__} — Diseno de placas base")
        self.resize(1500, 920)

        self._build_actions()
        self._build_forms()
        self._build_views()

        left = QSplitter(Qt.Vertical)
        cw = QWidget(); cl = QVBoxLayout(cw); cl.setContentsMargins(4, 4, 4, 0)
        cl.addWidget(QLabel("<b>Conexiones del proyecto</b>"))
        self.lst_con = QListWidget()
        self.lst_con.setMaximumHeight(140)
        self.lst_con.currentRowChanged.connect(self.on_select_connection)
        cl.addWidget(self.lst_con)
        hb = QHBoxLayout()
        for txt, fn in (("Nueva", self.con_new), ("Duplicar", self.con_dup),
                        ("Renombrar", self.con_rename), ("Eliminar", self.con_del)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hb.addWidget(bt)
        cl.addLayout(hb)
        left.addWidget(cw)
        left.addWidget(self.tabs_in)
        left.setSizes([190, 800])
        spl = QSplitter(Qt.Horizontal)
        spl.addWidget(left)
        spl.addWidget(self.tabs_out)
        spl.setSizes([470, 1030])
        self.setCentralWidget(spl)
        self.setStatusBar(QStatusBar())

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.recalc(fea=True))

        self.load_ui()
        self._refresh_list()
        self.recalc(fea=True)

    # =============================================================== acciones
    def _build_actions(self):
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)
        mb = self.menuBar()
        m_file = mb.addMenu("&Archivo")
        m_calc = mb.addMenu("&Calculo")
        m_exp = mb.addMenu("&Exportar")
        m_mat = mb.addMenu("&Materiales")
        m_help = mb.addMenu("A&yuda")

        def act(menu, text, slot, key=None, toolbar=False):
            a = QAction(text, self)
            if key:
                a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            menu.addAction(a)
            if toolbar:
                tb.addAction(a)
            return a

        act(m_file, "Nuevo", self.new, "Ctrl+N", True)
        act(m_file, "Abrir...", self.open, "Ctrl+O", True)
        act(m_file, "Guardar", self.save, "Ctrl+S", True)
        act(m_file, "Guardar como...", self.save_as, "Ctrl+Shift+S")
        m_file.addSeparator()
        act(m_file, "Importar base de datos AISC v14.1...", self.import_aisc)
        m_file.addSeparator()
        act(m_file, "Salir", self.close, "Ctrl+Q")
        tb.addSeparator()
        act(m_calc, "Recalcular ahora", lambda: self.recalc(fea=True), "F5")
        act(m_calc, "Calcular sin FEA", lambda: self.recalc(fea=False), "F6")
        m_calc.addSeparator()
        act(m_calc, "Analisis SOLIDO 3D (Gmsh + CalculiX)...", self.run_3d, "F8")
        tb.addSeparator()
        act(m_exp, "Memoria de calculo PDF (.pdf)...", self.export_pdf, None, True)
        act(m_exp, "Memoria de calculo Word (.docx)...", self.export_docx, None, True)
        act(m_exp, "Imagenes (.png)...", self.export_png)
        m_exp.addSeparator()
        act(m_exp, "Modelo solido 3D para Gmsh (.geo)...", self.export_3d)
        act(m_exp, "Modelo de cascaras CalculiX (.inp)...", self.export_ccx)
        act(m_help, "Acerca de", self.about)
        act(m_mat, "Biblioteca de materiales...", self.materials_dialog)
        m_exp.addSeparator()
        act(m_exp, "Reportes PDF de TODAS las conexiones...", lambda: self.export_all("pdf"))
        act(m_exp, "Reportes Word de TODAS las conexiones...", lambda: self.export_all("docx"))

        self.chk_auto = QCheckBox("FEA automatico")
        self.chk_auto.setToolTip("Recalcula el modelo de elementos finitos con cada cambio "
                                 "(mas lento).  Si esta desactivado, use F5.")
        self.chk_auto.setChecked(True)
        self.chk_auto.setVisible(False)
        self.lbl_verdict = QLabel("  ")
        f = QFont(); f.setBold(True); f.setPointSize(11)
        self.lbl_verdict.setFont(f)
        tb.addSeparator()
        tb.addWidget(self.lbl_verdict)

    # ============================================================= formularios
    def _build_forms(self):
        self.tabs_in = QTabWidget()
        self.forms = []

        def new_form(title):
            f = Form()
            f.changed.connect(self.on_change)
            self.forms.append(f)
            self.tabs_in.addTab(scroll(f), title)
            return f

        # ---- proyecto
        f = new_form("Proyecto")
        f.group("Identificacion")
        f.text("Proyecto", "name")
        f.text("Elemento", "element")
        f.text("Calculo", "author")
        f.text("Fecha", "date")
        f.group("Unidades de trabajo")
        self.cb_preset = QComboBox()
        self.cb_preset.addItem("(personalizado)")
        self.cb_preset.addItems(list(DEFAULT_SETS.keys()))
        self.cb_preset.currentTextChanged.connect(self.on_preset)
        f._lay.addRow("Sistema", self.cb_preset)
        f.combo("Longitud", "u_len", list(LEN_UNITS.keys()))
        f.combo("Fuerza", "u_force", list(FORCE_UNITS.keys()))
        f.combo("Momento", "u_moment", list(MOMENT_UNITS.keys()))
        f.combo("Esfuerzo", "u_stress", list(STRESS_UNITS.keys()))
        f.note("Se aplican a TODA la aplicacion: entradas, tabla de resultados y "
               "reportes.  El calculo interno siempre se hace en in-kip-ksi, que son "
               "las unidades nativas de AISC v14 y de los pernos en pulgadas.")
        f.finish()

        # ---- perfil
        f = new_form("Perfil")
        f.group("Catalogo AISC (1,660 perfiles) y secciones propias")
        self.cb_kind = QComboBox()
        self.cb_kind.currentTextChanged.connect(self.on_kind)
        f._lay.addRow("Familia", self.cb_kind)
        self.cb_shape = f.combo("Perfil", "section.label", [], help="Perfiles de la AISC Shapes Database: W, M, S, HP, C, MC, L, WT, MT, ST, HSS y tuberias. Las secciones creadas con 'Nueva seccion' aparecen en la familia 'Secciones personalizadas'.")
        rowb = QWidget(); hb = QHBoxLayout(rowb); hb.setContentsMargins(0, 0, 0, 0)
        for txt, fn in (("Nueva seccion...", self.new_section),
                        ("Editar", self.edit_section), ("Eliminar", self.del_section)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hb.addWidget(bt)
        f._lay.addRow("", rowb)
        self.lbl_shape = QLabel("")
        self.lbl_shape.setStyleSheet("color:#1f3864; font-size:8pt;")
        f._lay.addRow("", self.lbl_shape)
        f.combo("Acero", "section.steel", [s.name for s in M.SHAPE_STEELS], help="Grado del acero del perfil. Define Fy y Fu para la verificacion del propio perfil y del metal base de la soldadura.")
        f.group("Seccion doble")
        f.check("Doble, espalda con espalda", "section.double", help="Dos piezas iguales espalda con espalda (por ejemplo 2L o 2C), simetricas respecto al eje Y. Se calculan A, Ix, Sx y Zx dobles, e Iy, Sy y Zy con la separacion real. La soldadura se verifica como grupo en todo el contorno. No aplica a secciones redondas.")
        f.num("Separacion entre piezas", "section.gap", 0, 12, uk="L", help="Distancia libre entre las espaldas de las dos piezas (espesor de la cartela o del separador). En dobles angulos AISC tabula 0, 3/8 y 3/4 in.")
        f.group("Orientacion respecto a la placa")
        f.num("Rotacion", "section.rotation", -180, 180, 15.0, 1, "°", help="Giro del perfil respecto a la placa. 0° = eje fuerte paralelo a N, de modo que Mux flexiona el perfil en su eje fuerte. 90° = eje debil. Con angulos intermedios las formulas cerradas de DG1 usan el rectangulo envolvente; el FEA usa la geometria real.")
        f.note("0° = eje fuerte paralelo a N (Y).  90° = eje debil paralelo a N.  "
               "Con angulos distintos de 0/90 las formulas de DG1 usan el rectangulo "
               "envolvente; el FEA usa la geometria real.")
        f.group("Inclinacion de la columna (respecto a la normal de la placa)")
        f.num("Giro alrededor de X", "loads.tilt_x", -85, 85, 1.0, 2, "°", help="Inclinacion de la columna respecto a la normal de la placa, girando alrededor del eje X (la columna se inclina hacia +Y/-Y). 0° = perpendicular. Con inclinacion, Pu, Vux, Vuy, Mux y Muy se ingresan en los ejes de la COLUMNA (Pu = axial, V = transversal) y el programa los proyecta a los ejes de la placa para todas las verificaciones.")
        f.num("Giro alrededor de Y", "loads.tilt_y", -85, 85, 1.0, 2, "°", help="Inclinacion de la columna respecto a la normal de la placa, girando alrededor del eje Y (la columna se inclina hacia +X/-X). 0° = perpendicular. Puede combinarse con el giro alrededor de X.")
        self.lbl_tilt = QLabel("")
        self.lbl_tilt.setStyleSheet("color:#595959; font-size:8pt;")
        f._lay.addRow("En ejes de la placa", self.lbl_tilt)
        f.finish()

        # ---- placa
        f = new_form("Placa")
        f.group("Geometria")
        f.combo("Forma", "plate.shape", PLATE_SHAPES, help="Rectangular o circular. En placa circular las formulas cerradas usan el cuadrado equivalente de igual area (Leq = 0.8862·Dp); el FEA modela el circulo real.")
        f.num("N (largo, dir. Y)", "plate.N", 1, 200, uk="L", help="Dimension de la placa en la direccion Y, que es la direccion en que actua el momento Mux. Es el lado que gobierna el equilibrio de aplastamiento.")
        f.num("B (ancho, dir. X)", "plate.B", 1, 200, uk="L", help="Dimension de la placa en la direccion X, perpendicular a Mux. Es el ancho sobre el que se reparte la presion de contacto.")
        f.num("Dp (si es circular)", "plate.Dp", 1, 200, uk="L", help="Diametro de la placa. Solo se usa cuando la forma es Circular.")
        f.num("tp (espesor)", "plate.tp", 0.25, 12, uk="L", help="Espesor propuesto de la placa. El programa calcula el espesor requerido por las lineas de fluencia y lo compara contra este valor.")
        f.num("Mortero de nivelacion", "plate.grout", 0, 6, uk="L", help="Espesor del mortero de nivelacion bajo la placa. Reduce la altura embebida util de la llave de corte y, si no hay llave, aplica el factor 0.80 al cortante del anclaje (ACI 17.7.1.2.1).")
        f.group("Material")
        f.combo("Acero de placa", "plate.steel", [s.name for s in M.PLATE_STEELS], help="Grado del acero de la placa base. Su Fy gobierna el espesor requerido.")
        f.finish()

        # ---- pernos
        f = new_form("Pernos")
        f.group("Varilla de anclaje")
        f.combo("Diametro", "bolts.size", M.BOLT_SIZES, help="Diametro nominal del anclaje en pulgadas. De el se derivan Ab, el area de esfuerzo Ase de rosca UNC, el diametro de agujero en la placa segun AISC Tabla 14-2 y el area de apoyo de la tuerca hexagonal pesada.")
        self.lbl_bolt = QLabel("")
        self.lbl_bolt.setStyleSheet("color:#1f3864; font-size:8pt;")
        f._lay.addRow("", self.lbl_bolt)
        f.combo("Material", "bolts.steel", [s.name for s in M.ANCHOR_STEELS], help="Grado de la varilla de anclaje. Ademas de Fy y Fu define si el elemento es ductil, lo que decide el factor de reduccion de ACI Tabla 17.5.3.")
        f.combo("Tipo de anclaje", "bolts.atype", ANCHOR_TYPES, help="Con cabeza: la extraccion se calcula con 8·Abrg·f'c. Gancho L o J: con 0.9·f'c·eh·da. Recto: ACI no le reconoce resistencia a la extraccion y el programa lo marca como no valido si hay traccion.")
        f.combo("Instalacion (varilla recta)", "bolts.install", INSTALL_TYPES,
                help="Solo se usa con varilla recta. Preinstalada (vaciada en sitio): ACI no "
                     "le reconoce resistencia a la extraccion y no es valida a traccion. "
                     "Postinstalada con adhesivo (epoxico): se diseña por adherencia segun "
                     "ACI 318-19 17.6.5, con kc = 17 en el arrancamiento y el factor φ de la "
                     "categoria del producto.")
        f.num("hef (embebido efectivo)", "bolts.hef", 2, 120, uk="L", help="Profundidad efectiva de embebido, desde la superficie del concreto hasta el plano de apoyo de la cabeza o del gancho. Es el parametro que mas pesa en el arrancamiento del concreto.")
        f.num("eh gancho (0 = 3·db)", "bolts.eh", 0, 20, uk="L", help="Longitud del gancho medida desde el eje de la varilla. ACI la limita a 3·db <= eh <= 4.5·db. Deje 0 para que el programa use 3·db.")
        f.combo("Criterio del agujero", "bolts.hole_rule", M.HOLE_RULES,
                help="La Tabla 14-2 del Manual AISC (= Tabla 2.3 de la DG1) da los "
                     "diametros MAXIMOS recomendados: son muy holgados a proposito "
                     "para absorber la tolerancia de colocacion de los anclajes en el "
                     "concreto, y obligan a cubrirlos con arandela de placa. Ejemplo: "
                     "Ø5/8 in lleva agujero de 1-3/16 in = 30.2 mm. Si el grupo se "
                     "coloca con plantilla se justifica uno menor: la regla F844 (nota "
                     "al pie de la tabla) da db+5/16 hasta 1 in, y la ajustada db+1/16.")
        f.num("Abrg manual (0 = hex pesada)", "bolts.Abrg_user", 0, 100, uk="A", help="Area neta de aplastamiento de la cabeza. Deje 0 para que se calcule de la tuerca hexagonal pesada; indique un valor si usa una placa de anclaje soldada en la punta.")
        f.group("Anclaje adhesivo (postinstalado)")
        f.combo("Adherencia caracteristica", "bolts.adh_env", ADH_ENV,
                help="Sin datos del producto, ACI 318-19 Tabla 17.6.5.2.5 da valores minimos: "
                     "interior seco τcr = 300 psi, τuncr = 1000 psi; exterior 200 / 650 psi. "
                     "El programa aplica los factores de la tabla (0.4 si hay traccion "
                     "sostenida; 0.8 y 0.4 con sismo). Con 'Datos del producto' use los "
                     "valores del reporte ESR/ICC-ES, que ya traen sus propios factores.")
        f.num("τcr (concreto fisurado)", "bolts.tau_cr", 0.01, 5, uk="S",
              help="Esfuerzo de adherencia caracteristico en concreto fisurado, del reporte "
                   "del producto. Solo se usa con 'Datos del producto'.")
        f.num("τuncr (concreto no fisurado)", "bolts.tau_uncr", 0.01, 5, uk="S",
              help="Esfuerzo de adherencia caracteristico en concreto no fisurado. Tambien "
                   "define la distancia critica cNa = 10·da·√(τuncr/1100).")
        f.combo("Categoria del anclaje", "bolts.adh_cat", ADH_CATEGORY,
                help="Categoria de sensibilidad a la instalacion segun ACI 355.4, dada por el "
                     "reporte del producto. Define φ en traccion: cat. 1 = 0.75/0.65, "
                     "cat. 2 = 0.65/0.55, cat. 3 = 0.55/0.45 (condicion A/B).")
        f.num("Fraccion de traccion sostenida", "bolts.sustained", 0, 1, 0.05, 2,
              help="Parte de la traccion que actua de forma permanente (peso propio, "
                   "empuje de tierras). Si es mayor que cero se verifica 0.55·φ·Nba >= Nua,s "
                   "(ACI 17.5.2.2) y se reducen los valores de la Tabla 17.6.5.2.5.")
        f.group("Disposicion")
        f.combo("Patron", "bolts.pattern", PATTERNS, help="Coordenadas manuales: escriba x, y "
                "de cada anclaje en la tabla de abajo, respecto al centro de la placa. Perimetral coloca pernos en los cuatro lados; las opciones de 2 lados solo en los dos lados perpendiculares al eje indicado; Circular los reparte equiespaciados sobre un circulo.")
        f.int_("Pernos en eje MAYOR (fila en X)", "bolts.n_major", 2, 12, help="Cantidad de pernos por fila a lo largo del eje X, es decir en los lados perpendiculares a la direccion del momento. Son los que toman la traccion.")
        f.int_("Pernos en eje MENOR (fila en Y)", "bolts.n_minor", 2, 12, help="Cantidad de pernos por fila a lo largo del eje Y, en los lados paralelos al momento.")
        f.int_("Pernos en patron circular", "bolts.n_circ", 3, 36, help="Cantidad total de pernos equiespaciados sobre el circulo. Solo se usa con el patron Circular.")
        f.num("ex (borde en X)", "bolts.ex", 0.5, 20, uk="L", help="Distancia del centro del perno al borde de la placa en direccion X. Debe dejar material suficiente para la arandela; el programa avisa si baja del minimo recomendado.")
        f.num("ey (borde en Y)", "bolts.ey", 0.5, 20, uk="L", help="Distancia del centro del perno al borde de la placa en direccion Y. Junto con N fija el brazo f de la resultante de traccion.")
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-weight:bold;")
        f._lay.addRow("Total", self.lbl_count)
        f.note("Perimetral: 2·mayor + 2·menor − 4.   2 lados (eje mayor): 2·mayor.   "
               "2 lados (eje menor): 2·menor.")
        f.group("Coordenadas manuales")
        self.tbl_xy = PasteTable(0, 2)
        self.tbl_xy.pasted.connect(self._xy_paste)
        self.tbl_xy.setMinimumHeight(170)
        self.tbl_xy.verticalHeader().setDefaultSectionSize(22)
        self.tbl_xy.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_xy.itemChanged.connect(lambda *_: self._xy_changed())
        f._lay.addRow(self.tbl_xy)
        row = QWidget(); hl = QHBoxLayout(row); hl.setContentsMargins(0, 0, 0, 0)
        for txt, fn in (("Agregar", self._xy_add), ("Quitar", self._xy_del),
                        ("Pegar desde Excel", self._xy_paste_btn),
                        ("Copiar del patron actual", self._xy_copy)):
            bt = QPushButton(txt); bt.clicked.connect(fn); hl.addWidget(bt)
        f._lay.addRow(row)
        f.note("PEGAR DESDE EXCEL: copie dos columnas (x, y) en Excel y use el boton "
               "'Pegar desde Excel' (reemplaza toda la lista) o seleccione una celda y "
               "presione Ctrl+V (sobrescribe desde esa celda y agrega filas si hace falta). "
               "Los valores se leen en las unidades actuales; se aceptan coma o punto "
               "decimal, y los encabezados se ignoran.")
        f.note("Origen en el centro de la placa; +Y es el lado traccionado por Mux. "
               "Las filas se numeran P1, P2... igual que en los dibujos y en la tabla del FEA.")
        f.finish()

        # ---- llave
        f = new_form("Llave de corte")
        f.group("Llave de corte (shear lug)")
        f.check("Usar llave de corte", "lug.enabled", help="Al activarla, todo el cortante se asigna a la llave y deja de exigirse a los pernos, que es la practica habitual cuando el cortante es alto.")
        f.combo("Tipo de llave", "lug.ltype", LUG_TYPES, help="Placa: una pletina (o dos cruzadas). Perfil: cualquier seccion del catalogo (W, HSS, angulo, canal, tubo...). Con perfil se verifica cada direccion de cortante con la proyeccion del perfil: aplastamiento, flexion con Z, cortante, soldadura como grupo y desprendimiento del concreto.")
        self.cb_lugfam = QComboBox()
        self.cb_lugfam.currentTextChanged.connect(self.on_lug_family)
        f._lay.addRow("Familia (si es perfil)", self.cb_lugfam)
        self.cb_lugshape = f.combo("Perfil de la llave", "lug.label", [], help="Seccion usada como llave de corte.")
        f.num("Giro del perfil (0 o 90°)", "lug.rotation", 0, 90, 90.0, 0, "°", help="0°: el perfil queda con su eje fuerte a lo largo de X. 90°: girado. Se usa para decidir que momento resistente (Zx o Zy) trabaja en cada direccion de cortante.")
        f.combo("Orientacion", "lug.direction", LUG_DIRS, help="Eje al que es perpendicular la cara de aplastamiento de la llave. Con Ambos ejes se colocan dos llaves cruzadas y el cortante se reparte entre ellas.")
        f.num("W (ancho)", "lug.W", 1, 60, uk="L", help="Ancho de la llave medido perpendicular a la direccion del cortante. Es el ancho de aplastamiento contra el concreto.")
        f.num("H (altura bajo la placa)", "lug.H", 1, 30, uk="L", help="Altura total de la llave por debajo de la placa. La altura util de aplastamiento es H menos el espesor del mortero.")
        f.num("t (espesor)", "lug.t", 0.25, 6, uk="L", help="Espesor de la pletina de la llave. Gobierna su flexion en la cara inferior de la placa.")
        f.combo("Acero", "lug.steel", [s.name for s in M.PLATE_STEELS])
        f.num("Filete a cada lado", "lug.weld_size", 0.125, 1.5, uk="L")
        f.combo("Electrodo", "lug.electrode", [e.name for e in M.ELECTRODES])
        f.note("Con llave activa el cortante se asigna a la llave y no a los pernos. "
               "La altura embebida descuenta el espesor del mortero.")
        f.finish()

        # ---- rigidizadores
        f = new_form("Rigidizadores")
        f.group("Pletinas rigidizadoras")
        self.lbl_stiff_lock = QLabel("Rigidizadores NO disponibles: la columna esta inclinada "
                                     "(pestaña Cargas). Ponga el giro en 0° para usarlos.")
        self.lbl_stiff_lock.setStyleSheet("color:#9c0006; font-size:8pt;")
        self.lbl_stiff_lock.setWordWrap(True)
        f._lay.addRow("", self.lbl_stiff_lock)
        self.chk_stiff = f.check("Usar rigidizadores", "stiff.enabled", help="Las pletinas reducen el voladizo de la placa y por tanto el espesor requerido, a cambio de soldadura adicional.")
        f.combo("Posicion", "stiff.position", STIFF_POSITIONS, help="Cara del perfil a la que se sueldan las pletinas. En HSS lo habitual es Perimetro de 4 caras; en perfiles W, Alas o Ambos.")
        f.int_("Cantidad total", "stiff.count", 1, 16, help="Numero total de pletinas del conjunto; el programa las reparte entre las caras segun la posicion elegida.")
        f.num("L (proyeccion desde el perfil)", "stiff.L", 0.5, 40, uk="L", help="Cuanto sobresale la pletina desde la cara del perfil hacia el borde de la placa. Si excede el voladizo disponible el programa la recorta y lo avisa.")
        f.num("h (altura)", "stiff.h", 1, 40, uk="L", help="Altura de la pletina sobre la placa, medida en la cara del perfil. Define el modulo de seccion y la longitud de la soldadura a la columna.")
        f.num("t (espesor)", "stiff.t", 0.25, 3, uk="L", help="Espesor de la pletina. Junto con la altura define la esbeltez del borde libre, que se compara con 0.56·√(E/Fy).")
        f.combo("Acero", "stiff.steel", [s.name for s in M.PLATE_STEELS])
        f.group("Ubicacion a lo largo de la cara")
        f.combo("Criterio", "stiff.spacing_mode", STIFF_SPACING, help="Como se ubican las pletinas a lo largo de la cara: repartidas automaticamente, con una separacion que usted fija, o alineadas con los pernos que caen dentro de la cara del perfil.")
        f.num("Separacion centro a centro", "stiff.spacing", 0.5, 100, uk="L", help="Distancia entre pletinas contiguas de una misma cara. Solo se usa con el criterio de separacion fija. Es el parametro para acomodarlas respecto a los anclajes.")
        f.num("Angulo de arranque (columna circular)", "stiff.offset_angle", -180, 180, 5.0, 1, "°", help="Solo columna circular: los rigidizadores se disponen en forma RADIAL, repartidos por igual en 360°. Este es el angulo de la primera pletina medido desde +X. Con columna circular 'Posicion' y 'Criterio' no se usan; la cantidad es el numero total de pletinas radiales.")
        f.num("Corrimiento del grupo", "stiff.offset", -50, 50, uk="L", help="Desplaza todo el grupo de pletinas a lo largo de la cara. Util para esquivar un perno o para centrar el conjunto.")
        f.note("'Separacion fija' reparte las pletinas simetricamente con esa "
               "distancia entre ellas; el corrimiento desplaza todo el grupo. "
               "'Alineado con los pernos' usa las coordenadas de los pernos que "
               "caen dentro de la cara del perfil.")
        f.group("Forma de la pletina")
        f.combo("Forma", "stiff.shape", STIFF_SHAPES, help="Rectangular, triangular, o rectangular con la esquina exterior recortada. En las dos ultimas la seccion critica no esta en la cara del perfil y el programa barre toda la proyeccion.")
        f.num("Recorte horizontal de la esquina", "stiff.clip_h", 0, 20, uk="L", help="Longitud del recorte medida desde el extremo exterior. Solo aplica a la forma con esquina recortada.")
        f.num("Recorte vertical de la esquina", "stiff.clip_v", 0, 20, uk="L", help="Altura del recorte medida desde el borde superior. Solo aplica a la forma con esquina recortada.")
        f.num("Destaje en el vertice placa-columna", "stiff.clip_root", 0, 4, uk="L", help="Pequeno destaje en el encuentro de los dos cordones, practica habitual para evitar el cruce de soldaduras. Se descuenta de ambas longitudes de soldadura.")
        f.group("Soldadura")
        f.num("Filete a cada lado", "stiff.weld_size", 0.125, 1.5, uk="L")
        f.combo("Electrodo", "stiff.electrode", [e.name for e in M.ELECTRODES])
        f.finish()

        # ---- soldadura
        f = new_form("Soldadura")
        f.group("Alas (perfiles W)")
        f.combo("Tipo", "welds.flange.wtype", WELD_TYPES)
        f.num("Tamano (cateto / garganta)", "welds.flange.size", 0.0625, 2, uk="L")
        f.combo("Electrodo", "welds.flange.electrode", [e.name for e in M.ELECTRODES])
        f.check("Ambos lados del ala", "welds.flange.both_sides")
        f.group("Alma (perfiles W)")
        f.combo("Tipo", "welds.web.wtype", WELD_TYPES)
        f.num("Tamano", "welds.web.size", 0.0625, 2, uk="L")
        f.combo("Electrodo", "welds.web.electrode", [e.name for e in M.ELECTRODES])
        f.check("Ambos lados del alma", "welds.web.both_sides")
        f.group("Perimetral (HSS / Pipe)")
        f.combo("Tipo", "welds.perimeter.wtype", WELD_TYPES)
        f.num("Tamano", "welds.perimeter.size", 0.0625, 2, uk="L")
        f.combo("Electrodo", "welds.perimeter.electrode", [e.name for e in M.ELECTRODES])
        f.group("Opciones")
        f.check("Incremento direccional de resistencia (AISC J2-5)", "welds.directional")
        f.note("CJP con metal de aporte compatible: la resistencia es la del metal base "
               "(AISC J2.4) y no se calcula el deposito.")
        f.finish()

        # ---- concreto
        f = new_form("Concreto")
        f.group("Concreto y pedestal")
        self.cb_conc = f.combo("Material", "conc.material", ["(personalizado)"] + [c.name for c in M.CONCRETES], help="Concretos de la biblioteca (Materiales > Biblioteca de materiales). Al elegir uno se copian f'c y λ; con '(personalizado)' se escriben a mano.")
        self.cb_conc.currentTextChanged.connect(self.on_conc_material)
        f.num("f'c", "conc.fc", 2, 15, uk="S", help="Resistencia a compresion especificada del concreto del pedestal a 28 dias.")
        f.num("N2 pedestal (dir. Y)", "conc.N2", 4, 400, uk="L", help="Dimension del pedestal en direccion Y. Junto con B2 define el confinamiento y las distancias al borde que gobiernan el arrancamiento del concreto.")
        f.num("B2 pedestal (dir. X)", "conc.B2", 4, 400, uk="L", help="Dimension del pedestal en direccion X.")
        f.num("ha (altura del elemento)", "conc.ha", 4, 400, uk="L", help="Altura del elemento de concreto medida desde la superficie donde apoya la placa. Interviene en el factor de espesor del arrancamiento en cortante.")
        f.num("λa (concreto liviano)", "conc.lam", 0.5, 1.0, 0.05, 2, help="Factor de concreto liviano de ACI. Use 1.00 para concreto de peso normal.")
        f.check("Concreto fisurado en servicio", "conc.cracked", help="Marque si el concreto estara fisurado en la zona del anclaje bajo cargas de servicio, que es la hipotesis por defecto de ACI. Sin fisurar, las resistencias del concreto aumentan.")
        f.check("Refuerzo suplementario (condicion A)", "conc.cond_A", help="Condicion A de ACI Tabla 17.5.3: hay refuerzo suplementario que ata el cono de falla al elemento. Sube el factor de reduccion de 0.70 a 0.75.")
        f.check("Diseno sismico (ACI 17.10, factor 0.75)", "conc.seismic", help="Aplica el factor 0.75 a la resistencia del concreto de los anclajes. No verifica por usted el requisito de que el anclaje sea gobernado por la fluencia ductil del acero.")
        f.finish()

        # ---- cargas
        f = new_form("Cargas")
        f.group("Cargas factorizadas (LRFD)")
        f.num("Pu (compresion +)", "loads.Pu", -1e5, 1e5, uk="F", help="Carga axial factorizada en la base. POSITIVA en compresion, que es el caso habitual. Negativa significa traccion neta o levantamiento: la placa no apoya y toda la fuerza la toman los pernos.")
        f.num("Mux (traccion en +Y)", "loads.Mux", -1e6, 1e6, uk="M", help="Momento factorizado que flexiona la base alrededor del eje X. Por convencion produce TRACCION en el lado +Y de la placa, que es el borde superior del dibujo en planta. Es el momento que gobierna el equilibrio de DG1.")
        f.num("Muy", "loads.Muy", -1e6, 1e6, uk="M", help="Momento alrededor del eje Y. Entra en el esfuerzo del perfil, en la soldadura y en el FEA, pero el equilibrio cerrado de aplastamiento de DG1 es uniaxial y usa solo Mux.")
        f.num("Vux", "loads.Vux", -1e5, 1e5, uk="F", help="Cortante factorizado en direccion X. Si hay llave de corte lo toma ella; si no, se reparte entre todos los pernos.")
        f.num("Vuy", "loads.Vuy", -1e5, 1e5, uk="F", help="Cortante factorizado en direccion Y. El programa trabaja con la resultante de ambas componentes.")
        f.note("CONVENCION DE SIGNOS — Pu positivo en compresion.  Mux positivo "
               "tracciona el lado +Y, que es el borde superior del dibujo en planta; "
               "si su momento tracciona el lado opuesto, cambie el signo o gire la "
               "placa 180°.  Vux y Vuy son las componentes del cortante en los ejes "
               "de la placa.  Todos son valores YA FACTORIZADOS (LRFD).")
        f.note("La INCLINACION DE LA COLUMNA se define en la pestaña Perfil. Si esta "
               "inclinada, estas cargas se ingresan en los ejes de la columna.")
        f.group("Friccion")
        f.check("Descontar friccion placa-mortero del cortante en pernos", "loads.friction", help="Permite restar el producto del coeficiente de friccion por Pu del cortante que llega a los anclajes. Uselo solo si puede garantizar la compresion permanente y el estado de la interfaz.")
        f.num("Coeficiente μ", "loads.mu_fric", 0.2, 0.9, 0.05, 2, help="Coeficiente de friccion entre la placa y el mortero. Valores habituales de 0.40 a 0.55.")
        self.lbl_si = QLabel("")
        self.lbl_si.setStyleSheet("color:#595959; font-size:8pt;")
        f._lay.addRow("En SI", self.lbl_si)
        f.finish()

        # ---- FEA
        f = new_form("Elementos finitos")
        f.group("Modelo de placa (integrado)")
        f.check("Ejecutar FEA de la placa", "fea.enabled", help="Modelo de placa integrado, rapido, pensado para iterar. No sustituye a las verificaciones normativas: las complementa mostrando el reparto real de presiones y de traccion entre pernos.")
        f.int_("Divisiones en X", "fea.nx", 6, 60, help="Numero de divisiones de la malla en direccion X. Con mallas finas los agujeros se representan mejor pero el calculo tarda mas.")
        f.int_("Divisiones en Y", "fea.ny", 6, 60, help="Numero de divisiones de la malla en direccion Y.")
        f.combo("Modulo de balasto", "fea.ks_mode", ["Ec/hped", "manual"], help="Ec/hped estima el modulo de balasto como el modulo elastico del concreto dividido entre la altura del pedestal. Con manual usted lo impone.")
        f.num("ks manual", "fea.ks_manual", 1, 1e5, uk="K", help="Modulo de balasto del apoyo de concreto. Solo se usa en modo manual.")
        f.int_("Iteraciones de contacto max.", "fea.max_iter", 3, 200, help="Tope de iteraciones para resolver el contacto unilateral: resortes que solo trabajan a compresion y pernos que solo trabajan a traccion. Normalmente converge en 3 a 6.")
        f.check("Modelar los agujeros de perno en la malla", "fea.holes", help="Recorta los agujeros de la malla y hace que el perno apoye sobre el anillo de la tuerca en vez de sobre un nodo puntual. Requiere que la malla sea suficientemente fina.")
        f.note("Elemento MITC4 de Mindlin-Reissner sobre resortes de Winkler solo a "
               "compresion; pernos como resortes solo a traccion; rigidizadores como banda "
               "de espesor equivalente.")
        f.group("Modelo SOLIDO 3D (Gmsh + CalculiX)")
        f.text("CalculiX propio (opcional)", "fea.ccx_path", help="Dejelo vacio: el programa usa el CalculiX incluido en la carpeta solvers. Solo escriba una ruta si quiere usar otra version de ccx.exe.")
        f.num("Tamano de malla 3D (0 = automatico)", "fea.mesh3d", 0, 20, uk="L", help="Tamano caracteristico de los tetraedros. Valores pequenos dan mas detalle y mucho mas tiempo de calculo. Deje 0 para que lo estime el programa.")
        f.note("Exportar > Modelo solido 3D escribe el .geo con la geometria real "
               "(placa taladrada, perfil, rigidizadores y llave) mas un script "
               "correr_3d.py que lo malla con Gmsh, arma el .inp y lo resuelve con "
               "CalculiX.  Los resultados se abren en PrePoMax o CGX.")
        f.finish()

    # ================================================================== vistas
    def _build_views(self):
        self.tabs_out = QTabWidget()
        self.cv_plan = Canvas(size=(7, 7))
        self.cv_elev = Canvas(size=(8, 5))
        self.cv_stif = Canvas(size=(7, 5))
        self.tabs_out.addTab(self.cv_plan, "Planta")
        self.tabs_out.addTab(self.cv_elev, "Elevacion")
        self.tabs_out.addTab(self.cv_stif, "Rigidizador")

        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("Campo:"))
        self.cb_field = QComboBox()
        self.cb_field.addItems([a for a, _ in FIELDS_FEA])
        self.cb_field.currentIndexChanged.connect(self.draw_fea)
        top.addWidget(self.cb_field)
        btn = QPushButton("Recalcular FEA  (F5)")
        btn.clicked.connect(lambda: self.recalc(fea=True))
        top.addWidget(btn)
        top.addStretch(1)
        self.lbl_fea = QLabel("")
        self.lbl_fea.setWordWrap(True)
        lay.addLayout(top)
        self.cv_fea = Canvas(size=(7, 6))
        spl = QSplitter(Qt.Vertical)
        spl.addWidget(self.cv_fea)
        self.tbl_bolts = QTableWidget(0, 6)
        self.tbl_bolts.setHorizontalHeaderLabels(
            ["Perno", "x", "y", "Traccion T", "Esfuerzo σt", "D/C"])
        hb = self.tbl_bolts.horizontalHeader()
        for c in range(6):
            hb.setSectionResizeMode(c, QHeaderView.Stretch)
        self.tbl_bolts.verticalHeader().setVisible(False)
        self.tbl_bolts.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_bolts.setAlternatingRowColors(True)
        spl.addWidget(self.tbl_bolts)
        spl.setSizes([520, 230])
        lay.addWidget(spl, 1)
        lay.addWidget(self.lbl_fea)
        self.tabs_out.addTab(w, "Elementos finitos")

        # ---------------- modelo solido 3D
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        t3 = QHBoxLayout()
        self.btn3d = QPushButton("Ejecutar analisis 3D  (Gmsh + CalculiX)")
        self.btn3d.clicked.connect(self.run_3d)
        t3.addWidget(self.btn3d)
        t3.addWidget(QLabel("Campo:"))
        self.cb_f3 = QComboBox()
        self.cb_f3.addItems(["Solo geometria", "Von Mises", "Desplazamiento |U|",
                             "Desplazamiento Uz"])
        self.cb_f3.currentIndexChanged.connect(self.draw_3d)
        t3.addWidget(self.cb_f3)
        t3.addWidget(QLabel("Escala de deformada:"))
        self.sp_sc = QDoubleSpinBox()
        self.sp_sc.setRange(0, 100000); self.sp_sc.setDecimals(0)
        self.sp_sc.setValue(0); self.sp_sc.setSingleStep(50)
        self.sp_sc.setToolTip("0 = geometria sin deformar.  Un valor mayor amplifica "
                              "los desplazamientos para poder verlos.")
        self.sp_sc.valueChanged.connect(self.draw_3d)
        t3.addWidget(self.sp_sc)
        t3.addStretch(1)
        l3.addLayout(t3)
        sp3 = QSplitter(Qt.Vertical)
        self.cv_3d = Canvas3D()
        sp3.addWidget(self.cv_3d)
        low = QWidget(); ll = QHBoxLayout(low); ll.setContentsMargins(0, 0, 0, 0)
        self.tbl_w3 = QTableWidget(0, 7)
        self.tbl_b3 = QTableWidget(0, 4)
        for tb in (self.tbl_w3, self.tbl_b3):
            tb.verticalHeader().setVisible(False)
            tb.setEditTriggers(QTableWidget.NoEditTriggers)
            tb.setAlternatingRowColors(True)
            tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        bw = QWidget(); bl = QVBoxLayout(bw); bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(QLabel("<b>Soldadura perfil-placa (leida del solido)</b>"))
        bl.addWidget(self.tbl_w3)
        bb = QWidget(); b2 = QVBoxLayout(bb); b2.setContentsMargins(0, 0, 0, 0)
        b2.addWidget(QLabel("<b>Traccion por perno (3D)</b>"))
        b2.addWidget(self.tbl_b3)
        ll.addWidget(bw, 3); ll.addWidget(bb, 2)
        sp3.addWidget(low)
        sp3.setSizes([560, 230])
        l3.addWidget(sp3, 1)
        self.lbl_3d = QLabel("La vista 3D muestra siempre la geometria de la conexion "
                             "(se actualiza al editar; no necesita analisis). "
                             "El analisis solido incluye la placa con los agujeros "
                             "taladrados, el perfil, los rigidizadores y la llave, con "
                             "el concreto solo a compresion y los pernos solo a traccion. "
                             "Gmsh y CalculiX vienen incluidos: solo presione el boton "
                             "(o F8). Tarda unos minutos.")
        self.lbl_3d.setWordWrap(True)
        l3.addWidget(self.lbl_3d)
        self.tabs_out.addTab(w3, "Modelo 3D")

        # ---------------- memoria detallada
        self.txt_mem = QTextEdit()
        self.txt_mem.setReadOnly(True)
        wm = QWidget()
        lm = QVBoxLayout(wm)
        tm = QHBoxLayout()
        self.chk_mem = QCheckBox("Incluir la memoria detallada en los reportes")
        self.chk_mem.setChecked(True)
        tm.addWidget(self.chk_mem)
        bexp = QPushButton("Copiar al portapapeles")
        bexp.clicked.connect(lambda: QApplication.clipboard().setText(
            self.txt_mem.toPlainText()))
        tm.addWidget(bexp)
        tm.addStretch(1)
        lm.addLayout(tm)
        lm.addWidget(self.txt_mem, 1)
        self.tabs_out.addTab(wm, "Memoria detallada")

        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Verificacion", "Demanda", "Capacidad",
                                            "Unid.", "D/C", "Referencia / observacion"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        l2.addWidget(self.tbl, 1)
        self.txt_info = QTextEdit()
        self.txt_info.setReadOnly(True)
        self.txt_info.setMaximumHeight(190)
        l2.addWidget(self.txt_info)
        self.tabs_out.addTab(w2, "Resultados")

    # ============================================================ sincronizacion
    def apply_units(self):
        """Propaga el sistema de unidades elegido a todos los formularios."""
        self.us.set_units(self.prj.u_len, self.prj.u_force,
                          self.prj.u_stress, self.prj.u_moment)
        for f in self.forms:
            f.us = self.us
        cur = (self.prj.u_len, self.prj.u_force, self.prj.u_stress)
        name = "(personalizado)"
        for k, v in DEFAULT_SETS.items():
            if v == cur:
                name = k
                break
        self.cb_preset.blockSignals(True)
        self.cb_preset.setCurrentText(name)
        self.cb_preset.blockSignals(False)

    def on_preset(self, name):
        if self._loading or name not in DEFAULT_SETS:
            return
        L, F, S = DEFAULT_SETS[name]
        self.prj.u_len, self.prj.u_force, self.prj.u_stress = L, F, S
        self.prj.u_moment = {"in": "kip·in", "ft": "kip·ft", "mm": "kN·m",
                             "m": "kN·m", "cm": "tonf·m"}.get(L, "kip·in")
        self.load_ui()
        self.fill_table()

    def load_ui(self):
        for msg in self.prj.normalize():
            self.statusBar().showMessage(msg, 10000)
        self._loading = True
        try:
            self.apply_units()
            s = self.prj.section.shape()
            self.cb_kind.blockSignals(True)
            self.cb_kind.clear()
            self.cb_kind.addItems([fam_label(f) for f in CATALOG.families()])
            self.cb_kind.setCurrentText(fam_label(s.family))
            self.cb_kind.blockSignals(False)
            self._fill_shapes(s.family, s.label)
            ls = self.prj.lug.shape()
            self.cb_lugfam.blockSignals(True)
            self.cb_lugfam.clear()
            self.cb_lugfam.addItems([fam_label(f) for f in CATALOG.families()])
            self.cb_lugfam.setCurrentText(fam_label(ls.family))
            self.cb_lugfam.blockSignals(False)
            self._fill_lug(ls.family, ls.label)
            for f in self.forms:
                f.load(self.prj)
            self._xy_load()
        finally:
            self._loading = False
        self._update_labels()

    def store_ui(self):
        for f in self.forms:
            f.store(self.prj)
        self._xy_store()

    # ------------------------------------------ coordenadas manuales de pernos
    def _xy_load(self):
        u = self.us
        t = self.tbl_xy
        t.blockSignals(True)
        t.setHorizontalHeaderLabels([f"x ({u.L})", f"y ({u.L})"])
        t.setRowCount(0)
        for i, (x, y) in enumerate(self.prj.bolts.coords):
            t.insertRow(i)
            t.setVerticalHeaderItem(i, QTableWidgetItem(f"P{i + 1}"))
            for j, v in enumerate((x, y)):
                t.setItem(i, j, QTableWidgetItem(f"{u.out('L', v):.6g}"))
        t.blockSignals(False)

    def _xy_store(self):
        u = self.us
        out = []
        for i in range(self.tbl_xy.rowCount()):
            try:
                x = float(self.tbl_xy.item(i, 0).text().replace(",", ""))
                y = float(self.tbl_xy.item(i, 1).text().replace(",", ""))
            except (AttributeError, ValueError):
                continue
            out.append([u.inn("L", x), u.inn("L", y)])
        if out or self.tbl_xy.rowCount() == 0:
            self.prj.bolts.coords = out

    def _xy_changed(self):
        if self._loading:
            return
        self._xy_store()
        self.on_change()

    def _xy_paste_btn(self):
        rows = parse_xy_clipboard(QApplication.clipboard().text())
        if not rows:
            QMessageBox.information(self, "Pegar coordenadas",
                                    "El portapapeles no contiene dos columnas numericas (x, y).")
            return
        self._xy_paste(rows, 0, True)

    def _xy_paste(self, rows, start, replace=False):
        """Escribe las filas pegadas en la tabla (en unidades del usuario)."""
        self._xy_store()
        u = self.us
        t = self.tbl_xy
        data = [] if replace else [
            [float(t.item(i, j).text().replace(",", "")) if t.item(i, j) and t.item(i, j).text()
             else 0.0 for j in (0, 1)] for i in range(t.rowCount())]
        for k, (x, y) in enumerate(rows):
            i = (0 if replace else start) + k
            while len(data) <= i:
                data.append([0.0, 0.0])
            data[i] = [x, y]
        self._loading = True
        try:
            t.blockSignals(True)
            t.setRowCount(0)
            for i, (x, y) in enumerate(data):
                t.insertRow(i)
                t.setVerticalHeaderItem(i, QTableWidgetItem(f"P{i + 1}"))
                for j, v in enumerate((x, y)):
                    t.setItem(i, j, QTableWidgetItem(f"{v:.6g}"))
            t.blockSignals(False)
        finally:
            self._loading = False
        self._xy_store()
        self.on_change()

    def _xy_add(self):
        self._xy_store()
        c = self.prj.bolts.coords
        self.prj.bolts.coords = c + [[0.0, 0.0]]
        self._xy_load(); self.on_change()

    def _xy_del(self):
        self._xy_store()
        r = self.tbl_xy.currentRow()
        c = list(self.prj.bolts.coords)
        if c:
            c.pop(r if 0 <= r < len(c) else -1)
        self.prj.bolts.coords = c
        self._xy_load(); self.on_change()

    def _xy_copy(self):
        from . import geometry as GG
        self.store_ui()
        old = self.prj.bolts.pattern
        if old.startswith("Coordenadas"):
            return
        self.prj.bolts.coords = [[x, y] for x, y in GG.bolt_positions(self.prj)]
        self.prj.bolts.pattern = "Coordenadas manuales"
        self.load_ui(); self.on_change()

    def _fill_shapes(self, family, select=None):
        self.cb_shape.blockSignals(True)
        self.cb_shape.clear()
        labels = CATALOG.by_family(family)
        self.cb_shape.addItems(labels)
        if select and select in labels:
            self.cb_shape.setCurrentText(select)
        self.cb_shape.blockSignals(False)

    def _fill_lug(self, family, select=None):
        self.cb_lugshape.blockSignals(True)
        self.cb_lugshape.clear()
        labels = CATALOG.by_family(family)
        self.cb_lugshape.addItems(labels)
        if select and select in labels:
            self.cb_lugshape.setCurrentText(select)
        self.cb_lugshape.blockSignals(False)

    def on_kind(self, name):
        if self._loading:
            return
        fam = fam_from_label(name)
        self._fill_shapes(fam)
        steel = FAMILY_STEEL.get(fam)
        if steel:
            for fld in self.forms[1].fields:
                if fld[0] == "section.steel":
                    fld[1].setCurrentText(steel)
        self.on_change()

    def on_lug_family(self, name):
        if self._loading:
            return
        self._fill_lug(fam_from_label(name))
        self.on_change()

    def on_conc_material(self, name):
        if self._loading:
            return
        m = next((c for c in M.CONCRETES if c.name == name), None)
        if m is None:
            return
        self.store_ui()
        self.prj.conc.fc, self.prj.conc.lam = m.fc, m.lam
        self.load_ui()
        self.on_change()

    # ------------------------------------------------ secciones personalizadas
    def _after_custom(self, label):
        self.store_ui()
        self.prj.section.label = label
        self.load_ui()
        self.on_change()

    def new_section(self):
        d = SectionDialog(self.us, self)
        if d.exec() and d.result_shape is not None:
            CATALOG.add_custom(d.result_shape)
            self._after_custom(d.result_shape.label)

    def edit_section(self):
        s = self.prj.section.shape()
        if s.source == "AISC":
            QMessageBox.information(self, "Seccion", "Los perfiles AISC no se editan. "
                                    "Use 'Nueva seccion' para crear una a partir de sus "
                                    "dimensiones.")
            d = SectionDialog(self.us, self, s)
            d.ed_name.setText(s.label + "-MOD")
        else:
            d = SectionDialog(self.us, self, s)
        if d.exec() and d.result_shape is not None:
            CATALOG.add_custom(d.result_shape)
            self._after_custom(d.result_shape.label)

    def del_section(self):
        s = self.prj.section.shape()
        if s.source == "AISC":
            QMessageBox.information(self, "Seccion", "Solo se pueden eliminar secciones "
                                    "personalizadas o importadas.")
            return
        if QMessageBox.question(self, "Seccion", f"¿Eliminar {s.label}?") == QMessageBox.Yes:
            CATALOG.remove(s.label)
            self._after_custom("W14X90")

    # ------------------------------------------------------------- materiales
    def materials_dialog(self):
        d = MaterialsDialog(self.us, self)
        if d.exec():
            self.store_ui()
            self._refresh_material_combos()
            self.load_ui()
            self.on_change()

    def _refresh_material_combos(self):
        lists = {"section.steel": [x.name for x in M.SHAPE_STEELS] +
                 [x.name for x in M.PLATE_STEELS if x.note == "usuario"],
                 "plate.steel": [x.name for x in M.PLATE_STEELS],
                 "lug.steel": [x.name for x in M.PLATE_STEELS],
                 "stiff.steel": [x.name for x in M.PLATE_STEELS],
                 "bolts.steel": [x.name for x in M.ANCHOR_STEELS],
                 "conc.material": ["(personalizado)"] + [c.name for c in M.CONCRETES]}
        for f in self.forms:
            for fld in f.fields:
                if fld[0] in lists:
                    w = fld[1]
                    cur = w.currentText()
                    w.blockSignals(True)
                    w.clear()
                    w.addItems(list(dict.fromkeys(lists[fld[0]])))
                    w.setCurrentText(cur)
                    w.blockSignals(False)

    # ------------------------------------------------------------ conexiones
    def _refresh_list(self):
        self.lst_con.blockSignals(True)
        self.lst_con.clear()
        for p in self.book:
            self.lst_con.addItem(f"{p.element or '(sin nombre)'}   —   {p.section.describe()}")
        self.lst_con.setCurrentRow(self.cur)
        self.lst_con.blockSignals(False)

    def _switch(self, i):
        self.cur = max(0, min(i, len(self.book) - 1))
        self.prj = self.book[self.cur]
        self.res3d = None
        c = self.cache3d.get(id(self.prj))
        self.post3d, self._sig3d = (c[1], c[0]) if c else (None, None)
        rc = self.rep3d_cache.get(id(self.prj))
        self.rep3d = rc[1] if rc else None
        self.fill_3d_tables()
        self.load_ui()
        self._refresh_list()
        self.recalc(fea=True)

    def on_select_connection(self, i):
        if i < 0 or i == self.cur or i >= len(self.book):
            return
        self.store_ui()
        self._switch(i)

    def con_new(self):
        self.store_ui()
        p = Project()
        p.name = self.prj.name
        p.date = datetime.date.today().isoformat()
        p.u_len, p.u_force, p.u_stress, p.u_moment = (self.prj.u_len, self.prj.u_force,
                                                      self.prj.u_stress, self.prj.u_moment)
        p.element = f"PB-{len(self.book) + 1:02d}"
        self.book.append(p)
        self._switch(len(self.book) - 1)

    def con_dup(self):
        import copy
        self.store_ui()
        p = copy.deepcopy(self.prj)
        p.element = (self.prj.element or "PB") + "-copia"
        self.book.insert(self.cur + 1, p)
        self._switch(self.cur + 1)

    def con_rename(self):
        self.store_ui()
        t, ok = QInputDialog.getText(self, "Renombrar conexion", "Nombre / elemento:",
                                     text=self.prj.element)
        if ok and t.strip():
            self.prj.element = t.strip()
            self.load_ui()
            self._refresh_list()

    def con_del(self):
        if len(self.book) <= 1:
            QMessageBox.information(self, "Conexiones", "El proyecto debe tener al menos "
                                    "una conexion.")
            return
        if QMessageBox.question(self, "Conexiones",
                                f"¿Eliminar la conexion {self.prj.element}?") != QMessageBox.Yes:
            return
        self.cache3d.pop(id(self.prj), None)
        del self.book[self.cur]
        self._switch(min(self.cur, len(self.book) - 1))

    def export_all(self, fmt):
        self.store_ui()
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para los reportes")
        if not folder:
            return
        dlg = QProgressDialog("Generando reportes...", "Cancelar", 0, len(self.book), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        hechos = []
        for i, p in enumerate(self.book):
            if dlg.wasCanceled():
                break
            dlg.setLabelText(f"{p.element}  ({i + 1} de {len(self.book)})")
            QApplication.processEvents()
            try:
                r = solve(p, with_fea=True)
                c = self.cache3d.get(id(p))
                r.post3d = c[1] if c and c[0] == p.to_json() else None
                rc = self.rep3d_cache.get(id(p))
                r.rep3d = rc[1] if rc and rc[0] == p.to_json() else None
                tmp = tempfile.mkdtemp(prefix="pbase_")
                figs = report.save_figures(p, r, tmp)
                safe = "".join(ch if ch.isalnum() or ch in "-_ ." else "_"
                               for ch in (p.element or f"conexion_{i+1}"))
                fn = str(Path(folder) / f"{safe}.{fmt}")
                (report.export_pdf if fmt == "pdf" else report.export_docx)(
                    p, r, fn, figs, self.chk_mem.isChecked())
                hechos.append(Path(fn).name)
            except Exception as e:
                hechos.append(f"{p.element}: ERROR {e}")
            dlg.setValue(i + 1)
        dlg.close()
        QMessageBox.information(self, "Reportes", f"Generados en {folder}:\n\n" +
                                "\n".join(hechos))

    def on_change(self):
        if self._loading:
            return
        before = (self.prj.u_len, self.prj.u_force, self.prj.u_stress,
                  self.prj.u_moment)
        # los campos numericos se leen con las unidades ANTERIORES
        self.store_ui()
        changes = self.prj.normalize()
        if changes:
            self.load_ui()                  # refleja el cambio en la casilla
            QMessageBox.information(self, "Columna inclinada", "\n".join(changes))
        after = (self.prj.u_len, self.prj.u_force, self.prj.u_stress,
                 self.prj.u_moment)
        if before != after:
            self.load_ui()          # reescribe todo en las unidades nuevas
            self.fill_table()
        self._update_labels()
        self.timer.start(350)

    def _update_labels(self):
        tilted = self.prj.loads.tilted
        self.chk_stiff.setEnabled(not tilted)
        self.chk_stiff.setToolTip("No disponible con la columna inclinada." if tilted else "")
        self.lbl_stiff_lock.setVisible(tilted)
        s = self.prj.section.shape()
        e = self.prj.section.eff()
        uu = self.us
        dims = (f"OD={uu.q('L', s.d)}  t={uu.q('L', s.tw)}" if s.is_round else
                f"d={uu.q('L', s.d)}  bf={uu.q('L', s.bf)}  tw={uu.q('L', s.tw)}"
                + (f"  tf={uu.q('L', s.tf)}" if s.tf else ""))
        self.lbl_shape.setText(
            f"{KIND_LABELS.get(s.kind, s.kind)} · {dims}<br>"
            f"{'Seccion doble: ' if self.prj.section.is_double else ''}"
            f"A={uu.q('A', e.A)}  Ix={e.Ix:.4g}  Iy={e.Iy:.4g} in⁴  "
            f"Sx={e.Sx:.4g}  Sy={e.Sy:.4g} in³   [{s.source}]"
            + ("<br><i>Rigidizadores no disponibles: la soldadura se verifica como "
               "grupo en todo el contorno.</i>" if self.prj.section.generic else ""))
        it = self.lst_con.item(self.cur) if hasattr(self, "lst_con") else None
        if it is not None:
            it.setText(f"{self.prj.element or '(sin nombre)'}   —   {self.prj.section.describe()}")
        g = self.prj.bolts.geom()
        u = self.us
        self.lbl_bolt.setText(f"db={g.db:.4g} in ({g.db*25.4:.1f} mm)  Ab={u.q('A', g.Ab)}  "
                              f"Ase={u.q('A', g.Ase)}  agujero {u.q('L', g.dh)}  "
                              f"Abrg={u.q('A', g.Abrg)}")
        self.lbl_count.setText(f"{self.prj.bolts.n_total} pernos")
        L = self.prj.eloads
        self.lbl_tilt.setText(
            (f"Pu={L.Pu:.1f}  Vux={L.Vux:.1f}  Vuy={L.Vuy:.1f} kip;  "
             f"Mux={L.Mux:.0f}  Muy={L.Muy:.0f} kip·in") if self.prj.loads.tilted
            else "(columna perpendicular: sin cambios)")
        self.lbl_si.setText(f"Pu={L.Pu*KIP_TO_KN:.1f} kN   Mux={L.Mux*KIPIN_TO_KNM:.1f} kN·m   "
                            f"Muy={L.Muy*KIPIN_TO_KNM:.1f} kN·m   Vu={L.Vu*KIP_TO_KN:.1f} kN"
                            f"      |      Pu={L.Pu:.1f} kip   Mux={L.Mux:.0f} kip·in")

    # =================================================================== calculo
    def recalc(self, fea=False):
        if hasattr(self, "timer"):
            self.timer.stop()                   # evita que un recalculo pendiente pise este
        self.store_ui()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            prev = self.res.fea if (self.res is not None and not fea) else None
            self.res = solve(self.prj, with_fea=fea)
            if not fea and prev is not None:
                self.res.fea = None                 # resultados FEA previos quedan obsoletos
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error de calculo",
                                 f"{e}\n\n{traceback.format_exc()[-1500:]}")
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self.draw_all()
        self.fill_table()
        if self.res.rec is not None:
            self.txt_mem.setHtml(self.res.rec.to_html())
        self.statusBar().showMessage(
            "Calculo completo" + (" con FEA" if fea and self.prj.fea.enabled else
                                  " (FEA pendiente: F5)"), 5000)

    def draw_all(self):
        try:
            draw.plan_view(self.cv_plan.ax, self.prj)
            self.cv_plan.cv.draw_idle()
            draw.elevation_view(self.cv_elev.ax, self.prj)
            self.cv_elev.cv.draw_idle()
            draw.stiffener_detail(self.cv_stif.ax, self.prj)
            self.cv_stif.cv.draw_idle()
        except Exception as e:
            self.statusBar().showMessage(f"Error de dibujo: {e}", 8000)
        self.draw_fea()
        if self.cb_f3.currentIndex() == 0 or self.res3d is None:
            self.draw_3d()                      # la geometria 3D siempre esta al dia

    def draw_fea(self):
        self.cv_fea.reset()
        key = FIELDS_FEA[self.cb_field.currentIndex()][1]
        fr = self.res.fea if self.res else None
        cs = draw.fea_view(self.cv_fea.ax, self.prj, fr, key)
        if cs is not None:
            self.cv_fea.fig.colorbar(cs, ax=self.cv_fea.ax, shrink=0.85)
        self.cv_fea.cv.draw_idle()
        if fr is not None and fr.ok:
            u = self.us
            self.lbl_fea.setText(
                f"<b>w max</b> = {u.q('L', fr.w_max)}  ·  <b>p max</b> = {u.q('S', fr.press_max)}  ·  "
                f"<b>von Mises max</b> = {u.q('S', fr.vm_max)}  ·  "
                f"<b>T max perno</b> = {u.q('F', max(fr.bolt_T) if fr.bolt_T else 0)}  ·  "
                f"<b>soldadura</b> ≈ {u.q('LF', fr.weld_line_max)}<br>{fr.msg}")
            self.fill_bolts()
        elif fr is not None:
            self.lbl_fea.setText(f"<span style='color:#9c0006'>{fr.msg}</span>")
        else:
            self.lbl_fea.setText("FEA no ejecutado para el estado actual.  Presione F5.")

    def draw_3d(self):
        try:                                    # conserva la orientacion de la camara
            elev, azim = self.cv_3d.ax.elev, self.cv_3d.ax.azim
        except Exception:
            elev = azim = None
        k = self.cb_f3.currentIndex()
        self.cv_3d.reset(cbar=not (k == 0 or self.res3d is None or not self.res3d.ok))
        if k == 0 or self.res3d is None or not self.res3d.ok:
            try:
                view3d.plot_geometry(self.cv_3d.ax, self.prj)
            except Exception as e:
                # no deja la vista en blanco: muestra el error en el propio lienzo
                self.cv_3d.reset()
                self.cv_3d.ax.set_axis_off()
                self.cv_3d.ax.text2D(0.5, 0.5, "No se pudo dibujar la geometria 3D:\n"
                                     f"{type(e).__name__}: {str(e)[:160]}",
                                     ha="center", va="center", color="#9c0006",
                                     transform=self.cv_3d.ax.transAxes, fontsize=9)
                self.statusBar().showMessage(f"Error de dibujo 3D: {e}", 8000)
                traceback.print_exc()
            if elev is not None:
                self.cv_3d.ax.view_init(elev=elev, azim=azim)
            view3d.fit_to_axes(self.cv_3d.ax)
            self.cv_3d.cv.draw_idle()
            return
        fld = ["vm", "u", "uz"][k - 1]
        m = view3d.plot3d(self.cv_3d.ax, self.res3d, self.prj, fld,
                          float(self.sp_sc.value()))
        if m is not None:
            cax = self.cv_3d.fig.add_axes([0.90, 0.18, 0.018, 0.64])
            self.cv_3d.fig.colorbar(m, cax=cax)
        if elev is not None:
            self.cv_3d.ax.view_init(elev=elev, azim=azim)
        view3d.fit_to_axes(self.cv_3d.ax)
        self.cv_3d.cv.draw_idle()

    def run_3d(self):
        self.store_ui()
        if self.worker is not None and self.worker.isRunning():
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = (Path(self.path).parent if self.path else
                Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PlacaBasePro")
        folder = str(base / f"{self.prj.element or 'placa'}_3D_{stamp}")
        self._sig3d = self.prj.to_json()
        self.dlg3d = QProgressDialog("Preparando el modelo 3D ...", "Cancelar",
                                     0, 0, self)
        self.dlg3d.setWindowTitle("Analisis 3D")
        self.dlg3d.setWindowModality(Qt.WindowModal)
        self.dlg3d.setMinimumWidth(460)
        self.dlg3d.setCancelButton(None)
        self.dlg3d.show()
        self.btn3d.setEnabled(False)
        self.worker = Worker3D(self.prj, folder)
        self.worker.progress.connect(self.dlg3d.setLabelText)
        self.worker.done.connect(self._on_3d)
        self.worker.start()

    def _on_3d(self, res, msg):
        self.dlg3d.close()
        self.btn3d.setEnabled(True)
        if res is None:
            self.lbl_3d.setText(f"<span style='color:#9c0006'>{msg[:600]}</span>")
            QMessageBox.warning(self, "Analisis 3D", msg[-2500:])
            return
        self.res3d = res
        self.post3d = getattr(res, "post", None)
        if self.post3d is not None:
            self.cache3d[id(self.prj)] = (self._sig3d, self.post3d)
        self.rep3d = self._make_rep3d(res)
        self.rep3d_cache[id(self.prj)] = (self._sig3d, self.rep3d)
        self.fill_3d_tables()
        u = self.us
        self.lbl_3d.setText(
            f"<b>{res.n_nodes:,} nodos</b> y {res.n_elems:,} tetraedros.  "
            f"<b>|U| max</b> = {u.q('L', res.umax)}  ·  "
            f"<b>von Mises max</b> = {u.q('S', res.vmmax)}  ·  "
            + (f"equilibrio: {self.post3d.msg}<br>" if self.post3d else "<br>") +
            f"Archivos en: {getattr(res, 'folder', '')}<br>"
            "Los picos de von Mises en aristas vivas (borde de agujero, encuentro "
            "perfil-placa) son singularidades de malla: dependen del tamano de "
            "elemento y no deben leerse como esfuerzo real.")
        self.cb_f3.blockSignals(True)
        self.cb_f3.setCurrentIndex(1)           # muestra von Mises al terminar el analisis
        self.cb_f3.blockSignals(False)
        self.draw_3d()
        self.tabs_out.setCurrentIndex(4)

    def _make_rep3d(self, res):
        """Imagenes de von Mises y deformada (con etiqueta del maximo) para la memoria."""
        try:
            folder = Path(getattr(res, "folder", "") or tempfile.mkdtemp())
            folder.mkdir(parents=True, exist_ok=True)
            xs = [p for p in res.nodes.values()]
            dim = max(max(q[i] for q in xs) - min(q[i] for q in xs) for i in range(3))
            sc = 0.05 * dim / res.umax if res.umax > 0 else 0.0
            sc = 0.0 if sc <= 0 else max(1.0, float(f"{min(sc, 5000.0):.1g}"))
            vm = view3d.render_result_png(res, self.prj, "vm", str(folder / "reporte_vonmises.png"))
            de = view3d.render_result_png(res, self.prj, "u", str(folder / "reporte_deformada.png"), sc)
            if not vm and not de:
                return None
            nvm = max(res.vm, key=res.vm.get) if res.vm else None
            return dict(vm=vm, u=de, scale=sc, n_nodes=res.n_nodes, n_elems=res.n_elems,
                        umax=res.umax, vmmax=res.vmmax, vm_node=nvm)
        except Exception:
            traceback.print_exc()
            return None

    def fill_3d_tables(self):
        from .weld3d import summary_rows
        import math as _m
        post = getattr(self, "post3d", None)
        for tb in (self.tbl_w3, self.tbl_b3):
            tb.setRowCount(0)
        if post is None:
            return
        welds, bolts = summary_rows(self.prj, post)
        red, green = QColor("#ffc7ce"), QColor("#c6efce")
        for tb, rows, dc_cols in ((self.tbl_w3, welds, (5, 6)), (self.tbl_b3, bolts, ())):
            tb.setColumnCount(len(rows[0]))
            tb.setHorizontalHeaderLabels(rows[0])
            if tb is self.tbl_w3:
                tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            for r in rows[1:]:
                i = tb.rowCount(); tb.insertRow(i)
                for j, v in enumerate(r):
                    it = QTableWidgetItem(v)
                    if j in dc_cols:
                        try:
                            ok = float(v) <= 1.0
                        except ValueError:
                            ok = False
                        it.setBackground(green if ok else red)
                    tb.setItem(i, j, it)
        self.tbl_w3.setToolTip(
            "D/C pico: el punto mas cargado del cordon (concentracion elastica, por "
            "ejemplo donde el alma llega al ala). D/C media: la fuerza de toda la pared "
            "repartida en su longitud, que es lo que supone el calculo DG1. La "
            "compresion se transmite por contacto; el cordon se verifica a traccion y "
            "cortante.")

    def fill_bolts(self):
        """Tabla resumen de tensiones perno por perno (resultado del FEA)."""
        fr = self.res.fea if self.res else None
        self.tbl_bolts.setRowCount(0)
        if fr is None or not fr.ok:
            return
        u = self.us
        self.tbl_bolts.setHorizontalHeaderLabels(
            ["Perno", f"x ({u.L})", f"y ({u.L})", f"T ({u.F})",
             f"σt ({u.S})", "D/C"])
        red, green = QColor("#ffc7ce"), QColor("#c6efce")
        order = sorted(range(len(fr.bolt_T)), key=lambda i: -fr.bolt_T[i])
        for i in order:
            r = self.tbl_bolts.rowCount()
            self.tbl_bolts.insertRow(r)
            x, y = fr.bolt_xy[i]
            vals = [str(i + 1), u.fmt("L", x), u.fmt("L", y), u.fmt("F", fr.bolt_T[i]),
                    u.fmt("S", fr.bolt_sig[i]), f"{fr.bolt_ratio[i]:.3f}"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 5:
                    it.setBackground(green if fr.bolt_ratio[i] <= 1 else red)
                    fo = it.font(); fo.setBold(True); it.setFont(fo)
                self.tbl_bolts.setItem(r, j, it)

    def fill_table(self):
        r = self.res
        self.tbl.setRowCount(0)
        red, green, grey = QColor("#ffc7ce"), QColor("#c6efce"), QColor("#eeeeee")
        for ch in r.checks:
            i = self.tbl.rowCount()
            self.tbl.insertRow(i)
            dv, cv, ul = report.ck_vals(self.us, ch)
            vals = [ch.title, f"{dv:,.3f}", f"{cv:,.3f}", ul,
                    "—" if ch.skip else f"{ch.ratio:.3f}",
                    ch.ref + ("  —  " + ch.note if ch.note else "")]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j in (1, 2, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 4:
                    it.setBackground(grey if ch.skip else (green if ch.ok else red))
                    f = it.font(); f.setBold(True); it.setFont(f)
                it.setToolTip(v)
                self.tbl.setItem(i, j, it)

        br = r.br
        gov = r.governing
        u = self.us
        ee = "∞" if br.e == float("inf") else u.q("L", br.e)
        html = [f"<b>{br.case}</b> — e = {ee}, ecrit = {u.q('L', br.ecrit)}, "
                f"Y = {u.q('L', br.Y)}, fp = {u.fmt('S', br.fp)} / {u.q('S', br.fp_max)}, "
                f"Tu = {u.q('F', br.Tu)} en {br.n_t} pernos (f = {u.q('L', br.f_arm)}).  "
                f"t requerido = <b>{u.q('L', r.treq)}</b> vs tp = {u.q('L', self.prj.plate.tp)}."]
        if gov:
            html.append(f"Gobierna: <b>{gov.title}</b>  (D/C = {gov.ratio:.3f})")
        for w in r.warnings:
            col = "#9c0006" if w.startswith("**") else "#7f6000"
            html.append(f"<span style='color:{col}'>• {w}</span>")
        self.txt_info.setHtml("<br>".join(html))

        ok = r.ok
        self.lbl_verdict.setText(f"  {'CUMPLE' if ok else 'NO CUMPLE'}   D/C max = {r.max_ratio:.3f}  ")
        self.lbl_verdict.setStyleSheet(
            f"background:{'#c6efce' if ok else '#ffc7ce'}; color:{'#006100' if ok else '#9c0006'};"
            "border-radius:4px; padding:2px 8px;")

    # ================================================================= archivo
    def new(self):
        if QMessageBox.question(self, "Nuevo", "¿Descartar el proyecto actual?") != QMessageBox.Yes:
            return
        self.prj = Project()
        self.prj.date = datetime.date.today().isoformat()
        self.book = [self.prj]
        self.cur = 0
        self.cache3d = {}; self.rep3d_cache = {}; self.rep3d = None
        self.path = None
        self._switch(0)

    def open(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", "",
                                            "Placa base (*.pbase *.json)")
        if not fn:
            return
        try:
            self.book = load_book(fn)
            self.cache3d = {}; self.rep3d_cache = {}; self.rep3d = None
            self.path = fn
            self._refresh_material_combos()
            self._switch(0)
            self.setWindowTitle(f"PlacaBasePro {__version__} — {Path(fn).name}")
        except Exception as e:
            QMessageBox.critical(self, "Abrir", f"No se pudo abrir el archivo:\n{e}")

    def save(self):
        if not self.path:
            return self.save_as()
        self.store_ui()
        save_book(self.path, self.book)
        self.statusBar().showMessage(f"Guardado: {self.path}", 4000)

    def save_as(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto",
                                            f"{self.prj.element or 'placa'}.pbase",
                                            "Placa base (*.pbase)")
        if fn:
            self.path = fn
            self.save()
            self.setWindowTitle(f"PlacaBasePro {__version__} — {Path(fn).name}")

    def import_aisc(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "Importar AISC Shapes Database v14.1", "",
            "AISC shapes (*.xlsx *.xlsm *.csv)")
        if not fn:
            return
        try:
            n, msg = CATALOG.import_aisc(fn)
            s = self.prj.section.shape()
            self._fill_shapes(s.kind, s.label)
            QMessageBox.information(self, "Importar AISC", msg)
        except Exception as e:
            QMessageBox.critical(self, "Importar AISC", f"Error:\n{e}")

    # ================================================================ exportar
    def _ensure_results(self):
        if self.res is None or (self.prj.fea.enabled and self.res.fea is None):
            self.recalc(fea=True)

    def _attach_3d(self):
        """El 3D entra al reporte solo si se corrio con el proyecto tal como esta."""
        ok = (getattr(self, "post3d", None) is not None and
              getattr(self, "_sig3d", None) == self.prj.to_json())
        if self.res is not None:
            self.res.post3d = self.post3d if ok else None
            rc = self.rep3d_cache.get(id(self.prj))
            self.res.rep3d = rc[1] if (rc and rc[0] == self.prj.to_json()) else None

    def export_pdf(self):
        self._ensure_results()
        self._attach_3d()
        fn, _ = QFileDialog.getSaveFileName(self, "Memoria de calculo en PDF",
                                            f"Memoria_{self.prj.element}.pdf", "PDF (*.pdf)")
        if not fn:
            return
        try:
            tmp = tempfile.mkdtemp(prefix="pbase_")
            figs = report.save_figures(self.prj, self.res, tmp)
            report.export_pdf(self.prj, self.res, fn, figs, self.chk_mem.isChecked())
            self._done(fn)
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"{e}\n\n{traceback.format_exc()[-1200:]}")

    def export_3d(self):
        self.store_ui()
        fn, _ = QFileDialog.getSaveFileName(
            self, "Modelo solido 3D (Gmsh)",
            f"{self.prj.element or 'placa'}_3d.geo", "Gmsh (*.geo)")
        if not fn:
            return
        try:
            geo, drv = mesh3d.export_3d(self.prj, fn, self.prj.fea.mesh3d)
        except Exception as e:
            QMessageBox.critical(self, "Modelo 3D", f"{e}")
            return
        if QMessageBox.question(
                self, "Modelo 3D",
                f"Generados:\n\n{geo}\n{drv}\n\n"
                "¿Mallar ahora con Gmsh?  (puede tardar varios minutos)"
                ) != QMessageBox.Yes:
            self._done(geo)
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        ok, out, inp = mesh3d.run_gmsh(geo)
        QApplication.restoreOverrideCursor()
        if ok:
            QMessageBox.information(
                self, "Modelo 3D",
                f"Malla generada:\n{inp}\n\n"
                f"Ejecute ahora, en esa carpeta:\n    python correr_3d.py\n\n"
                "arma el .inp de CalculiX con apoyos, resortes de perno y cargas, "
                "y lo resuelve.")
        else:
            QMessageBox.warning(self, "Gmsh", out[-2500:])

    def export_docx(self):
        self._ensure_results()
        self._attach_3d()
        fn, _ = QFileDialog.getSaveFileName(self, "Memoria de calculo",
                                            f"Memoria_{self.prj.element}.docx", "Word (*.docx)")
        if not fn:
            return
        try:
            tmp = tempfile.mkdtemp(prefix="pbase_")
            figs = report.save_figures(self.prj, self.res, tmp)
            report.export_docx(self.prj, self.res, fn, figs, self.chk_mem.isChecked())
            self._done(fn)
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"{e}\n\n{traceback.format_exc()[-1200:]}")

    def export_png(self):
        self._ensure_results()
        d = QFileDialog.getExistingDirectory(self, "Carpeta de destino")
        if d:
            paths = report.save_figures(self.prj, self.res, d)
            self._done(f"{len(paths)} imagenes en {d}")

    def export_ccx(self):
        self.store_ui()
        fn, _ = QFileDialog.getSaveFileName(self, "Modelo CalculiX",
                                            f"{self.prj.element or 'placa'}.inp", "CalculiX (*.inp)")
        if fn:
            ccx.export_inp(self.prj, fn)
            self._done(fn)

    def run_ccx(self):
        self.store_ui()
        fn, _ = QFileDialog.getSaveFileName(self, "Modelo CalculiX",
                                            f"{self.prj.element or 'placa'}.inp", "CalculiX (*.inp)")
        if not fn:
            return
        ccx.export_inp(self.prj, fn)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        ok, out = ccx.run_ccx(fn, mesh3d.ccx_exe(self.prj.fea.ccx_path))
        QApplication.restoreOverrideCursor()
        if ok:
            u, s = ccx.read_frd_max(str(Path(fn).with_suffix(".frd")))
            QMessageBox.information(
                self, "CalculiX",
                f"Analisis terminado.\n\n|U| max = {u:.4f} in\nvon Mises max = {s:.2f} ksi\n\n"
                f"Abra el archivo .frd en PrePoMax o CGX para el post-proceso completo.")
        else:
            QMessageBox.warning(self, "CalculiX", out[-2500:])

    def _done(self, what):
        self.statusBar().showMessage(f"Exportado: {what}", 6000)
        QMessageBox.information(self, "Exportar", f"Archivo generado:\n{what}")

    def about(self):
        QMessageBox.about(
            self, "Acerca de PlacaBasePro",
            f"<b>PlacaBasePro {__version__}</b><br>"
            "Diseno y verificacion de placas base para perfiles W, HSS y Pipe.<br><br>"
            "AISC 360-22 · AISC Design Guide 1 (2ª Ed.) · ACI 318-19 Cap. 17<br>"
            "FEA: placa MITC4 sobre fundacion elastica unilateral con los agujeros "
            "de perno mallados, y modelo solido 3D via Gmsh + CalculiX.<br><br>"
            "Los resultados deben ser revisados por un ingeniero responsable.")

    def closeEvent(self, ev):
        ev.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PlacaBasePro")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    return app.exec()
