# 🎮 GameAuto Daily

游戏日常自动化工具 —— 一键完成鸣潮、终末地、异环的每日任务。

图形界面配置，支持定时任务、钉钉推送、AI 异常处理，打包为单文件免安装。

## ✨ 功能特性

- **三款游戏**: 鸣潮 (ok-ww)、终末地 (MaaEnd)、异环 (ok-nte)
- **图形界面**: 暗黑电竞风，5 套可切换主题皮肤
- **多账号流水线**: 鸣潮支持多账号依次切换执行
- **实时日志**: 彩色分级显示，左右可拖拽分栏
- **定时任务**: 一键创建 Windows 计划任务，每天自动运行
- **AI 异常处理**: 截图 + 多模态模型自动处理弹窗/卡死
- **钉钉通知**: 任务报告推送 + 异常告警
- **网络自愈**: WiFi 故障自动切换备用网络
- **自动关机**: 任务完成自动关机
- **单文件打包**: 无需安装 Python，下载即用

## 📥 安装使用

### 方式一：免安装（推荐）

从 [Releases](../../releases) 下载 `GameAutoDaily.exe`，放到任意目录，**以管理员身份运行**。

首次启动后，在左侧配置面板填写各项路径和密钥，点击「💾 保存配置」。

### 方式二：源码运行

**环境要求**: Windows 10/11 64位、Python 3.8+、管理员权限

```bash
# 1. 克隆或下载项目
git clone https://github.com/<用户名>/GameAuto.git
cd GameAuto

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python main.py
```

双击 `run.bat` 可一键安装依赖并启动。

### 方式三：自行打包

```bash
pip install -r requirements.txt
pyinstaller build.spec
# 输出: dist/GameAutoDaily.exe
```

或双击 `build.bat`。

## 📖 使用教程

### 1. 基础配置

启动后界面分为**左右两栏**，中间拖拽条可调节宽度。

**左侧 — 7 个配置 Tab：**

| Tab | 配置项 | 说明 |
|-----|--------|------|
| **总设置** | 日志路径、自动关机、计划任务、超时参数 | 默认即可，按需调整 |
| **鸣潮** | ok-ww 路径、账号列表、运行模式 | 必填：可执行文件路径 + 账号尾号 |
| **终末地** | MaaEnd 路径 | 必填：可执行文件路径 |
| **异环** | ok-nte 路径 | 可选 |
| **钉钉** | Webhook URL、@手机号 | 需要钉钉群机器人 |
| **AI** | API Key、模型 | 需要阿里云 DashScope |
| **网络** | WiFi 名称 | 网络故障时自动切换 |

**右侧 — 运行日志 + 控制面板**

### 2. 填写路径

每个路径字段右侧有 📂 按钮，点击浏览文件/文件夹。关键路径：

- `okww_exe`: ok-ww 的 exe 文件（如 `D:\tools\ok-ww\ok-ww.exe`）
- `maaend_exe`: MaaEnd 的 exe 文件
- `okww_log_dir` / `maaend_log_dir`: 自动填充，通常与工具同目录

### 3. 账号配置（鸣潮）

- `okww_run_mode`: 1 = 单账号，2 = 多账号
- `okww_expected_accounts`: 账号尾号列表，点「+ 添加」逐个输入

多账号模式下，程序会自动切号并依次执行。

### 4. 运行任务

1. 填写必要配置
2. 点击「**💾 保存配置**」
3. 点击「**▶ 开始**」
4. 右侧日志区实时显示运行状态
5. 中途可点「⏹ 停止」瞬间刹停

### 5. 定时任务

1. 在「总设置」Tab 勾选「计划任务 - 启用」
2. 设置执行时间（如 `09:40`）
3. 点击「💾 保存配置」或直接点「创建」按钮
4. 状态栏显示 `✅ 已创建 | 下次运行: ...`
5. 每天到点自动启动 exe 并执行，全程无人值守

可在 Windows「任务计划程序」中查看/管理。

### 6. 钉钉通知

1. 创建钉钉群 → 群设置 → 智能群助手 → 添加机器人 → 选择「自定义（通过 Webhook）」
2. 复制 Webhook URL，填入「钉钉」Tab
3. 启用「详细报告」，填入需 @ 的手机号
4. 任务完成后自动推送执行报告，异常时发送告警

### 7. AI 异常处理

1. 前往 [阿里云 DashScope](https://dashscope.console.aliyun.com/) 获取 API Key
2. 在「AI」Tab 填入 Key，选择模型
3. 推荐模型：`qwen3-vl-flash`（经济）/ `qwen3-vl-plus`（精准）
4. 运行时若长时间无日志更新，AI 会自动截图分析并操作

### 8. 主题切换

标题栏右侧有 5 个主题按钮：暗夜绿 / 深海蓝 / 碳素灰 / 日落橙 / 极光白，点击即切。

## 🏗 项目结构

```
GameAuto/
├── main.py                 # 入口（管理员提权 + GUI/自动模式）
├── gui.py                  # CustomTkinter GUI
├── config_manager.py       # JSON 配置管理
├── core/                   # 核心逻辑
│   ├── task_runner.py      # 后台任务编排
│   ├── log_analyzer.py     # 日志分析（3 游戏）
│   ├── ai_assistant.py     # AI 多模态处理
│   ├── process_tools.py    # 窗口/进程管理
│   ├── network.py          # WiFi 自愈
│   ├── dingtalk.py         # 钉钉推送
│   ├── scheduler.py        # Windows 计划任务
│   ├── history.py          # 历史记录告警
│   ├── shutdown.py         # 自动关机
│   └── logger.py           # 日志记录
├── Switcher/               # 鸣潮账号切换
│   ├── WwAccountSwitcher.py
│   └── imgs/               # 模板图片
├── resources/
│   └── default_config.json # 默认配置模板
├── requirements.txt
├── build.spec              # PyInstaller 打包配置
├── build.bat / run.bat
└── README.md
```

## ⚠️ 注意事项

1. **管理员权限**: 程序需要管理员权限以控制游戏窗口
2. **屏幕分辨率**: 建议 1920×1080 以上
3. **游戏状态**: 运行前确保游戏已关闭，程序会自动清理进程
4. **首次使用**: 请先在 GUI 中填写路径和密钥再启动任务
5. **隐私安全**: `config.json` 包含本地密钥，不会上传 GitHub

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)
