"""ClustroView platform sidebar: 12 module entries grouped into sections.



The sidebar shows ALL ClustroView platform modules, but only "Clustering"

is currently active. Other modules are fully implemented.

"""

from __future__ import annotations



from dataclasses import dataclass

from typing import Callable, Optional



from PySide6.QtCore import Qt, Signal

from PySide6.QtGui import QColor, QPainter, QPixmap

from PySide6.QtWidgets import (

    QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,

)





# ====================================================================

#  Module definition

# ====================================================================

@dataclass(frozen=True)

class ModuleEntry:

    key: str

    label: str

    icon: str        # Unicode glyph used as the icon

    active: bool = False





# Group: Overview (single entry)

_OVERVIEW = [ModuleEntry("overview", "Overview", "\u2302")]



# Group: Data

_DATA = [

    ModuleEntry("upload", "Upload Data", "\u21EA"),

    ModuleEntry("datasets", "Datasets", "\u25A4"),

    ModuleEntry("preprocessing", "Preprocessing", "\u2699"),

]



# Group: Analysis

_ANALYSIS = [

    ModuleEntry("clustering", "Clustering", "\u25C8", active=True),

    ModuleEntry("marker_genes", "Marker Genes", "\u2697"),

    ModuleEntry("dimensionality", "Dimensionality", "\u223F"),

    ModuleEntry("statistics", "Statistics", "\u2261"),

]



# Group: Visualization

_VISUALIZATION = [

    ModuleEntry("plots", "Plots", "\u2197"),

    ModuleEntry("heatmaps", "Heatmaps", "\u25A6"),

    ModuleEntry("trajectory", "Trajectory", "\u2933"),

    ModuleEntry("comparison", "Comparison", "\u2295"),

]



_NAVIGATION = [
    ModuleEntry("homepage", "Homepage", "\u2302"),
]

_GROUPS = [

    ("", _OVERVIEW, False),  # No section label for overview

    ("DATA", _DATA, True),

    ("ANALYSIS", _ANALYSIS, True),

    ("VISUALIZATION", _VISUALIZATION, True),

    ("", _NAVIGATION, False),

]



_ALL_KEYS = (

    [m.key for _, mods, _ in _GROUPS for m in mods]

)





# ====================================================================

#  Glyph -> QPixmap icon

# ====================================================================

def _glyph_pixmap(glyph: str, color: str = "#333", size: int = 16) -> QPixmap:

    pm = QPixmap(size, size)

    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)

    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setPen(QColor(color))

    f = p.font()

    f.setPixelSize(int(size * 0.78))

    f.setBold(True)

    p.setFont(f)

    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)

    p.end()

    return pm





# ====================================================================

#  Stylesheets

# ====================================================================

_BRAND_LIGHT = """

QFrame#brand {

    background: transparent;

}

QLabel#brandTitle {

    color: #1a1a1a; font-size: 19px; font-weight: 800;

    letter-spacing: 0.5px; padding: 0;

}

QLabel#brandSub {

    color: #9aa0a6; font-size: 8.5px; font-weight: 600;

    letter-spacing: 1.5px; padding: 0;

}

"""



_BRAND_DARK = """

QFrame#brand {

    background: transparent;

}

QLabel#brandTitle {

    color: #f5f5f7; font-size: 19px; font-weight: 800;

    letter-spacing: 0.5px; padding: 0;

}

QLabel#brandSub {

    color: #6a6a70; font-size: 8.5px; font-weight: 600;

    letter-spacing: 1.5px; padding: 0;

}

"""



_NAV_LIGHT = """

QFrame#sidebar {

    background: #fafafa;

    border-right: 1px solid #ececec;

}

QPushButton.nav {

    text-align: left;

    font-size: 12px;

    color: #444;

    border: none;

    border-radius: 6px;

    padding: 7px 10px;

    background: transparent;

}

QPushButton.nav:hover {

    background: #eef3fb;

    color: #1a6bc0;

}

QPushButton.nav:checked {

    background: #e3eefb;

    color: #1a6bc0;

    font-weight: 600;

}

QPushButton.nav:checked:hover {

    background: #d8e6f8;

}

QLabel.section {

    color: #9aa0a6;

    font-size: 9px;

    font-weight: 700;

    letter-spacing: 1.5px;

    padding: 12px 10px 4px 10px;

}

QFrame#sep {

    background: #ececec;

    max-height: 1px;

    min-height: 1px;

}

"""



_NAV_DARK = """

QFrame#sidebar {

    background: #161618;

    border-right: 1px solid #2a2a2e;

}

QPushButton.nav {

    text-align: left;

    font-size: 12px;

    color: #c0c0c5;

    border: none;

    border-radius: 6px;

    padding: 7px 10px;

    background: transparent;

}

QPushButton.nav:hover {

    background: rgba(100,180,255,0.10);

    color: #f5f5f7;

}

QPushButton.nav:checked {

    background: rgba(100,180,255,0.18);

    color: #f5f5f7;

    font-weight: 600;

}

QPushButton.nav:checked:hover {

    background: rgba(100,180,255,0.25);

}

QLabel.section {

    color: #6a6a70;

    font-size: 9px;

    font-weight: 700;

    letter-spacing: 1.5px;

    padding: 12px 10px 4px 10px;

}

QFrame#sep {

    background: #2a2a2e;

    max-height: 1px;

    min-height: 1px;

}

"""





