# -*- coding: utf-8 -*-
"""使用 Nuitka 打包 MBAutoFarm 的构建脚本。

用法: python build.py
产物: dist/main.dist/ 目录，内含 main.exe 及 sample/、Theme/ 资源，
      整个目录拷贝到目标机器即可运行。

说明:
- 使用 --standalone（目录形态）而非 --onefile：程序通过 __file__ 相对路径
  读写 config.json 和 sample/ 资源，onefile 会把这些路径指向临时解压目录，
  导致配置无法持久保存。
"""
import os
import subprocess
import sys

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SOURCE_DIR, "dist")

NUITKA_ARGS = [
    "--standalone",
    "--enable-plugin=pyside6",
    "--windows-console-mode=disable",  # GUI 程序，不显示控制台窗口
    "--assume-yes-for-downloads",      # 自动下载依赖工具（如 ccache）
    "--remove-output",                 # 构建前清理上次的产物
    "--output-dir=%s" % OUTPUT_DIR,
    # 运行时通过 __file__ 相对路径访问的资源目录
    "--include-data-dir=%s=sample" % os.path.join(SOURCE_DIR, "sample"),
    "--include-data-dir=%s=Theme" % os.path.join(SOURCE_DIR, "Theme"),
]


def main():
    cmd = ([sys.executable, "-m", "nuitka"] + NUITKA_ARGS +
           [os.path.join(SOURCE_DIR, "MBAutoFarm.py")])
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=SOURCE_DIR)


if __name__ == "__main__":
    sys.exit(main())
