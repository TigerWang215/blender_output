# 界面调研笔记（2026-10-10）

调研参考了 KiCad 的原理图和 PCB 编辑器、PyOpticL、gtrace、Zemax OpticStudio、Franzen 的 ComponentLibrary、Ray Optics Simulation，以及 Figma 和 draw.io 的操作方式。

| 功能 | 参考 | 本项目的做法 |
|---|---|---|
| 原理图驱动布局 | KiCad 的 F8 | 随光路图实时同步 |
| 新元件暂存区 | KiCad 用户常反馈元件落在板外 | 在平台下方设置有标签的暂存区域，并显示状态栏提示 |
| 双向联动选择 | KiCad | 两视图同步选择，双击跳到光路图并居中 |
| 批量字段编辑 | KiCad Symbol Fields Table | 元件表 (Ctrl+T)，支持下拉框、撤销和导出 CSV |
| 反射镜沿光束角平分线定向 | PyOpticL 和 gtrace 在代码中计算 | 反射镜、轴上光学元件、终点和分束立方体自动定向。手动旋转可覆盖，A 恢复 |
| 在光路中插入元件 | OpticStudio 的 Add Fold Mirror，PyOpticL 的 `place_element_along_beam` | 将符号放到光路图上的光束会拆分光束，上游保留 ID，以维持测量点关联 |
| 方向键按网格微调 | KiCad、Figma | 方向键移动一个孔位，Shift 移动 1 mm。光路图中是 1/5 格 |
| 按修饰键临时关闭吸附 | draw.io 的 Alt | 在布局中按 Alt 拖动 |
| 复制 | Figma、draw.io 的 Ctrl+D | 在光路图按 Ctrl+D，平台布局同步创建副本 |
| 重叠外框提示 | KiCad | 重叠元件显示红色虚线边框，可从「平台布局 → 显示重叠元件」查看 |
| 固定屏幕大小的标签 | Qt 的 `ItemIgnoresTransformations`，KiCad 元件位号 | 用于测量点标签，可按 Ctrl+= 或 Ctrl+- 调整 |
| 缩放到所选对象 | 常见 CAD 软件 | Z |

待实现：按 F8 后元件跟随光标、区分移动和拖动、以支柱孔为移动基准、紧凑排布选中元件、检查光束遮挡的设计规则。当前拖动元件时光束始终保持连接。
