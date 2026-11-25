"""Convert a layout snapshot into a Blender scene in a background process."""

from argparse import ArgumentParser
from base64 import b64decode
from dataclasses import dataclass
import json
import os
from pathlib import Path
import struct
import sys

MAC_UNICODE_FONT = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")


@dataclass(frozen=True)
class MaterialStyle:
    name: str
    roughness: float
    metallic: float = 0.0
    transmission: float = 0.0
    ior: float = 1.5
    color: tuple[float, float, float] | None = None  # Blender's scene-linear RGB
    emission: float = 0.0
    unlit: bool = False


MATERIAL_STYLES = {
    "splitter_glass": MaterialStyle("分束器光学玻璃", 0.025, transmission=1.0, ior=1.52, color=(0.99, 0.995, 1.0)),
    "glass": MaterialStyle("透镜光学玻璃", 0.035, transmission=1.0, ior=1.52, color=(0.97, 0.99, 1.0)),
    "waveplate": MaterialStyle("波片光学玻璃", 0.04, transmission=1.0, ior=1.54, color=(1.0, 0.99, 0.96)),
    "mirror": MaterialStyle("镜面反射镀层", 0.04, metallic=1.0, color=(0.93, 0.95, 0.97)),
    "lcos": MaterialStyle("LCOS 反射面", 0.11, metallic=0.95, color=(0.67, 0.74, 0.8)),
    "grating": MaterialStyle("光栅反射镀层", 0.19, metallic=0.9),
    "sensor": MaterialStyle("探测器感光面", 0.19, color=(0.09, 0.12, 0.15), ior=1.52),
    "anodized": MaterialStyle("阳极氧化铝", 0.39, metallic=0.6),
    "aluminum": MaterialStyle("拉丝铝", 0.32, metallic=0.9),
    "steel": MaterialStyle("不锈钢", 0.3, metallic=0.94),
    "brass": MaterialStyle("黄铜", 0.31, metallic=0.9),
    "board": MaterialStyle("面包板金属台面", 0.43, metallic=0.77),
    "recess": MaterialStyle("哑光暗面", 0.82),
    "housing": MaterialStyle("设备外壳", 0.47, metallic=0.25),
    "polymer": MaterialStyle("工程塑料", 0.56),
    "rubber": MaterialStyle("橡胶护套", 0.73, ior=1.46),
    "aperture": MaterialStyle("激光器出光口", 0.22),
    "marker": MaterialStyle("光路标记", 0.48, emission=1.5),
    "beam": MaterialStyle("光束发光", 0.38, emission=0.9, unlit=True),
}


def write_glb(document, path):
    binary = bytearray()
    offsets = []
    for buffer in document["buffers"]:
        offsets.append(len(binary))
        binary.extend(b64decode(buffer["uri"].split(",", 1)[1]))
        binary.extend(b"\0" * (-len(binary) % 4))
    for view in document["bufferViews"]:
        view["byteOffset"] = offsets[view["buffer"]] + view.get("byteOffset", 0)
        view["buffer"] = 0
    document["buffers"] = [{"byteLength": len(binary)}]
    data = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    data += b" " * (-len(data) % 4)
    with path.open("wb") as output:
        output.write(struct.pack("<4sII", b"glTF", 2, 28 + len(data) + len(binary)))
        output.write(struct.pack("<I4s", len(data), b"JSON"))
        output.write(data)
        output.write(struct.pack("<I4s", len(binary), b"BIN\0"))
        output.write(binary)


