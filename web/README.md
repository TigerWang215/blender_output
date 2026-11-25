# 网页端浏览与功率记录

在桌面程序中编辑布局，可用浏览器查看布局、实验记录表并录入功率或添加光斑照片。网页端和桌面端共用同一个 `<布局文件名>.logbook.sqlite`。

- 网页服务只读取布局 JSON。功率读数和照片通过与桌面版一致的 `Logbook` 代码录入。
- 浏览布局不会写入日志。原先没有日志时，首次录入读数会创建日志文件。
- 网页录入的读数会在几秒内同步到桌面。桌面编辑布局或记录读数后，网页也会在几秒内刷新。
- 网页端代码集中在 `web/`。如果移除此目录，桌面程序会隐藏「网页访问」菜单项。

## 启动

在项目目录中安装依赖，再启动桌面程序：

```sh
python -m pip install -r web/requirements.txt
python run.py
```

从「文件 → 网页访问（在局域网内共享）」开关网页服务。程序会记住选择。启用后，菜单栏右侧显示访问地址。点击可打开，选中可复制。

- **绿点**：网页服务正在运行。
- **灰点**：网页服务已关闭，或已有其他程序窗口或 `start_web.bat` 在该端口提供服务。
- **红点**：服务不可用。悬停查看原因。如果缺少 FastAPI 或 Uvicorn，提示中会显示安装命令。

桌面程序关闭后，由它启动的网页服务也会停止。可单独运行服务，以便桌面程序关闭时仍能访问：

```sh
python web/server.py
```

Windows 下也可双击 `web\start_web.bat`。按 Ctrl+C 或关闭启动窗口可停止。默认在本机浏览器打开 `http://localhost:8000`。允许局域网访问后，其他电脑、平板或手机可打开 `http://<主机地址>:8000`。

## 设置 `web/config.json`

将 `web/config.example.json` 复制为 `web/config.json` 再编辑。默认仅本机能访问，显示 `examples` 目录。要在实验室局域网中使用，可按需修改：

```json
{
  "folders": ["../layouts"],
  "password": "pick-your-own",
  "host": "0.0.0.0",
  "port": 8000
}
```

- `folders`：按填写顺序显示目录，空目录也会列出。可用相对于 `web/` 的路径，或用绝对路径，例如 `D:/Lab/layouts`。只列出用本程序保存的布局 JSON。
- `password`：实验室共享密码，每个浏览器登录时需输入。使用 `0.0.0.0` 之前请设置密码。空字符串表示无需密码。
- `host`：`127.0.0.1` 仅允许本机连接。`0.0.0.0` 允许其他设备连接。
- `port`：默认 8000。如果端口被占用可改用其他端口，并相应调整防火墙规则。

可指定其他配置文件，例如 `python web/server.py /path/to/config.json`。

## 在实验室 Windows 主机部署

1. 将完整项目目录复制到实验室主机，包含 `optolayout`、`component_library`、`web` 和布局目录。保留它们之间的目录关系。
2. 从 python.org 安装 Python 3.13，勾选「Add python.exe to PATH」并保留 `py` 启动器。
3. 在项目目录运行：

   ```powershell
   py -3.13 -m pip install -r requirements.txt -r web\requirements.txt
   ```

4. 如需从同一网络的其他设备访问，以管理员身份在 PowerShell 中允许访问相应端口：

   ```powershell
   New-NetFirewallRule -DisplayName "Optical Layout web (8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Domain,Private,Public -RemoteAddress LocalSubnet
   ```

   也可使用以下等效命令：

   ```cmd
   netsh advfirewall firewall add rule name="Optical Layout web (8000)" dir=in action=allow protocol=TCP localport=8000 remoteip=localsubnet
   ```

   `LocalSubnet` 将访问限制在本地子网。
5. 运行 `ipconfig`，查看正在使用的网络接口的 IPv4 地址。也可尝试用主机名访问 `http://<计算机名>:8000`。
6. 启动桌面程序，从另一台设备访问 `http://<主机地址>:8000`。连接失败时，检查防火墙规则和两台设备是否处于允许互访的网络。部分校园网络会阻止终端互访。
7. 如需登录后自动启动网页服务，可按 Win+R，输入 `shell:startup`，将 `web\start_web.bat` 的快捷方式放入启动目录。也可使用任务计划程序：

   ```cmd
   schtasks /create /tn "Optical Layout web" /sc onlogon /tr "\"C:\path\to\Optical Layout Designer\web\start_web.bat\""
   ```

### 文件存放位置

请让网页服务和桌面程序在同一台主机上读取同一份布局。SQLite 可以协调这台主机上两者对功率日志的写入。

其他设备应通过网页端记录读数。多台电脑通过 OneDrive 或共享目录同时写一个 SQLite 文件，可能出现读数冲突或丢失。可以通过 OneDrive 备份，录入仍集中在实验室主机上。

## 页面

- **布局列表**：查看已配置目录中的布局。
- **平台布局**：二维绘图与桌面导出一致。悬停在测量点上可查看名称、最近读数、测量时间和变化。单击打开日志。用滚轮或双指缩放，拖动平移，按「适应窗口」重置视角。3D 视图位于桌面版。
- **功率测量点**：查看最新读数、趋势、全部读数和光斑照片。添加读数时填写数值、单位、功率计和备注，时间自动记录。可选择图片文件，或用手机和平板直接拍照。
- **实验记录表**：默认选择布局中已保存的测量点。可打印或复制到 OneNote 和 Excel。在网页上改变所选点只影响当前记录表。

## 测试

```sh
python tests/test_web.py
```

测试在示例副本上运行。