# ====================================================================

#  Sidebar widget

# ====================================================================

class Sidebar(QFrame):

    """Fixed-width left navigation sidebar."""



    module_selected = Signal(str)  # emits module key



    def __init__(

        self,

        active_key: str = "upload",

        on_theme_toggle: Optional[Callable[[], None]] = None,

        theme_is_dark: bool = False,

        parent: Optional[QWidget] = None,

    ):

        super().__init__(parent)

        self.setObjectName("sidebar")

        self.setFixedWidth(210)

        self.setStyleSheet(_NAV_LIGHT)



        self._active_key = active_key

        self._on_theme_toggle = on_theme_toggle

        self._dark = theme_is_dark

        self._buttons: dict[str, QPushButton] = {}



        self._build_ui()

        self._refresh_icons()



    # ----------------------------------------------------------------

    #  UI

    # ----------------------------------------------------------------

    def _build_ui(self) -> None:

        ly = QVBoxLayout(self)

        ly.setContentsMargins(10, 14, 10, 12)

        ly.setSpacing(0)



        # Brand

        brand = QFrame()

        brand.setObjectName("brand")

        bl = QVBoxLayout(brand)

        bl.setContentsMargins(4, 0, 4, 8)

        bl.setSpacing(2)

        t = QLabel("ClustroView")

        t.setObjectName("brandTitle")

        s = QLabel("EXPLORE. COMPARE. UNDERSTAND.")

        s.setObjectName("brandSub")

        bl.addWidget(t)

        bl.addWidget(s)

        ly.addWidget(brand)



        # Spacer

        sp = QFrame()

        sp.setObjectName("sep")

        sp.setFixedHeight(1)

        ly.addWidget(sp)



        # Module groups

        for label, mods, has_label in _GROUPS:

            if has_label:

                sec = QLabel(label)

                sec.setProperty("class", "section")

                sec.setStyleSheet(

                    "color: #9aa0a6; font-size: 9px; font-weight: 700;"

                    " letter-spacing: 1.5px; padding: 12px 10px 4px 10px;"

                )

                ly.addWidget(sec)

            for m in mods:

                btn = QPushButton(f"  {m.label}")

                btn.setProperty("class", "nav")

                btn.setCheckable(True)

                btn.setChecked(m.key == self._active_key)

                btn.setCursor(Qt.CursorShape.PointingHandCursor)

                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

                btn.clicked.connect(lambda _=False, k=m.key: self._on_module(k))

                ly.addWidget(btn)

                self._buttons[m.key] = btn



        ly.addStretch()



        # Theme toggle at the bottom

        self._theme_btn = QPushButton("\u263E  Dark")

        self._theme_btn.setProperty("class", "nav")

        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._theme_btn.clicked.connect(self._toggle_theme)

        ly.addWidget(self._theme_btn)



        self._brand_title = t

        self._brand_sub = s

        self._section_labels: list[QLabel] = []



    def _on_module(self, key: str) -> None:

        if key == self._active_key:

            return

        # Update visual selection

        for k, b in self._buttons.items():

            b.setChecked(k == key)

        self._active_key = key

        self.module_selected.emit(key)



    def _toggle_theme(self) -> None:

        if self._on_theme_toggle:

            self._on_theme_toggle()



    # ----------------------------------------------------------------

    #  Theme

    # ----------------------------------------------------------------

    def set_dark(self, dark: bool) -> None:

        self._dark = dark

        self.setStyleSheet(_NAV_DARK if dark else _NAV_LIGHT)

        self._brand_title.setStyleSheet(

            "color: #f5f5f7; font-size: 19px; font-weight: 800; letter-spacing: 0.5px;"

            if dark else

            "color: #1a1a1a; font-size: 19px; font-weight: 800; letter-spacing: 0.5px;"

        )

        self._brand_sub.setStyleSheet(

            "color: #6a6a70; font-size: 8.5px; font-weight: 600; letter-spacing: 1.5px;"

            if dark else

            "color: #9aa0a6; font-size: 8.5px; font-weight: 600; letter-spacing: 1.5px;"

        )

        self._theme_btn.setText("\u2600  Light" if dark else "\u263E  Dark")

        self._refresh_icons()



    def _refresh_icons(self) -> None:

        col = "#c0c0c5" if self._dark else "#555"

        active_col = "#f5f5f7" if self._dark else "#1a6bc0"

        for key, btn in self._buttons.items():

            # find glyph

            glyph = "\u25A0"

            for _, mods, _ in _GROUPS:

                for m in mods:

                    if m.key == key:

                        glyph = m.icon

                        break

            ic = _glyph_pixmap(glyph, col)

            btn.setIcon(ic)



    # ----------------------------------------------------------------

    #  Public

    # ----------------------------------------------------------------

    def get_active(self) -> str:

        return self._active_key

