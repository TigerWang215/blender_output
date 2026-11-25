# 元件库

`mounts.json` 列出 3D 使用的安装座、产品页面、尺寸和光轴高度。仓库附带 `mesh/` 下的简化网格，足以在 3D 中查看安装座形状。完整 STEP 文件需从厂家下载。缺少网格的元件会以简化形状显示，3D 视图提示可查看缺少的模型。

## LCOS 空间光调制器

在「光路图符号」中选 **LCOS 空间光调制器**，默认标签为 `LCOS1`，料号可填写实物型号。将入射和反射光束接到同一光窗。自动定向按镜面反射几何计算，可在平台布局中手动调整角度。这里的 LCOS 用于光路布局和装配预览。

通用机头采用程序生成的近似外形，水平占地约 30 × 50 mm（含安装脚），正面光窗约 16 × 12 mm。外壳参照实物照片的形态，光窗尺度参考厂家资料。装配尺寸以实际型号的外形和安装孔图为准。 [Hamamatsu X15213 数据手册](https://lcos-slm.hamamatsu.com/content/dam/hamamatsu-photonics/sites/documents/99_SALES_LIBRARY/lpd/x15213_E.pdf) · [HOLOEYE PLUTO-2.1](https://holoeye.com/products/spatial-light-modulators/pluto-2-1-lcos-phase-only-refl/)

## 光栅与 CCD 相机

- 在「光路图符号」中选 **光栅**。放置时可输入宽度、高度和厚度，默认 25 × 25 × 6 mm。放置后在光路图选中光栅，也可从右侧「光栅尺寸」修改。尺寸随布局保存，并更新占地、物料清单和三维模型。较高的光栅会抬升光学中心，使安装脚留在平台上。光束走向可按实际布置手动连接。 [Thorlabs 光栅尺寸参考](https://www.thorlabs.com/catalogpages/V21/879.pdf)
- 在「光路图符号」中选 **CCD 相机**。相机作为接收端，自动将前端感光口朝向所连光束。机身包含圆形接口、方形感光窗、侧出线和支架，采用照片参考的通用外形。

## 从 STEP 文件添加元件

分别准备二维符号与 3D 模型。二维符号需要手工绘制，在光路图和平台布局中共用，3D 模型可用厂家 STEP 文件生成。

1. **取得 STEP 文件。** 从厂家产品页面下载，Thorlabs 通常放在 CAD 选项卡。保存到 `component_library/step/`，例如 `component_library/step/KM200.step`。后续命令使用去掉扩展名的文件名。
2. **对齐模型。** 按[对齐坐标系](#对齐坐标系)调整模型。厂家模型通常需在 `tools/simplify_cad.py` 的 `POSES` 中增加一项。
3. **生成网格。** 先安装 `cadquery-ocp` 和 `pyvista`，再运行：

   ```sh
   python tools/simplify_cad.py KM200
   ```

   3D 视图使用输出的 `component_library/mesh/KM200.ply`。命令还会打印 `base … mm below the optic`，即第 5 步所用的光轴高度。如果预览中的模型形状或高度有误，请修正姿态后重新生成。
4. **绘制二维符号。** 在 `optolayout/symbols.py` 中编写绘图函数，调用 `register()`，传入新类型标识、显示名称、默认料号和工具栏分组：

   ```python
   register("mirror_km200", "2 英寸反射镜（Thorlabs）", _tl_mirror_2in, "KM200", "反射镜")
   ```

   用 mm 在元件自己的坐标系中绘制，将反射镜表面或透镜中心的光学点放在原点，光束沿 +x，安装座在其后方的 −x。可从类似的符号改起。
5. **关联 3D 模型。** 在 `optolayout/mounts3d.py` 的 `MODELS` 中添加 STEP 文件名和第 3 步得到的光轴高度：

   ```python
   "mirror_km200": Model3D("KM200.step", 38.10, mirror_disc=50.8),
   ```

   `mirror_disc` 或 `glass_disc` 添加光学元件本体，`extras` 列出计入物料清单的转接件。
6. **设置占地尺寸。** 将俯视网格边界加入同一文件的 `MESH_FOOTPRINT`，以便检查重叠以及计算转接件或底座尺寸。省略时，重叠检查用较宽松的二维轮廓，转接件和底座默认宽 20 mm。可用以下命令获取边界：

   ```sh
   python -c "import pyvista as pv; print(pv.read('component_library/mesh/KM200.ply').bounds[:4])"
   ```

   数字依次是 xmin、xmax、ymin 和 ymax：

   ```python
   "KM200": (-40.0, 9.0, -38.0, 38.0),
   ```
7. **设置安装方式。**
   - **Olego**：在 `OLEGO_PILLARS` 中关联立柱。安装座底面不在光轴正下方时，将偏移加入 `MOUNT_BASE_OFFSET`。参见 [Olego 说明](../docs/OLEGO_MATING.md)。
   - **LightFlow**：在 `LIGHTFLOW_ELEMENTS` 中加入 `LightFlowElement`，填写底座占地尺寸和螺钉孔位。省略时使用与元件占地相同的通用底座。参见 [LightFlow 说明](../docs/LIGHTFLOW_BOARD.md)。
   - **PyOpticL、网格和预钻孔平台**：可沿用按占地尺寸和光轴高度计算的转接件或支柱。
8. **检查效果。** 重启程序并放置元件，在「平台布局」和「3D」中检查。安装座应将元件抬到光束高度、朝向光束，并与二维符号一致。

也可在 `mounts.json` 和下表登记来源，方便他人复现。这份 JSON 用于记录型号、来源、尺寸和光轴高度。

## 重建已有模型

下表中的完整 STEP 文件需自行下载。收到厂家更新后，可将文件按表中名称存到 `component_library/step/`，运行 `python tools/simplify_cad.py <文件名不含扩展名>` 重新生成网格。

| 二维元件类型 | 元件 | 文件名 | 来源 | 光轴距底面 |
|---|---|---|---|---|
| `mirror_1in` | Thorlabs KM100 | `KM100.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=KM100) | 25.40 mm |
| `mirror_half_in` | Thorlabs KM05 | `KM05.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=KM05) | 14.73 mm |
| `mirror_polaris_half` | Thorlabs POLARIS-K05S1 | `POLARIS-K05S1.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=POLARIS-K05S1) | 12.70 mm |
| `mirror_d` | 自制立柱上的 Thorlabs DMM1 | `DMM1_lab.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=DMM1) （仅 DMM1） | 25.40 mm |
| `mirror_rd_1in`, `mirror_rd_half_in` | Radiant Dyes MDI-HS, 1" | `MDI-HS-2-3030.stp` | [radiant-dyes.com](https://www.radiant-dyes.com) （未列出时可联系厂家） | 26.50 mm |
| `mirror_newport_half` | Newport M05 | `Newport-M05.stp` | [newport.com](https://www.newport.com) | 12.66 mm |
| `hwp`, `qwp` | Thorlabs RSP1 | `RSP1.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=RSP1) | 27.73 mm |
| `hwp_half`, `qwp_half` | Thorlabs RSP05 | `RSP05.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=RSP05) | 13.98 mm |
| `hwp_crm`, `qwp_crm` | Thorlabs CRM1T | `CRM1T-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=CRM1T) | 22.40 mm |
| `fiber` | HCA3 上的 Thorlabs PAF2-A4A | `PAF2-A4A_on_HCA3.step` | [PAF2-A4A](https://www.thorlabs.com/thorproduct.cfm?partnumber=PAF2-A4A), HCA3（组合两者） | 26.99 mm |
| `iris` | Thorlabs IDA12 | `IDA12.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=IDA12) | 13.3 mm |
| `lens_1in`, `fiber_cage` | Thorlabs CP33 | `CP33-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=CP33) | 20.32 mm |
| `lens_lmr1` | Thorlabs LMR1 | `LMR1-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=LMR1) | 22.10 mm |
| `shutter` | SRS SR475 | `3DSR475.stp` | [thinksrs.com](https://www.thinksrs.com) | 4.75 mm |
| 功率探头 | Thorlabs S121C | `S121C-Step.step` | [thorlabs.com](https://www.thorlabs.com/thorproduct.cfm?partnumber=S121C) | 不适用 |

立方体、AOM、激光器、光束终止器和光电二极管等缺少登记的元件会用简化形状绘制。仓库中 `mesh/Olego/` 和 `mesh/LightFlow/` 的网格分别用于显示 Olego 立柱和 LightFlow 底座。`Olego_step/` 和 `lightflow small mount - new/` 的 STL 文件可用于打印或加工相应部件。

## 对齐坐标系

所有模型采用元件库坐标系：

- 原点在光学中心。
- +x 沿光轴或光学面的法线。
- +z 向上，安装座底面位于其下方。
- 单位为 mm。

厂家文件往往使用其他坐标系，未对齐会造成偏移或旋转。`tools/simplify_cad.py` 的 `POSES` 记录文件坐标中的光学中心，以及对应 +x 和 +z 的方向。

- 已根据下载文件测量的模型包括 `MDI-HS-2-3030`、`Newport-M05`、`CP33-Step`、`CRM1T-Step`、`LMR1-Step`、`3DSR475` 和 `S121C-Step`。厂家更新模型后仍需检查。
- 其他模型需要各自的姿态。可用 `mounts.json` 的 `bbox_mm` 核对元件库坐标系内的包围盒。[PyOpticL](https://github.com/UMassIonTrappers/PyOpticL) 提供许多 Thorlabs 元件的变换参数，相关链接见 `cad_source`。

## 来源

- 光轴高度优先参考 PyOpticL 的 `mount_position`，其次使用模型的包围盒。所用来源记录在 `optic_center_height_source`。
- 厂家名称和料号是各自所有者的商标，本项目与厂家无隶属关系。
