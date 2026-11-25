# Optical Layout Designer 中文版

用于设计光学平台上的光路、预览器件摆放，并将布局导出到 Blender。

## 下载 macOS 应用

[在 GitHub Release 下载 ZIP 安装包](https://github.com/TigerWang215/-blender-/releases/tag/macos-v1.0-20261125)

适用于 **Apple 芯片 Mac，macOS 26.5 或更新版本**。在发布页的 **Assets** 下载 ZIP，解压后将 `Optical Layout Designer.app` 拖入「应用程序」。

## 主要功能

- 绘制光路图，在光学面包板上按实际尺寸摆放器件。
- 在 3D 视图中检查布局，设置光束波长、束径、透镜焦距和光阑孔径。
- 记录光功率并生成物料清单。
- 一键导出到 Blender，可附带独立的器件名称。

## 从源码运行

```sh
python -m pip install -r requirements.txt
python run.py examples/demo_schematic.json
```

具体操作见[中文手册](docs/USER_AGENT_GUIDE.md)。

## 许可证

本项目基于 Jiahao Lyu 的 Optical Layout Designer 修改，源代码采用 MIT 许可证。原版权声明见 [LICENSE](LICENSE)。厂商元件模型和安装包里的第三方依赖各自适用其许可。
