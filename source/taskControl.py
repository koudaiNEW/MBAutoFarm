# -*- coding: utf-8 -*-

import os
import random
import threading
import time
import ctypes
from ctypes import wintypes

import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32process
from PIL import ImageGrab
import json

APP_SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample")

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


def find_pids_by_process_name(name):
    """通过 Toolhelp32 快照按进程名查找 PID 列表（不区分大小写）。

    读快照不需要 OpenProcess，目标进程提权或有反作弊保护时也能找到。
    """
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return []
    pids = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        ret = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ret:
            if entry.szExeFile.lower() == name.lower():
                pids.append(entry.th32ProcessID)
            ret = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return pids


def find_window_by_process_name(name):
    """按进程名查找可见窗口句柄，未找到返回 None。"""
    pids = set(find_pids_by_process_name(name))
    if not pids:
        return None
    matches = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in pids:
            matches.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return matches[0] if matches else None



class taskControl:

    def __init__(self, configPath=None, ui=None):
        self.configPath = configPath
        self.ui = ui
        self.taskRuning = False
        self.taskName = None
        self.taskType = None
        self.taskTarget = None
        self.taskThread_ = None
        self.taskLoopCnt = 0
        self.taskStartTime = None  # 当前任务开始时间（time.time()）
        self._template_cache = {}
        self._lastPos = {}  # findImage 各模板上次命中的左上角位置（动态 ROI）
        self._greenPixelRange = None  # greenMark.png 绿色判定阈值 (gbMin, grMin, gMin)
        self.taskFixFailCnt = 0
        if configPath:  # 读取配置文件
            self.loadConfig()

    def taskThread(self):
        """任务处理主逻辑。"""
        self.ui.log_printf("INFO", u"开始执行任务：%s", self.taskName)
        if not self.setupWindow():
            self.ui.log_printf("ERROR", u"任务失败：%s, 未找到目标进程", self.taskName)
            return
        
        while self.taskRuning:
            try: 
                self.activateWindow()
                if self.findImage(os.path.join("crossDay1.png")) : # 检查是否存在签到
                    self.crossDayFlow()
                if self.findImage(os.path.join("challengeCompleted.png")) : # 检查是否存在挑战任务完成
                    self.pressKey("space")
                if self.taskType < 8:  # 非钓鱼任务，进入标准流程
                    self.standardCollectionFlow()
                else:  # 钓鱼任务，进入钓鱼流程
                    self.fishingFlow()
            except Exception as e:
                self.ui.log_printf("ERROR", u"任务失败：%s, %s", self.taskName, e)
                self.ui.log_printf("INFO", u"重启任务：%s", self.taskName)
        self.ui.log_printf("INFO", u"任务已停止：%s", self.taskName)

    def loadConfig(self):
        """读取 config.json"""
        self.ui._tasks = []
        self.ui.taskListWidget.clear()
        if not os.path.exists(self.configPath): # 配置文件不存在则创建
            self.configProcess = "MabinogiMobile.exe"
            self.configResolution = (1280, 960)
            self.configMatchThreshold = 0.86
            self.configClickRandomOffset = 15
            self.saveConfig()
            return
        try:
            with open(self.configPath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            self.ui.log_printf("ERROR", "读取配置文件失败: %s", e)
            return
        # 读取任务列表
        for task in data.get("tasks", []): 
            self.ui._tasks.append(task)
            self.ui.taskListWidget.addItem(task["name"])
        # 读取配置项
        self.configProcess = data.get("gameProcess", "MabinogiMobile.exe")
        self.configResolution = tuple(data.get("gameResolution", [1280, 960]))
        self.configMatchThreshold = data.get("matchThreshold", 0.86)
        self.configClickRandomOffset = data.get("clickRandomOffset", 15)

    def saveConfig(self):
        """保存 config.json"""
        data = {
            "tasks": self.ui._tasks,
            "gameProcess": self.configProcess,
            "gameResolution": self.configResolution,
            "matchThreshold": self.configMatchThreshold,
            "clickRandomOffset": self.configClickRandomOffset,
        }
        with open(self.configPath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        self.ui.log_printf("INFO", u"已保存配置文件：%s", self.configPath)

    def startTask(self, injectionTask):
        if self.taskRuning:  # 正在运行任务，不允许启动新的任务
            self.ui.log_printf("ERROR", u"任务已启动，请勿重复启动")
            return
        self.taskName = injectionTask['name']
        self.taskType = injectionTask['type']
        self.taskTarget = injectionTask['target']
        self.taskBackpackClean = injectionTask['backpackClean']
        self.taskFixTool = injectionTask['fixTool']
        self.taskRuning = True
        self.taskStartTime = time.time()
        self.ui.log_printf("INFO", u"启动任务线程: name=%s", self.taskName)
        self.taskThread_ = threading.Thread(target=self.taskThread, daemon=True)
        self.taskThread_.start()

    def stopTask(self):
        self.ui.log_printf("INFO", u"停止任务，等待线程结束...")
        self.taskRuning = False
        # if self.taskThread_:
        #     self.taskThread_.join()
            
    def setupWindow(self):
        """查找目标进程窗口，找不到则每秒重试直到任务停止。"""
        logged = False
        while self.taskRuning:
            hwnd = find_window_by_process_name(self.configProcess)
            if hwnd:
                self.hwnd = hwnd
                self.ui.log_printf("DEBUG", u"已找到目标窗口: %s",
                                   self.configProcess)
                self.ui.log_printf("DEBUG", u"窗口句柄 hwnd=%s", hwnd)
                return True
            if not logged:
                self.ui.log_printf("WARNING",
                                   u"未找到进程“%s”的窗口，等待中...",
                                   self.configProcess)
                logged = True
            time.sleep(1.0)
        return False

    def activateWindow(self):
        """将目标窗口置于前台。"""
        self.ui.log_printf("DEBUG", u"激活目标窗口")
        try:
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception as e:
            self.ui.log_printf("WARNING", u"激活窗口失败: %s", e)
        time.sleep(0.2)

    def ensureForeground(self):
        """输入前确保目标窗口在前台，否则重新激活（点击/按键落在前台窗口上）。"""
        try:
            if self.hwnd and win32gui.GetForegroundWindow() != self.hwnd:
                self.ui.log_printf("INFO", u"焦点不在目标窗口，重新激活")
                self.activateWindow()
        except Exception:
            pass
        
    def loadTemplate(self, rel_path):
        """加载目标图像（带缓存；imdecode 方式读取以兼容非 ASCII 路径）。"""
        if rel_path not in self._template_cache:
            path = os.path.join(APP_SAMPLE_DIR, rel_path)
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8),
                               cv2.IMREAD_COLOR)
            if img is None:
                self.ui.log_printf("ERROR", u"无法读取目标图像: %s", path)
            else:
                self.ui.log_printf("DEBUG", u"加载目标图像 %s", rel_path)
            self._template_cache[rel_path] = img
        return self._template_cache[rel_path]
        
    def captureGame(self):
        """捕捉窗口客户区画面（彩色）并缩放至目标分辨率。"""
        try:
            origin, size = self.clientGeometry()
            img = ImageGrab.grab(bbox=(origin[0], origin[1],
                                       origin[0] + size[0],
                                       origin[1] + size[1]))
        except OSError as e:
            self.ui.log_printf("WARNING", u"截图失败: %s", e)
            return None
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        if size != tuple(self.configResolution):  # 已是目标分辨率时跳过多余缩放
            frame = cv2.resize(frame, self.configResolution)
        return frame

    def clientGeometry(self):
        """返回窗口客户区在屏幕上的 (原点, 尺寸)。"""
        left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
        origin = win32gui.ClientToScreen(self.hwnd, (left, top))
        return origin, (right - left, bottom - top)

    def findImage(self, rel_path, matchingDegree = 0.0, logging=True):
        """在当前画面中查找目标图像，返回配置分辨率坐标系下的中心点或 None。

        灰度匹配；命中过的模板先在上次位置附近的局部区域（ROI）搜索，
        未命中再全图搜索，局部匹配可显著降低耗时。
        """
        template = self.loadTemplate(rel_path)
        shot = self.captureGame() if template is not None else None
        if shot is None:
            return None
        threshold = matchingDegree if matchingDegree > 0.0 else self.configMatchThreshold
        gray_tpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        gray_shot = cv2.cvtColor(shot, cv2.COLOR_BGR2GRAY)
        last = self._lastPos.get(rel_path)
        if last is not None:  # 先在上次命中位置 ±80px 的局部区域搜索
            m = 80
            h, w = gray_tpl.shape[:2]
            x0, y0 = max(last[0] - m, 0), max(last[1] - m, 0)
            x1 = min(last[0] + w + m, gray_shot.shape[1])
            y1 = min(last[1] + h + m, gray_shot.shape[0])
            pos = self._matchTemplate(rel_path, gray_shot[y0:y1, x0:x1],
                                      gray_tpl, threshold, (x0, y0), logging)
            if pos is not None:
                return pos
        return self._matchTemplate(rel_path, gray_shot, gray_tpl,
                                   threshold, (0, 0), logging)

    def _matchTemplate(self, rel_path, region, template, threshold, offset, logging):
        """在 region 内匹配模板，命中则记录左上角位置并返回中心点（配置坐标系）。"""
        result = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < threshold:
            return None
        h, w = template.shape[:2]
        top_left = (max_loc[0] + offset[0], max_loc[1] + offset[1])
        self._lastPos[rel_path] = top_left
        pos = (top_left[0] + w // 2, top_left[1] + h // 2)
        if logging:
            self.ui.log_printf("DEBUG", u"匹配到 %s 相似度=%.2f 位置=%s", rel_path, max_val, str(pos))
        return pos
    
    def waitImage(self, rel_path, timeout=None, interval=0.2):
        """循环查找目标图像直到出现；timeout 秒未出现返回 None。"""
        start = time.time()
        while self.taskRuning:
            pos = self.findImage(rel_path)
            if pos is not None:
                return pos
            if timeout is not None and time.time() - start >= timeout:
                self.ui.log_printf("WARNING", u"%ss 内未找到 %s", timeout, rel_path)
                return None
            time.sleep(interval)
        return None

    def countGreenPixels(self, rect=(570, 370, 710, 450)):
        """统计指定区域内的绿色像素数，rect 为配置分辨率坐标系下的
        (x1, y1, x2, y2)，默认为钓鱼进度条区域 X:570-700, Y:403-435。

        绿色判定以 sample/fishing/greenMark.png 为参考：取参考像素 G 通道
        相对 B/R 的最小优势差值和 G 最小值，减容差后作为阈值，要求 G 显著
        高于 B 和 R（避免水面等蓝绿色被误判），截图失败返回 0。
        """
        if self._greenPixelRange is None:
            mark = self.loadTemplate(os.path.join("fishing", "greenMark.png"))
            if mark is None:
                return 0
            px = mark.reshape(-1, 3).astype(np.int16)
            b, g, r = px[:, 0], px[:, 1], px[:, 2]
            tol = 60
            self._greenPixelRange = (int((g - b).min()) - tol,
                                     int((g - r).min()) - tol,
                                     int(g.min()) - tol - 20)
        shot = self.captureGame()
        if shot is None:
            return 0
        x1, y1, x2, y2 = rect
        region = shot[y1:y2 + 1, x1:x2 + 1].astype(np.int16)
        gbMin, grMin, gMin = self._greenPixelRange
        b = region[:, :, 0]
        g = region[:, :, 1]
        r = region[:, :, 2]
        mask = (g > b + gbMin) & (g > r + grMin) & (g > gMin)
        return int(np.count_nonzero(mask))

    def checkGreenPixelTrend(self, maxSamples=30, interval=0.2, minGrowth=30):
        """持续监控钓鱼区域（X:570-700, Y:403-435）绿色像素变化趋势。

        每隔 interval 秒统计一次绿色像素数，以监控期间出现的最低/最高值
        为基准：从低点净增 minGrowth 以上判定为持续增多，返回 True；
        从高点净减 minGrowth 以上判定为持续减少，返回 False；
        采样 maxSamples 次净变化仍不足 minGrowth 视为保持不变，返回 False。
        （进度条按离散步进更新，不能用相邻样本的连续增减做判定。）
        """
        low = high = None
        for i in range(maxSamples):
            if self.taskRuning is False:
                return False
            cur = self.countGreenPixels()
            if low is None:
                low = high = cur
            else:
                low = min(low, cur)
                high = max(high, cur)
                if cur >= low + minGrowth:
                    self.ui.log_printf("INFO", u"绿色像素持续增多: %d -> %d", low, cur)
                    return True
                if cur <= high - minGrowth:
                    self.ui.log_printf("INFO", u"绿色像素持续减少: %d -> %d", high, cur)
                    return False
            if i < maxSamples - 1:
                time.sleep(interval)
        return False

    def pressKey(self, key, delay=0.15):
        """按下并松开指定按键，支持单个字母/数字及 "space"、"esc"。"""
        self.ensureForeground()
        if key == "space":
            vk = win32con.VK_SPACE
        elif key == "esc":
            vk = win32con.VK_ESCAPE
        else:
            vk = ord(key.upper())
        self.ui.log_printf("DEBUG", u"按键 %s", key)
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(delay)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    def moveCursor(self, pos):
        """将设置坐标系下的点换算为屏幕坐标并移动光标（不点击）。"""
        origin, size = self.clientGeometry()
        x = origin[0] + int(pos[0] * size[0] / self.configResolution[0])
        y = origin[1] + int(pos[1] * size[1] / self.configResolution[1])
        self.ui.log_printf("DEBUG", u"移动光标 (%d, %d)", x, y)
        win32api.SetCursorPos((x, y))

    def clickPos(self, pos):
        """将配置坐标系下的点换算为屏幕坐标并点击鼠标左键。

        点击前在 XY 轴各加 CLICK_RANDOM_OFFSET 像素以内的随机偏移。
        """
        self.ensureForeground()
        origin, size = self.clientGeometry()
        x = origin[0] + int(pos[0] * size[0] / self.configResolution[0])
        y = origin[1] + int(pos[1] * size[1] / self.configResolution[1])
        x += random.randint(-self.configClickRandomOffset, self.configClickRandomOffset)
        y += random.randint(-self.configClickRandomOffset, self.configClickRandomOffset)
        self.ui.log_printf("DEBUG", u"点击 (%d, %d)", x, y)
        win32api.SetCursorPos((x, y))
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.15)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        
    def cursorSliding(self, pos, direction, distance=None, steps=20, duration=0.4):
        """按住左键从 pos 沿 direction 拖动 distance 像素（配置坐标系）。

        按住期间用 SetCursorPos 分 steps 步插值移动（绝对定位，不受指针加速
        影响），终点限制在客户区内，全程耗时约 duration 秒。
        """
        self.ensureForeground()
        origin, size = self.clientGeometry()
        x0 = origin[0] + int(pos[0] * size[0] / self.configResolution[0])
        y0 = origin[1] + int(pos[1] * size[1] / self.configResolution[1])
        x0 += random.randint(-self.configClickRandomOffset, self.configClickRandomOffset)
        y0 += random.randint(-self.configClickRandomOffset, self.configClickRandomOffset)
        if distance is None:
            distance = (self.configResolution[1] if direction in ("up", "down")
                        else self.configResolution[0]) // 2
        if direction == "up":
            dx, dy = 0, -distance
        elif direction == "down":
            dx, dy = 0, distance
        elif direction == "left":
            dx, dy = -distance, 0
        elif direction == "right":
            dx, dy = distance, 0
        else:
            self.ui.log_printf("ERROR", u"未知拖动方向: %s", direction)
            return
        dx = int(dx * size[0] / self.configResolution[0])
        dy = int(dy * size[1] / self.configResolution[1])
        x1 = min(max(x0 + dx, origin[0]), origin[0] + size[0] - 1)
        y1 = min(max(y0 + dy, origin[1]), origin[1] + size[1] - 1)
        self.ui.log_printf("DEBUG", u"拖动 (%d, %d) -> (%d, %d)",
                           x0, y0, x1, y1)
        win32api.SetCursorPos((x0, y0))
        time.sleep(0.06)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.15)
        for i in range(1, steps + 1):
            win32api.SetCursorPos((x0 + (x1 - x0) * i // steps,
                                   y0 + (y1 - y0) * i // steps))
            time.sleep(duration / steps)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def scrollDown(self, times=3, interval=0.05):
        """输入鼠标滚轮向下滚动 times 次。"""
        self.ui.log_printf("DEBUG", u"滚轮向下滚动 %d 次", times)
        for _ in range(times):
            if not self.taskRuning:
                return
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -120, 0)
            time.sleep(interval)
            
    def appBlockWait(self, timeout):
        outTime = time.time() + timeout
        while time.time() < outTime:
            if self.taskRuning is False:
                return 

    def circularSearchOperation(self, imagePath=None, allTimes=6, interval=0.5, 
                                hitKey=None, noHitKey=None, 
                                clickImage=False, clickOffset=(0, 0), 
                                movCursor=False, 
                                hitResults=True, hitOutCnt=1, 
                                hitFun=None, noHitFun=None,
                                hitFunParams=None, noHitFunParams=None,
                                matchingDegree = 0.0, logging=True):
        if imagePath is None:
            self.ui.log_printf("ERROR", u"请指定图片样本路径")
            return False
        hit = 0
        for i in range(allTimes):
            if self.taskRuning is False: # 任务停止
                return False
            pos = self.findImage(imagePath, matchingDegree, logging) # 寻找图片
            if (pos is not None and hitResults is True)or(pos is None and hitResults is False): # 匹配到目标
                hit += 1
                if hit >= hitOutCnt: # 连续匹配
                    if hitKey is not None: # 按下按键
                        self.pressKey(hitKey)
                    if clickImage is True: # 点击坐标
                        pos = pos[0] + clickOffset[0], pos[1] + clickOffset[1]
                        self.clickPos(pos)
                    if movCursor is True: # 移动光标
                        self.moveCursor(pos)
                    if hitFun is not None: # 匹配到目标时执行函数
                        hitFun(hitFunParams)
                    return True
            else: # 未匹配到目标
                hit = 0
                if noHitFun is not None: # 未匹配到目标时执行函数
                    noHitFun(noHitFunParams)
                if noHitKey is not None: # 每个查询周期未匹配到目标时按键
                    self.pressKey(noHitKey)
            self.appBlockWait(interval) # 阻塞等待时间
        return False
        
    def standardCollectionFlow(self):
        self.ui.log_printf("INFO", u"单轮采集开始")
        # 确认为当前为主界面
        if self.circularSearchOperation(imagePath=os.path.join("mainInterfaceMark.png"),
                                        allTimes=6, interval=1.0,
                                        noHitKey='esc') is False:
            self.ui.log_printf("ERROR", u"未在主界面，尝试按 Esc 退出失败")
            return
        # 按下C进入人物界面
        self.appBlockWait(0.6)
        self.pressKey('c')
        self.appBlockWait(0.6)
        # 点击live图标进入生活技能界面
        if self.circularSearchOperation(imagePath=os.path.join("liveSkill1.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到生活技能图标，尝试点击失败")
            return
        self.appBlockWait(0.6)
        # 点击生活技能图标
        if self.circularSearchOperation(imagePath=os.path.join("taskType", "%d.png" % self.taskType),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到目标生活技能图标，尝试点击失败")
            return
        self.appBlockWait(0.6)
        # 移动光标到采集物列表
        if self.circularSearchOperation(imagePath=os.path.join("taskType", str(self.taskType), "listCheck.png"),
                                        allTimes=6, interval=0.5,
                                        movCursor=True) is False:
            self.ui.log_printf("ERROR", u"未找到采集物列表，尝试移动光标失败")
            return
        self.appBlockWait(0.6)
        # 点击目标采集物
        if self.taskTarget < 4:
            if self.circularSearchOperation(imagePath=os.path.join("taskType", str(self.taskType), "%d.png" % self.taskTarget),
                                            allTimes=6, interval=0.5,
                                            clickImage=True) is False:
                self.ui.log_printf("ERROR", u"未找到目标采集物，尝试点击失败")
                return
        else:
            if self.circularSearchOperation(imagePath=os.path.join("taskType", str(self.taskType), "%d.png" % self.taskTarget),
                                            allTimes=12, interval=0.2,
                                            clickImage=True, 
                                            noHitFun=self.scrollDown, noHitFunParams=3) is False:
                self.ui.log_printf("ERROR", u"未找到目标采集物，尝试点击失败")
                return
        self.appBlockWait(0.6)
        # 点击采集
        if self.circularSearchOperation(imagePath=os.path.join("gotoCollection.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到采集按钮，尝试点击失败")
            return
        self.appBlockWait(0.6)
        # 检查是否需要维修工具
        if self.circularSearchOperation(imagePath=os.path.join("fixToolMark.png"),
                                        allTimes=4, interval=0.5) is True:
            if self.taskFixTool == False:
                self.ui.log_printf("ERROR", u"未配置维修工具选项，无可用采集工具，任务退出")
                self.taskRuning = False
                return
            self.fixToolFlow()
            return
        # 等待采集退出
        if self.circularSearchOperation(imagePath=os.path.join("inWorking.png"),
                                        allTimes=600, interval=1.0,
                                        hitResults=False, hitOutCnt=3,
                                        logging=False) is False:
            self.ui.log_printf("ERROR", u"采集超时")
            return
        self.ui.log_printf("INFO", u"采集退出")
        # 整理背包
        if self.taskBackpackClean == True:
            self.taskLoopCnt += 1
            if self.taskLoopCnt > 4 :
                self.taskLoopCnt = 0
                self.packBackpackFlow()
        self.ui.log_printf("INFO", u"单轮采集完成")

    def fixToolFlow(self):
        self.ui.log_printf("INFO", u"开始执行修复工具流程")
        # 返回主界面
        if self.circularSearchOperation(imagePath=os.path.join("mainInterfaceMark.png"),
                                        allTimes=3, interval=1.0,
                                        noHitKey='esc') is False:
            self.ui.log_printf("ERROR", u"未在主界面，尝试按 Esc 退出失败")
            return
        # 进入本地地图
        if self.circularSearchOperation(imagePath=os.path.join("mapMark.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='m') is False:
            self.ui.log_printf("ERROR", u"未找到地图图标，尝试按 M 键进入失败")
            return
        self.appBlockWait(1.0)
        # 进入欧拉大陆
        if self.circularSearchOperation(imagePath=os.path.join("mapOula.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True,
                                        matchingDegree=0.7) is False:
            self.ui.log_printf("ERROR", u"未找到欧拉大陆图标，尝试点击失败")
            return
        self.appBlockWait(1.0)
        # 移动光标并缩小地图
        self.moveCursor((self.configResolution[0] // 2, self.configResolution[1] // 2))
        self.scrollDown(10)
        self.appBlockWait(0.5)
        if self.taskFixFailCnt > 2: # 达到失败重试次数，移动到杜巴顿广场再次尝试
            self.taskFixFailCnt = 0
            # 查找杜巴顿
            if self.circularSearchOperation(imagePath=os.path.join("mapDubadun.png"),
                                            allTimes=6, interval=0.5,
                                            clickImage=True, clickOffset=(0, -15)) is False:
                self.ui.log_printf("ERROR", u"未找到杜巴顿图标，尝试点击失败")
                return
            self.appBlockWait(1.5)
            # 查找广场
            if self.circularSearchOperation(imagePath=os.path.join("mapSquare.png"),
                                            allTimes=6, interval=0.5,
                                            clickImage=True) is False:
                self.ui.log_printf("ERROR", u"未找到广场图标，尝试点击失败")
                return
            self.appBlockWait(1.0)
            # 前往广场
            if self.circularSearchOperation(imagePath=os.path.join("goHere.png"),
                                            allTimes=6, interval=0.5,
                                            hitKey='space') is False:
                self.ui.log_printf("ERROR", u"未找到前往此处图标")
                return
            self.appBlockWait(1.0)
            # 等待到位
            if self.circularSearchOperation(imagePath=os.path.join("inWorking.png"),
                                            allTimes=600, interval=1.0,
                                            hitResults=False, hitOutCnt=12) is False:
                self.ui.log_printf("ERROR", u"广场到位超时")
                return
            self.ui.log_printf("INFO", u"到位完成")
            return
        
        # 往上拖动地图并查找提尔克那
        if self.circularSearchOperation(imagePath=os.path.join("mapTier.png"),
                                        allTimes=10, interval=1.0,
                                        clickImage=True, clickOffset=(0,-15),
                                        noHitFun=self.cursorSliding, noHitFunParams=((self.configResolution[0] // 2, self.configResolution[1] // 2), 'up')) is False:
            self.taskFixFailCnt += 1
            self.ui.log_printf("ERROR", u"未找到提尔克那图标，尝试点击失败")
            return
        self.appBlockWait(1.0)
        # 点击佛格斯
        if self.circularSearchOperation(imagePath=os.path.join("mapFogesi.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.taskFixFailCnt += 1
            self.ui.log_printf("ERROR", u"未找到佛格斯图标，尝试点击失败")
            return
        self.appBlockWait(1.0)
        # 前往佛格斯
        if self.circularSearchOperation(imagePath=os.path.join("goHere.png.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='space') is False:
            self.taskFixFailCnt += 1
            self.ui.log_printf("ERROR", u"未找到前往此处图标")
            return
        # 查找修理按钮
        if self.circularSearchOperation(imagePath=os.path.join("fixToolKey.png"),
                                        allTimes=300, interval=1,
                                        clickImage=True) is False:
            self.taskFixFailCnt += 1
            self.ui.log_printf("ERROR", u"未找到修理图标，尝试点击失败")
            return
        self.appBlockWait(2.0)
        # 按下空格跳过对话
        self.pressKey("space")
        self.appBlockWait(2.0)
        # 点击全部修理
        if self.circularSearchOperation(imagePath=os.path.join("fixAllKey.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到全部修理图标，尝试点击失败")
            return
        self.appBlockWait(2.0)
        # 按下空格确认
        if self.circularSearchOperation(imagePath=os.path.join("fixKey.png.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='space') is False:
            self.ui.log_printf("ERROR", u"未找到修复图标")
            return
        self.appBlockWait(2.0)
        # 跳过对话
        if self.circularSearchOperation(imagePath=os.path.join("fixToolOut.png.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='esc') is False:
            self.ui.log_printf("ERROR", u"未找到跳过对话图标")
            return
        self.appBlockWait(2.0)
        # 结束对话
        if self.circularSearchOperation(imagePath=os.path.join("endTalkKey.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到结束对话图标，尝试点击失败")
            return
        self.appBlockWait(2.0)
        # 按下空格跳过对话
        self.pressKey("space")
        self.appBlockWait(1.0)
        self.taskFixFailCnt = 0
        self.ui.log_printf("INFO", u"工具修复流程结束")
        
    def packBackpackFlow(self):
        self.ui.log_printf("INFO", u"开始执行整理背包流程")
        # 进入背包
        if self.circularSearchOperation(imagePath=os.path.join("mainInterfaceMark.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='i') is False:
            self.ui.log_printf("ERROR", u"从主界面进入背包失败")
            return
        self.appBlockWait(1.0)
        # 检查当前是否为道具页
        if self.circularSearchOperation(imagePath=os.path.join("propPage.png"),
                                        allTimes=1, interval=0,
                                        clickImage=True) is True:
            self.appBlockWait(0.5)
        # 进入整理
        if self.circularSearchOperation(imagePath=os.path.join("organize1.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='a') is False:
            self.ui.log_printf("ERROR", u"从背包进入整理失败")
            return
        self.appBlockWait(1.0)
        # 检查大胆整理关闭
        if self.circularSearchOperation(imagePath=os.path.join("organizeBold.png"),
                                        allTimes=2, interval=0.5,
                                        clickImage=True) is True:
            self.appBlockWait(0.5)
        # 检查是否需要整理
        if self.circularSearchOperation(imagePath=os.path.join("noOrganize.png"),
                                        allTimes=3, interval=0.5) is True:
            self.ui.log_printf("INFO", u"无需整理背包")
            self.appBlockWait(0.5)
            self.pressKey("esc")
            self.appBlockWait(0.5)
            self.pressKey("esc")
            return
        # 整理1
        if self.circularSearchOperation(imagePath=os.path.join("organize2.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='space') is False:
            self.ui.log_printf("ERROR", u"从背包进入整理失败")
            return
        self.appBlockWait(1.0)
        # 整理2
        if self.circularSearchOperation(imagePath=os.path.join("organize3.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='space') is False:
            self.ui.log_printf("ERROR", u"执行整理2失败")
            return
        self.appBlockWait(1.0)
        # 确认
        if self.circularSearchOperation(imagePath=os.path.join("organizeConfirm.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='space') is False:
            self.ui.log_printf("ERROR", u"执行整理确认失败")
            return
        self.appBlockWait(1.0)
        # 返回主界面
        if self.circularSearchOperation(imagePath=os.path.join("mainInterfaceMark.png"),
                                        allTimes=6, interval=0.5,
                                        noHitKey='esc') is False:
            self.ui.log_printf("ERROR", u"从背包返回主界面失败")
            return
        self.ui.log_printf("INFO", u"整理背包流程结束")
        
    def crossDayFlow(self):
        # 光标点击画面
        if self.circularSearchOperation(imagePath=os.path.join("crossDay1.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True, clickOffset=(0,60)) is False:
            self.ui.log_printf("ERROR", u"未找到每日界面标志1")
        self.appBlockWait(3.0)
        # 点击跳过出席簿
        if self.circularSearchOperation(imagePath=os.path.join("crossDay2.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到跳过出席簿图标")
        self.appBlockWait(3.0)
        # 点击确认
        if self.circularSearchOperation(imagePath=os.path.join("crossDay3.png"),
                                        allTimes=6, interval=0.5,
                                        hitKey='space') is False:
            self.ui.log_printf("ERROR", u"未找到确认图标")
        self.appBlockWait(5.0)
        # 退出SP界面
        self.pressKey("esc")

    def fishingFlow(self):
        self.ui.log_printf("WARNING", u"执行钓鱼流程时应收起宠物")
        if self.taskTarget == 6:
            self.fishingDFFlow()
        else:
            self.fishingSTDFlow()
            
    def fishingDFFlow(self):
        self.inFishState()
    
    def fishingSTDFlow(self):
        # 确认为当前为主界面
        if self.circularSearchOperation(imagePath=os.path.join("mainInterfaceMark.png"),
                                        allTimes=6, interval=1.0,
                                        noHitKey='esc') is False:
            self.ui.log_printf("ERROR", u"未在主界面，尝试按 Esc 退出失败")
            return
        self.appBlockWait(1.0)
        # 按下C进入人物界面
        self.pressKey('c')
        self.appBlockWait(1.0)
        # 点击live图标进入生活技能界面
        if self.circularSearchOperation(imagePath=os.path.join("liveSkill1.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到生活技能图标，尝试点击失败")
            return
        self.appBlockWait(0.5)
        # 点击生活技能图标
        if self.circularSearchOperation(imagePath=os.path.join("taskType", "%d.png" % self.taskType),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到目标生活技能图标，尝试点击失败")
            return
        self.appBlockWait(0.5)
        # 移动光标到采集物列表
        if self.circularSearchOperation(imagePath=os.path.join("taskType", str(self.taskType), "listCheck.png"),
                                        allTimes=6, interval=0.5,
                                        movCursor=True) is False:
            self.ui.log_printf("ERROR", u"未找到采集物列表，尝试移动光标失败")
            return
        self.appBlockWait(0.5)
        # 点击目标采集物
        if self.taskTarget < 4:
            if self.circularSearchOperation(imagePath=os.path.join("taskType", str(self.taskType), "%d.png" % self.taskTarget),
                                            allTimes=6, interval=0.5,
                                            clickImage=True) is False:
                self.ui.log_printf("ERROR", u"未找到目标采集物，尝试点击失败")
                return
        else:
            if self.circularSearchOperation(imagePath=os.path.join("taskType", str(self.taskType), "%d.png" % self.taskTarget),
                                            allTimes=12, interval=0.2,
                                            clickImage=True, 
                                            noHitFun=self.scrollDown, noHitFunParams=3) is False:
                self.ui.log_printf("ERROR", u"未找到目标采集物，尝试点击失败")
                return
        self.appBlockWait(0.5)
        # 点击前往钓鱼场
        if self.circularSearchOperation(imagePath=os.path.join("fishing", "gotoFishing.png"),
                                        allTimes=6, interval=0.5,
                                        clickImage=True) is False:
            self.ui.log_printf("ERROR", u"未找到采集按钮，尝试点击失败")
            return
        self.appBlockWait(0.5)
        # 检查是否需要维修工具
        if self.circularSearchOperation(imagePath=os.path.join("fixToolMark.png"),
                                        allTimes=3, interval=0.5) is True:
            if self.taskFixTool == False:
                self.ui.log_printf("ERROR", u"未配置维修工具选项，无可用采集工具，任务退出")
                self.taskRuning = False
                return
            self.fixToolFlow()
            return
        # 到位检查
        if self.circularSearchOperation(imagePath=os.path.join("inWorking.png"),
                                        allTimes=300, interval=1.0,
                                        hitResults=False, hitOutCnt=12) is False:
            self.ui.log_printf("ERROR", u"钓鱼场到位超时")
            return
        self.ui.log_printf("INFO", u"到达钓鱼场")
        # 骑乘检查
        if self.circularSearchOperation(imagePath=os.path.join("rideMark.png"),
                                        allTimes=3, interval=0.5,
                                        clickImage=True) is True:
            self.ui.log_printf("INFO", u"退出骑乘状态")
            self.appBlockWait(2.0)
        # 钓鱼流程
        self.inFishState()

    def inFishState(self):
        moveState = False
        packBackpackCleanCnt = 0
        # 拉远视角
        self.moveCursor((self.configResolution[0] // 2, self.configResolution[1] // 2))
        self.scrollDown(10)
        self.appBlockWait(0.5)
        self.ui.log_printf("WARNING", u"已调整视角，钓鱼中请勿拉近视角")
        while self.taskRuning:
            # 移动
            if moveState is False:
                self.pressKey('w', 0.05) 
                moveState = True
            else:
                self.pressKey('s', 0.05) 
                moveState = False
            # 尝试抛竿
            if self.circularSearchOperation(imagePath=os.path.join("fishing", "casting.png"),
                                            allTimes=6, interval=0.5,
                                            hitKey='space') is False:
                self.ui.log_printf("ERROR", u"未找到抛竿图标")
                return
            self.appBlockWait(0.5)
            # 检查是否需要维修工具
            if self.circularSearchOperation(imagePath=os.path.join("fixToolMark.png"),
                                            allTimes=2, interval=0.5) is True:
                if self.taskFixTool == False:
                    self.ui.log_printf("ERROR", u"未配置维修工具选项，无可用采集工具，任务退出")
                    self.taskRuning = False
                    return
                self.fixToolFlow()
                return
            # 检查钓鱼模式
            if self.circularSearchOperation(imagePath=os.path.join("fishing", "autoState.png"),
                                            allTimes=2, interval=0.5,
                                            clickImage=True) is True:
                self.ui.log_printf("INFO", u"钓鱼切换为专心钓鱼")
                self.appBlockWait(0.5)
                # 切换状态
                if self.circularSearchOperation(imagePath=os.path.join("fishing", "fishingFocusMark.png"),
                                                allTimes=6, interval=0.5,
                                                hitKey='space') is False:
                    self.ui.log_printf("ERROR", u"未找到专心钓鱼图标")
                    return
                self.appBlockWait(0.5)
            # 等待上钩
            if self.circularSearchOperation(imagePath=os.path.join("fishing", "baitMark.png"),
                                            allTimes=300, interval=0.2) is False:
                self.ui.log_printf("ERROR", u"等待上钩超时")
                return
            self.ui.log_printf("INFO", u"已上钩")
            # 等待钓鱼结束
            self.inFishCook()
            time.sleep(3.0)
            # 清理背包
            if self.taskBackpackClean:
                packBackpackCleanCnt += 1
                if packBackpackCleanCnt >= 20:
                    packBackpackCleanCnt = 0
                    self.packBackpackFlow()
                    
    def inFishCook(self):
        # 拉远视角
        self.moveCursor((self.configResolution[0] // 2, self.configResolution[1] // 2))
        self.scrollDown(10)
        self.appBlockWait(0.2)
        greenIncreaseCnt = 0
        lastGreenPixels = self.countGreenPixels()
        fishingCloseCnt = 0
        while self.taskRuning:
            greenPixels = self.countGreenPixels()
            if greenPixels > lastGreenPixels :
                greenIncreaseCnt += 1
                if greenIncreaseCnt >= 2:
                    greenIncreaseCnt = 0
                    # 老人与海
                    if self.circularSearchOperation(imagePath=os.path.join("fishing", "baitMark.png"),
                                                    allTimes=10, interval=0.2,
                                                    hitKey='space') is False:
                        self.ui.log_printf("WARNING", u"提杆CD中")
            else:
                greenIncreaseCnt = 0
            lastGreenPixels = greenPixels
            # 检查钓鱼是否结束
            if self.findImage(os.path.join("fishing", "inFishingMark.png"), logging=False) is None:
                fishingCloseCnt += 1
                if fishingCloseCnt >= 3:
                    self.ui.log_printf("INFO", u"本轮钓鱼结束")
                    break
            else:
                fishingCloseCnt = 0
            self.appBlockWait(0.08)
