"""Beam diameters, apertures, and source parameters along routed layouts."""

from math import exp, isclose
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from optolayout.beam_optics import trace_beams  # noqa: E402
from optolayout.model import Beam, Component, Layout  # noqa: E402


def _add(layout, name, typ, x, **settings):
    layout.components[name] = Component(name, typ, x, 20, **settings)


def _connect(layout, *part_ids):
    for a, b in zip(part_ids, part_ids[1:]):
        layout.beams[f"{a}_{b}"] = Beam(f"{a}_{b}", a, b, wavelength_nm=632.8)


def _trace(layout, **options):
    return trace_beams(layout, {c.id: (c.x, c.y, 50.8) for c in layout.components.values()}, **options)


def test_lens_and_source():
    layout = Layout()
    _add(layout, "source", "beam_entry", 0, source_diameter_mm=3)
    _add(layout, "lens", "lens_1in", 100, focal_length_mm=100)
    _add(layout, "screen", "ccd", 250)
    _connect(layout, "source", "lens", "screen")
    profiles = _trace(layout)
    before, after = profiles["source_lens"], profiles["lens_screen"]
    assert before.sections[0] == (0.0, 1.5)
    assert isclose(before.sections[-1][1], after.sections[0][1], abs_tol=1e-10)
    waist_at, radius = min(after.sections, key=lambda section: section[1])
    assert isclose(waist_at, 100, abs_tol=1e-7)
    assert 0.013 < radius < 0.014
    assert isclose(after.sections[-1][1], 0.75, abs_tol=0.002)
    layout.components["lens"].focal_length_mm = -100
    after = _trace(layout)["lens_screen"]
    assert isclose(after.sections[-1][1], 3.75, abs_tol=0.002)


def test_iris_and_absorber():
    layout = Layout()
    _add(layout, "source", "laser", 0, source_diameter_mm=3)
    _add(layout, "iris", "variable_iris", 50, aperture_diameter_mm=1.5)
    _add(layout, "dump", "dump", 100)
    _add(layout, "after", "mirror_1in", 140)
    _connect(layout, "source", "iris", "dump", "after")
    profiles = _trace(layout)
    assert set(profiles) == {"source_iris", "iris_dump"}
    passed = profiles["iris_dump"]
    assert isclose(passed.transmission, 1 - exp(-0.5), abs_tol=1e-4)
    assert 0.69 < passed.sections[0][1] <= 0.75
    assert _trace(layout, profiles=False)["iris_dump"].sections
    layout.components["iris"].aperture_diameter_mm = 0
    assert set(_trace(layout)) == {"source_iris"}
    assert set(_trace(layout, profiles=False)) == {"source_iris"}


def test_saved_parameters():
    layout = Layout()
    _add(layout, "source", "laser", 0, source_diameter_mm=3)
    _add(layout, "iris", "variable_iris", 50, aperture_diameter_mm=0)
    _add(layout, "lens", "lens_half_in", 100, focal_length_mm=-75)
    _add(layout, "screen", "ccd", 250)
    _connect(layout, "source", "iris", "lens", "screen")
    layout.schematic_from_layout()
    data = layout.to_dict()
    assert "focal_length_mm" not in data["components"][0]
    saved = Layout.from_dict(data)
    assert saved.to_dict() == data
    assert saved.schematic.elements["s_iris"].aperture_diameter_mm == 0
    assert saved.schematic.elements["s_lens"].focal_length_mm == -75
    assert set(_trace(saved)) == {"source_iris"}


if __name__ == "__main__":
    test_lens_and_source()
    test_iris_and_absorber()
    test_saved_parameters()
    print("ok")
