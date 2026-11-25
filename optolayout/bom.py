"""Bill of materials: every part grouped by part number with a quantity, plus
the posts, clamping forks and adapters the 3D generator stands them on."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from .model import Layout, grating_size_text
from .mounts3d import (DEFAULT_BEAM_HEIGHT, DRILLED_STYLES, LIGHTFLOW_ELEMENTS, MODELS, OLEGO_PILLARS, PLATE_T,
                       SCREW_D, drilled_holes, mount_block, nearest_stock, part_base_height, pillar_info, post_length,
                       sunk_depth, table_screw_holes)
from .symbols import SYMBOLS


@dataclass
class BomRow:
    part_number: str
    description: str
    qty: int = 0
    refs: list[str] = field(default_factory=list)
    section: str = "Optics & mounts"


def _natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


def bill_of_materials(layout: Layout, beam_height: float = DEFAULT_BEAM_HEIGHT) -> list[BomRow]:
    rows: dict[tuple[str, str, str], BomRow] = {}

    def add(section, pn, desc, ref, n=1):
        key = (section, pn, desc)
        r = rows.get(key)
        if r is None:
            r = rows[key] = BomRow(pn, desc, 0, [], section)
        r.qty += n
        if ref:
            r.refs.append(ref)

    # what each part is: from the schematic (it defines parts); layout-only parts too
    parts = []  # (label, layout type, part number, grating size)
    sch = layout.schematic
    for e in sch.elements.values():
        t = e.layout_type()
        parts.append((e.label, t, e.part_number or SYMBOLS[t].default_part, e.grating_size_mm))
    for c in layout.components.values():
        if not c.sch_id or c.sch_id not in sch.elements:
            parts.append((c.label, c.type, c.part_number or SYMBOLS[c.type].default_part, c.grating_size_mm))
    for label, t, pn, size in parts:
        if SYMBOLS[t].physical:
            name = SYMBOLS[t].name
            if t == "grating":
                name += " · " + grating_size_text(size)
            add("Optics & mounts", pn or "(no part number)", name, label)

    # what holds them up: one post + fork per part (as in the 3D model), and adapters
    placed = [c for c in layout.components.values() if c.type in MODELS]
    t = layout.table
    if t.style in DRILLED_STYLES:
        _drilled_hardware(layout, placed, add)
        placed = []
    for c in placed:
        m = MODELS[c.type]
        for pn, desc in m.extras:
            add("Adapters", pn, desc, c.label)
        if not m.post:
            continue
        if layout.table.style == "olego" and c.type in OLEGO_PILLARS:
            name = OLEGO_PILLARS[c.type]
            h = pillar_info(name)[0]
            add("Posts & clamps", name, f"Olego 立柱，{h:.1f} mm", c.label)
            add("Posts & clamps", "4-40 cap screw", '将立柱法兰固定到平台（每根立柱 4 枚）', c.label, 4)
            continue
        if layout.table.style == "olego":
            add("Posts & clamps", "(Olego pillar not in the library)", f"用于{SYMBOLS[c.type].name}的立柱", c.label)
            continue
        if c.type == "grating":
            L = beam_height - part_base_height(c.type, c.grating_size_mm)
            if L <= 1:
                continue
        else:
            L = post_length(m, beam_height)
        stock = nearest_stock(L)
        add("Posts & clamps", f"Ø1\" pedestal post, {L:.1f} mm",
            f"截取至 {L:.1f} mm ({L / 25.4:.3f} in)，最接近的库存规格为 {stock:g} in", c.label)
        add("Posts & clamps", "CF125", 'Ø1 英寸支柱用压叉', c.label)
        add("Posts & clamps", '1/4"-20 x 1/2" cap screw', '将压叉固定到光学面包板', c.label)
    order = {"Optics & mounts": 0, "Adapters": 1, "Posts & clamps": 2, "Baseplate & screws": 3}
    out = sorted(rows.values(), key=lambda r: (order.get(r.section, 9), r.part_number.startswith("("),
                                              _natural(r.part_number)))
    for r in out:
        r.refs.sort(key=_natural)
    return out


def _drilled_hardware(layout: Layout, placed, add) -> None:
    """A board drilled per part (PyOpticL baseplate, LightFlow optical circuit
    board): the plate, the adapters or pedestals, screws and dowels (no posts)."""
    t = layout.table
    lf = t.style == "lightflow"
    on = [c for c in placed if t.on_board(c.x, c.y)]
    sec = "Baseplate & screws"
    if lf:
        add(sec, f"Optical circuit board {t.width:.1f} x {t.height:.1f} x {PLATE_T[t.style]:g} mm",
            'LightFlow 铝制平台，按元件位置钻孔并攻丝' + ("（带缺口）" if t.cutouts else ""), "")
    else:
        add(sec, f"Baseplate {t.width:.1f} x {t.height:.1f} x {PLATE_T[t.style]:g} mm",
            'PyOpticL 基板，按下列位置铣孔和凹槽' + ("（带缺口）" if t.cutouts else ""), "")
    for c in on:
        m = MODELS[c.type]
        for pn, desc in m.extras:
            add("Adapters", pn, desc, c.label)
        if not m.post:
            continue
        b = mount_block(c.type, t.style, c.grating_size_mm)
        holes = drilled_holes(c.type, t.style, c.x, c.y, c.angle)
        n = sum(1 for h in holes if h[2] == SCREW_D)
        dowels = len(holes) - n
        if b is not None:
            size = f"{b.x1 - b.x0:.1f} x {b.y1 - b.y0:.1f} x {b.z1 - b.z0:.1f} mm"
            if lf:
                e = LIGHTFLOW_ELEMENTS.get(c.type)
                desc = ('机加工件（未记录底座）' if e is None else f"机加工实验室元件 {e.name}"
                        if e.source == "lab" else f"机加工 LightFlow 元件「{e.name}」（OQD 平台）")
                add("Adapters", f"Pedestal {size}", desc, c.label)
                add(sec, "8-32 cap screw", '将底座固定到平台（8-32 螺纹孔，深 6.25 mm）', c.label, n)
            else:
                add("Adapters", f"Surface adapter {size}", '3D 打印件，PyOpticL Surface_Adapter', c.label)
                add(sec, "8-32 cap screw", '将转接件固定到基板', c.label, n)
            if c.type not in ("pbs", "bs", "pbs_half"):  # a cube sits on (or in) its block
                add(sec, "8-32 cap screw", '将安装座固定到' + ("底座" if lf else "转接件"), c.label)
        elif c.type == "iris" and not lf:
            add("Adapters", "Slide adapter", '3D 打印件，PyOpticL Slide_Adapter', c.label)
            add(sec, "8-32 cap screw", '将滑入式转接件固定到基板', c.label)
        else:
            add(sec, "8-32 cap screw", '将安装座固定到' + ("平台" if lf else "基板（从底部安装）"), c.label, n)
        if dowels:
            add(sec, "M2 dowel pin", '定位安装座（M2 孔，深 2.1 mm）', c.label, dowels)
        if sunk_depth(c.type, t.style, c.grating_size_mm) > 0:
            add(sec, "(pocket)", '为低于板面的安装座铣制凹槽', c.label)
    parts = [(c.type, c.x, c.y, c.angle, c.grating_size_mm) for c in layout.components.values()
             if SYMBOLS[c.type].physical and t.on_board(c.x, c.y)]
    holes = table_screw_holes(t, parts)
    if holes:
        if lf:
            add(sec, '1/4"-20 x 3/4" cap screw', '将平台固定到光学台（通孔）', "", len(holes))
        else:
            add(sec, '1/4"-20 x 1-1/4" cap screw', '将基板固定到光学台（沉孔）', "", len(holes))


def write_bom_csv(rows: list[BomRow], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Section", "Part no.", "Description", "Qty", "Used by"])
        for r in rows:
            w.writerow([r.section, r.part_number, r.description, r.qty, " ".join(r.refs)])


class BomDialog(QDialog):
    """Parts grouped by part number with quantities; follows edits live."""

    COLS = ["料号", "说明", "数量", "使用位置"]
    SECTIONS = {"Optics & mounts": "光学元件与安装座", "Adapters": "转接件",
                "Posts & clamps": "支柱与压叉", "Baseplate & screws": "基板与螺钉"}

    def __init__(self, layout_getter, edited_signal, parent=None):
        super().__init__(parent)
        self.setWindowTitle('物料清单')
        self.resize(860, 560)
        self.get_layout = layout_getter
        self.height = QDoubleSpinBox()
        self.height.setRange(20, 300)
        self.height.setDecimals(1)
        self.height.setSuffix(" mm")
        self.height.setValue(DEFAULT_BEAM_HEIGHT)
        self.height.valueChanged.connect(self.reload)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.total = QLabel()
        export = QPushButton('导出 CSV…')
        export.clicked.connect(self._export)
        top = QHBoxLayout()
        top.addWidget(QLabel('光束高度（决定支柱长度）：'))
        top.addWidget(self.height)
        top.addStretch(1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.total)
        bottom.addStretch(1)
        bottom.addWidget(export)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        hint = QLabel('在光路图的「属性」或「元件表」(Ctrl+T) 中设置料号。支柱、压叉和转接件与 3D 模型一致。')
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addLayout(bottom)
        edited_signal.connect(self.reload)
        self.reload()

    def rows(self) -> list[BomRow]:
        return bill_of_materials(self.get_layout(), self.height.value())

    def reload(self, *_):
        if not self.isVisible() and self.table.rowCount():
            return
        rows = self.rows()
        self.table.setRowCount(0)
        section = None
        for r in rows:
            if r.section != section:
                section = r.section
                i = self.table.rowCount()
                self.table.insertRow(i)
                head = QTableWidgetItem(self.SECTIONS.get(section, section))
                f = head.font()
                f.setBold(True)
                head.setFont(f)
                head.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(i, 0, head)
                self.table.setSpan(i, 0, 1, len(self.COLS))
            i = self.table.rowCount()
            self.table.insertRow(i)
            qty = QTableWidgetItem(str(r.qty))
            qty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for c, it in enumerate([QTableWidgetItem(r.part_number), QTableWidgetItem(r.description), qty,
                                    QTableWidgetItem(" ".join(r.refs))]):
                self.table.setItem(i, c, it)
        self.table.resizeColumnsToContents()
        n = sum(r.qty for r in rows if r.section == "Optics & mounts")
        self.total.setText(f"{n} 个元件，清单共 {len(rows)} 项")

    def showEvent(self, e):
        super().showEvent(e)
        self.reload()

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, '导出物料清单', "bom.csv", "CSV (*.csv)")
        if p:
            write_bom_csv(self.rows(), p)
