# Optical Layout Designer 中文版

光路布局、光功率记录和 Blender 导出。这个私有仓库存放 macOS 安装包及对应手册。

- [下载应用和源码](https://github.com/TigerWang215/-blender-/releases/tag/v1.0.0-zh-macos.1)
- [中文操作手册](USER_AGENT_GUIDE.md)

## 安装

使用 Apple Silicon Mac 和 macOS 14 或更新版本。从 Release 获取 macOS arm64 应用，按发布说明合并分卷并校验 ZIP。解压后将 `Optical Layout Designer.app` 拖进「应用程序」。这个构建使用本地临时签名，未通过 Apple 公证。若系统阻止打开，可校验文件并检查该应用的「隐私与安全性」提示。使用导出功能时，将 Blender 放到「应用程序」。

下载的 ZIP 和手册可用 Release 内的 `SHA256SUMS.txt` 校验。在文件所在目录运行 `shasum -a 256 -c SHA256SUMS.txt`。

## 来源与许可

基于 Jiahao Lyu 的 [Optical Layout Designer](https://github.com/FrankLyu/Optical-Layout-Designer/tree/29d6961885281eb86f8e66cccd20f6af6295143e)，保留原项目 [MIT 许可证](LICENSE)。中文界面和文档及 Blender 导出属于此处的定制修改。原项目标注的厂家 CAD 衍生模型和应用包中的第三方依赖分别遵循各自条款。
