# MBAutoFarm

《瑪奇 Mobile》（Mabinogi Mobile）自动采集辅助工具。基于 PySide6 图形界面、OpenCV 图像模板匹配与 Win32 键鼠模拟，实现采集任务的自动循环执行。

> 仅供学习与研究使用，请遵守游戏用户协议。

## 功能特性

- **任务列表管理**：添加 / 删除 / 双击重命名任务，每个任务独立保存采集类型与采集目标配置，通过 `config.json` 持久化，启动时自动恢复。
- **采集类型联动**：支持日常采集、伐木、采矿、采集药草、剪羊毛、收割、锄地、昆虫采集、钓鱼共 9 种类型，采集目标下拉框随类型自动更新。
- **自动化流程**：
  - 标准采集流程：打开生活技能菜单 → 选择采集类型与目标（目标靠后时自动滚轮翻页）→ 前往采集点 → 等待采集完成（含加载检测）→ 整理背包 → 循环。
  - 工具修复流程：检测到工具磨损标记后自动前往修理点修复并返回任务。
  - 每步图像检测带 3s 超时重试机制，步骤间 2s 延时，点击位置带随机像素偏移。
- **运行状态显示**：实时显示当前任务名称、已执行时间，运行状态标签（蓝底"已停止" / 绿底"运行中"）。
- **分级日志窗口**：DEBUG / INFO / WARNING / ERROR 四级着色显示，带时间戳，上限 10000 条自动丢弃最早记录，线程安全。

## 运行环境

- Windows（依赖 Win32 API 进行窗口捕捉与键鼠模拟）
- Python 3.10+（开发环境为 3.14）
- 依赖库：`PySide6`、`opencv-python`、`numpy`、`Pillow`、`pywin32`
- 游戏进程：`MabinogiMobile.exe`，窗口分辨率 **1280×960**

```bash
pip install -r requirements.txt
```

## 使用方法
- 安装包运行：
1. [点击此处](https://github.com/koudaiNEW/MBAutoFarm/releases)下载最新包体.
2. 解压后双击MBAutoFarm.exe运行.
- 源码运行：
```bash
cd source
python MBAutoFarm.py
```

1. 确认游戏窗口以 1280×960 分辨率运行。
2. 在"任务列表"中点击 **添加** 创建任务（双击可重命名），选中任务后在"任务配置"中选择采集类型与采集目标，点击 **保存** 写入 `config.json`。
3. 选中任务点击 **开始**，程序将自动查找游戏窗口并开始循环采集；点击 **停止** 终止任务。

## 目录结构

```
MBAutoFarm/
├── LICENSE              # MIT License
├── MBAutoFarm.ui        # Qt Designer 界面文件
├── plan.txt             # 任务流程设计描述
└── source/
    ├── MBAutoFarm.py    # 程序入口
    ├── appUI.py         # 界面类（任务列表、日志、状态显示等）
    ├── taskControl.py   # 任务控制（图像匹配、键鼠模拟、采集流程）
    ├── build.py         # Nuitka 打包脚本
    ├── config.json      # 任务配置（运行时生成/更新）
    ├── sample/          # 各步骤判断用的目标图像
    │   └── taskType/    # 各采集类型及目标的模板图像
    └── Theme/           # Qt 主题（qss、图标、qrc 资源）
```

## 打包发布

使用 Nuitka 打包为独立可执行程序（需先 `pip install nuitka`）：

```bash
cd source
python build.py
```

产物为 `source/dist/MBAutoFarm.dist/` 目录，内含 `MBAutoFarm.exe` 及全部资源，整个目录拷贝到目标机器即可运行。

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
