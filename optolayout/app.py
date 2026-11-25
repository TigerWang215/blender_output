"""Main window: Schematic and Layout tabs, properties, power log, files.

The schematic defines the system (parts, part numbers, beams); the layout
places it on the table. See docs/SCHEMATIC.md."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import (QEventLoop, QLibraryInfo, QLineF, QPointF, QProcess, QRectF,
                            QSettings, QSize, QStandardPaths, QTemporaryDir, Qt, QTimer, QTranslator)
from PySide6.QtGui import (QAction, QColor, QImage, QKeySequence, QPainter,
                           QPen)
from PySide6.QtWidgets import (QApplication, QProgressBar, QCheckBox, QHBoxLayout, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox,
                               QDockWidget, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGraphicsView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from .logbook import Logbook, logbook_path_for
from .measure_ui import MeasurementDialog, PointsPanel, export_power_csv
from .mounts3d import BOARD_BEAM_HEIGHT, DEFAULT_BEAM_HEIGHT, DRILLED_STYLES
from .model import (BEAM_SOURCE_TYPES, BOARD_STYLES, DEFAULT_APERTURE_DIAMETER_MM, DEFAULT_SOURCE_DIAMETER_MM, SCH_KINDS,
                    WAVELENGTH_COLORS, Beam, Component, Layout, MeasurementPoint, grating_size_text, new_id,
                    wavelengths_in_use)
from .schematic import MODE_LINK, PartsTable, SchematicPage, SchematicScene, SchSetFieldsCmd
from . import labels
from .scene import (AddPointCmd, BeamItem, ComponentItem, DeleteCmd, LayoutScene, PartPair, PointItem,
                    SetFieldsCmd)
from .icons import icon
from .symbols import SYMBOLS, make_icon

MODE_SELECT, MODE_PLACE, MODE_BEAM, MODE_POINT, MODE_RULER = "select", "place", "beam", "point", "ruler"


def swatch_icon(color: str, size: int = 12):
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return QIcon(pm)


def hole_text(table, x, y) -> str:
    if not table.has_grid:
        return "预钻孔" if table.on_board(x, y) else "平台外"
    h = table.hole_at(x, y)
    if h is None:
        return "平台外"
    name, dx, dy = h
    what = "孔位" if table.grid_holes else "网格点"
    if abs(dx) < 0.05 and abs(dy) < 0.05:
        return f"{what} {name}"
    return f"靠近{what} {name} ({dx:+.1f}, {dy:+.1f} mm)"


class LayoutView(QGraphicsView):
    def __init__(self, scene: LayoutScene, win: "MainWindow"):
        super().__init__(scene)
        self.win = win
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._pan_start = None
        self._press_positions: dict[str, tuple[float, float]] | None = None
        self.beam_from: str | None = None
        self._cursor_scene = QPointF()
        self.ruler: tuple[QPointF, QPointF] | None = None  # last measurement, kept until Esc
        self._ruling = False
        self.setMouseTracking(True)
        self.scale(2.0, 2.0)

    def ruler_snap(self, pos: QPointF, screen_pt) -> QPointF:
        """Snap a ruler end to a part's optical point, or to a hole, when close."""
        sc: LayoutScene = self.scene()
        z = max(sc.view_zoom, 1e-6)
        for it in self.items(screen_pt.x() - 8, screen_pt.y() - 8, 16, 16):
            if isinstance(it, ComponentItem):
                return QPointF(it.comp.x, it.comp.y)
        t = sc.layout.table
        hx = t.hole_offset + round((pos.x() - t.hole_offset) / t.hole_pitch) * t.hole_pitch
        hy = t.hole_offset + round((pos.y() - t.hole_offset) / t.hole_pitch) * t.hole_pitch
        if math.hypot(hx - pos.x(), hy - pos.y()) * z < 7 and t.hole_at(hx, hy) is not None:
            return QPointF(hx, hy)
        return pos

    # zoom / pan ----------------------------------------------------------
    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def fit(self):
        self.fitInView(self.scene().table_rect().adjusted(-20, -20, 20, 30), Qt.KeepAspectRatio)

    def mousePressEvent(self, e):
        sc: LayoutScene = self.scene()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and e.modifiers() & Qt.ControlModifier
                                              and self.win.mode == MODE_SELECT and not self.itemAt(e.position().toPoint())):
            self._pan_start = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        pos = self.mapToScene(e.position().toPoint())
        sc.free_drag = bool(e.modifiers() & Qt.AltModifier)  # Alt-drag: no snapping
        if e.button() == Qt.LeftButton and self.win.mode == MODE_RULER:
            p0 = pos if e.modifiers() & Qt.AltModifier else self.ruler_snap(pos, e.position().toPoint())
            self.ruler = (p0, p0)
            self._ruling = True
            self.viewport().update()
            return
        if e.button() == Qt.LeftButton and self.win.mode == MODE_POINT:
            placed = False
            beam = self._beam_at(e.position().toPoint())
            if beam is not None:
                self.win.add_point_on(beam.beam.id, pos)
                placed = True
            else:
                for it in self.items(e.position().toPoint()):  # a fiber coupler: power out of its fiber
                    if isinstance(it, ComponentItem) and sc.layout.fiber_end(it.comp.id) is not None:
                        self.win.add_fiber_point(it.comp.id)
                        placed = True
                        break
            if placed and not e.modifiers() & Qt.ShiftModifier:  # one point at a time; Shift-click for more
                self.win.set_mode(MODE_SELECT)
            return
        super().mousePressEvent(e)
        if e.button() == Qt.LeftButton:
            self._press_positions = {c: (sc.layout.components[c].x, sc.layout.components[c].y)
                                     for c in sc.selected_ids()[0]}

    def mouseMoveEvent(self, e):
        self._cursor_scene = self.mapToScene(e.position().toPoint())
        self.win.show_cursor(self._cursor_scene)
        if self._pan_start is not None:
            d = e.position() - self._pan_start
            self._pan_start = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self._ruling and self.ruler is not None:
            p1 = (self._cursor_scene if e.modifiers() & Qt.AltModifier
                  else self.ruler_snap(self._cursor_scene, e.position().toPoint()))
            self.ruler = (self.ruler[0], p1)
            self.win.show_ruler(*self.ruler)
            self.viewport().update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan_start is not None:
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            return
        if self._ruling:
            self._ruling = False
            return
        super().mouseReleaseEvent(e)
        sc: LayoutScene = self.scene()
        sc.free_drag = False
        if self._press_positions:
            changes = {}
            for cid, (x0, y0) in self._press_positions.items():
                c = sc.layout.components.get(cid)
                if c and (abs(c.x - x0) > 1e-6 or abs(c.y - y0) > 1e-6):
                    changes[cid] = ({"x": x0, "y": y0, "pinned": c.pinned}, {"x": c.x, "y": c.y, "pinned": True})
            if changes:
                sc.undo.push(SetFieldsCmd(sc, changes, "移动"))
        self._press_positions = None

    def _beam_at(self, pt) -> BeamItem | None:
        # generous pick radius: beams are thin
        r = 6
        for it in self.items(pt.x() - r, pt.y() - r, 2 * r, 2 * r):
            if isinstance(it, BeamItem):
                return it
        return None

    def _component_at(self, pt) -> ComponentItem | None:
        for it in self.items(pt):
            if isinstance(it, ComponentItem):
                return it
        return None

    def keyPressEvent(self, e):
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in arrows:
            dx, dy = arrows[e.key()]
            self.win.nudge_selected(dx, dy, fine=bool(e.modifiers() & Qt.ShiftModifier))
            return
        super().keyPressEvent(e)

    def drawForeground(self, p, rect):
        super().drawForeground(p, rect)
        if self.ruler is None or self.win.mode != MODE_RULER:
            return
        a, b = self.ruler
        z = max(self.scene().view_zoom, 1e-6)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#e8590c"), 2.0 / z)
        p.setPen(pen)
        p.drawLine(a, b)
        ln = QLineF(a, b)
        L = ln.length()
        tick = 7 / z
        if L > 0:
            n = QPointF(-ln.dy() / L, ln.dx() / L) * tick
            for q in (a, b):
                p.drawLine(q - n, q + n)
        p.setBrush(QColor("#e8590c"))
        for q in (a, b):
            p.drawEllipse(q, 2.5 / z, 2.5 / z)
        txt = f"{L:.1f} mm  ({L / 25.4:.3f} in)"
        sub = f"dx {b.x() - a.x():+.1f}  dy {b.y() - a.y():+.1f} mm"
        px = 13 / z
        w1, h1 = labels.text_size(txt, px)
        w2, h2 = labels.text_size(sub, px * 0.85, bold=False)
        m = ln.pointAt(0.5)
        box = QRectF(m.x() + 8 / z, m.y() + 8 / z, max(w1, w2) + 8 / z, h1 + h2 + 4 / z)
        p.setPen(QPen(QColor("#e8590c"), 1 / z))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(box, 3 / z, 3 / z)
        p.setPen(QColor("#111111"))
        labels.draw_halo_text(p, QRectF(box.left() + 4 / z, box.top() + 2 / z, w1, h1), txt, px,
                              align=Qt.AlignLeft | Qt.AlignVCenter)
        labels.draw_halo_text(p, QRectF(box.left() + 4 / z, box.top() + 2 / z + h1, w2, h2), sub, px * 0.85,
                              bold=False, color="#444444", align=Qt.AlignLeft | Qt.AlignVCenter)

    def mouseDoubleClickEvent(self, e):
        it = self._component_at(e.position().toPoint())
        if it is not None:
            self.win.edit_in_schematic(it.comp)
            return
        super().mouseDoubleClickEvent(e)


