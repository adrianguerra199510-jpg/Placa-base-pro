# -*- coding: utf-8 -*-
"""Identidad visual de PlacaBasePro: ruta de los recursos graficos y colores de marca."""
from __future__ import annotations
import os
import sys
from pathlib import Path

DARK = "#12171E"          # negro azulado del logo
ORANGE = "#E85D0C"        # naranja del logo
ORANGE_DK = "#C44A06"
GREY = "#F3F4F1"          # fondo claro del logo
SLATE = "#4A5563"         # gris del lema


def asset(name: str) -> str:
    """Ruta de un recurso de placabase/data (tambien dentro del ejecutable de PyInstaller)."""
    for base in (Path(__file__).parent / "data", Path(getattr(sys, "_MEIPASS", ".")) / "placabase" / "data"):
        p = base / name
        if p.exists():
            return str(p)
    return str(Path(__file__).parent / "data" / name)


LOGO = lambda: asset("logo.png")          # logo horizontal con lema (fondo transparente)
ICON = lambda: asset("icon.png")          # icono cuadrado 256 px
ICO = lambda: asset("placabasepro.ico")   # icono de Windows (.ico multi-tamano)

STYLE = f"""
QToolBar {{ background: {GREY}; border-bottom: 2px solid {ORANGE}; spacing: 4px; padding: 2px; }}
QTabBar::tab {{ padding: 5px 12px; }}
QTabBar::tab:selected {{ border-bottom: 3px solid {ORANGE}; font-weight: bold; color: {DARK}; }}
QGroupBox {{ font-weight: bold; color: {DARK}; }}
QHeaderView::section {{ background: {GREY}; color: {DARK}; border: 0; border-bottom: 1px solid #c9ccc6; padding: 3px; }}
QStatusBar {{ background: {DARK}; color: #e8eaed; }}
QPushButton:hover {{ border-color: {ORANGE}; }}
"""
