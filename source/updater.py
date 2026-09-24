# -*- coding: utf-8 -*-
"""启动后自动检查 GitHub Releases 更新。

查询 koudaiNEW/MBAutoFarm 的 latest release：tag 与 APP_VERSION 一致则
无需更新；不一致则弹窗询问用户，确认后下载其中的 zip 资产
（MBAutoFarm.dist 的压缩包），解压后覆盖程序目录并重启。

运行中的 exe 及其 DLL 在 Windows 上被锁定无法直接覆盖，因此覆盖动作由
临时批处理完成：主程序退出后批处理用 robocopy 将新文件覆盖到程序目录，
再重新启动 MBAutoFarm.exe。robocopy 不带 /PURGE，config.json 等运行时
生成的文件会被保留。
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
import time

REPO = "koudaiNEW/MBAutoFarm"
LATEST_API = "https://api.github.com/repos/%s/releases/latest" % REPO
EXE_NAME = "MBAutoFarm.exe"
USER_AGENT = "MBAutoFarm-updater"

_UPDATE_BAT = """@echo off
setlocal
set "PID=%~1"
set "SRC=%~2"
set "DST=%~3"
set "WORK=%~4"
set "LOG=%TEMP%\\MBAutoFarm_update.log"
echo [%date% %time%] wait pid=%PID% >> "%LOG%"
:waitloop
tasklist /FI "PID eq %PID%" /NH 2>nul | findstr /C:" %PID% " >nul 2>nul
if not errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto waitloop
)
echo [%date% %time%] copy %SRC% -^> %DST% >> "%LOG%"
robocopy "%SRC%" "%DST%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
echo [%date% %time%] robocopy rc=%errorlevel% >> "%LOG%"
if errorlevel 8 exit /b 1
start "" "%DST%\\MBAutoFarm.exe"
cd /d "%TEMP%"
rmdir /s /q "%WORK%" 2>nul
endlocal
(goto) 2>nul & del "%~f0" >nul 2>nul
"""


def is_frozen():
    """是否运行在打包后的 exe 环境中（Nuitka / PyInstaller）。"""
    if getattr(sys, "frozen", False):
        return True
    main = sys.modules.get("__main__")
    return hasattr(main, "__compiled__") or "__compiled__" in globals()


def normalize_version(v):
    """统一版本号格式，忽略 tag 常见的 v 前缀。"""
    return (v or "").strip().lstrip("vV")


class Updater:
    def __init__(self, app_version, log, parent=None):
        self.appVersion = app_version
        self.log = log
        self.parent = parent  # 弹窗的父窗口（QWidget）
        self.checkAppVersion = True

    def check_async(self):
        """打包环境下后台线程检查更新；开发环境跳过。"""
        if not is_frozen():
            self.log("INFO", "开发环境运行，跳过更新检查")
            return
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        lastCheckTime = 0
        while self.checkAppVersion:
            try:
                if time.time() - lastCheckTime > 2 * 60 * 60:
                    lastCheckTime = time.time()
                    self._check_and_update()
            except Exception as e:
                self.log("WARNING", "检查更新失败: %s", e)
            time.sleep(10 * 60)

    def _confirm_update(self, tag):
        """在 GUI 线程弹窗询问是否更新，返回 True 表示用户选择更新。"""
        from PySide6.QtCore import QCoreApplication, QTimer
        from PySide6.QtWidgets import QMessageBox
        app = QCoreApplication.instance()
        if app is None:
            return False
        result = {}
        answered = threading.Event()

        def ask():
            box = QMessageBox(self.parent)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("发现新版本")
            box.setText("最新版本 %s\n当前版本 %s" % (tag, self.appVersion))
            box.setInformativeText("是否立即下载并更新？\n更新时程序将自动退出、覆盖安装并重新运行。")
            yes = box.addButton("更新", QMessageBox.ButtonRole.YesRole)
            box.addButton("不更新", QMessageBox.ButtonRole.NoRole)
            box.setDefaultButton(yes)
            box.exec()
            result["yes"] = box.clickedButton() is yes
            answered.set()

        QTimer.singleShot(0, app, ask)  # ask 在 app 所在的 GUI 线程执行
        answered.wait()
        return result.get("yes", False)

    def _check_and_update(self):
        self.log("INFO", "正在检查更新...")
        release = self._fetch_json(LATEST_API)
        tag = release.get("tag_name", "")
        self.log("INFO", "当前版本 v%s，最新版本 %s", self.appVersion, tag)
        if normalize_version(tag) == normalize_version(self.appVersion):
            self.log("INFO", "当前已是最新版本")
            return
        asset_url = None
        for asset in release.get("assets", []):
            if asset.get("name", "").lower().endswith(".zip"):
                asset_url = asset.get("browser_download_url")
                break
        if not asset_url:
            self.log("WARNING", "最新版本 %s 未包含 zip 更新包，无法自动更新", tag)
            return
        if not self._confirm_update(tag):
            self.checkAppVersion = False
            self.log("INFO", "已取消更新")
            return
        work_dir = tempfile.mkdtemp(prefix="MBAutoFarm_update_")
        zip_path = os.path.join(work_dir, "update.zip")
        self._download(asset_url, zip_path)
        src_dir = self._extract(zip_path, work_dir)
        self._apply_and_restart(src_dir, work_dir)

    def _fetch_json(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _download(self, url, dst):
        self.log("INFO", "开始下载更新包: %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dst, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            received, last_pct = 0, -1
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)
                if total:
                    pct = received * 10 // total  # 每 10% 记录一次
                    if pct != last_pct:
                        last_pct = pct
                        self.log("INFO", "下载进度 %d%%", min(pct * 10, 100))
        self.log("INFO", "更新包下载完成")

    def _extract(self, zip_path, work_dir):
        """解压并返回内含 MBAutoFarm.exe 的目录（兼容 zip 内是否含一层目录）。"""
        extract_dir = os.path.join(work_dir, "extracted")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        candidates = [extract_dir]
        for name in os.listdir(extract_dir):
            sub = os.path.join(extract_dir, name)
            if os.path.isdir(sub):
                candidates.append(sub)
        for cand in candidates:
            if os.path.isfile(os.path.join(cand, EXE_NAME)):
                return cand
        raise RuntimeError("更新包中未找到 %s" % EXE_NAME)

    def _apply_and_restart(self, src_dir, work_dir):
        """启动批处理等待本进程退出后覆盖程序目录并重启，然后退出主程序。"""
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
        bat_path = os.path.join(tempfile.gettempdir(),
                                "MBAutoFarm_apply_%d.bat" % os.getpid())
        with open(bat_path, "w", encoding="ascii") as f:
            f.write(_UPDATE_BAT)
        self.log("INFO", "更新包已就绪，程序将退出、覆盖安装并自动重启")
        time.sleep(3)
        # 必须以 NUL 提供有效的标准句柄：DETACHED 方式启动的 cmd 句柄无效，
        # 执行到管道命令（tasklist | findstr）会直接崩溃
        null = open(os.devnull, "r+b")
        try:
            subprocess.Popen(["cmd", "/c", bat_path, str(os.getpid()),
                              src_dir, app_dir, work_dir],
                             cwd=tempfile.gettempdir(),
                             stdin=null, stdout=null, stderr=null,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            null.close()
        from PySide6.QtCore import QCoreApplication, QMetaObject, Qt
        app = QCoreApplication.instance()
        if app is not None:
            QMetaObject.invokeMethod(app, "quit", Qt.QueuedConnection)
