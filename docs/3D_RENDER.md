## 生成高质量 3D 渲染图

```sh
python -m pip install cadquery-ocp mitsuba
python tools/render3d.py examples/demo_3d_simple.json examples/render/demo.png --theme dark
```

- `optolayout/cad3d.py` 将二维布局转换为 3D 装配。从 `component_library/step` 读取 Thorlabs STEP 模型，并将元件放在带压叉的 Ø1 英寸 Thorlabs 支柱上。调整各支柱长度，使元件光轴与光束等高。默认光束高度为 2 英寸（50.8 mm），可用 `--beam-height` 调整。装配也包含光学面包板和光束。
- `tools/render3d.py` 使用 Mitsuba 生成棚拍效果。用 `--theme dark` 选择深色背景，或用 `--theme light` 选择白色背景。用 `--spp` 设置采样质量，`--size WxH` 设置分辨率。渲染时也可在 PNG 旁生成装配的 `.step` 文件，用 FreeCAD 打开。
- 此流程有 1 英寸和 ½ 英寸反射镜、波片、光纤耦合器和可调光阑的 3D 模型，暂时略过其他类型。Radiant Dyes 安装座在其 CAD 可用前使用 KM100 模型。
- `examples/make_demo_3d.py` 生成一个含可调光阑、两面反射镜和光纤耦合器的最小示例。

## 编辑器中的实时 3D

- 按 Ctrl+3 打开「3D」。拖动旋转，滚轮缩放，Shift + 拖动平移，F 适应窗口。在「平台布局」移动元件后，3D 会更新。在 3D 选项卡顶部修改光束高度，会同步调整支柱长度。
- 实时 3D 需要 `pyvista` 和 `pyvistaqt`。可运行 `python -m pip install pyvista pyvistaqt` 安装。
- 厂家安装座使用 `component_library/mesh/` 的简化网格，每个约 8000 个三角面。Olego 立柱保留完整细节。加入 STEP 文件后，可运行 `python tools/simplify_cad.py` 创建网格，需要 `cadquery-ocp`。缺少 CAD 时，`optolayout/view3d.py` 使用简化形状。
- 在 3D 选项卡使用「文件 → 导出当前视图为 PNG」，可保存当前预览。
