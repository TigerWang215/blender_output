# 配置 Olego 立柱和安装座

在 Olego 平台上，每个安装座使用专用立柱。立柱的方形法兰通过 4-40 螺钉固定到平台。安装座落在立柱顶部较宽、较低的台阶上，称为承座。旁边较小的凸起用于定位。

3D 视图、重叠检查和物料清单均使用这里列出的装配数据。现有大部分模型的光轴高度在 50.8 mm（2 英寸）上下 0.05 mm 内，例外见末尾。

## 1. 安装座的厂家 CAD

1. 将厂家的 `.step` 或 `.stp` 文件放入 `component_library/step/`。
2. 用 `tools/simplify_cad.py` 先转换一次，或者打开原始文件检查包围盒和光学开孔。
   - 光学中心是光学开孔中心，位于镜面或透镜、波片中央。
   - 光束方向沿开孔轴线。
   - 底面是安装座向下固定所用螺纹孔所在的面。
3. 在 `tools/simplify_cad.py` 的 `POSES` 中添加一项。填写文件坐标下的光学中心 `origin`、光学面朝向或透镜及波片的光束方向 `x`、远离底面的向上方向 `z`。

   示例 MDI-HS：`dict(origin=(25.44, 25.0, -15.8), x=(0, 0, -1), z=(0, 1, 0))`。
4. 运行 `python tools/simplify_cad.py <文件名不含扩展名>`。输出中 `base X mm below the optic` 的数值就是安装座的 `base_height`。
5. 在 `optolayout/mounts3d.py` 中编辑两个表：
   - `MODELS`：加入 `"<元件类型>": Model3D("<文件>", <base_height>, mirror_disc=…)`，也可使用 `glass_disc`。
   - `MESH_FOOTPRINT`：加入网格的 xy 边界（`pv.read(mesh).bounds`），供重叠检查使用。
6. 安装底面的螺纹孔不在光学中心正下方时，在 `MOUNT_BASE_OFFSET` 中填写偏移。例如，MDI-HS 的螺纹孔在反射镜后方 20.5 mm。在元件库坐标中测量底面中心，x 沿光束，y 向左。立柱会放在该位置。
7. 如需给安装座的不同区域着色，在 `REGION_COLORS` 中添加规则，可参考 MDI-HS。

## 2. 立柱

1. 将立柱文件放入 `component_library/Olego_step/`。SolidWorks 的 `.sldprt` 文件可用 `python tools/sldprt_to_step.py` 转换，该脚本调用本机 SolidWorks，把 `.step` 保存在原文件旁。也可用 `.stl`，例如 MDI-HS 立柱。
2. 在 `tools/simplify_cad.py` 的 `PILLAR_UP` 中添加模型，并填写文件坐标中从法兰向上指向安装座的轴，例如 `"+y"`。
3. 运行 `python tools/simplify_cad.py <立柱名称>`。脚本会将立柱竖起，以法兰中心为原点、法兰底部为 z = 0，输出 `component_library/mesh/Olego/<名称>.ply`，并在 `mesh/Olego/pillars.json` 记录立柱高度、承座及顶部各平坦台阶。

   自动选择的承座是最上方 15 mm 内面积最大的朝上平面。请核对安装座实际落在该台阶上。如有偏差，编辑 `pillars.json`。
4. 在 `optolayout/mounts3d.py` 的 `OLEGO_PILLARS` 中加入 `"<元件类型>": "<立柱名称>"`。

## 3. 检查装配

光轴高度等于承座高度加上安装座的 `base_height`。可打印所有元件类型检查光轴高度是否约为 50.8 mm：

```sh
python -c "from optolayout.mounts3d import *; [print(t, optic_height(t, 'olego')) for t in OLEGO_PILLARS]"
```

在 `OLEGO_OPTIC_RULE` 中处理例外。对于直接放在承座内的分束立方体，可用 `("seat+", d)` 表示光轴距承座 `d`。对于螺纹凸台高于安装板的安装座（例如 CP33 立柱上的 CRM1T）或仍使用简化模型的元件，可用 `("fixed", h)` 指定固定高度 `h`。

最后在 3D 视图中放大检查安装状态。

## 已有立柱（2026-10-11）

| 立柱 | 高度 (mm) | 承座高度 (mm) | 对应元件 | 光轴高度 (mm) |
|---|---|---|---|---|
| Olego_MDI_HS (STL) | 25.32 | 24.30 | Radiant Dyes MDI-HS | 50.80 |
| Olego_M05 | 39.60 | 38.10 | Newport M05 | 50.76 |
| Olego_M05_0deg | 39.60 | 38.10 | 使光束沿原路返回的 M05 | 50.76 |
| Olego_polaris_0.5inch_mirror | 39.37 | 38.10 | Thorlabs Polaris K05 | 50.80 |
| Olego_CP33 | 31.50 | 30.50 | CP33、CRM1T、笼式光纤耦合器 | 50.82 |
| Olego_RSP05 | 37.85 | 36.80 | RSP05 | 50.78 |
| Olego_PBS_0.5in | 45.47 | 44.50 | ½ 英寸 PBS 立方体 | 50.85 |
| Olego_LMR1 | 29.90 | 27.90 | LMR1 | **50.00** |
| Olego_SR475 | 44.00 | 44.00 | SR475 快门 | **48.75** |
| PD36A2_mount | 30.80 | 25.80 | PDA36A2（暂用简化形状） | 50.80（固定） |

尚未达到 2 英寸的两项：

- **LMR1**：22.1 mm 的安装座高度可能用错了测量基准面。
- **SR475**：作为光阑使用的 3 mm 孔距底面 4.75 mm，使光束偏低约 2 mm。应确认快门在立柱上的安装方向及光阑位置。
