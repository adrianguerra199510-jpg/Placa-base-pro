# -*- coding: utf-8 -*-
"""Widgets auxiliares para construir formularios enlazados al modelo."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QFormLayout, QDoubleSpinBox, QSpinBox,
                               QComboBox, QCheckBox, QLineEdit, QLabel, QGroupBox,
                               QVBoxLayout, QScrollArea, QFrame)
from PySide6.QtCore import Qt, Signal, QEvent, QObject

from .units import UnitSet


def _get(obj, path):
    for p in path.split("."):
        obj = getattr(obj, p)
    return obj


def _set(obj, path, val):
    parts = path.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], val)


class Form(QWidget):
    """Formulario cuyos campos leen/escriben rutas del Project ('plate.tp')."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(4, 4, 4, 4)
        self.fields = []          # (path, widget, tipo, magnitud)
        self.us = UnitSet()       # la ventana principal la reemplaza
        self._lay = None
        self._help = {}           # widget -> descripcion
        self.info = None          # panel de ayuda al pie del formulario
        self.group("")

    def _emit(self, *_):
        self.changed.emit()

    # -------------------------------------------------------------- ayuda
    def _register_help(self, w, label, txt):
        if not txt:
            return
        full = f"<b>{label}</b><br>{txt}" if label else txt
        w.setToolTip(full)
        self._help[w] = full
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.FocusIn, QEvent.Enter, QEvent.HoverEnter):
            txt = self._help.get(obj)
            if txt and self.info is not None:
                self.info.setText(txt)
        return False

    def help_panel(self):
        """Panel fijo al pie que describe el campo sobre el que esta el cursor."""
        fr = QFrame()
        fr.setFrameShape(QFrame.StyledPanel)
        fr.setStyleSheet("QFrame{background:#f4f7fb;border:1px solid #c8d6e8;}")
        lay = QVBoxLayout(fr)
        lay.setContentsMargins(8, 6, 8, 6)
        self.info = QLabel("Pase el cursor sobre cualquier campo para ver su "
                           "descripcion.")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.RichText)
        self.info.setStyleSheet("color:#24405f; font-size:8.5pt;")
        self.info.setMinimumHeight(52)
        self.info.setAlignment(Qt.AlignTop)
        lay.addWidget(self.info)
        self.outer.addWidget(fr)
        return fr

    # ----------------------------------------------------------- estructura
    def group(self, title):
        box = QGroupBox(title) if title else QWidget()
        lay = QFormLayout(box)
        lay.setLabelAlignment(Qt.AlignRight)
        lay.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.outer.addWidget(box)
        self._lay = lay
        return box

    def note(self, text):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setStyleSheet("color:#595959; font-size:8pt;")
        self._lay.addRow(lb)
        return lb

    def finish(self, with_help=True):
        self.outer.addStretch(1)
        if with_help and self._help:
            self.help_panel()

    # --------------------------------------------------------------- campos
    def num(self, label, path, lo=0.0, hi=1e6, step=0.125, dec=3, suffix="",
            uk=None, help=""):
        """uk = magnitud ('L','F','M','S','A','K'); si se indica, el campo se
        muestra y se lee en las unidades que haya elegido el usuario."""
        w = QDoubleSpinBox()
        w.setRange(-1e12 if lo < 0 else 0.0, 1e12)
        w._lo, w._hi = lo, hi
        w.setDecimals(dec); w.setSingleStep(step)
        w.setKeyboardTracking(False)
        if suffix and not uk:
            w.setSuffix(" " + suffix)
        w.valueChanged.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "f", uk))
        return w

    def int_(self, label, path, lo=0, hi=999, help=""):
        w = QSpinBox(); w.setRange(lo, hi); w.setKeyboardTracking(False)
        w.valueChanged.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "i", None))
        return w

    def combo(self, label, path, items, editable=False, help=""):
        w = QComboBox(); w.addItems(list(items)); w.setEditable(editable)
        w.setMaxVisibleItems(25)
        w.currentTextChanged.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "c", None))
        return w

    def check(self, label, path, help=""):
        w = QCheckBox(label)
        w.toggled.connect(self._emit)
        self._lay.addRow("", w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "b", None))
        return w

    def text(self, label, path, help=""):
        w = QLineEdit()
        w.editingFinished.connect(self._emit)
        self._lay.addRow(label, w)
        self._register_help(w, label, help)
        self.fields.append((path, w, "t", None))
        return w

    # ----------------------------------------------------------- sincronizar
    def load(self, prj):
        for path, w, k, uk in self.fields:
            w.blockSignals(True)
            try:
                v = _get(prj, path)
                if k == "f":
                    if uk:
                        w.setSuffix(" " + self.us.label(uk))
                        w.setDecimals(self.us.dec(uk))
                        w.setSingleStep(self.us.step(uk))
                        lo = self.us.out(uk, w._lo)
                        hi = self.us.out(uk, w._hi)
                        w.setRange(min(lo, hi), max(lo, hi))
                        w.setValue(self.us.out(uk, float(v)))
                    else:
                        w.setRange(w._lo, w._hi)
                        w.setValue(float(v))
                elif k == "i":
                    w.setValue(int(v))
                elif k == "c":
                    i = w.findText(str(v))
                    if i < 0 and w.isEditable():
                        w.setEditText(str(v))
                    elif i >= 0:
                        w.setCurrentIndex(i)
                elif k == "b":
                    w.setChecked(bool(v))
                elif k == "t":
                    w.setText(str(v))
            finally:
                w.blockSignals(False)

    def store(self, prj):
        for path, w, k, uk in self.fields:
            if k == "f":
                _set(prj, path, self.us.inn(uk, float(w.value())) if uk
                     else float(w.value()))
            elif k == "i":
                _set(prj, path, int(w.value()))
            elif k == "c":
                _set(prj, path, w.currentText())
            elif k == "b":
                _set(prj, path, bool(w.isChecked()))
            elif k == "t":
                _set(prj, path, w.text())


def scroll(widget):
    sa = QScrollArea()
    sa.setWidget(widget)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    return sa