def export_layout(layout, beam_height, path, *, physical_beams=False):
    import pyvista as pv
    from optolayout.mounts3d import optic_height
    from optolayout.view3d import populate

    plotter = pv.Plotter(off_screen=True, lighting="none")
    gltf_path = path.with_suffix(".gltf")
    metadata = {}
    beam_profiles = {}
    material_roles = {
        "board": "board", "holes": "recess", "pockets": "recess", "posts": "steel", "pillars": "polymer",
        "adapters": "aluminum" if layout.table.style == "lightflow" else "polymer",
    }
    try:
        parts = populate(plotter, layout, beam_height=beam_height, material_roles=material_roles,
                         physical_beams=physical_beams, beam_profiles=beam_profiles)
        for part_id, actors in parts.items():
            part = layout.components[part_id]
            height = optic_height(part.type, layout.table.style, beam_height, part.grating_size_mm)
            for index, _actor in enumerate(actors):
                metadata[f"{part_id}_{index}"] = {
                    "optolayout_part_id": part_id,
                    "optolayout_label": part.label or part_id,
                    "optolayout_part_number": part.part_number,
                    "optolayout_origin": [part.x * 0.001, -part.y * 0.001, height * 0.001],
                }
        for beam in layout.beams.values():
            extras = {}
            if beam.wavelength_nm is not None:
                extras["optolayout_wavelength_nm"] = beam.wavelength_nm
            profile = beam_profiles.get(beam.id)
            if profile is not None and profile.sections:
                extras["optolayout_aperture_transmission"] = profile.transmission
                if physical_beams:
                    extras["optolayout_start_diameter_mm"] = 2 * profile.sections[0][1]
                    extras["optolayout_end_diameter_mm"] = 2 * profile.sections[-1][1]
            if extras:
                metadata[f"beam_{beam.id}"] = extras
        for name, actor in plotter.renderer.actors.items():
            actor.SetObjectName(name)
            actor.SetScale(0.001, 0.001, 0.001)  # glTF uses meters.
            actor.RotateX(-90)  # Z-up to glTF's Y-up, preserving the board's X axis.
            dataset = actor.mapper.dataset
            if "Normals" in dataset.point_data:
                dataset.point_data["NORMAL"] = dataset.point_data["Normals"]
        plotter.export_gltf(str(gltf_path), rotate_scene=False)
        document = json.loads(gltf_path.read_text(encoding="utf-8"))
    finally:
        plotter.close()
        gltf_path.unlink(missing_ok=True)

    camera_nodes = {i for i, node in enumerate(document["nodes"]) if "camera" in node}
    document.pop("cameras", None)
    for node in document["nodes"]:
        node.pop("camera", None)
        if "children" in node:
            node["children"] = [i for i in node["children"] if i not in camera_nodes]
        if "mesh" not in node:
            continue
        name = node["name"]
        role = material_roles.get(name)
        if role is None and name.startswith("beam_"):
            role = "beam"
        if role is None and name.startswith("meter_") and name.endswith("_bead"):
            role = "marker"
        extras = metadata.get(name, {})
        if role is not None:
            extras["optolayout_material"] = role
        if extras:
            node.setdefault("extras", {}).update(extras)
    write_glb(document, path)


def _principled(material):
    if material is not None and material.node_tree is not None:
        return next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    return None