def board_summary(lay, scene) -> str:
    """What the Properties panel shows when nothing is selected: the board,
    what is on it, and which colour is which wavelength."""
    t = lay.table
    on = [c for c in lay.components.values() if t.on_board(c.x, c.y)]
    waiting = len(lay.components) - len(on)
    total = sum(lay.beam_length(b) for b in lay.beams.values())
    pts = [p for p in lay.points.values() if not p.archived]
    rows = [f"{t.width:g} × {t.height:g} mm ({t.width / 25.4:g} × {t.height / 25.4:g} in)",
            BOARD_STYLES.get(t.style, ("",))[0] + ("，带缺口" if t.cutouts else "")
            + (f"：{t.columns()} × {t.rows()} 孔，孔距 {t.hole_pitch:g} mm" if t.has_grid else "")
            + (f"，平台固定螺钉 {len(scene.table_screw_holes())} 枚" if t.style in DRILLED_STYLES else ""),
            f"平台上有 {len(on)} 个元件" + (f"，另有 {waiting} 个在平台下方等待放置" if waiting else ""),
            f"{len(lay.beams)} 段光束，共 {total:.0f} mm",
            f"{len(pts)} 个测量点"]
    if scene.clashes:
        rows.append(f"<span style='color:#d62728'>⚠ {len(scene.clashes)} 个元件发生重叠</span>")
    html = "<br>".join(rows)
    used = wavelengths_in_use(lay)
    if used:
        html += "<br><br><b>波长</b>"
        for color, name, n in used:
            html += (f"<br><span style='color:{color}; font-size:14px'>■</span>&nbsp;{name}"
                     f" <span style='color:#777'>（{n} 段）</span>")
    html += ("<br><br><span style='color:#777'>拖动元件可移动位置。方向键微调一格，Shift + 方向键移动 1 mm。"
             "选中两个元件可查看两者之间的光程。请在「光路图」中添加元件和光束。</span>")
    return html


class BoardDialog(QDialog):
    """Board name, size, hole pattern and cut-outs (for irregular boards)."""

    def __init__(self, t, parent=None):
        super().__init__(parent)
        self.setWindowTitle("光学平台")
        self.name = QLineEdit(t.name)
        self.width = QDoubleSpinBox()
        self.height = QDoubleSpinBox()
        for s, v in ((self.width, t.width), (self.height, t.height)):
            s.setRange(10, 10000)
            s.setDecimals(2)
            s.setSuffix(" mm")
            s.setValue(v)
        self.style = QComboBox()
        for key, (label, _p) in BOARD_STYLES.items():
            self.style.addItem(label, key)
        self.style.setCurrentIndex(max(0, self.style.findData(t.style)))
        self.cutouts = QLineEdit("; ".join(", ".join(f"{v:g}" for v in c) for c in t.cutouts))
        self.cutouts.setPlaceholderText("可留空，或输入 x, y, w, h; x, y, w, h（以左上角为原点，单位 mm）")
        form = QFormLayout(self)
        form.addRow("名称", self.name)
        form.addRow("宽度", self.width)
        form.addRow("高度", self.height)
        form.addRow("孔位", self.style)
        form.addRow("缺口", self.cutouts)
        hint = QLabel("可从平台上切去一个或多个矩形区域，形成不规则形状。")
        hint.setStyleSheet("color:#777")
        hint.setWordWrap(True)
        form.addRow(hint)
        from PySide6.QtWidgets import QDialogButtonBox
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _parse(self):
        out = []
        for chunk in self.cutouts.text().split(";"):
            if chunk.strip():
                vals = [float(v) for v in chunk.replace(" ", "").split(",")]
                if len(vals) != 4:
                    raise ValueError
                out.append(vals)
        return out

    def _ok(self):
        try:
            self._cut = self._parse()
        except ValueError:
            QMessageBox.warning(self, "光学平台", "每个缺口填写 x, y, w, h，多个缺口用半角分号分隔。")
            return
        self.accept()

    def apply(self, t):
        t.name, t.width, t.height = self.name.text().strip(), self.width.value(), self.height.value()
        style = self.style.currentData()
        if style != t.style:
            t.apply_style(style)
        t.cutouts = self._cut


