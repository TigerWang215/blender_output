"""Schematic layer: the layout follows the schematic, fields live in the
schematic, parts table, duplicate, legacy files get a schematic, save/load."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from optolayout.app import MainWindow, export_scene  # noqa: E402
from optolayout.model import Layout, SchElement, SchLink  # noqa: E402
from optolayout.orient import auto_angle  # noqa: E402
from optolayout.schematic import AddElementCmd, AddLinkCmd, NewPartDialog, SchSetFieldsCmd  # noqa: E402


def test_orient():
    assert auto_angle("mirror", (0, 0), [(-10, 0)], [(0, -10)]) == 135  # in from left, out up (screen)
    assert auto_angle("lcos", (0, 0), [(-10, 0)], [(0, -10)]) == 135
    assert auto_angle("lcos", (0, 0), [(-10, 0)], [(-20, 0)]) == 180
    assert auto_angle("ccd", (0, 0), [(-10, 0)], []) == 180
    assert auto_angle("mirror", (0, 0), [(10, 0)], [(0, 10)]) == 315
    assert auto_angle("fiber", (0, 0), [(0, 10)], []) == 270  # faces the beam coming from below
    assert auto_angle("lens", (0, 0), [(-10, 0)], [(10, 0)]) == 0
    assert auto_angle("pbs", (0, 0), [(-10, 0)], [(10, 0), (0, -10)]) == 0  # "/" sends +x up
    assert auto_angle("pbs", (0, 0), [(-10, 0)], [(10, 0), (0, 10)]) == 90
    assert auto_angle("pbs", (0, 0), [(-10, 0)], [(10, 0), (0, -10)], "pbs_mounted") == 90  # "\\" cube


def test_schematic():
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "demo_schematic.json"
    shutil.copy(ROOT / "examples" / "demo_schematic.json", src)
    w = MainWindow(str(src))
    w.show()
    QApplication.processEvents()
    lay = w.scene.layout
    sch = lay.schematic
    assert len(sch.elements) == 8 and len(sch.links) == 7
    # the layout was filled from the schematic on open, arranged like it, every beam present
    assert len(lay.components) == 8 and set(lay.beams) == set(sch.links)
    t = lay.table
    assert all(0 < c.x < t.width and 0 < c.y < t.height for c in lay.components.values())
    assert len({(c.x, c.y) for c in lay.components.values()}) == 8
    assert not w.scene.clashes, w.scene.clashes
    m1 = lay.component_for("m1")
    assert m1.type == "mirror_rd_1in" and m1.label == "M1" and abs(m1.angle - 135) < 1e-6
    assert lay.component_for("l1").part_number == "LA1509-A"

    # part type and part number are set in the schematic (properties panel)
    w.tabs.setCurrentIndex(0)
    w.sch_scene.el_items["m1"].setSelected(True)
    props = w.sch_page.props
    assert props.obj is sch.elements["m1"]
    props.part.setCurrentIndex(props.part.findData("mirror_half_in"))
    props._commit("part", props.part.currentData())
    assert m1.type == "mirror_half_in" and m1.part_number == "KM05"
    props.part_number.setText("POLARIS-K05")
    props._commit("part_number", "POLARIS-K05")
    assert m1.part_number == "POLARIS-K05"
    w.scene.undo.undo()
    w.scene.undo.undo()
    assert m1.type == "mirror_rd_1in"

    # kind change resets the part to the new kind's default
    w.scene.undo.push(SchSetFieldsCmd(w.sch_scene, {"bd": ({"kind": "dump"}, {"kind": "photodiode"})}, "k"))
    assert lay.component_for("bd").type == "photodiode"
    w.scene.undo.undo()

    palette = w.sch_page.palette
    assert "lcos" in {palette.item(row).data(Qt.UserRole) for row in range(palette.count())}
    assert sch.next_label("lcos") == "LCOS1"
    w.scene.undo.push(SchSetFieldsCmd(w.sch_scene, {"m1": ({"kind": "mirror"}, {"kind": "lcos"})}, "LCOS"))
    assert m1.type == "lcos" and abs(m1.angle - 135) < 1e-6
    round_trip = Layout.from_dict(lay.to_dict())
    assert round_trip.schematic.elements["m1"].kind == round_trip.component_for("m1").type == "lcos"
    w.scene.undo.undo()

    # parts table edits go through undo
    w.show_parts_table()
    tbl = w._parts_table
    row = [e.id for e in tbl._rows()].index("fc")
    tbl.table.item(row, 3).setText("PAF2-A4A")
    assert lay.component_for("fc").part_number == "PAF2-A4A"
    w.scene.undo.undo()
    assert lay.component_for("fc").part_number == "2x CP33 + SM1FCA"  # the cage fiber coupler's default part number
    tbl.close()

    # duplicate: copies elements and the beam between them, with fresh labels
    w.sch_scene.clearSelection()
    for e in ("aom", "l1"):
        w.sch_scene.el_items[e].setSelected(True)
    w.duplicate_selected()
    assert len(sch.elements) == 10 and len(sch.links) == 8
    assert {"AOM2", "L2"} <= {e.label for e in sch.elements.values()}
    assert len(lay.components) == 10
    w.scene.undo.undo()
    assert len(sch.elements) == 8 and len(lay.components) == 8

    # wavelength of a beam is set on the schematic connection
    k = sch.links["k_pbs_aom"]
    w.scene.undo.push(SchSetFieldsCmd(w.sch_scene, {k.id: ({"color": k.color, "wavelength_nm": 399.0},
                                                           {"color": "#2e9e3e", "wavelength_nm": 556.0})}, "wl"))
    assert lay.beams[k.id].color == "#2e9e3e" and lay.beams[k.id].wavelength_nm == 556.0

    # save / load keeps both layers and placement
    w.save_file()
    lay2 = Layout.load(src)
    assert len(lay2.schematic.elements) == 8 and len(lay2.components) == 8
    assert lay2.component_for("m1").x == m1.x and lay2.beams[k.id].wavelength_nm == 556.0

    out = Path(os.environ.get("SCH_SHOT_DIR", tmp))
    export_scene(w.sch_scene, str(out / "schematic.png"))
    export_scene(w.scene, str(out / "layout.png"))
    assert all(it._screen for it in w.scene.point_items.values())
    w.scene.undo.setClean()
    w.close()

    # an older layout without a schematic gets one, keeping beam ids (measurement points stay)
    old = tmp / "demo_399nm.json"
    shutil.copy(ROOT / "examples" / "demo_399nm.json", old)
    before = Layout.load(old)
    w2 = MainWindow(str(old))
    lay3 = w2.scene.layout
    assert len(lay3.schematic.elements) == len(before.components)
    assert set(lay3.schematic.links) == set(before.beams) == set(lay3.beams)
    assert all((lay3.components[c].x, lay3.components[c].y, lay3.components[c].angle) ==
               (before.components[c].x, before.components[c].y, before.components[c].angle)
               for c in before.components), "older files keep their placement and angles"
    assert all(not p.archived for p in lay3.points.values() if not before.points[p.id].archived)
    w2.scene.undo.setClean()
    w2.close()
    print("ok")


def test_grating_dimensions_and_ccd():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.tabs.setCurrentIndex(0)
    scene = window.scene
    schematic = window.sch_scene
    palette = window.sch_page.palette
    assert {"grating", "ccd"} <= {palette.item(row).data(Qt.UserRole) for row in range(palette.count())}

    grating = SchElement("grating", "grating", label="GR1")
    dialog = NewPartDialog(grating, schematic.sch)
    assert dialog.grating_size.size_mm() == (25.0, 25.0, 6.0)
    dialog.grating_size.set_size((30, 21, 7.5))
    dialog.accept()
    scene.undo.push(AddElementCmd(schematic, grating))
    part = scene.layout.component_for(grating.id)
    assert part.grating_size_mm == (30.0, 21.0, 7.5)
    scene.set_fields(part.id, {"x": 150, "y": 120, "pinned": True})
    item = scene.comp_items[part.id]
    old_span = item.outline().boundingRect().height()

    props = window.sch_page.props
    props.show_obj(schematic.sch.elements[grating.id])
    props.grating_size.fields[0].setValue(50)
    props.grating_size.fields[0].editingFinished.emit()
    assert part.grating_size_mm == (50.0, 21.0, 7.5)
    assert item.outline().boundingRect().height() == old_span + 20
    scene.undo.undo()
    assert part.grating_size_mm == (30.0, 21.0, 7.5)
    scene.undo.redo()
    assert part.grating_size_mm == (50.0, 21.0, 7.5)
    assert (part.x, part.y) == (150, 120)

    camera = SchElement("camera", "ccd", label="CCD1")
    scene.undo.push(AddElementCmd(schematic, camera))
    detector = scene.layout.component_for(camera.id)
    scene.set_fields(detector.id, {"x": 300, "y": 120, "pinned": True})
    scene.undo.push(AddLinkCmd(schematic, SchLink("image", grating.id, camera.id)))
    assert detector.type == "ccd" and detector.angle == 180
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "grating.json"
        scene.layout.save(path)
        reopened = Layout.load(path)
    assert reopened.schematic.elements[grating.id].grating_size_mm == (50.0, 21.0, 7.5)
    assert reopened.component_for(grating.id).grating_size_mm == (50.0, 21.0, 7.5)
    assert reopened.component_for(camera.id).type == "ccd"
    scene.undo.setClean()
    window.close()
    print("ok")


if __name__ == "__main__":
    test_orient()
    test_schematic()
    test_grating_dimensions_and_ccd()