def _srgb_to_linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _apply_material_style(material, style):
    shader = _principled(material)
    if shader is None:
        return
    inputs = shader.inputs
    base = inputs["Base Color"]
    # VTK exports its display RGB as a glTF factor. Blender shaders expect linear RGB.
    rgb = style.color if style.color is not None else tuple(_srgb_to_linear(value) for value in base.default_value[:3])
    color = (*rgb, 1.0)
    material.diffuse_color = color
    if style.unlit:
        tree = material.node_tree
        output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output)
        emission = tree.nodes.new("ShaderNodeEmission")
        emission.location = shader.location
        emission.inputs["Color"].default_value = color
        emission.inputs["Strength"].default_value = style.emission
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        tree.nodes.remove(shader)
        return

    base.default_value = color
    if base.is_linked:
        # Keep vendor meshes' per-vertex colours in the shader.
        link = base.links[0]
        source = link.from_socket
        material.node_tree.links.remove(link)
        gamma = material.node_tree.nodes.new("ShaderNodeGamma")
        gamma.inputs["Gamma"].default_value = 2.2
        gamma.location = (shader.location.x - 150, shader.location.y)
        material.node_tree.links.new(source, gamma.inputs["Color"])
        material.node_tree.links.new(gamma.outputs["Color"], base)
    inputs["Metallic"].default_value = style.metallic
    inputs["Roughness"].default_value = style.roughness
    inputs["IOR"].default_value = style.ior
    inputs["Alpha"].default_value = 1.0
    (inputs.get("Transmission Weight") or inputs["Transmission"]).default_value = style.transmission
    if style.emission:
        (inputs.get("Emission Color") or inputs["Emission"]).default_value = color
        inputs["Emission Strength"].default_value = style.emission
    if style.transmission:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        if hasattr(material, "use_raytrace_refraction"):
            material.use_raytrace_refraction = True
        elif hasattr(material, "use_screen_refraction"):
            material.use_screen_refraction = True


def _add_component_labels(collection, labels, size, rotation):
    import bpy

    font = None
    if MAC_UNICODE_FONT.is_file() and any(not name.isascii() for name, _location in labels):
        font = bpy.data.fonts.load(str(MAC_UNICODE_FONT), check_existing=True)

    material = bpy.data.materials.new("元器件名称")
    material.diffuse_color = (0.85, 0.29, 0.025, 1.0)
    material.use_nodes = True
    shader = _principled(material)
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = 0.7
    (shader.inputs.get("Emission Color") or shader.inputs["Emission"]).default_value = material.diffuse_color
    shader.inputs["Emission Strength"].default_value = 0.65
    angle = rotation.to_euler()
    for name, location in labels:
        text = bpy.data.curves.new(f"{name} · 名称", "FONT")
        text.body = name
        text.align_x = "CENTER"
        text.size = size
        text.materials.append(material)
        if font is not None:
            text.font = font
        obj = bpy.data.objects.new(text.name, text)
        obj.location = location
        obj.rotation_euler = angle
        obj.show_in_front = True
        collection.objects.link(obj)