class PropertiesPanel(QWidget):
    """Layout properties. What a part IS (label, part, part number) belongs to
    the schematic and is shown read-only here; the layout only sets where it
    sits and how it is turned."""

    def __init__(self, scene: LayoutScene):
        super().__init__()
        self.scene = scene
        self.obj = None
        form = QFormLayout(self)
        self.title = QLabel("未选择对象")
        f = self.title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.15)
        self.title.setFont(f)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.AutoText)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label = QLineEdit()  # editable for measurement points only
        self.x = self._spin(-10000, 10000, " mm")
        self.y = self._spin(-10000, 10000, " mm")
        self.angle = self._spin(-360, 360, " °")
        self.auto = QCheckBox("按光束方向自动定向")
        self.auto.toggled.connect(self._auto_toggled)
        self.edit_btn = QPushButton("在光路图中编辑元件")
        self.edit_btn.clicked.connect(lambda: self.obj is not None and self.edit_in_schematic(self.obj))
        self.edit_in_schematic = lambda _obj: None
        self.log_btn = QPushButton("打开功率日志…")
        self.log_btn.clicked.connect(lambda: self.obj and self.open_log(self.obj.id))
        self.open_log = lambda _pid: None
        form.addRow(self.title)
        form.addRow(self.info)
        form.addRow("标签", self.label)
        form.addRow("X", self.x)
        form.addRow("Y", self.y)
        form.addRow("角度", self.angle)
        form.addRow("", self.auto)
        form.addRow("", self.edit_btn)
        form.addRow("", self.log_btn)
        self.rows = {"label": self.label, "x": self.x, "y": self.y, "angle": self.angle}
        for key, w in self.rows.items():
            w.editingFinished.connect(lambda k=key: self._commit(k))
        scene.selection_info.connect(self.show_obj)
        scene.edited.connect(lambda: self.show_obj(self.obj))
        self.show_obj(None)

    @staticmethod
    def _spin(lo, hi, suffix):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSuffix(suffix)
        s.setKeyboardTracking(False)
        return s

    def _show(self, w, on):
        w.setVisible(on)
        lbl = self.layout().labelForField(w)
        if lbl is not None:
            lbl.setVisible(on)

    def show_obj(self, obj):
        lay = self.scene.layout
        if isinstance(obj, Component) and obj.id not in lay.components:
            obj = None
        if isinstance(obj, Beam) and obj.id not in lay.beams:
            obj = None
        self.obj = obj
        is_comp = isinstance(obj, Component)
        is_beam = isinstance(obj, Beam)
        is_point = isinstance(obj, MeasurementPoint)
        for w in (self.x, self.y, self.angle, self.auto):
            self._show(w, is_comp)
        self._show(self.label, is_point)
        self.edit_btn.setVisible(is_comp or is_beam)
        self.edit_btn.setText("在光路图中编辑元件" if is_comp else "在光路图中编辑光束")
        self.log_btn.setVisible(is_point)
        for w in list(self.rows.values()) + [self.auto]:
            w.blockSignals(True)
        if is_comp:
            el = lay.schematic.elements.get(obj.sch_id) if obj.sch_id else None
            self.title.setText(obj.label or SYMBOLS[obj.type].name)
            lines = [SYMBOLS[obj.type].name, obj.part_number or "未设置料号",
                     "支柱位置 " + hole_text(lay.table, obj.x, obj.y)]
            if obj.type == "grating":
                lines.append("光栅尺寸 " + grating_size_text(obj.grating_size_mm))
            if obj.type in BEAM_SOURCE_TYPES:
                lines.append(f"初始束径 {obj.source_diameter_mm or DEFAULT_SOURCE_DIAMETER_MM:g} mm")
            if obj.type in SCH_KINDS["lens"][2]:
                lines.append(f"焦距 {obj.focal_length_mm:g} mm" if obj.focal_length_mm else "未设置焦距")
            if obj.type == "variable_iris":
                diameter = obj.aperture_diameter_mm
                lines.append(f"通光直径 {DEFAULT_APERTURE_DIAMETER_MM if diameter is None else diameter:g} mm")
            if el is not None and el.notes:
                lines.append(el.notes)
            if obj.id in self.scene.clashes:
                lines.append("⚠ 与其他元件重叠")
            if obj.id in self.scene.off_table():
                lines.append("尚未放在平台上，请拖到目标位置。")
            self.info.setText("\n".join(lines))
            self.x.setValue(obj.x)
            self.y.setValue(obj.y)
            self.angle.setValue(obj.angle)
            self.angle.setEnabled(not obj.auto_angle)
            self.auto.setChecked(obj.auto_angle)
        elif is_beam:
            a, b = lay.components.get(obj.source), lay.components.get(obj.target)
            self.title.setText(f"光束 {a.label if a else '?'} → {b.label if b else '?'}")
            L = math.hypot(b.x - a.x, b.y - a.y) if a and b else 0
            wl = f"{obj.wavelength_nm:g} nm" if obj.wavelength_nm else "未设置波长"
            n = len([p for p in lay.points_on(obj.id) if not p.archived])
            self.info.setText(f"{wl}\n长度 {L:.1f} mm ({L / 25.4:.2f} in)\n{n} 个测量点")
        elif isinstance(obj, PartPair):
            a, b = lay.components.get(obj[0]), lay.components.get(obj[1])
            name = lambda c: c.label or SYMBOLS[c.type].name  # noqa: E731
            self.title.setText(f"{name(a)} ↔ {name(b)}" if a and b else "两个元件")
            if a and b:
                d = math.hypot(b.x - a.x, b.y - a.y)
                lines = [f"直线距离：{d:.1f} mm ({d / 25.4:.3f} in)",
                         f"dx {b.x - a.x:+.1f} mm, dy {b.y - a.y:+.1f} mm"]
                path = lay.optical_path(a.id, b.id)
                if path is None:
                    lines.append("两个元件之间没有连通的光路。")
                else:
                    L, ids = path
                    lines.insert(0, f"光程：{L:.1f} mm ({L / 25.4:.3f} in)")
                    lines.append("沿光束经过：" + " → ".join(name(lay.components[c]) for c in ids))
                    segs = []
                    for u, v in zip(ids, ids[1:]):
                        cu, cv = lay.components[u], lay.components[v]
                        segs.append(f"{math.hypot(cv.x - cu.x, cv.y - cu.y):.1f}")
                    lines.append("各段长度（mm）：" + " + ".join(segs))
                self.info.setText("\n".join(lines))
        elif is_point:
            self.title.setText(f"测量点 {obj.label}" + ("（已归档）" if obj.archived else ""))
            part = lay.components.get(obj.part_id or "")
            self.info.setText(f"测量 {part.label or SYMBOLS[part.type].name} 的光纤输出功率。测量点"
                              "随耦合器一起移动。" if part is not None else "拖动标记可沿光束移动测量点。")
            self.label.setText(obj.label)
        else:
            self.title.setText(lay.table.name or "光学平台")
            self.info.setText(board_summary(lay, self.scene))
        for w in list(self.rows.values()) + [self.auto]:
            w.blockSignals(False)

    def _auto_toggled(self, on):
        if isinstance(self.obj, Component) and self.obj.auto_angle != on:
            self.scene.undo.push(SetFieldsCmd(self.scene, {self.obj.id: ({"auto_angle": self.obj.auto_angle},
                                                                         {"auto_angle": on})}, "自动定向"))

    def _commit(self, key):
        if self.obj is None:
            return
        w = self.rows[key]
        val = w.text() if isinstance(w, QLineEdit) else w.value()
        if getattr(self.obj, key, None) == val:
            return
        old, new = {key: getattr(self.obj, key)}, {key: val}
        if key == "angle" and isinstance(self.obj, Component):
            old["auto_angle"], new["auto_angle"] = self.obj.auto_angle, False
        if key in ("x", "y") and isinstance(self.obj, Component):
            old["pinned"], new["pinned"] = self.obj.pinned, True
        self.scene.undo.push(SetFieldsCmd(self.scene, {self.obj.id: (old, new)}, f"编辑{key}"))


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.scene = LayoutScene()
        self.view = LayoutView(self.scene, self)
        self.sch_scene = SchematicScene(self.scene.undo)
        self.sch_page = SchematicPage(self.sch_scene, lambda: self.beam_style(), WAVELENGTH_COLORS)
        self.sch_page.hint = lambda msg: self.statusBar().showMessage(msg)
        self.sch_page.back_to_select = lambda: self.set_mode(MODE_SELECT)
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(20, 20))
        self.tabs.addTab(self.sch_page, icon("schematic"), "光路图")
        self.tabs.addTab(self.view, icon("layout"), "平台布局")
        self.view3d_holder = QWidget()  # the 3D tab is built the first time it is opened
        QVBoxLayout(self.view3d_holder).setContentsMargins(0, 0, 0, 0)
        self.view3d = None
        self._view3d_loading = False
        try:  # an OpenGL widget from the start: adding the first one to a window that is already on screen
            # makes Windows close and reopen the whole window
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            QOpenGLWidget(self.view3d_holder).hide()
        except Exception:
            pass
        self.tabs.addTab(self.view3d_holder, icon("3d"), "3D")
        self.tabs.setCurrentIndex(1)
        self.setCentralWidget(self.tabs)
        self._syncing_sel = False
        self._fit_pending = {0, 1}  # tabs to fit once they are on screen with their real size
        self.path: Path | None = None
        self.mode = MODE_SELECT
        self._blender_job = None

        self.layout_docks = []
        self.settings = QSettings("optolayout", "Optical Layout Designer")
        try:
            self.scene.text_scale = self.sch_scene.text_scale = float(self.settings.value("text_scale", 1.0))
        except (TypeError, ValueError):
            pass

        self.props = PropertiesPanel(self.scene)
        self.props.open_log = self.open_point_log
        self.props.edit_in_schematic = self.edit_in_schematic
        pdock = QDockWidget("属性", self)
        pdock.setWidget(self.props)
        self.addDockWidget(Qt.RightDockWidgetArea, pdock)
        self.layout_docks.append(pdock)

        self.logbook: Logbook | None = None
        self._no_log = False  # opened without its power log: nothing is logged
        self._log_layout: Path | None = None  # the layout file the log belongs to
        self._dialogs: dict[str, MeasurementDialog] = {}
        self.points_panel = PointsPanel()
        self.points_panel.open_point.connect(self.open_point_log)
        self.points_panel.show_archived_changed.connect(self.scene.set_show_archived)
        mdock = QDockWidget("功率日志", self)
        mdock.setWidget(self.points_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, mdock)
        self.layout_docks.append(mdock)
        self._log_poll = QTimer(self)  # readings logged elsewhere (the web pages) show up here
        self._log_poll.timeout.connect(self._poll_logbook)
        self._log_poll.start(3000)
        self.scene.point_clicked.connect(self.open_point_log)
        self.scene.edited.connect(self.refresh_measurements)
        self.scene.edited.connect(self._layers_changed)
        self.sch_scene.edited.connect(self._schematic_changed)
        self.scene.selectionChanged.connect(self._layout_sel_to_sch)
        self.sch_scene.selectionChanged.connect(self._sch_sel_to_layout)
        self.tabs.currentChanged.connect(self._tab_changed)

        self._build_actions()
        self.scene.undo.cleanChanged.connect(lambda _: self._update_title())
        self.statusBar()
        self.pos_lbl = QLabel()
        self.statusBar().addPermanentWidget(self.pos_lbl)
        # web status at the right end of the menu bar: a coloured dot and the address other PCs open
        self.web_corner = corner = QWidget()  # kept: PySide doesn't give a corner widget to the menu bar
        row = QHBoxLayout(corner)
        row.setContentsMargins(0, 0, 10, 0)
        row.setSpacing(5)
        self.web_dot = QLabel("●")
        self.web_lbl = QLabel()
        self.web_lbl.setOpenExternalLinks(True)
        self.web_lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)  # click to open, select to copy
        row.addWidget(self.web_dot)
        row.addWidget(self.web_lbl)
        self.menuBar().setCornerWidget(corner, Qt.TopRightCorner)
        self._web_state("grey")
        if self.a_web.isChecked() and QApplication.platformName() not in ("offscreen", "minimal"):
            QTimer.singleShot(0, lambda: self.set_web(True, remember=False))  # tests start it themselves
        if path:
            self.open_path(path)
        else:
            self.sch_scene.set_layout(self.scene.layout)
        self.resize(1400, 900)
        self._update_title()
        self._tab_changed(self.tabs.currentIndex())

    # ---- actions ------------------------------------------------------------
    def _act(self, text, slot, shortcut=None, tb=None, icon_name=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if icon_name:
            a.setIcon(icon(icon_name))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            keys = a.shortcut().toString(QKeySequence.NativeText)
            if keys and f"({keys})" not in text:
                a.setToolTip(f"{text}  ({keys})")
        self.addAction(a)
        if tb is not None:
            tb.addAction(a)
        return a

    def _build_actions(self):
        m = self.menuBar()
        fm = m.addMenu("文件(&F)")
        self.a_new = self._act("新建", self.new_file, QKeySequence.New, icon_name="new")
        self.a_open = self._act("打开…", self.open_file, QKeySequence.Open, icon_name="open")
        self.a_save = self._act("保存", self.save_file, QKeySequence.Save, icon_name="save")
        for a in (self.a_new, self.a_open, self.a_save):
            fm.addAction(a)
        fm.addAction(self._act("另存为…", self.save_as, QKeySequence.SaveAs))
        fm.addSeparator()
        fm.addAction(self._act("导出当前视图为 SVG…", lambda: self.export("svg"), "Ctrl+E"))
        fm.addAction(self._act("导出当前视图为 PNG…", lambda: self.export("png"), "Ctrl+Shift+E"))
        self.a_blender = None
        if sys.platform == "darwin":
            self.a_blender = self._act("在 Blender 中打开", self.open_in_blender)
            self.a_blender.setToolTip("生成当前布局的 .blend 文件，可按束径显示并附带元器件名称。")
            fm.addAction(self.a_blender)
        fm.addAction(self._act("导出功率日志（CSV）…", self.export_csv))
        fm.addAction(self._act("导出物料清单（CSV）…", self.export_bom))
        fm.addSeparator()
        fm.addAction(self._act("平台尺寸、孔位和形状…", self.edit_table))
        # the web pages (web/), served while the app is open; gone if the web folder is deleted
        self.web = None
        self.web_config = None  # None: web/config.json
        self.a_web = self._act("网页访问（在局域网内共享）", lambda on: self.set_web(on))
        self.a_web.setCheckable(True)
        self.a_web.setChecked(self.settings.value("web_on", True, type=bool))
        self.a_web.setToolTip("程序打开时，允许局域网内的其他设备通过浏览器查看布局、记录功率。")
        if (Path(__file__).resolve().parents[1] / "web" / "embed.py").exists():
            fm.addSeparator()
            fm.addAction(self.a_web)

        em = m.addMenu("编辑(&E)")
        undo = self.scene.undo.createUndoAction(self, "撤销")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.scene.undo.createRedoAction(self, "重做")
        redo.setShortcut(QKeySequence.Redo)
        undo.setIcon(icon("undo"))
        redo.setIcon(icon("redo"))
        em.addAction(undo)
        em.addAction(redo)
        em.addSeparator()
        em.addAction(self._act("删除", self.delete_selected, QKeySequence.Delete))
        em.addAction(self._act("复制光路图元件", self.duplicate_selected, "Ctrl+D"))
        em.addAction(self._act("全选", self.select_all, QKeySequence.SelectAll))
        em.addSeparator()
        em.addAction(self._act("旋转 +45°", lambda: self.rotate_selected(45), "R"))
        em.addAction(self._act("旋转 −45°", lambda: self.rotate_selected(-45), "Shift+R"))
        em.addAction(self._act("旋转 +5°", lambda: self.rotate_selected(5), "]"))
        em.addAction(self._act("旋转 −5°", lambda: self.rotate_selected(-5), "["))
        em.addAction(self._act("按光束方向自动定向", self.auto_aim_selected, "A"))
        em.addSeparator()
        em.addAction(self._act("元件表…", self.show_parts_table, "Ctrl+T", icon_name="table"))
        self.a_bom = self._act("物料清单…", self.show_bom, "Ctrl+Shift+B", icon_name="bom")
        em.addAction(self.a_bom)

        vm = m.addMenu("视图(&V)")
        vm.addAction(self._act("光路图", lambda: self.tabs.setCurrentIndex(0), "Ctrl+1", icon_name="schematic"))
        vm.addAction(self._act("平台布局", lambda: self.tabs.setCurrentIndex(1), "Ctrl+2", icon_name="layout"))
        vm.addAction(self._act("3D", lambda: self.tabs.setCurrentIndex(2), "Ctrl+3", icon_name="3d"))
        vm.addAction(self._act("在光路图和平台布局之间切换", self.toggle_tab, "Ctrl+Tab"))
        vm.addSeparator()
        vm.addAction(self._act("适应窗口", self.fit_current, "F", icon_name="fit"))
        vm.addAction(self._act("缩放至所选对象", self.zoom_to_selection, "Z"))
        vm.addSeparator()
        vm.addAction(self._act("放大文字", lambda: self.scale_text(1.15), "Ctrl+="))
        vm.addAction(self._act("缩小文字", lambda: self.scale_text(1 / 1.15), "Ctrl+-"))
        vm.addAction(self._act("重置文字大小", lambda: self.scale_text(None), "Ctrl+0"))
        vm.addSeparator()
        self.a_lengths = self._act("在布局中显示光束长度", self.toggle_lengths, "Ctrl+L")
        self.a_lengths.setCheckable(True)
        vm.addAction(self.a_lengths)
        self.a_coords = self._act("在平台边缘显示孔位坐标", self.toggle_coords)
        self.a_coords.setCheckable(True)
        self.a_coords.setChecked(True)
        vm.addAction(self.a_coords)

        lm = m.addMenu("平台布局(&L)")
        lm.addAction(self._act("按光路图重新排布…", self.arrange_like_schematic))
        lm.addAction(self._act("显示重叠元件", self.show_clashes))

        self.a_sheet = self._act("实验记录表…", self.show_lab_sheet, "Ctrl+P", icon_name="sheet")
        fm.insertAction(fm.actions()[fm.actions().index(self.a_save) + 2], self.a_sheet)  # after Save As

        tb = self.addToolBar("工具")
        tb.setObjectName("tools")
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)  # icons with a short name under each
        tb.setIconSize(QSize(24, 24))
        for a in (self.a_new, self.a_open, self.a_save):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(undo)
        tb.addAction(redo)
        tb.addSeparator()
        self.a_select = self._act("选择或移动 (S)", lambda: self.set_mode(MODE_SELECT), "S", tb, "select")
        self.a_beam = self._act("绘制光束 (B)", lambda: self.set_mode(MODE_BEAM), "B", tb, "beam")
        self.a_point = self._act("添加功率测量点 (M)", lambda: self.set_mode(MODE_POINT), "M", tb, "point")
        self.a_ruler = self._act("测距 (L)", lambda: self.set_mode(MODE_RULER), "L", tb, "ruler")
        self._act("取消", lambda: self.set_mode(MODE_SELECT), "Esc")
        for a in (self.a_select, self.a_beam, self.a_point, self.a_ruler):
            a.setCheckable(True)
        # tools that only make sense on one tab are hidden on the other
        self.sch_only = [self.a_beam, tb.addSeparator(), tb.addWidget(QLabel("新光束："))]
        self.wl_combo = QComboBox()
        for name, (wl, color) in WAVELENGTH_COLORS.items():
            self.wl_combo.addItem(swatch_icon(color), name, (wl, color))
        self.sch_only.append(tb.addWidget(self.wl_combo))
        self.layout_only = [self.a_point, self.a_ruler, tb.addSeparator(), tb.addWidget(QLabel("吸附："))]
        self.snap_combo = QComboBox()
        self.snap_combo.addItem("孔位 (25.4 mm)", LayoutScene.SNAP_HOLES)
        self.snap_combo.addItem("半格 (12.7 mm)", LayoutScene.SNAP_HALF)
        self.snap_combo.addItem("不吸附", LayoutScene.SNAP_FREE)
        self.snap_combo.currentIndexChanged.connect(
            lambda i: setattr(self.scene, "snap_mode", self.snap_combo.itemData(i)))
        self.layout_only.append(tb.addWidget(self.snap_combo))
        tb.addSeparator()
        self._act("适应窗口 (F)", self.fit_current, None, tb, "fit")
        self._act("元件表 (Ctrl+T)", self.show_parts_table, None, tb, "table")
        tb.addAction(self.a_bom)
        self.a_bigger = self._act("放大文字 (Ctrl+=)", lambda: self.scale_text(1.15), None, tb, "bigger")
        self.a_smaller = self._act("缩小文字 (Ctrl+−)", lambda: self.scale_text(1 / 1.15), None, tb, "smaller")
        tb.addSeparator()
        tb.addAction(self.a_sheet)
        # layouts in the same folder, to switch between them (switcher.py)
        from .switcher import LayoutSwitcher
        tb.addSeparator()
        tb.addWidget(QLabel("布局："))
        self.switcher = LayoutSwitcher(lambda: self.path, self._last_folder, lambda p: self.switch_to(p),
                                       lambda: self.open_file())
        tb.addWidget(self.switcher)
        # short names under the toolbar icons; menus and tooltips keep the full text
        short = {"新建": "新建", "打开…": "打开", "保存": "保存", "选择或移动 (S)": "选择",
                 "绘制光束 (B)": "光束", "添加功率测量点 (M)": "测功率", "测距 (L)": "测距",
                 "适应窗口 (F)": "适应窗口", "元件表 (Ctrl+T)": "元件", "物料清单…": "物料清单",
                 "放大文字 (Ctrl+=)": "A+", "缩小文字 (Ctrl+−)": "A−", "实验记录表…": "记录表"}
        for a in tb.actions():
            if a.text() in short:
                a.setToolTip(a.toolTip())  # fix the tooltip before the short name could become it
                a.setIconText(short[a.text()])
        undo.setIconText("撤销")
        redo.setIconText("重做")

    def update_snap_labels(self):
        """The snap choices name this board's hole spacing."""
        t = self.scene.layout.table
        what = "孔位" if t.grid_holes else "网格"
        self.snap_combo.setItemText(0, f"{what} ({t.hole_pitch:g} mm)" if t.has_grid else "孔位（仅预钻孔）")
        self.snap_combo.setItemText(1, f"半格{what} ({t.hole_pitch / 2:g} mm)"
                                    + ("，含中心孔" if t.center_holes else ""))

    def beam_style(self):
        return self.wl_combo.currentData()

    def on_schematic(self) -> bool:
        return self.tabs.currentIndex() == 0

    def set_mode(self, mode):
        sch = self.on_schematic()
        if sch and mode in (MODE_POINT, MODE_RULER):
            self.statusBar().showMessage("请在「平台布局」选项卡使用测量点和测距功能 (Ctrl+2)。", 5000)
            return
        if not sch and mode == MODE_BEAM:
            self.statusBar().showMessage("请在「光路图」选项卡绘制光束 (Ctrl+1)，平台布局会同步更新。", 5000)
            mode = MODE_SELECT
        self.a_select.setChecked(mode == MODE_SELECT)
        self.a_beam.setChecked(mode == MODE_BEAM)
        self.a_point.setChecked(mode == MODE_POINT)
        self.a_ruler.setChecked(mode == MODE_RULER)
        if sch:
            self.sch_page.set_mode(MODE_LINK if mode == MODE_BEAM else mode)
            return
        self.mode = mode
        if mode != MODE_RULER:
            self.view.ruler = None
        self.view.setCursor(Qt.CrossCursor if mode == MODE_RULER else Qt.ArrowCursor)
        self.view.setDragMode(QGraphicsView.RubberBandDrag if mode == MODE_SELECT else QGraphicsView.NoDrag)
        hints = {MODE_SELECT: '平台布局：拖动元件可移动位置，按住 Alt 可取消吸附。方向键移动一孔，Shift + 方向键移动 1 mm。R 或 [ ] 旋转，A 按光束自动定向。双击元件可在光路图中编辑。',
                 MODE_POINT: '单击光束可在中点添加功率测量点，之后可沿光束拖动。单击光纤耦合器可测量光纤输出。添加后返回选择工具。按住 Shift 可连续添加，Esc 退出。',
                 MODE_RULER: '拖动以测距。端点吸附到元件或孔位，按住 Alt 可取消吸附。选择两个元件可查看两者之间的光程。Esc 退出。'}
        self.statusBar().showMessage(hints[mode])
        self.view.viewport().update()

    def show_cursor(self, pt):
        h = self.scene.layout.table.hole_at(pt.x(), pt.y())
        hole = f"   hole {h[0]}" if h and abs(h[1]) < 6 and abs(h[2]) < 6 else ""
        self.pos_lbl.setText(f"x = {pt.x():7.1f} mm   y = {pt.y():7.1f} mm{hole}")

    def show_ruler(self, a, b):
        L = math.hypot(b.x() - a.x(), b.y() - a.y())
        self.statusBar().showMessage(f"测距：{L:.1f} mm ({L / 25.4:.3f} in), dx {b.x() - a.x():+.1f} mm, "
                                     f"dy {b.y() - a.y():+.1f} mm")

    def toggle_lengths(self, on):
        self.scene.show_lengths = bool(on)
        self.scene.layout_annotations()
        self.scene.update()

    def toggle_coords(self, on):
        self.scene.show_coords = bool(on)
        self.scene.update()

    # ---- edits ----------------------------------------------------------------
    def delete_selected(self):
        if self.on_schematic():
            self.sch_page.delete_selected()
            return
        points = self.scene.selected_points()
        if points:
            self.scene.undo.push(DeleteCmd(self.scene, [], [], points))
        elif any(self.scene.selected_ids()):
            self.statusBar().showMessage("请在「光路图」中删除元件和光束，平台布局会同步更新。",
                                         6000)

    def duplicate_selected(self):
        if not self.on_schematic():
            self._sch_sel_to_front()
        self.sch_page.duplicate_selected()

    def _sch_sel_to_front(self):
        self.tabs.setCurrentIndex(0)

    def select_all(self):
        sc = self.sch_scene if self.on_schematic() else self.scene
        for it in sc.items():
            if it.flags() & it.GraphicsItemFlag.ItemIsSelectable and not isinstance(it, PointItem):
                it.setSelected(True)

    def nudge_selected(self, dx, dy, fine=False):
        sc = self.scene
        t = sc.layout.table
        if fine or sc.snap_mode == LayoutScene.SNAP_FREE:
            step = 1.0
        else:
            step = t.hole_pitch if sc.snap_mode == LayoutScene.SNAP_HOLES else t.hole_pitch / 2
        comps, _ = sc.selected_ids()
        lc = sc.layout.components
        ch = {c: ({"x": lc[c].x, "y": lc[c].y, "pinned": lc[c].pinned},
                  {"x": lc[c].x + dx * step, "y": lc[c].y + dy * step, "pinned": True}) for c in comps}
        if ch:
            sc.undo.push(SetFieldsCmd(sc, ch, "微调位置"))

    def auto_aim_selected(self):
        if self.on_schematic():
            els, _ = self.sch_scene.selected_ids()
            ch = {e: ({"auto_angle": self.sch_scene.sch.elements[e].auto_angle}, {"auto_angle": True}) for e in els}
            if ch:
                self.scene.undo.push(SchSetFieldsCmd(self.sch_scene, ch, "自动定向"))
            return
        comps, _ = self.scene.selected_ids()
        ch = {c: ({"auto_angle": self.scene.layout.components[c].auto_angle}, {"auto_angle": True}) for c in comps}
        if ch:
            self.scene.undo.push(SetFieldsCmd(self.scene, ch, "自动定向"))

    def show_parts_table(self):
        if getattr(self, "_parts_table", None) is None:
            self._parts_table = PartsTable(self.sch_scene, self)
        else:
            self._parts_table.reload()
        self._parts_table.show()
        self._parts_table.raise_()

    def show_bom(self):
        if getattr(self, "_bom", None) is None:
            from .bom import BomDialog
            self._bom = BomDialog(lambda: self.scene.layout, self.scene.edited, self)
        self._bom.show()
        self._bom.raise_()

    def export_bom(self):
        from .bom import bill_of_materials, write_bom_csv
        p, _ = QFileDialog.getSaveFileName(self, "导出物料清单", "bom.csv", "CSV (*.csv)")
        if p:
            write_bom_csv(bill_of_materials(self.scene.layout), p)
            self.statusBar().showMessage(f"物料清单已保存至 {p}", 5000)

    def toggle_tab(self):
        self.tabs.setCurrentIndex(1 if self.tabs.currentIndex() != 1 else 0)

    def fit_current(self):
        if self.tabs.currentIndex() == 2:
            if self.view3d is not None:
                self.view3d.fit()
        elif self.on_schematic():
            self.sch_page.view.fit()
        else:
            self.view.fit()

    def zoom_to_selection(self):
        view, sc = (self.sch_page.view, self.sch_scene) if self.on_schematic() else (self.view, self.scene)
        sel = sc.selectedItems()
        if not sel:
            return self.fit_current()
        r = sel[0].sceneBoundingRect()
        for it in sel[1:]:
            r = r.united(it.sceneBoundingRect())
        view.fitInView(r.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)

    def scale_text(self, k):
        v = 1.0 if k is None else min(4.0, max(0.4, self.scene.text_scale * k))
        self.scene.set_text_scale(v)
        self.sch_scene.set_text_scale(v)
        self.settings.setValue("text_scale", v)
        self.statusBar().showMessage(f"文字大小：{v * 100:.0f} %", 3000)

    def edit_in_schematic(self, obj):
        """Cross-probe: jump to the schematic with this part (or beam) selected."""
        self.tabs.setCurrentIndex(0)
        self.sch_scene.clearSelection()
        if isinstance(obj, Component) and obj.sch_id in self.sch_scene.el_items:
            it = self.sch_scene.el_items[obj.sch_id]
        elif isinstance(obj, Beam) and obj.id in self.sch_scene.link_items:
            it = self.sch_scene.link_items[obj.id]
        else:
            return
        it.setSelected(True)
        self.sch_page.view.centerOn(it)
        self.sch_page.props.label.setFocus()

    def arrange_like_schematic(self):
        """Move every part to the schematic's arrangement, scaled onto the table (undoable)."""
        lay = self.scene.layout
        if not lay.components:
            return
        r = QMessageBox.question(self, "按光路图重新排布",
                                 '要按光路图重新放置所有元件吗？\n当前的位置会被覆盖，可按 Ctrl+Z 撤销。')
        if r != QMessageBox.Yes:
            return
        self._arrange()

    def _arrange(self):
        lay = self.scene.layout
        saved = {c.id: (c.x, c.y) for c in lay.components.values()}
        ch = {}
        placed = []
        for c in lay.components.values():
            el = lay.schematic.elements.get(c.sch_id)
            if el is None:
                continue
            others = lay.components
            lay.components = {o.id: o for o in placed}  # only already-arranged parts block holes
            x, y = self.scene._new_part_position(c, el, True)
            lay.components = others
            placed.append(type(c)(**{**c.__dict__, "x": x, "y": y}))
            ch[c.id] = ({"x": saved[c.id][0], "y": saved[c.id][1], "pinned": c.pinned},
                        {"x": x, "y": y, "pinned": False})
        if ch:
            self.scene.undo.push(SetFieldsCmd(self.scene, ch, "按光路图重新排布"))

    def show_clashes(self):
        self.tabs.setCurrentIndex(1)
        self.scene.clearSelection()
        for cid in self.scene.clashes:
            self.scene.comp_items[cid].setSelected(True)
        n = len(self.scene.clashes)
        self.statusBar().showMessage(f"{n} 个元件与其他元件重叠" if n else "没有重叠元件", 6000)
        if n:
            self.zoom_to_selection()

    # ---- schematic <-> layout ----------------------------------------------------
    def request_fit(self, *tabs):
        self._fit_pending.update(tabs or (0, 1))
        QTimer.singleShot(0, self._fit_pending_views)

    def _fit_pending_views(self):
        """Fit a tab the first time it is shown after a file opens. A hidden tab
        has no real size yet, so fitting it then leaves it zoomed into a corner."""
        idx = self.tabs.currentIndex()
        if idx in self._fit_pending and self.isVisible():
            self._fit_pending.discard(idx)
            self.fit_current()

    def _ensure_view3d(self):
        """Build the 3D view on first use (it loads VTK, which takes a moment)."""
        if self.view3d is not None or self._view3d_loading:
            return
        lay = self.view3d_holder.layout()
        self._view3d_loading = True
        loading = QWidget()
        lv = QVBoxLayout(loading)
        lv.addStretch(1)
        msg = QLabel("正在加载 3D 渲染引擎…")
        msg.setAlignment(Qt.AlignCenter)
        lv.addWidget(msg)
        bar = QProgressBar()
        bar.setRange(0, 0)  # busy
        bar.setFixedWidth(320)
        bar.setTextVisible(False)
        lv.addWidget(bar, 0, Qt.AlignHCenter)
        lv.addStretch(1)
        lay.addWidget(loading)
        for _ in range(3):  # paint the message before the import blocks for a moment
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
        try:
            from .view3d import make_view3d_widget
            self.view3d = make_view3d_widget(lambda: self.scene.layout, lambda: self.scene.latest,
                                             self.open_point_log, self.a_blender)
        except Exception as e:  # pyvista missing or no OpenGL
            self._drop(loading)
            self._view3d_loading = False
            msg = QLabel(f"3D 视图需要安装 pyvista 和 pyvistaqt。\n\n    python -m pip install pyvista "
                         f"pyvistaqt\n\n({type(e).__name__}: {e})")
            msg.setAlignment(Qt.AlignCenter)
            msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(msg)
            self.view3d = False
            return
        self._drop(loading)
        self._view3d_loading = False
        lay.addWidget(self.view3d)
        self.scene.edited.connect(self.view3d.schedule)

    def _drop(self, widget):
        """Take a widget out now (deleteLater alone waits for the event loop)."""
        self.view3d_holder.layout().removeWidget(widget)
        widget.hide()
        widget.deleteLater()

    def _tab_changed(self, idx):
        QTimer.singleShot(0, self._fit_pending_views)
        sch = idx == 0
        if idx == 2:
            self._ensure_view3d()
        for d in self.layout_docks:
            d.setVisible(idx == 1)
        for a in self.layout_only:
            a.setVisible(idx == 1)
            a.setEnabled(idx == 1)
        for a in self.sch_only:
            a.setVisible(sch)
            a.setEnabled(sch)
        self.set_mode(MODE_SELECT)
        if idx == 2:
            self.statusBar().showMessage('3D 视图：拖动旋转，滚轮缩放，Shift + 拖动平移，F 适应窗口。可在「平台布局」中移动元件。')
        if sch:
            self.sch_scene.refresh_status()
        else:
            sel = self.scene.selectedItems()
            if sel:
                self.view.ensureVisible(sel[0], 80, 80)

    def _schematic_changed(self):
        created = self.scene.sync_from_schematic()
        if created:
            waiting = [c for c in created if c in self.scene.off_table()]
            if waiting:
                self.statusBar().showMessage(
                    f"「平台布局」中有 {len(waiting)} 个新元件等待放置。请拖到"
                    "平台上。", 8000)
        self._layers_changed()

    def _layers_changed(self):
        self.sch_scene.refresh_status()
        self.sch_scene.update()
        self.scene.update()

    def _layout_sel_to_sch(self):
        """Cross-probe: selecting parts in the layout selects their schematic elements."""
        if self._syncing_sel:
            return
        try:
            comps, _ = self.scene.selected_ids()
        except RuntimeError:
            return
        ids = {self.scene.layout.components[c].sch_id for c in comps}
        self._syncing_sel = True
        try:
            for eid, it in self.sch_scene.el_items.items():
                it.setSelected(eid in ids)
        finally:
            self._syncing_sel = False

    def _sch_sel_to_layout(self):
        if self._syncing_sel:
            return
        try:
            els, _ = self.sch_scene.selected_ids()
        except RuntimeError:
            return
        els = set(els)
        self._syncing_sel = True
        try:
            for cid, it in self.scene.comp_items.items():
                it.setSelected(bool(self.scene.layout.components[cid].sch_id) and
                               self.scene.layout.components[cid].sch_id in els)
        finally:
            self._syncing_sel = False

    # ---- power logger --------------------------------------------------------
    def add_point_on(self, beam_id: str, click: QPointF | None = None) -> MeasurementPoint:
        lay = self.scene.layout
        t = 0.5
        if click is not None and lay.points_on(beam_id):
            # midpoint is taken: put the new point where the user clicked
            line = self.scene.beam_items[beam_id].line()
            d = line.p2() - line.p1()
            L2 = d.x() ** 2 + d.y() ** 2 or 1
            q = click - line.p1()
            t = min(0.97, max(0.03, (q.x() * d.x() + q.y() * d.y()) / L2))
        pt = MeasurementPoint(id=new_id("mp"), label=lay.next_point_label(), beam_id=beam_id, t=t)
        self.scene.undo.push(AddPointCmd(self.scene, pt))
        if self.logbook:
            self.logbook.register_point(pt.id, pt.label)
        return lay.points[pt.id]

    def add_fiber_point(self, comp_id: str) -> MeasurementPoint:
        """A point at a fiber coupler's fiber end: the power after fiber coupling.
        One per coupler; clicking a coupler that has one opens its log."""
        lay = self.scene.layout
        have = [p for p in lay.points_at_part(comp_id) if not p.archived]
        if have:
            self.open_point_log(have[0].id)
            return have[0]
        pt = MeasurementPoint(id=new_id("mp"), label=lay.next_point_label(), beam_id=None, part_id=comp_id)
        self.scene.undo.push(AddPointCmd(self.scene, pt))
        if self.logbook:
            self.logbook.register_point(pt.id, pt.label)
        return lay.points[pt.id]

    def _ensure_logbook(self) -> bool:
        if self.logbook:
            return True
        if self._no_log:
            QMessageBox.information(self, "功率日志", '当前布局未关联功率日志，无法记录读数。请重新打开并选择日志，或将布局另存为新文件后开始记录。')
            return False
        QMessageBox.information(self, "功率日志", '请先保存布局。功率日志（<布局文件名>.logbook.sqlite）会保存在同一目录。')
        self.save_as()
        return self.logbook is not None

    def open_point_log(self, pid: str):
        pt = self.scene.layout.points.get(pid)
        if pt is None or not self._ensure_logbook():
            return
        dlg = self._dialogs.get(pid)
        if dlg is None:
            lay = self.scene.layout
            b = lay.beams.get(pt.beam_id or "")
            part = lay.components.get(pt.part_id or "")
            if b:
                names = [lay.components[c].label or SYMBOLS[lay.components[c].type].name for c in (b.source, b.target)]
                desc = f"on beam {names[0]} → {names[1]}"
            elif part is not None:
                desc = f"{part.label or SYMBOLS[part.type].name} 的光纤输出（耦合后功率）"
                b = next((x for x in lay.beams.values() if x.target == part.id), None)  # for the wavelength
            else:
                desc = "未关联光束"
            dlg = MeasurementDialog(self.logbook, pt, desc, b.wavelength_nm if b else None, self)
            self._title_log(dlg)
            dlg.changed.connect(self.refresh_measurements)
            dlg.finished.connect(lambda _r, pid=pid: self._dialogs.pop(pid, None))
            self._dialogs[pid] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _title_log(self, dlg):
        """A log window's title, with the point's lab sheet name if it has one."""
        name = self.scene.layout.point_name(dlg.point.id)
        dlg.setWindowTitle(f"{dlg.point.label}{f' · {name}' if name else ''} — 功率日志")

    def show_lab_sheet(self):
        """Printable sheet of chosen points: names, latest power, the layout picture."""
        from .labsheet import PICTURE_PX, LabSheetDialog
        if not [p for p in self.scene.layout.points.values() if not p.archived]:
            QMessageBox.information(self, "实验记录表", '还没有测量点。请先在「平台布局」中添加 (M)。')
            return
        dlg = LabSheetDialog(self.scene.layout, self.logbook, self.path.name if self.path else "未命名",
                             lambda: render_scene_image(self.scene, PICTURE_PX), self.store_lab_sheet, self)
        dlg.exec()

    def store_lab_sheet(self, sheet):
        from .scene import SetLabSheetCmd
        self.scene.undo.push(SetLabSheetCmd(self.scene, sheet))
        for d in self._dialogs.values():
            self._title_log(d)

    def _poll_logbook(self):
        """Refresh the power labels and open log windows when another program wrote to the log."""
        try:
            changed = self.logbook is not None and self.logbook.changed_on_disk()
        except Exception:  # noqa: BLE001 - a busy or vanished file: look again next time
            return
        if changed:
            self.refresh_measurements()
            for d in self._dialogs.values():
                d.reload()

    def refresh_measurements(self):
        lay = self.scene.layout
        latest = self.logbook.latest_two() if self.logbook else {}
        pics = self.logbook.picture_counts() if self.logbook else {}
        self.scene.set_latest(latest)
        self.points_panel.refresh(list(lay.points.values()), latest, pics)
        if getattr(self, "view3d", None):
            self.view3d.schedule()  # new readings show on the 3D sensors

    def ask_missing_log(self, path: Path) -> str:
        """The layout has measurement points but no log next to it: "choose",
        "new" or "none". Nobody can answer on a headless (test) display: new."""
        if QApplication.platformName() in ("offscreen", "minimal"):
            return "new"
        box = QMessageBox(QMessageBox.Question, "功率日志",
                          f"未找到 {path.name} 的功率日志。应将 {logbook_path_for(path).name} 放在同一目录。",
                          QMessageBox.NoButton, self)
        box.setInformativeText('读数可能保存在其他位置。首次记录读数时才会创建新日志。')
        choose = box.addButton("选择日志文件…", QMessageBox.AcceptRole)
        new = box.addButton("使用新日志", QMessageBox.YesRole)
        box.addButton("打开布局（不加载日志）", QMessageBox.RejectRole)
        box.setDefaultButton(choose)
        box.exec()
        return "choose" if box.clickedButton() is choose else "new" if box.clickedButton() is new else "none"

    def _attach_for_open(self, path: Path):
        """Attach the layout's log; if it is missing and the layout has points, ask."""
        self._no_log = False
        lb = logbook_path_for(path)
        if lb.exists() or not self.scene.layout.points:
            return self._attach_logbook(path)
        while True:
            choice = self.ask_missing_log(path)
            if choice == "new":
                return self._attach_logbook(path)
            if choice == "none":
                self._no_log = True
                self._log_layout = path
                return self.refresh_measurements()
            src, _ = QFileDialog.getOpenFileName(self, "选择功率日志", str(path.parent),
                                                 "功率日志 (*.sqlite);;所有文件 (*)")
            how = self.ask_copy_or_use(Path(src), path) if src else None
            if how == "copy":
                import shutil
                shutil.copy2(src, lb)
                return self._attach_logbook(path)
            if how == "use":
                return self._attach_logbook(path, Path(src))

    def ask_copy_or_use(self, src: Path, path: Path) -> str | None:
        """A log file picked for a layout: "copy" it next to the layout, "use" it where it is, or None."""
        box = QMessageBox(QMessageBox.Question, "功率日志", f"为 {path.name} 使用 {src.name}：",
                          QMessageBox.Cancel, self)
        copy = box.addButton(f"复制为 {logbook_path_for(path).name}", QMessageBox.AcceptRole)
        use = box.addButton("使用原位置的日志", QMessageBox.YesRole)
        box.setInformativeText('复制日志后，副本会保存在布局旁，以后与布局一起打开。使用原位置的日志时，只在本次会话向原文件写入读数。')
        box.exec()
        return "copy" if box.clickedButton() is copy else "use" if box.clickedButton() is use else None

    def _attach_logbook(self, path: Path, log_path: Path | None = None):
        self._no_log = False
        self._log_layout = path
        old = self.logbook
        new_path = log_path or logbook_path_for(path)
        if (old is not None and not old.in_memory and old.path.resolve() != new_path.resolve()
                and not new_path.exists()):
            # Save As to a new place: carry the history along
            import sqlite3
            dst = sqlite3.connect(str(new_path))
            old.db.backup(dst)
            dst.close()
        if old is not None:
            old.close()
        for d in list(self._dialogs.values()):
            d.close()
        self.logbook = Logbook(new_path)
        for pt in self.scene.layout.points.values():
            self.logbook.register_point(pt.id, pt.label)
        self.refresh_measurements()

    def export_csv(self):
        if not self._ensure_logbook():
            return
        p, _ = QFileDialog.getSaveFileName(self, "导出功率日志", "power_log.csv", "CSV (*.csv)")
        if p:
            labels = {pid: pt.label for pid, pt in self.scene.layout.points.items()}
            labels.update({pid: lbl for pid, lbl in self.logbook.known_points() if pid not in labels})
            n = export_power_csv(self.logbook, labels, p)
            self.statusBar().showMessage(f"已将 {n} 条读数导出至 {p}", 5000)

    def rotate_selected(self, delta):
        if self.on_schematic():
            self.sch_page.rotate_selected(delta)
            return
        comps, _ = self.scene.selected_ids()
        changes = {}
        for cid in comps:
            c = self.scene.layout.components[cid]
            changes[cid] = ({"angle": c.angle, "auto_angle": c.auto_angle},
                            {"angle": (c.angle + delta) % 360, "auto_angle": False})
        if changes and any(c["auto_angle"] for c, _n in changes.values()):
            self.statusBar().showMessage('手动旋转后，所选元件的自动定向已关闭。按 A 可重新开启。', 6000)
        if changes:
            self.scene.undo.push(SetFieldsCmd(self.scene, changes, "旋转"))

    def edit_table(self):
        t = self.scene.layout.table
        dlg = BoardDialog(t, self)
        if dlg.exec() == QDialog.Accepted:
            old_style = t.style
            dlg.apply(t)
            if self.view3d is not None and t.style != old_style:
                self.view3d.board_changed(old_style)
            self.scene.set_layout(self.scene.layout)
            self.update_snap_labels()
            self.request_fit(1)

    # ---- files ----------------------------------------------------------------
    def _update_title(self):
        name = self.path.name if self.path else "未命名"
        try:
            star = "" if self.scene.undo.isClean() else " *"
        except RuntimeError:  # undo stack already destroyed during shutdown
            return
        self.setWindowTitle(f"{name}{star} — Optical Layout Designer")

    def save_prompt(self) -> QMessageBox:
        """Word-style: Save / Don't Save / Cancel; Enter saves, Esc cancels."""
        box = QMessageBox(QMessageBox.Warning, "Optical Layout Designer",
                          f"要保存对 {self.path.name if self.path else '未命名'} 的更改吗？",
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
        box.button(QMessageBox.Discard).setText("不保存")
        box.setDefaultButton(QMessageBox.Save)
        box.setEscapeButton(QMessageBox.Cancel)
        return box

    def _confirm_discard(self) -> bool:
        """True when it is fine to drop the current layout (saved first if asked)."""
        if self.scene.undo.isClean():
            return True
        r = self.save_prompt().exec()
        if r == QMessageBox.Save:
            self.save_file()  # Save As when untitled; cancelling that keeps the window
            return self.scene.undo.isClean()
        return r == QMessageBox.Discard

    def new_file(self):
        if self._confirm_discard():
            self.scene.set_layout(Layout())
            self.sch_scene.set_layout(self.scene.layout)
            self.props.show_obj(None)
            self.path = None
            self._no_log, self._log_layout = False, None
            if self.logbook:
                self.logbook.close()
                self.logbook = None
            self.switcher.refresh()
            self.refresh_measurements()
            self._update_title()
            self.request_fit()

    def _last_folder(self) -> Path | None:
        f = self.settings.value("last_folder", "")
        return Path(f) if f else None

    def switch_to(self, p: Path) -> bool:
        """Open another layout (the folder drop-down); False if the user cancelled."""
        if not self._confirm_discard():
            return False
        self.open_path(p)
        return True

    def open_file(self):
        if not self._confirm_discard():
            return
        start = self.path.parent if self.path else self._last_folder()
        p, _ = QFileDialog.getOpenFileName(self, "打开布局", str(start or ""), "布局文件 (*.json)")
        if p:
            self.open_path(p)

    def open_path(self, p):
        if self.logbook:
            self.logbook.close()
            self.logbook = None
        lay = Layout.load(p)
        if lay.components and not lay.schematic.elements:
            lay.schematic_from_layout()  # older file: build its schematic once
        self.scene.set_layout(lay)
        self.sch_scene.set_layout(self.scene.layout)
        self.scene.sync_from_schematic()
        self.props.show_obj(None)  # the board summary of the file just opened
        self.update_snap_labels()
        if self.view3d:
            self.view3d.reset_for_new_file()
        self.path = Path(p)
        self._attach_for_open(self.path)
        self._update_title()
        self.settings.setValue("last_folder", str(self.path.parent))
        self.switcher.refresh()
        lay = self.scene.layout
        self.tabs.setCurrentIndex(0 if lay.schematic.elements and not lay.components else 1)
        self.request_fit()
        self.scene.undo.setClean()

    def save_file(self):
        if self.path is None:
            return self.save_as()
        self.scene.layout.save(self.path)
        self.settings.setValue("last_folder", str(self.path.parent))
        if self._log_layout != self.path or (self.logbook is None and not self._no_log):  # new file or Save As
            self._attach_logbook(self.path)
            self.switcher.refresh()
        else:
            for pt in self.scene.layout.points.values():
                self.logbook.register_point(pt.id, pt.label)
        self.scene.undo.setClean()
        self._update_title()

    def save_as(self):
        p, _ = QFileDialog.getSaveFileName(self, "保存布局", "layout.json", "布局文件 (*.json)")
        if p:
            self.path = Path(p)
            self.save_file()

    def export(self, kind):
        if self.tabs.currentIndex() == 2:  # 3D: save what the view shows
            if self.view3d:
                p, _ = QFileDialog.getSaveFileName(self, "保存 3D 视图", "board_3d.png", "PNG (*.png)")
                if p:
                    self.view3d.plotter.screenshot(p)
            return
        sch = self.on_schematic()
        p, _ = QFileDialog.getSaveFileName(self, "导出", f"{'schematic' if sch else 'layout'}.{kind}", f"*.{kind}")
        if p:
            export_scene(self.sch_scene if sch else self.scene, p)

    def open_in_blender(self):
        if self._blender_job is not None:
            return
        blender_app = next((folder / "Blender.app" for folder in
                            (Path("/Applications"), Path.home() / "Applications")
                            if (folder / "Blender.app/Contents/MacOS/Blender").is_file()), None)
        if blender_app is None:
            QMessageBox.warning(self, "找不到 Blender", "请将 Blender.app 放在「应用程序」目录中。")
            return

        options = QDialog(self)
        options.setWindowTitle("导出到 Blender")
        form = QVBoxLayout(options)
        names = QCheckBox("附带元器件名称")
        width = QCheckBox("按束径显示光束")
        width.setChecked(bool(self.view3d and self.view3d.physical_beams.isChecked()))
        form.addWidget(names)
        form.addWidget(width)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("导出并打开")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(options.accept)
        buttons.rejected.connect(options.reject)
        form.addWidget(buttons)
        confirmed = options.exec() == QDialog.Accepted
        include_names = names.isChecked()
        physical_beams = width.isChecked()
        options.deleteLater()
        if not confirmed:
            return

        work = QTemporaryDir()
        if not work.isValid():
            QMessageBox.warning(self, "无法生成 Blender 项目", "无法创建临时导出目录。")
            return
        snapshot = Path(work.path()) / "layout.json"
        layout = self.scene.layout
        try:
            layout.save(snapshot)
        except OSError as error:
            work.remove()
            QMessageBox.warning(self, "无法保存布局快照", str(error))
            return

        height = (self.view3d.beam_h.value() if self.view3d
                  else BOARD_BEAM_HEIGHT.get(layout.table.style, DEFAULT_BEAM_HEIGHT))
        name = self.path.stem if self.path else "未命名布局"
        process = QProcess(self)
        process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        process.setProcessChannelMode(QProcess.MergedChannels)
        self._blender_job = process
        self.a_blender.setEnabled(False)
        self.statusBar().showMessage("正在生成 Blender 项目…")

        def finished(code, _status=None):
            if self._blender_job is not process:
                return
            self._blender_job = None
            self.a_blender.setEnabled(True)
            try:
                if process.property("cancelled"):
                    return
                if code != 0:
                    detail = bytes(process.readAllStandardOutput()).decode("utf-8", "replace").strip()
                    raise OSError(detail[-1600:] or process.errorString())
                result = self._publish_blender_project(snapshot.with_suffix(".blend"), name)
                started, _pid = QProcess.startDetached("/usr/bin/open", ["-n", "-a", str(blender_app), str(result)])
                if not started:
                    raise OSError(f"项目已保存，但无法启动 Blender。\n{result}")
                self.statusBar().showMessage(f"已交给 Blender 打开：{result}", 12000)
            except OSError as error:
                self.statusBar().clearMessage()
                QMessageBox.warning(self, "无法打开 Blender 项目", str(error))
            finally:
                work.remove()
                process.deleteLater()

        process.finished.connect(finished)
        process.errorOccurred.connect(lambda error: finished(-1) if error == QProcess.FailedToStart else None)
        arguments = ["-B", "-m", "optolayout.blender_export", str(snapshot), str(height),
                     str(blender_app / "Contents/MacOS/Blender")]
        if include_names:
            arguments.append("--component-labels")
        if physical_beams:
            arguments.append("--physical-beams")
        process.start(sys.executable, arguments)

    def _publish_blender_project(self, source, name):
        from datetime import datetime
        import os
        import shutil
        import tempfile
        from uuid import uuid4

        directory = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "Blender"
        directory.mkdir(parents=True, exist_ok=True)
        name = name.encode("utf-8")[:180].decode("utf-8", "ignore") or "布局"
        destination = directory / f"{name}-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.blend"
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            try:
                with source.open("rb") as incoming:
                    shutil.copyfileobj(incoming, output)
                output.close()
                os.link(temporary, destination)
            finally:
                temporary.unlink()
        return destination

    def _web_state(self, state: str) -> None:
        """The dot in front of the web status: green serving, grey off or served elsewhere, red unavailable."""
        color = {"green": "#2e9e44", "grey": "#9aa0a6", "red": "#d62728"}[state]
        self.web_dot.setStyleSheet(f"color: {color}; font-size: 14px")
        self.web_corner.adjustSize()
        self.menuBar().setCornerWidget(self.web_corner, Qt.TopRightCorner)  # makes the menu bar re-measure it

    def set_web(self, on: bool, remember: bool = True) -> None:
        """Start or stop serving the web pages (see web/embed.py)."""
        if remember:
            self.settings.setValue("web_on", bool(on))
        self.a_web.setChecked(on)
        if not on:
            if self.web is not None:
                self.web.stop()
            self.web_lbl.setText("网页访问：已关闭")
            self._web_state("grey")
            self.web_lbl.setToolTip("在「文件 → 网页访问」中开启。")
            return
        if self.web is not None and self.web.status == "running":
            return
        try:
            from web.embed import WebShare
        except ImportError as e:
            self.web_lbl.setText("网页访问：不可用")
            self.web_lbl.setToolTip(f"无法加载网页目录（{e}）")
            self._web_state("red")
            return
        self.web = WebShare(self.web_config)  # exactly the folders in web/config.json
        status = self.web.start()
        url = self.web.url
        if status == "running":
            self.web_lbl.setText(f'网页访问：<a href="{url}">{url}</a>')
            self._web_state("green")
            self.web_lbl.setToolTip("实验室局域网内的其他设备可打开此地址。右键或选中文字可复制。")
        elif status == "busy":
            self.web_lbl.setText(f'网页服务已在运行：<a href="{url}">{url}</a>')
            self._web_state("grey")
            self.web_lbl.setToolTip('另一个程序窗口或 start_web.bat 已在此端口提供网页访问。')
        else:
            self.web_lbl.setText("网页访问：不可用")
            self.web_lbl.setToolTip(self.web.error)
            self._web_state("red")
            self.statusBar().showMessage(f"网页访问不可用：{self.web.error}", 10000)

    def closeEvent(self, e):
        if self._confirm_discard():
            if self._blender_job is not None:
                process = self._blender_job
                process.setProperty("cancelled", True)
                process.kill()
                process.waitForFinished(2000)
            if self.web is not None:
                self.web.stop()
            e.accept()
        else:
            e.ignore()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._fit_pending_views)


