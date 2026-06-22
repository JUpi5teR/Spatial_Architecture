# coding: utf-8
"""Homepage view - notebook management entry point.

Apple-inspired redesign. Public API (signals, methods, child widgets)
is unchanged so MainController / MainWindow integration still works.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF, QPoint
from PySide6.QtGui import (
    QPixmap, QFont, QColor, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QAbstractItemView,
)

from backend.models import NotebookManager, DatasetManager
from utils.logger import logger


# ============================================================================
# Design tokens (Apple HIG inspired)
# ============================================================================
_FONT_STACK = (
    '-apple-system, BlinkMacSystemFont, "SF Pro Display", '
    '"SF Pro Text", "Segoe UI Variable", "Segoe UI", '
    'Helvetica, Arial, sans-serif'
)

# Light
BG_LIGHT          = '#f5f5f7'
SURFACE_LIGHT     = '#ffffff'
SURFACE_ALT_LIGHT = '#fbfbfd'
DIVIDER_LIGHT     = '#e3e3e8'
TXT_PRI_LIGHT     = '#1d1d1f'
TXT_SEC_LIGHT     = '#6e6e73'
TXT_TER_LIGHT     = '#86868b'
ACCENT_LIGHT      = '#0071e3'
ACCENT_HOVER_LIGHT= '#0077ed'
ACCENT_PRESS_LIGHT= '#006edb'
BTN_GHOST_HOVER_L = 'rgba(0,0,0,0.04)'
BTN_GHOST_PRESS_L = 'rgba(0,0,0,0.08)'
SEARCH_BG_LIGHT   = 'rgba(0,0,0,0.04)'
SEARCH_FOCUS_LIGHT= 'rgba(0,0,0,0.08)'
SHADOW_LIGHT      = 'rgba(0,0,0,0.08)'

# Dark
BG_DARK           = '#1c1c1e'
SURFACE_DARK      = '#2c2c2e'
SURFACE_ALT_DARK  = '#242426'
DIVIDER_DARK      = '#3a3a3c'
TXT_PRI_DARK      = '#f5f5f7'
TXT_SEC_DARK      = '#98989d'
TXT_TER_DARK      = '#6e6e73'
ACCENT_DARK       = '#0a84ff'
ACCENT_HOVER_DARK = '#1f8fff'
ACCENT_PRESS_DARK = '#0066cc'
BTN_GHOST_HOVER_D = 'rgba(255,255,255,0.08)'
BTN_GHOST_PRESS_D = 'rgba(255,255,255,0.14)'
SEARCH_BG_DARK    = 'rgba(255,255,255,0.08)'
SEARCH_FOCUS_DARK = 'rgba(255,255,255,0.14)'
SHADOW_DARK       = 'rgba(0,0,0,0.32)'


# ============================================================================
# Helpers
# ============================================================================

def _make_ghost_btn(text, dark, font_px=13):
    hov = BTN_GHOST_HOVER_D if dark else BTN_GHOST_HOVER_L
    prs = BTN_GHOST_PRESS_D if dark else BTN_GHOST_PRESS_L
    fg = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
    return (
        f"QPushButton {{"
        f" background: transparent; border: none; color: {fg};"
        f" border-radius: 8px; padding: 6px 12px; font-size: {font_px}px;"
        f" font-family: {_FONT_STACK}; font-weight: 500;"
        f" }}"
        f"QPushButton:hover {{ background: {hov}; }}"
        f"QPushButton:pressed {{ background: {prs}; }}"
    )


def _make_primary_btn(dark):
    bg = ACCENT_DARK if dark else ACCENT_LIGHT
    hov = ACCENT_HOVER_DARK if dark else ACCENT_HOVER_LIGHT
    prs = ACCENT_PRESS_DARK if dark else ACCENT_PRESS_LIGHT
    return (
        f"QPushButton {{"
        f" background: {bg}; color: #ffffff; border: none;"
        f" border-radius: 18px; padding: 8px 18px;"
        f" font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
        f" }}"
        f"QPushButton:hover {{ background: {hov}; }}"
        f"QPushButton:pressed {{ background: {prs}; }}"
    )

def _paint_rounded_card(p, rect, radius, surface_color, dark, hover=False):
    """Paint a soft-shadowed rounded card (Apple HIG style).

    QGraphicsDropShadowEffect would draw a rectangular halo around the
    widget regardless of its rounded QSS, so we paint three layered
    semi-transparent rounded rects to simulate a soft drop shadow that
    respects the rounded corners.
    """
    if hover:
        outer_dy, outer_a = 16, 10
        mid_dy, mid_a = 10, 22
        close_dy, close_a = 4, 38
    else:
        outer_dy, outer_a = 12, 6
        mid_dy, mid_a = 7, 14
        close_dy, close_a = 3, 26
    # Dark mode needs slightly stronger shadow to read on a dark surface.
    if dark:
        outer_a += 8
        mid_a += 10
        close_a += 12
    for dy, alpha in ((outer_dy, outer_a), (mid_dy, mid_a), (close_dy, close_a)):
        sr = QRectF(rect)
        sr.translate(0, dy)
        path = QPainterPath()
        path.addRoundedRect(sr, radius, radius)
        p.fillPath(path, QColor(0, 0, 0, alpha))
    sp = QPainterPath()
    sp.addRoundedRect(rect, radius, radius)
    p.fillPath(sp, surface_color)

# ============================================================================
# Create Notebook Dialog (Apple sheet-style)
# ============================================================================
class CreateNotebookDialog(QDialog):
    """Modal dialog for creating a new notebook."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Notebook")
        self.setFixedSize(440, 280)
        self._dark = False
        self._build()
        self.setStyleSheet(
            f"QDialog {{ background: {SURFACE_LIGHT}; font-family: {_FONT_STACK}; }}"
        )

    def set_dark(self, dark):
        self._dark = dark
        bg = SURFACE_DARK if dark else SURFACE_LIGHT
        fg = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        field_bg = SURFACE_ALT_DARK if dark else SURFACE_ALT_LIGHT
        field_border = DIVIDER_DARK if dark else DIVIDER_LIGHT
        self.setStyleSheet(
            f"QDialog {{ background: {bg}; font-family: {_FONT_STACK}; color: {fg}; }}"
            f"QLabel {{ font-size: 13px; color: {sec}; }}"
            f"QLineEdit {{"
            f"  background: {field_bg}; border: 1px solid {field_border};"
            f"  border-radius: 10px; padding: 9px 12px; font-size: 14px;"
            f"  color: {fg}; font-family: {_FONT_STACK};"
            f"  selection-background-color: {ACCENT_LIGHT};"
            f"}}"
            f"QLineEdit:focus {{ border-color: {ACCENT_LIGHT}; }}"
        )

    def _build(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(28, 24, 28, 20)
        ly.setSpacing(6)

        title = QLabel("New Notebook")
        title.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 20px; font-weight: 700;"
            f" color: {TXT_PRI_LIGHT};"
        )
        ly.addWidget(title)
        ly.addSpacing(8)

        name_lbl = QLabel("NAME")
        name_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 10px; font-weight: 700;"
            f" color: {TXT_TER_LIGHT}; letter-spacing: 0.6px;"
        )
        ly.addWidget(name_lbl)
        ly.addSpacing(2)

        default_name = "Notebook_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self._name_input = QLineEdit(default_name)
        self._name_input.selectAll()
        self._default_name = default_name
        ly.addWidget(self._name_input)
        ly.addSpacing(10)

        desc_lbl = QLabel("DESCRIPTION (OPTIONAL)")
        desc_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 10px; font-weight: 700;"
            f" color: {TXT_TER_LIGHT}; letter-spacing: 0.6px;"
        )
        ly.addWidget(desc_lbl)
        ly.addSpacing(2)

        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("What is this notebook for?")
        ly.addWidget(self._desc_input)
        ly.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(_make_ghost_btn("Cancel", False).replace("font-size: 13px;", "font-size: 13px; padding: 7px 14px;"))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        ok_btn = QPushButton("Create")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(_make_primary_btn(False).replace("padding: 8px 18px;", "padding: 8px 22px;"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btns.addWidget(ok_btn)
        ly.addLayout(btns)

    def notebook_name(self):
        name = self._name_input.text().strip()
        return name if name else self._default_name


# ============================================================================
# Notebook Card (Apple large tile)
# ============================================================================
class NotebookCard(QFrame):

    clicked = Signal(int)
    rename_requested = Signal(int, str)
    delete_requested = Signal(int)

    CARD_W = 280
    CARD_H = 320
    # Layout margins (px) reserved so paintEvent can paint a soft shadow
    # around the rounded card without leaking past the widget edges.
    SHADOW_MARGIN_X = 18
    SHADOW_MARGIN_TOP = 14
    SHADOW_MARGIN_BOTTOM = 22
    CARD_RADIUS = 16.0

    def __init__(self, notebook, dataset_count, cover_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("notebookCard")
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notebook = notebook
        self._dataset_count = dataset_count
        self._cover_path = cover_path
        self._dark = False
        self._hover = False
        self._build_ui()

    def _refresh_card_style(self):
        # Card surface and its soft shadow are drawn in paintEvent so the
        # shadow follows the rounded corners instead of leaking a rectangle.
        self.setStyleSheet(
            "QFrame#notebookCard { background: transparent; border: none; }"
        )

    def paintEvent(self, event):
        # Custom paint replaces QGraphicsDropShadowEffect so the shadow
        # follows the rounded corners instead of leaking a rectangle.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(
            self.SHADOW_MARGIN_X,
            self.SHADOW_MARGIN_TOP,
            self.width() - 2 * self.SHADOW_MARGIN_X,
            self.height() - self.SHADOW_MARGIN_TOP - self.SHADOW_MARGIN_BOTTOM,
        )
        _paint_rounded_card(
            p, rect, self.CARD_RADIUS,
            QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT),
            self._dark, hover=self._hover,
        )
        p.end()
        # Children paint themselves on top via Qt's automatic dispatch.

    def _build_ui(self):
        ly = QVBoxLayout(self)
        # Margins reserve room for the layered soft shadow drawn in paintEvent.
        ly.setContentsMargins(self.SHADOW_MARGIN_X, self.SHADOW_MARGIN_TOP,
                              self.SHADOW_MARGIN_X, self.SHADOW_MARGIN_BOTTOM)
        ly.setSpacing(0)

        # Cover area
        cover_h = 168
        self._cover_label = QLabel(self)
        self._cover_label.setFixedHeight(cover_h)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_label.setStyleSheet(
            "border-top-left-radius: 16px; border-top-right-radius: 16px;"
        )
        self._load_cover()
        ly.addWidget(self._cover_label)

        # Body
        body = QFrame()
        body.setStyleSheet("background: transparent;")
        body_ly = QVBoxLayout(body)
        body_ly.setContentsMargins(18, 14, 18, 14)
        body_ly.setSpacing(4)

        # Name row
        title_row = QHBoxLayout()
        title_row.setSpacing(2)
        self._name_lbl = QLabel(self._notebook.name)
        self._name_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 16px; font-weight: 600;"
            f" color: {TXT_PRI_LIGHT}; background: transparent;"
        )
        self._name_lbl.setWordWrap(False)
        self._name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title_row.addWidget(self._name_lbl, 1)

        self._menu_btn = QPushButton("\u2026")
        self._menu_btn.setFixedSize(28, 28)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setStyleSheet(
            _make_ghost_btn("\u2026", False).replace("font-size: 13px;", "font-size: 16px; padding: 0;")
        )
        self._menu_btn.clicked.connect(self._show_menu)
        title_row.addWidget(self._menu_btn)
        body_ly.addLayout(title_row)

        # Meta row
        meta = QHBoxLayout()
        meta.setSpacing(6)
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 12px;"
            f" color: {TXT_SEC_LIGHT}; background: transparent;"
        )
        meta.addWidget(self._count_lbl)
        meta.addStretch()
        self._time_lbl = QLabel(self._fmt(self._notebook.updated_at))
        self._time_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 12px;"
            f" color: {TXT_TER_LIGHT}; background: transparent;"
        )
        meta.addWidget(self._time_lbl)
        body_ly.addLayout(meta)
        body_ly.addStretch()

        # Footer with "Open" chip
        footer = QHBoxLayout()
        footer.setSpacing(0)
        self._open_chip = QLabel("Open  \u203A")
        self._open_chip.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
            f" color: {ACCENT_LIGHT}; background: transparent;"
        )
        self._open_chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        footer.addWidget(self._open_chip)
        footer.addStretch()
        body_ly.addLayout(footer)

        ly.addWidget(body, 1)
        self._update_count_label()
        self._refresh_card_style()

    def _update_count_label(self):
        n = self._dataset_count
        suffix = "" if n == 1 else "s"
        self._count_lbl.setText(f"{n} dataset{suffix}")

    def _load_cover(self):
        if self._cover_path:
            pixmap = QPixmap(self._cover_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.CARD_W, 168,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                rounded = QPixmap(scaled.size())
                rounded.fill(Qt.GlobalColor.transparent)
                p = QPainter(rounded)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(QRectF(0, 0, scaled.width(), scaled.height()), 16, 16)
                p.setClipPath(path)
                p.drawPixmap(0, 0, scaled)
                p.end()
                self._cover_label.setPixmap(rounded)
                return
        self._cover_label.setPixmap(self._placeholder_pixmap(self.CARD_W, 168))

    def _placeholder_pixmap(self, w, h):
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c1 = QColor("#a0c4ff") if not self._dark else QColor("#3a5a8a")
        c2 = QColor("#cdb4db") if not self._dark else QColor("#4a3a5a")
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 16, 16)
        p.fillPath(path, c1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c2)
        blob = QPainterPath()
        blob.addEllipse(QPoint(int(w * 0.75), int(h * 0.7)), int(w * 0.35), int(h * 0.5))
        p.fillPath(path.intersected(blob), c2)
        p.end()
        return pm

    # ---- public ----
    def set_dark(self, dark):
        self._dark = dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        acc = ACCENT_DARK if dark else ACCENT_LIGHT
        self._name_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 16px; font-weight: 600;"
            f" color: {pri}; background: transparent;"
        )
        self._count_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 12px; color: {sec}; background: transparent;"
        )
        self._time_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 12px; color: {ter}; background: transparent;"
        )
        self._open_chip.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
            f" color: {acc}; background: transparent;"
        )
        self._menu_btn.setStyleSheet(
            _make_ghost_btn("\u2026", dark).replace("font-size: 13px;", "font-size: 16px; padding: 0;")
        )
        self._refresh_card_style()
        self._load_cover()  # re-render placeholder with new palette

    def set_dataset_count(self, n):
        self._dataset_count = n
        self._update_count_label()

    # ---- events ----
    def enterEvent(self, event):
        if not self._hover:
            self._hover = True
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._hover:
            self._hover = False
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._notebook.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._notebook.id)
        super().mouseDoubleClickEvent(event)

    # ---- menu actions ----
    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {SURFACE_DARK if self._dark else SURFACE_LIGHT};"
            f" color: {TXT_PRI_DARK if self._dark else TXT_PRI_LIGHT};"
            f" border: 1px solid {DIVIDER_DARK if self._dark else DIVIDER_LIGHT};"
            f" border-radius: 10px; padding: 6px; font-family: {_FONT_STACK}; }}"
            f"QMenu::item {{ padding: 6px 24px; border-radius: 6px; }}"
            f"QMenu::item:selected {{"
            f" background: {(BTN_GHOST_HOVER_D if self._dark else BTN_GHOST_HOVER_L)}; }}"
        )
        menu.addAction("Rename").triggered.connect(self._on_rename)
        menu.addAction("Move to Trash").triggered.connect(self._on_delete)
        btn = self._menu_btn
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _on_rename(self):
        new_name, ok = QInputDialog.getText(
            self, "Rename Notebook", "New name:",
            QLineEdit.EchoMode.Normal, self._notebook.name,
        )
        if ok and new_name.strip() and new_name.strip() != self._notebook.name:
            self.rename_requested.emit(self._notebook.id, new_name.strip())

    def _on_delete(self):
        reply = QMessageBox.question(
            self, "Move to Trash",
            f"Move \"{self._notebook.name}\" to Trash?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self._notebook.id)

    @staticmethod
    def _fmt(ts):
        if ts is None:
            return ""
        s = str(ts)
        return s[:10] if len(s) >= 10 else s


# ============================================================================
# Empty state (illustration + CTA)
# ============================================================================
class _EmptyArt(QWidget):
    """Hand-drawn minimal illustration for the empty state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False

    def set_dark(self, dark):
        self._dark = dark
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c1 = QColor("#e8efff") if not self._dark else QColor("#2a3a5a")
        c2 = QColor("#f0e8ff") if not self._dark else QColor("#3a2a4a")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c1)
        p.drawEllipse(20, 20, 140, 110)
        p.setBrush(c2)
        p.drawEllipse(80, 35, 130, 100)
        p.setBrush(QColor(SURFACE_LIGHT) if not self._dark else QColor(SURFACE_DARK))
        p.setPen(QPen(QColor(DIVIDER_LIGHT) if not self._dark else QColor(DIVIDER_DARK), 1.5))
        p.drawRoundedRect(70, 50, 80, 100, 10, 10)
        p.setPen(QPen(QColor(TXT_TER_LIGHT) if not self._dark else QColor(TXT_TER_DARK), 2))
        p.drawLine(82, 72, 138, 72)
        p.drawLine(82, 88, 138, 88)
        p.drawLine(82, 104, 122, 104)
        plus_color = QColor(ACCENT_LIGHT if not self._dark else ACCENT_DARK)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(plus_color)
        p.drawEllipse(132, 40, 28, 28)
        p.setPen(QPen(QColor("#ffffff"), 2.5))
        p.drawLine(146, 47, 146, 61)
        p.drawLine(139, 54, 153, 54)
        p.end()


class EmptyState(QFrame):
    def __init__(self, on_create, dark=False, parent=None):
        super().__init__(parent)
        self._dark = dark
        self._on_create = on_create
        ly = QVBoxLayout(self)
        ly.setContentsMargins(20, 60, 20, 60)
        ly.setSpacing(14)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._art = _EmptyArt(self)
        self._art.setFixedSize(220, 160)
        ly.addWidget(self._art, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("No notebooks yet")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("emptyTitle")
        ly.addWidget(title)

        subtitle = QLabel("Create your first notebook to start\nanalysing spatial transcriptomics data.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("emptySubtitle")
        ly.addWidget(subtitle)

        cta = QPushButton("+ New Notebook")
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setObjectName("emptyCta")
        cta.clicked.connect(self._on_create)
        ly.addSpacing(8)
        ly.addWidget(cta, 0, Qt.AlignmentFlag.AlignHCenter)
        self._apply_text()

    def _apply_text(self):
        dark = self._dark
        title = self.findChild(QLabel, "emptyTitle")
        subtitle = self.findChild(QLabel, "emptySubtitle")
        cta = self.findChild(QPushButton, "emptyCta")
        if title is not None:
            title.setStyleSheet(
                f"font-family: {_FONT_STACK}; font-size: 22px; font-weight: 700;"
                f" color: {TXT_PRI_DARK if dark else TXT_PRI_LIGHT}; background: transparent;"
            )
        if subtitle is not None:
            subtitle.setStyleSheet(
                f"font-family: {_FONT_STACK}; font-size: 14px;"
                f" color: {TXT_SEC_DARK if dark else TXT_SEC_LIGHT}; background: transparent;"
            )
        if cta is not None:
            cta.setStyleSheet(
                _make_primary_btn(dark).replace("padding: 8px 18px;", "padding: 10px 22px;")
                .replace("font-size: 13px;", "font-size: 14px;")
            )

    def set_dark(self, dark):
        self._dark = dark
        self._art.set_dark(dark)
        self._apply_text()


# ============================================================================
# Notebook Grid with Search
# ============================================================================
class NotebookGrid(QWidget):

    notebook_selected = Signal(int)
    notebook_renamed = Signal(int, str)
    notebook_deleted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nb_mgr = NotebookManager()
        self._ds_mgr = DatasetManager()
        self._cards = []
        self._dark = False
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 8, 0, 8)
        ly.setSpacing(12)

        # Search row
        search_row = QHBoxLayout()
        search_row.setContentsMargins(32, 4, 32, 4)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search notebooks")
        self._search.setFixedHeight(36)
        self._search.setStyleSheet(self._search_qss(False))
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)
        ly.addLayout(search_row)

        # Grid scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar { background: transparent; width: 8px; }"
            "QScrollBar::handle { background: rgba(0,0,0,0.15); border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:hover { background: rgba(0,0,0,0.25); }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
        )

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QVBoxLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(32, 16, 32, 24)
        self._grid_layout.setSpacing(0)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        scroll.setWidget(self._grid_widget)
        ly.addWidget(scroll, 1)

    def _search_qss(self, dark):
        bg = SEARCH_BG_DARK if dark else SEARCH_BG_LIGHT
        focus_bg = SEARCH_FOCUS_DARK if dark else SEARCH_FOCUS_LIGHT
        fg = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        ph = TXT_TER_DARK if dark else TXT_TER_LIGHT
        return (
            f"QLineEdit {{"
            f" background: {bg}; color: {fg};"
            f" border: none; border-radius: 18px;"
            f" padding: 4px 16px 4px 38px; font-size: 13px;"
            f" font-family: {_FONT_STACK};"
            f" }}"
            f"QLineEdit:focus {{ background: {focus_bg}; }}"
        )

    def _on_search(self, text):
        q = text.strip().lower()
        for card in self._cards:
            if not q:
                card.setVisible(True)
            else:
                card.setVisible(q in card._notebook.name.lower())

    def refresh(self):
        self._clear_grid()
        notebooks = self._nb_mgr.list_active()

        if not notebooks:
            self._empty = EmptyState(self._on_create_clicked, dark=self._dark)
            self._grid_layout.addWidget(self._empty)
            return

        grid = QWidget()
        grid.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(24)
        grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        cols = 4
        for i, nb in enumerate(notebooks):
            count = self._ds_mgr.count_by_notebook(nb.id)
            cover_path = self._find_notebook_cover(nb.id)
            card = NotebookCard(nb, count, cover_path)
            card.set_dark(self._dark)
            card.clicked.connect(self.notebook_selected.emit)
            card.rename_requested.connect(self._on_rename)
            card.delete_requested.connect(self._on_delete)
            self._cards.append(card)
            grid_layout.addWidget(card, i // cols, i % cols)

        self._grid_layout.addWidget(grid)
        self._grid_layout.addStretch(1)

    def _on_create_clicked(self):
        # Walk up to HomepageView and ask it to create
        parent = self.parent()
        while parent is not None and not isinstance(parent, HomepageView):
            parent = parent.parent()
        if parent is not None:
            parent._create_notebook()

    def _find_notebook_cover(self, notebook_id):
        try:
            datasets = self._ds_mgr.list_by_notebook(notebook_id)
            if not datasets:
                return None
            from view.datasets_view import _find_cover_image
            for ds in datasets:
                gt_path = getattr(ds, "ground_truth_path", None) or ds.file_path
                path = _find_cover_image(gt_path)
                if path:
                    return path
        except Exception:
            pass
        return None

    def _clear_grid(self):
        self._cards.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _on_rename(self, nb_id, new_name):
        self._nb_mgr.update_name(nb_id, new_name)
        self.notebook_renamed.emit(nb_id, new_name)
        self.refresh()

    def _on_delete(self, nb_id):
        self._nb_mgr.soft_delete(nb_id)
        self.notebook_deleted.emit(nb_id)
        self.refresh()

    def set_dark(self, dark):
        self._dark = dark
        self._search.setStyleSheet(self._search_qss(dark))
        for card in self._cards:
            card.set_dark(dark)
        if hasattr(self, "_empty") and self._empty is not None:
            self._empty.set_dark(dark)


# ============================================================================
# Database Panel (clean Apple-style table)
# ============================================================================
class DatabasePanel(QWidget):

    dataset_selected = Signal(int, int)

    # Layout margins (px) reserved so paintEvent can paint a soft shadow
    # around the rounded card surface without leaking past the widget edges.
    SHADOW_MARGIN_X = 20
    SHADOW_MARGIN_TOP = 20
    SHADOW_MARGIN_BOTTOM = 24
    CARD_RADIUS = 16.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ds_mgr = DatasetManager()
        self._dark = False
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        # Margins reserve room for the layered soft shadow drawn in paintEvent.
        ly.setContentsMargins(self.SHADOW_MARGIN_X, self.SHADOW_MARGIN_TOP,
                              self.SHADOW_MARGIN_X, self.SHADOW_MARGIN_BOTTOM)
        ly.setSpacing(8)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Name", "Notebook", "Uploaded", "Path", "Status",
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._table.setStyleSheet(self._table_qss(False))
        self._table.verticalScrollBar().setStyleSheet(self._scrollbar_qss())
        ly.addWidget(self._table)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(
            self.SHADOW_MARGIN_X,
            self.SHADOW_MARGIN_TOP,
            self.width() - 2 * self.SHADOW_MARGIN_X,
            self.height() - self.SHADOW_MARGIN_TOP - self.SHADOW_MARGIN_BOTTOM,
        )
        _paint_rounded_card(
            p, rect, self.CARD_RADIUS,
            QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT),
            self._dark,
        )
        p.end()

    def _table_qss(self, dark):
        bg = SURFACE_DARK if dark else SURFACE_LIGHT
        hdr = SURFACE_ALT_DARK if dark else SURFACE_ALT_LIGHT
        txt = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        div = DIVIDER_DARK if dark else DIVIDER_LIGHT
        return (
            f"QTableWidget {{"
            f" background: {bg}; border: none; border-radius: 14px;"
            f" gridline-color: transparent; font-size: 13px; color: {txt};"
            f" font-family: {_FONT_STACK}; selection-background-color: rgba(0,113,227,0.18);"
            f" selection-color: {txt};"
            f" }}"
            f"QTableWidget::item {{ padding: 10px 12px; border-bottom: 1px solid {div}; }}"
            f"QTableWidget::item:selected {{ background: rgba(0,113,227,0.16); color: {ACCENT_LIGHT}; }}"
            f"QHeaderView::section {{"
            f" background: {hdr}; color: {ter}; padding: 10px 12px;"
            f" border: none; border-bottom: 1px solid {div};"
            f" font-weight: 700; font-size: 11px; letter-spacing: 0.5px;"
            f" text-transform: uppercase; font-family: {_FONT_STACK};"
            f" }}"
            f"QTableCornerButton::section {{ background: {hdr}; border: none; }}"
        )

    def _scrollbar_qss(self):
        return (
            "QScrollBar { background: transparent; width: 8px; }"
            "QScrollBar::handle { background: rgba(0,0,0,0.15); border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:hover { background: rgba(0,0,0,0.25); }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
        )

    def refresh(self):
        datasets = self._ds_mgr.list_all_active()
        self._table.setRowCount(len(datasets))
        for i, ds in enumerate(datasets):
            self._table.setItem(i, 0, QTableWidgetItem(ds.name))
            nb_name = getattr(ds, "notebook_name", str(ds.notebook_id))
            self._table.setItem(i, 1, QTableWidgetItem(nb_name))
            self._table.setItem(i, 2, QTableWidgetItem(self._fmt(ds.upload_time)))
            self._table.setItem(i, 3, QTableWidgetItem(ds.file_path))
            self._table.setItem(i, 4, QTableWidgetItem(ds.status))
        self._table.resizeColumnsToContents()

    def set_dark(self, dark):
        self._dark = dark
        self._table.setStyleSheet(self._table_qss(dark))
        self.update()

    @staticmethod
    def _fmt(ts):
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return str(ts)[:16]


# ============================================================================
# Segmented Control (Apple HIG style)
# ============================================================================
class SegmentedControl(QWidget):
    segment_changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self._buttons = []
        self._current = 0
        self._dark = False
        ly = QHBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)
        container = QFrame()
        container.setObjectName("segmentedContainer")
        c_ly = QHBoxLayout(container)
        c_ly.setContentsMargins(2, 2, 2, 2)
        c_ly.setSpacing(0)
        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda _, ix=i: self._on_click(ix))
            c_ly.addWidget(btn)
            self._buttons.append(btn)
        ly.addWidget(container)
        self._refresh_style()

    def _on_click(self, idx):
        if idx == self._current:
            return
        self._current = idx
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == idx)
        self._refresh_style()
        self.segment_changed.emit(idx)

    def current_index(self):
        return self._current

    def _container_qss(self, dark):
        bg = "rgba(0,0,0,0.06)" if not dark else "rgba(255,255,255,0.08)"
        return f"QFrame#segmentedContainer {{ background: {bg}; border-radius: 9px; border: none; }}"

    def _button_qss(self, dark, selected):
        if selected:
            bg = SURFACE_LIGHT if not dark else SURFACE_DARK
            fg = TXT_PRI_LIGHT if not dark else TXT_PRI_DARK
            return (
                f"QPushButton {{"
                f" background: {bg}; color: {fg}; border: none;"
                f" border-radius: 7px; padding: 0 16px;"
                f" font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
                f" }}"
            )
        fg = TXT_SEC_LIGHT if not dark else TXT_SEC_DARK
        return (
            f"QPushButton {{"
            f" background: transparent; color: {fg}; border: none;"
            f" border-radius: 7px; padding: 0 16px;"
            f" font-family: {_FONT_STACK}; font-size: 13px; font-weight: 500;"
            f" }}"
            f"QPushButton:hover {{ color: {TXT_PRI_LIGHT if not dark else TXT_PRI_DARK}; }}"
        )

    def _refresh_style(self):
        container = self.findChild(QFrame, "segmentedContainer")
        if container is not None:
            container.setStyleSheet(self._container_qss(self._dark))
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(self._button_qss(self._dark, i == self._current))

    def set_dark(self, dark):
        self._dark = dark
        self._refresh_style()


# ============================================================================
# Trash Panel (side sheet)
# ============================================================================
class TrashPanel(QFrame):
    closed = Signal()
    restored = Signal(int)
    permanently_deleted = Signal(int)

    # Layout margins (px) reserved so paintEvent can paint a soft shadow
    # around the rounded card surface. Right margin is 0 because the panel
    # is anchored to the right edge of the parent window.
    SHADOW_MARGIN_LEFT = 14
    SHADOW_MARGIN_TOP = 14
    SHADOW_MARGIN_RIGHT = 0
    SHADOW_MARGIN_BOTTOM = 22
    CARD_RADIUS = 16.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nb_mgr = NotebookManager()
        self._dark = False
        self.setObjectName("trashPanel")
        self.setFixedWidth(360)
        self._build_ui()
        self._apply_theme()

    def set_dark(self, dark):
        self._dark = dark
        self._apply_theme()
        self._refresh()
        self.update()

    def _apply_theme(self):
        dark = self._dark
        # Surface is drawn in paintEvent; keep QSS transparent.
        self.setStyleSheet(
            "QFrame#trashPanel { background: transparent; border: none; }"
        )

    def _build_ui(self):
        ly = QVBoxLayout(self)
        # Margins reserve room for the layered soft shadow drawn in paintEvent.
        ly.setContentsMargins(self.SHADOW_MARGIN_LEFT, self.SHADOW_MARGIN_TOP,
                              self.SHADOW_MARGIN_RIGHT, self.SHADOW_MARGIN_BOTTOM)
        ly.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Trash")
        title.setObjectName("trashTitle")
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            _make_ghost_btn("\u2715", False).replace("font-size: 13px;", "font-size: 14px; padding: 0;")
        )
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        ly.addLayout(header)
        title.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 18px; font-weight: 700;"
            f" color: {TXT_PRI_LIGHT}; background: transparent;"
        )

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._card_container = QWidget()
        self._card_container.setStyleSheet("background: transparent;")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(10)
        self._scroll.setWidget(self._card_container)
        ly.addWidget(self._scroll, 1)

        self._refresh()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(
            self.SHADOW_MARGIN_LEFT,
            self.SHADOW_MARGIN_TOP,
            self.width() - self.SHADOW_MARGIN_LEFT - self.SHADOW_MARGIN_RIGHT,
            self.height() - self.SHADOW_MARGIN_TOP - self.SHADOW_MARGIN_BOTTOM,
        )
        _paint_rounded_card(
            p, rect, self.CARD_RADIUS,
            QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT),
            self._dark,
        )
        p.end()

    def _refresh(self):
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        notebooks = self._nb_mgr.list_trash()
        if not notebooks:
            empty = QLabel("Trash is empty.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"font-family: {_FONT_STACK}; font-size: 13px;"
                f" color: {TXT_TER_LIGHT}; padding: 24px; background: transparent;"
            )
            self._card_layout.addWidget(empty)
            return

        for nb in notebooks:
            self._card_layout.addWidget(self._build_card(nb))
        self._card_layout.addStretch()

    def _build_card(self, nb):
        card = QFrame()
        card_bg = SURFACE_ALT_DARK if self._dark else SURFACE_ALT_LIGHT
        card.setStyleSheet(
            f"QFrame {{ background: {card_bg}; border: none; border-radius: 12px; }}"
        )
        c_ly = QVBoxLayout(card)
        c_ly.setContentsMargins(14, 12, 14, 12)
        c_ly.setSpacing(8)

        name = QLabel(nb.name)
        name.setWordWrap(True)
        name.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 14px; font-weight: 600;"
            f" color: {TXT_PRI_LIGHT}; background: transparent;"
        )
        c_ly.addWidget(name)

        ts = str(nb.deleted_at)[:10] if nb.deleted_at else "-"
        time_lbl = QLabel("Deleted " + ts)
        time_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 11px;"
            f" color: {TXT_TER_LIGHT}; background: transparent;"
        )
        c_ly.addWidget(time_lbl)

        btn_ly = QHBoxLayout()
        btn_ly.setSpacing(8)
        restore_btn = QPushButton("Restore")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setStyleSheet(
            _make_primary_btn(self._dark).replace("padding: 8px 18px;", "padding: 6px 14px;")
            .replace("font-size: 13px;", "font-size: 12px;")
            .replace("border-radius: 18px;", "border-radius: 14px;")
        )
        restore_btn.clicked.connect(lambda _, nid=nb.id: self._restore(nid))
        btn_ly.addWidget(restore_btn)

        perm_btn = QPushButton("Delete")
        perm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        perm_btn.setStyleSheet(
            _make_ghost_btn("Delete", self._dark).replace("padding: 6px 12px;", "padding: 6px 14px;")
            .replace("font-size: 13px;", "font-size: 12px;")
            .replace("border-radius: 8px;", "border-radius: 14px;")
        )
        perm_btn.clicked.connect(lambda _, nid=nb.id: self._perm_delete(nid))
        btn_ly.addWidget(perm_btn)
        btn_ly.addStretch()
        c_ly.addLayout(btn_ly)
        return card

    def _restore(self, nb_id):
        self._nb_mgr.restore(nb_id)
        self.restored.emit(nb_id)
        self._refresh()

    def _perm_delete(self, nb_id):
        reply = QMessageBox.warning(
            self, "Delete Forever",
            "This action cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._nb_mgr.permanent_delete(nb_id)
            self.permanently_deleted.emit(nb_id)
            self._refresh()


# ============================================================================
# Dimming overlay (for trash sheet)
# ============================================================================
class DimOverlay(QWidget):
    clicked_outside = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.18);")
        self.hide()

    def mousePressEvent(self, event):
        self.clicked_outside.emit()
        event.accept()


# ============================================================================
# Homepage View (root container)
# ============================================================================
class HomepageView(QWidget):

    notebook_opened = Signal(int)
    theme_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trash_panel = None
        self._dim_overlay = None
        self._dark = False
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)
        self.setStyleSheet(f"HomepageView {{ background: {BG_LIGHT}; }}")

        # === Top bar ===
        top = QFrame()
        top.setStyleSheet("background: transparent; border: none;")
        top.setFixedHeight(72)
        top_ly = QHBoxLayout(top)
        top_ly.setContentsMargins(32, 16, 24, 12)
        top_ly.setSpacing(16)

        # Brand block
        brand = QHBoxLayout()
        brand.setSpacing(10)
        self._logo = QLabel("\u25C8")
        self._logo.setObjectName("brandLogo")
        brand.addWidget(self._logo)
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        self._home_title_label = QLabel("ClustroView")
        self._home_title_label.setObjectName("brandTitle")
        title_block.addWidget(self._home_title_label)
        self._home_subtitle_label = QLabel("Spatial Transcriptomics")
        self._home_subtitle_label.setObjectName("brandSubtitle")
        title_block.addWidget(self._home_subtitle_label)
        brand.addLayout(title_block)
        top_ly.addLayout(brand)
        top_ly.addStretch()

        # Right-side actions
        self._theme_btn = QPushButton()
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setObjectName("themeBtn")
        self._theme_btn.clicked.connect(self._toggle_theme)
        top_ly.addWidget(self._theme_btn)

        self._trash_top_btn = QPushButton()
        self._trash_top_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trash_top_btn.setObjectName("trashBtn")
        self._trash_top_btn.clicked.connect(self._show_trash)
        top_ly.addWidget(self._trash_top_btn)

        self._new_btn = QPushButton("+ New Notebook")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.setObjectName("newBtn")
        self._new_btn.clicked.connect(self._create_notebook)
        top_ly.addSpacing(4)
        top_ly.addWidget(self._new_btn)

        ly.addWidget(top)

        # === Content area ===
        content = QFrame()
        content.setStyleSheet("background: transparent; border: none;")
        c_ly = QVBoxLayout(content)
        c_ly.setContentsMargins(32, 8, 32, 8)
        c_ly.setSpacing(0)

        self._segmented = SegmentedControl(["Notebooks", "Database"])
        self._segmented.segment_changed.connect(self._on_segment_changed)
        c_ly.addWidget(self._segmented, 0, Qt.AlignmentFlag.AlignLeft)
        c_ly.addSpacing(20)

        self._page_stack = QFrame()
        self._page_stack.setStyleSheet("background: transparent; border: none;")
        ps_ly = QVBoxLayout(self._page_stack)
        ps_ly.setContentsMargins(0, 0, 0, 0)
        ps_ly.setSpacing(0)

        self._notebook_grid = NotebookGrid()
        self._notebook_grid.notebook_selected.connect(self.notebook_opened.emit)
        self._notebook_grid.notebook_renamed.connect(self._on_refresh)
        self._notebook_grid.notebook_deleted.connect(self._on_refresh)
        self._database_panel = DatabasePanel()
        self._database_panel.hide()
        ps_ly.addWidget(self._notebook_grid)
        ps_ly.addWidget(self._database_panel)
        c_ly.addWidget(self._page_stack, 1)
        ly.addWidget(content, 1)

        # Initial styles
        self._apply_brand_styles()
        self._apply_icon_btn_styles()
        self._apply_primary_btn_style()
        self._update_icon_glyphs()

    # ---- top-bar styling helpers ----
    def _icon_btn_qss(self, dark):
        hov = BTN_GHOST_HOVER_D if dark else BTN_GHOST_HOVER_L
        prs = BTN_GHOST_PRESS_D if dark else BTN_GHOST_PRESS_L
        fg = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        return (
            f"QPushButton {{"
            f" background: transparent; color: {fg}; border: none;"
            f" border-radius: 16px; min-width: 32px; min-height: 32px;"
            f" font-family: {_FONT_STACK}; font-size: 16px; font-weight: 600;"
            f" padding: 0 8px;"
            f" }}"
            f"QPushButton:hover {{ background: {hov}; }}"
            f"QPushButton:pressed {{ background: {prs}; }}"
        )

    def _apply_brand_styles(self):
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        acc = ACCENT_DARK if dark else ACCENT_LIGHT
        self._logo.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 22px; font-weight: 700;"
            f" color: {acc}; background: transparent;"
        )
        self._home_title_label.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 17px; font-weight: 700;"
            f" color: {pri}; background: transparent;"
        )
        self._home_subtitle_label.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 11px; font-weight: 500;"
            f" color: {sec}; background: transparent;"
        )

    def _apply_icon_btn_styles(self):
        qss = self._icon_btn_qss(self._dark)
        self._theme_btn.setStyleSheet(qss)
        self._trash_top_btn.setStyleSheet(qss)

    def _apply_primary_btn_style(self):
        self._new_btn.setStyleSheet(_make_primary_btn(self._dark))

    def _update_icon_glyphs(self):
        self._theme_btn.setText("\u263E" if not self._dark else "\u2600")
        self._theme_btn.setToolTip("Switch to Dark" if not self._dark else "Switch to Light")
        self._trash_top_btn.setText("\u267B")
        self._trash_top_btn.setToolTip("Trash")

    # ---- segment change ----
    def _on_segment_changed(self, idx):
        if idx == 0:
            self._notebook_grid.show()
            self._database_panel.hide()
        else:
            self._notebook_grid.hide()
            self._database_panel.show()
            self._database_panel.refresh()

    # ---- public ----
    def refresh(self):
        self._notebook_grid.refresh()
        self._database_panel.refresh()

    def _create_notebook(self):
        dlg = CreateNotebookDialog(self)
        if self._dark:
            dlg.set_dark(True)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.notebook_name()
            nb_mgr = NotebookManager()
            nb = nb_mgr.create(name)
            self.refresh()
            self.notebook_opened.emit(nb.id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._trash_panel is not None and self._trash_panel.isVisible():
            w = self.width()
            h = self.height()
            self._dim_overlay.setGeometry(0, 0, w, h)
            self._trash_panel.setGeometry(w - self._trash_panel.width(), 0,
                                          self._trash_panel.width(), h)

    def set_dark(self, dark):
        self._dark = dark
        bg = BG_DARK if dark else BG_LIGHT
        self.setStyleSheet(f"HomepageView {{ background: {bg}; }}")

        self._apply_brand_styles()
        self._apply_icon_btn_styles()
        self._apply_primary_btn_style()
        self._segmented.set_dark(dark)
        self._notebook_grid.set_dark(dark)
        self._database_panel.set_dark(dark)

        if self._trash_panel is not None:
            self._trash_panel.set_dark(dark)

    def _on_refresh(self, *args):
        self.refresh()

    def _toggle_theme(self):
        if getattr(self, "_theme_switching", False):
            return
        self._theme_switching = True
        try:
            self._dark = not self._dark
            self.setUpdatesEnabled(False)
            try:
                from view.main_window import apply_theme
                apply_theme(self._dark)
                self.set_dark(self._dark)
            finally:
                self.setUpdatesEnabled(True)
            self.theme_toggled.emit(self._dark)
            self._update_icon_glyphs()
        finally:
            self._theme_switching = False

    def _show_trash(self):
        if self._trash_panel is None:
            self._trash_panel = TrashPanel(self)
            self._trash_panel.closed.connect(self._hide_trash)
            self._trash_panel.restored.connect(self._on_refresh)
            self._trash_panel.permanently_deleted.connect(self._on_refresh)
            self._trash_panel.set_dark(self._dark)
        if self._dim_overlay is None:
            self._dim_overlay = DimOverlay(self)
            self._dim_overlay.clicked_outside.connect(self._hide_trash)
        w = self.width()
        h = self.height()
        self._dim_overlay.setGeometry(0, 0, w, h)
        self._trash_panel.setGeometry(w - self._trash_panel.width(), 0,
                                      self._trash_panel.width(), h)
        self._dim_overlay.show()
        self._dim_overlay.raise_()
        self._trash_panel.show()
        self._trash_panel.raise_()

    def _hide_trash(self):
        if self._trash_panel is not None:
            self._trash_panel.hide()
        if self._dim_overlay is not None:
            self._dim_overlay.hide()