def save_blend(source, destination, *, component_labels=False):
    import bpy
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "MILLIMETERS"
    if hasattr(scene.eevee, "use_raytracing"):
        scene.eevee.use_raytracing = True
    elif hasattr(scene.eevee, "use_ssr_refraction"):
        scene.eevee.use_ssr = True
        scene.eevee.use_ssr_refraction = True

    def collection(name):
        result = bpy.data.collections.new(name)
        scene.collection.children.link(result)
        return result

    parts = collection("光学元件")
    platform = collection("面包板与支架")
    beams = collection("光束")
    meters = collection("功率测量点")
    parents = {}
    label_tops = {}
    styled_materials = {}
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    bpy.context.view_layer.update()
    corners = []
    for obj in meshes:
        world = obj.matrix_world.copy()
        bounds = [world @ Vector(point) for point in obj.bound_box]
        corners.extend(bounds)
        part_id = obj.get("optolayout_part_id")
        if part_id is not None:
            target = parts
            if part_id not in parents:
                parent = bpy.data.objects.new(obj["optolayout_label"], None)
                parent.empty_display_size = 0.008
                parent.location = obj["optolayout_origin"]
                parent["元件 ID"] = part_id
                parent["料号"] = obj["optolayout_part_number"]
                parts.objects.link(parent)
                parents[part_id] = parent
            if component_labels:
                top = max(point.z for point in bounds)
                previous = label_tops.get(part_id)
                if previous is None or top > previous[1]:
                    label_tops[part_id] = (obj["optolayout_label"], top)
            obj.parent = parents[part_id]
        else:
            target = beams if obj.name.startswith("beam_") else meters if obj.name.startswith("meter_") else platform
            obj.parent = None
        bpy.context.view_layer.update()
        obj.matrix_world = world
        for previous in list(obj.users_collection):
            previous.objects.unlink(obj)
        target.objects.link(obj)
        role = obj.get("optolayout_material")
        style = MATERIAL_STYLES.get(role)
        if style is not None and obj.data.users > 1:
            obj.data = obj.data.copy()
        for index, material in enumerate(obj.data.materials):
            if material is None:
                continue
            if style is None:
                shader = _principled(material)
                if shader is not None:
                    material.diffuse_color = shader.inputs["Base Color"].default_value
                continue
            key = (material, role)
            if key not in styled_materials:
                styled = material.copy()
                styled.name = style.name
                _apply_material_style(styled, style)
                styled_materials[key] = styled
            obj.data.materials[index] = styled_materials[key]

    if beams.objects:
        try:
            scene.view_settings.view_transform = "Khronos PBR Neutral"
        except TypeError:  # Blender versions before the neutral transform was added.
            scene.view_settings.view_transform = "Standard"

    for material in {original for original, _role in styled_materials}:
        if material.users == 0:
            bpy.data.materials.remove(material)

    for obj in list(scene.objects):
        if obj.type == "EMPTY" and not obj.children and obj not in parents.values():
            bpy.data.objects.remove(obj, do_unlink=True)
    for group in list(scene.collection.children):
        if not group.all_objects:
            bpy.data.collections.remove(group)
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = None

    if corners:
        low = Vector(tuple(min(v[i] for v in corners) for i in range(3)))
        high = Vector(tuple(max(v[i] for v in corners) for i in range(3)))
        span = max(high - low)
        view_rotation = Vector((1, -1.4, 1)).to_track_quat("Z", "Y")
        if label_tops:
            size = max(0.010, min(0.032, span * 0.032))
            gap = size * 0.75
            labels = [(name, (parents[part_id].location.x, parents[part_id].location.y, top + gap))
                      for part_id, (name, top) in label_tops.items()]
            _add_component_labels(collection("元器件名称"), labels, size, view_rotation)
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    space = area.spaces.active
                    space.shading.color_type = "MATERIAL"
                    if screen.name == "Layout":
                        space.shading.type = "MATERIAL"
                        space.shading.studio_light = "studio.exr"
                    space.overlay.show_relationship_lines = False
                    space.region_3d.view_location = (low + high) / 2
                    space.region_3d.view_distance = span * 1.85
                    space.region_3d.view_rotation = view_rotation
    bpy.ops.wm.save_as_mainfile(filepath=destination, compress=False)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--component-labels", action="store_true", help="Add independent text labels above components.")
    if "--" in sys.argv:  # Invoked by Blender after the mesh export.
        parser.add_argument("source")
        parser.add_argument("destination")
        args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
        save_blend(args.source, args.destination, component_labels=args.component_labels)
        return

    parser.add_argument("snapshot", type=Path)
    parser.add_argument("height", type=float)
    parser.add_argument("blender")
    parser.add_argument("--physical-beams", action="store_true", help="Use beam diameters, lenses and apertures for display.")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from optolayout.model import Layout

    work = args.snapshot.parent
    app = QApplication([])
    export_layout(Layout.load(args.snapshot), args.height, work / "layout.glb", physical_beams=args.physical_beams)
    app.quit()
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "QT_QPA_PLATFORM", "QT_API", "BLENDER_USER_CONFIG",
                "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES"):
        environment.pop(key, None)
    environment["BLENDER_USER_RESOURCES"] = str(work / "blender-profile")
    environment["TMPDIR"] = str(work)
    command = [args.blender, "--background", "--factory-startup", "--python-exit-code", "1",
               "--python", str(Path(__file__).resolve()), "--", str(work / "layout.glb"), str(work / "layout.blend")]
    if args.component_labels:
        command.append("--component-labels")
    os.execve(args.blender, command, environment)


if __name__ == "__main__":
    main()