def render_scene_image(scene: LayoutScene, width_px: int) -> QImage:
    """The board as export_scene draws it, as an image width_px wide."""
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        src = export_rect(scene)
        export_scene(scene, tmp, px_per_mm=width_px / max(src.width(), 1))
        return QImage(tmp)
    finally:
        os.remove(tmp)


def export_rect(scene) -> QRectF:
    """The area an export shows: the board with its labels and legend."""
    if hasattr(scene, "table_rect"):
        m = 30 if getattr(scene, "show_coords", False) else 10  # room for the hole letters / numbers
        src = scene.table_rect().adjusted(-m, -m, m, m + 10)
        if hasattr(scene, "name_rect"):
            src = src.united(scene.name_rect().adjusted(-5, -5, 5, 5))
        if hasattr(scene, "legend_rect") and not scene.legend_rect().isEmpty():
            src = src.united(scene.legend_rect().adjusted(-5, -5, 5, 5))
        for it in getattr(scene, "point_items", {}).values():  # callouts off the board (fiber ends)
            src = src.united(it.sceneBoundingRect().adjusted(-5, -5, 5, 5))
        return src
    return scene.items_rect().adjusted(-30, -30, 30, 30)  # schematic: everything drawn, with a margin


def export_scene(scene: LayoutScene, path: str, px_per_mm: float = 4.0) -> None:
    """Export the table area to SVG (vector, mm units) or PNG/JPG."""
    sel = scene.selectedItems()
    scene.clearSelection()
    rats = getattr(scene, "show_ratsnest", None)
    if rats is not None:
        scene.show_ratsnest = False
    if hasattr(scene, "begin_export"):  # size labels for the export, not the current zoom
        scene.begin_export()
    src = export_rect(scene)
    if path.lower().endswith(".svg"):
        from PySide6.QtSvg import QSvgGenerator
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setTitle("光学平台布局")
        gen.setSize(QSize(int(src.width()), int(src.height())))
        gen.setViewBox(QRectF(0, 0, src.width(), src.height()))
        gen.setResolution(int(25.4))  # 1 SVG unit = 1 mm
        p = QPainter(gen)
        scene.render(p, QRectF(0, 0, src.width(), src.height()), src)
        p.end()
    else:
        img = QImage(int(src.width() * px_per_mm), int(src.height() * px_per_mm), QImage.Format_ARGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
        p.end()
        img.save(path)
    for it in sel:
        it.setSelected(True)
    if rats is not None:
        scene.show_ratsnest = rats
    if hasattr(scene, "end_export"):
        scene.end_export()


def install_error_handler(win_getter) -> None:
    """Report unexpected errors in a message box and keep running, instead of
    the app disappearing. Each error is also written to a log file next to the
    settings (path shown in the message)."""
    import traceback
    log = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or ".") / "errors.log"
    showing = [False]

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        sys.__stderr__ and sys.__stderr__.write(text)
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as fh:
                from datetime import datetime
                fh.write(f"---- {datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
        except OSError:
            pass
        if showing[0]:
            return  # one box at a time
        showing[0] = True
        try:
            box = QMessageBox(win_getter())
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("程序遇到错误")
            box.setText(f"{etype.__name__}: {value}\n\n程序会继续运行。如果图面显示异常，可按 Ctrl+Z 撤销上次编辑。"
                        "请尽快保存。")
            box.setDetailedText(text + f"\n错误已记录至 {log}")
            box.exec()
        finally:
            showing[0] = False

    sys.excepthook = hook


def set_gl_format() -> None:
    """The OpenGL format the 3D tab (VTK) needs, made the default before any
    window exists. pyvistaqt sets it only when the 3D tab is first opened, which
    is too late on macOS: there the main window already has an old OpenGL 2.1
    context and the 3D view stays black."""
    from PySide6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()  # desktop OpenGL 3.2 core, as pyvistaqt asks for
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setVersion(3, 2)
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    for setter in (fmt.setRedBufferSize, fmt.setGreenBufferSize, fmt.setBlueBufferSize, fmt.setAlphaBufferSize,
                   fmt.setDepthBufferSize):
        setter(8)
    fmt.setStencilBufferSize(0)
    fmt.setSamples(0)  # VTK does its own anti-aliasing
    QSurfaceFormat.setDefaultFormat(fmt)


def main():
    set_gl_format()  # before the QApplication, as Qt asks
    app = QApplication(sys.argv)
    qt_translator = QTranslator(app)
    if qt_translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt_translator)
    app.setApplicationName("Optical Layout Designer")
    install_error_handler(lambda: QApplication.activeWindow())
    w = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
