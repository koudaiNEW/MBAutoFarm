# -*- coding: utf-8 -*-

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt, Signal, QTimer)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QGridLayout, QGroupBox,
    QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QSpacerItem, QTextEdit, QWidget)
import threading
import html
import json
import os
import time


class Ui_MBAutoFarmWidget(object):
    LOG_MAX_LINES = 10000  # 日志最大显示条数，超出时丢弃最早的日志

    # 采集类型 -> 采集目标可选项（顺序与 collectionTypeComboBox 条目一致）
    COLLECTION_TARGETS = [
        [u"巢穴", u"蜘蛛网", u"水", u"水井", u"乳牛", u"苹果树"],
        [u"树木", u"尖叶树", u"粗壮树", u"成材树", u"甲胃树"],
        [u"矿脉", u"铁矿脉", u"冰", u"煤炭矿脉", u"铜矿脉", u"白铜矿脉"],
        [u"药草", u"血红药草", u"箭花", u"魔力药草", u"新芽蘑菇",
         u"壮壮蘑菇", u"毅力草", u"咻咻蘑菇", u"躲躲花", u"净净蘑菇"],
        [u"羊", u"卷毛羊"],
        [u"小麦", u"玉米"],
        [u"马铃薯", u"洋葱", u"贝类"],
        [u"光群", u"雪原光群", u"宁静的光群", u"温暖的光群", u"冰冷的光群"],
        [u"默认"],
    ]

    LOG_COLORS = {
        "DEBUG": "gray",
        "INFO": "white",
        "WARNING": "darkorange",
        "ERROR": "red",
    }

    class _LogEmitter(QObject):
        logMessage = Signal(str)

    def __init__(self, configPath=None):
        self.configPath = configPath
        self._log_emitter = self._LogEmitter()
        self._log_lock = threading.Lock()
        self._log_connected = False
        # 任务列表数据模型，与 taskListWidget 的行一一对应
        # 每项: {"name": str, "type": int, "target": int}
        self._tasks = []
        self._updating_ui = False  # 程序化更新下拉框时抑制配置回写
        self.taskCtl = None  
        
    def setTaskControl(self, taskCtl):
        """设置任务控制对象，用于在 UI 中控制任务。"""
        self.taskCtl = taskCtl
        self.taskCtl.loadConfig()


    def setupUi(self, MBAutoFarmWidget):
        if not MBAutoFarmWidget.objectName():
            MBAutoFarmWidget.setObjectName(u"MBAutoFarmWidget")
        MBAutoFarmWidget.resize(500, 600)
        self.gridLayout = QGridLayout(MBAutoFarmWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.taskLogBox = QGroupBox(MBAutoFarmWidget)
        self.taskLogBox.setObjectName(u"taskLogBox")
        self.gridLayout_5 = QGridLayout(self.taskLogBox)
        self.gridLayout_5.setObjectName(u"gridLayout_5")
        self.taskLogTextEdit = QTextEdit(self.taskLogBox)
        self.taskLogTextEdit.setObjectName(u"taskLogTextEdit")
        self.taskLogTextEdit.setReadOnly(True)

        self.gridLayout_5.addWidget(self.taskLogTextEdit, 0, 0, 1, 1)


        self.gridLayout.addWidget(self.taskLogBox, 2, 1, 1, 1)

        self.taskListBox = QGroupBox(MBAutoFarmWidget)
        self.taskListBox.setObjectName(u"taskListBox")
        self.gridLayout_3 = QGridLayout(self.taskListBox)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.taskListAddButton = QPushButton(self.taskListBox)
        self.taskListAddButton.setObjectName(u"taskListAddButton")

        self.gridLayout_3.addWidget(self.taskListAddButton, 1, 1, 1, 1)

        self.taskListDelButton = QPushButton(self.taskListBox)
        self.taskListDelButton.setObjectName(u"taskListDelButton")

        self.gridLayout_3.addWidget(self.taskListDelButton, 1, 2, 1, 1)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_3.addItem(self.horizontalSpacer_2, 1, 0, 1, 1)

        self.taskListWidget = QListWidget(self.taskListBox)
        self.taskListWidget.setObjectName(u"taskListWidget")

        self.gridLayout_3.addWidget(self.taskListWidget, 0, 0, 1, 3)


        self.gridLayout.addWidget(self.taskListBox, 1, 0, 2, 1)

        self.taskStatusBox = QGroupBox(MBAutoFarmWidget)
        self.taskStatusBox.setObjectName(u"taskStatusBox")
        self.gridLayout_2 = QGridLayout(self.taskStatusBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.taskChooseNameTitleLable = QLabel(self.taskStatusBox)
        self.taskChooseNameTitleLable.setObjectName(u"taskChooseNameTitleLable")
        self.taskChooseNameTitleLable.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayout_2.addWidget(self.taskChooseNameTitleLable, 1, 3, 1, 1)

        self.taskStatusLabel = QLabel(self.taskStatusBox)
        self.taskStatusLabel.setObjectName(u"taskStatusLabel")
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self.taskStatusLabel.setFont(font)

        self.gridLayout_2.addWidget(self.taskStatusLabel, 0, 6, 1, 1)

        self.taskRuntimeLabel = QLabel(self.taskStatusBox)
        self.taskRuntimeLabel.setObjectName(u"taskRuntimeLabel")
        self.taskRuntimeLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gridLayout_2.addWidget(self.taskRuntimeLabel, 2, 6, 1, 1)

        self.taskChooseNameLabel = QLabel(self.taskStatusBox)
        self.taskChooseNameLabel.setObjectName(u"taskChooseNameLabel")
        self.taskChooseNameLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gridLayout_2.addWidget(self.taskChooseNameLabel, 1, 6, 1, 1)

        self.taskStopButton = QPushButton(self.taskStatusBox)
        self.taskStopButton.setObjectName(u"taskStopButton")

        self.gridLayout_2.addWidget(self.taskStopButton, 2, 2, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_2.addItem(self.horizontalSpacer, 0, 3, 1, 1)

        self.taskStartButton = QPushButton(self.taskStatusBox)
        self.taskStartButton.setObjectName(u"taskStartButton")

        self.gridLayout_2.addWidget(self.taskStartButton, 2, 0, 1, 1)

        self.taskRuntimeTitleLabel = QLabel(self.taskStatusBox)
        self.taskRuntimeTitleLabel.setObjectName(u"taskRuntimeTitleLabel")
        self.taskRuntimeTitleLabel.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayout_2.addWidget(self.taskRuntimeTitleLabel, 2, 3, 1, 1)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.gridLayout_2.addItem(self.verticalSpacer, 3, 0, 1, 1)


        self.gridLayout.addWidget(self.taskStatusBox, 0, 0, 1, 2)

        self.taskConfigBox = QGroupBox(MBAutoFarmWidget)
        self.taskConfigBox.setObjectName(u"taskConfigBox")
        self.gridLayout_4 = QGridLayout(self.taskConfigBox)
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.collectionTypeComboBox = QComboBox(self.taskConfigBox)
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.addItem("")
        self.collectionTypeComboBox.setObjectName(u"collectionTypeComboBox")

        self.gridLayout_4.addWidget(self.collectionTypeComboBox, 0, 1, 1, 1)

        self.collectionTargetTitleLabel = QLabel(self.taskConfigBox)
        self.collectionTargetTitleLabel.setObjectName(u"collectionTargetTitleLabel")
        self.collectionTargetTitleLabel.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayout_4.addWidget(self.collectionTargetTitleLabel, 1, 0, 1, 1)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.gridLayout_4.addItem(self.horizontalSpacer_3, 0, 2, 1, 1)

        self.collectionTargetComboBox = QComboBox(self.taskConfigBox)
        self.collectionTargetComboBox.setObjectName(u"collectionTargetComboBox")

        self.gridLayout_4.addWidget(self.collectionTargetComboBox, 1, 1, 1, 1)

        self.collectionTypeTitleLabel = QLabel(self.taskConfigBox)
        self.collectionTypeTitleLabel.setObjectName(u"collectionTypeTitleLabel")
        self.collectionTypeTitleLabel.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.gridLayout_4.addWidget(self.collectionTypeTitleLabel, 0, 0, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.gridLayout_4.addItem(self.verticalSpacer_2, 2, 0, 2, 1)

        self.taskConfigSaveButton = QPushButton(self.taskConfigBox)
        self.taskConfigSaveButton.setObjectName(u"taskConfigSaveButton")

        self.gridLayout_4.addWidget(self.taskConfigSaveButton, 3, 1, 1, 1)


        self.gridLayout.addWidget(self.taskConfigBox, 1, 1, 1, 1)

        self.gridLayout.setRowStretch(0, 2)
        self.gridLayout.setRowStretch(1, 2)
        self.gridLayout.setRowStretch(2, 6)
        self.gridLayout.setColumnStretch(0, 4)
        self.gridLayout.setColumnStretch(1, 6)

        self.retranslateUi(MBAutoFarmWidget)

        QMetaObject.connectSlotsByName(MBAutoFarmWidget)

        self.configSetup()
    # setupUi

    def retranslateUi(self, MBAutoFarmWidget):
        MBAutoFarmWidget.setWindowTitle(QCoreApplication.translate("MBAutoFarmWidget", u"MBAutoFarm", None))
        self.taskLogBox.setTitle(QCoreApplication.translate("MBAutoFarmWidget", u"\u65e5\u5fd7", None))
        self.taskListBox.setTitle(QCoreApplication.translate("MBAutoFarmWidget", u"\u4efb\u52a1\u5217\u8868", None))
        self.taskListAddButton.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u6dfb\u52a0", None))
        self.taskListDelButton.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u5220\u9664", None))
        self.taskStatusBox.setTitle(QCoreApplication.translate("MBAutoFarmWidget", u"\u4efb\u52a1\u72b6\u6001", None))
        self.taskChooseNameTitleLable.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u5f53\u524d\u4efb\u52a1:", None))
        self.taskStatusLabel.setText(QCoreApplication.translate("MBAutoFarmWidget", u"        \u5df2\u505c\u6b62        ", None))
        self.taskRuntimeLabel.setText(QCoreApplication.translate("MBAutoFarmWidget", u"TextLabel", None))
        self.taskChooseNameLabel.setText(QCoreApplication.translate("MBAutoFarmWidget", u"TextLabel", None))
        self.taskStopButton.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u505c\u6b62", None))
        self.taskStartButton.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u5f00\u59cb", None))
        self.taskRuntimeTitleLabel.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u6267\u884c\u65f6\u95f4:", None))
        self.taskConfigBox.setTitle(QCoreApplication.translate("MBAutoFarmWidget", u"\u4efb\u52a1\u914d\u7f6e", None))
        self.collectionTypeComboBox.setItemText(0, QCoreApplication.translate("MBAutoFarmWidget", u"\u65e5\u5e38\u91c7\u96c6", None))
        self.collectionTypeComboBox.setItemText(1, QCoreApplication.translate("MBAutoFarmWidget", u"\u4f10\u6728", None))
        self.collectionTypeComboBox.setItemText(2, QCoreApplication.translate("MBAutoFarmWidget", u"\u91c7\u77ff", None))
        self.collectionTypeComboBox.setItemText(3, QCoreApplication.translate("MBAutoFarmWidget", u"\u91c7\u96c6\u836f\u8349", None))
        self.collectionTypeComboBox.setItemText(4, QCoreApplication.translate("MBAutoFarmWidget", u"\u526a\u7f8a\u6bdb", None))
        self.collectionTypeComboBox.setItemText(5, QCoreApplication.translate("MBAutoFarmWidget", u"\u6536\u5272", None))
        self.collectionTypeComboBox.setItemText(6, QCoreApplication.translate("MBAutoFarmWidget", u"\u9504\u5730", None))
        self.collectionTypeComboBox.setItemText(7, QCoreApplication.translate("MBAutoFarmWidget", u"\u6606\u866b\u91c7\u96c6", None))
        self.collectionTypeComboBox.setItemText(8, QCoreApplication.translate("MBAutoFarmWidget", u"\u9493\u9c7c", None))

        self.collectionTargetTitleLabel.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u91c7\u96c6\u76ee\u6807:", None))
        self.collectionTypeTitleLabel.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u91c7\u96c6\u7c7b\u578b:", None))
        self.taskConfigSaveButton.setText(QCoreApplication.translate("MBAutoFarmWidget", u"\u4fdd\u5b58", None))
    # retranslateUi

    def configSetup(self):
        self.taskStartButton.clicked.connect(self.taskStartButtonClicked)
        self.taskStopButton.clicked.connect(self.taskStopButtonClicked)
        self.taskListAddButton.clicked.connect(self.taskListAddButtonClicked)
        self.taskListDelButton.clicked.connect(self.taskListDelButtonClicked)
        self.taskConfigSaveButton.clicked.connect(self.taskConfigSaveButtonClicked)
        self.collectionTypeComboBox.currentIndexChanged.connect(self.collectionTypeChanged)
        self.collectionTargetComboBox.currentIndexChanged.connect(self.collectionTargetChanged)
        self.taskListWidget.currentRowChanged.connect(self.taskSelected)
        self.taskListWidget.itemChanged.connect(self.taskItemRenamed)
        # 初始化采集目标下拉框，与当前采集类型保持一致
        self.collectionTypeChanged(self.collectionTypeComboBox.currentIndex())
        # 启动时读取配置文件，恢复任务列表
        # self.loadConfig()
        # 任务状态刷新定时器：每秒更新当前任务名称与已执行时间
        self._taskStatusTimer = QTimer(self.taskLogTextEdit)
        self._taskStatusTimer.setInterval(1000)
        self._taskStatusTimer.timeout.connect(self.updateTaskStatus)
        self.updateTaskStatus()

    def updateTaskStatus(self):
        """刷新当前运行任务的名称、已执行时间与运行状态标签。"""
        ctl = self.taskCtl
        if ctl is not None and ctl.taskRuning and ctl.taskStartTime is not None:
            self.taskChooseNameLabel.setText(ctl.taskName or u"")
            elapsed = int(time.time() - ctl.taskStartTime)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.taskRuntimeLabel.setText("%02d:%02d:%02d" % (h, m, s))
            self.taskStatusLabel.setText(u"        运行中        ")
            self.taskStatusLabel.setStyleSheet(
                "background-color: green; color: black;")
        else:
            self.taskChooseNameLabel.setText(u"无")
            self.taskRuntimeLabel.setText("00:00:00")
            self.taskStatusLabel.setText(u"        已停止        ")
            self.taskStatusLabel.setStyleSheet(
                "background-color: blue; color: black;")

    def collectionTypeChanged(self, index):
        """采集类型变化时，更新 collectionTargetComboBox 的可选项。"""
        self.collectionTargetComboBox.clear()
        if 0 <= index < len(self.COLLECTION_TARGETS):
            self.collectionTargetComboBox.addItems(self.COLLECTION_TARGETS[index])
        # 用户手动切换类型时，回写到当前选中任务的配置
        if not self._updating_ui:
            row = self.taskListWidget.currentRow()
            if 0 <= row < len(self._tasks):
                self._tasks[row]["type"] = index

    def collectionTargetChanged(self, index):
        """采集目标变化时，回写到当前选中任务的配置。"""
        if self._updating_ui:
            return
        row = self.taskListWidget.currentRow()
        if 0 <= row < len(self._tasks):
            self._tasks[row]["target"] = index

    def taskSelected(self, row):
        """选中任务列表中的任务时，将其配置加载到采集类型/目标下拉框。"""
        if not (0 <= row < len(self._tasks)):
            return
        task = self._tasks[row]
        self._updating_ui = True
        try:
            self.collectionTypeComboBox.setCurrentIndex(task["type"])
            self.collectionTargetComboBox.setCurrentIndex(task["target"])
        finally:
            self._updating_ui = False

    def taskItemRenamed(self, item):
        """任务项被重命名（双击编辑）后，同步名称到数据模型。"""
        row = self.taskListWidget.row(item)
        if 0 <= row < len(self._tasks):
            self._tasks[row]["name"] = item.text()

    def _addTaskItem(self, name, type_index=0, target_index=0):
        """向数据模型和 taskListWidget 添加一条任务。"""
        self._tasks.append({"name": name, "type": type_index,
                            "target": target_index})
        item = QListWidgetItem(name)
        # 允许双击编辑重命名
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.taskListWidget.addItem(item)

    def log_printf(self, level, fmt, *args):
        """仿 printf 的日志接口，线程安全，可在任意线程调用。

        level: DEBUG / INFO / WARNING / ERROR（不区分大小写），
               显示颜色分别为 灰 / 白 / 深橙 / 红。
        用法: ui.log_printf("INFO", "task %s finished, cost %d ms", name, cost)
        需在 setupUi() 之后调用；未初始化时回退到标准输出。
        """
        level = str(level).upper()
        if level not in self.LOG_COLORS:
            level = "INFO"
        msg = fmt % args if args else str(fmt)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        text_edit = getattr(self, "taskLogTextEdit", None)
        if text_edit is None:
            print("[%s] [%s] %s" % (timestamp, level, msg))
            return
        with self._log_lock:
            if not self._log_connected:
                self._log_emitter.logMessage.connect(text_edit.append)
                self._log_connected = True
        html_msg = '<span style="color:%s;">[%s] [%s] %s</span>' % (
            self.LOG_COLORS[level], timestamp, level, html.escape(msg))
        # 跨线程发射信号时 Qt 自动排队到 GUI 线程执行 append
        self._log_emitter.logMessage.emit(html_msg)


    def taskStartButtonClicked(self):
        self.log_printf("DEBUG", "start button clicked.")
        if self.taskCtl:
            if self.taskCtl.taskRuning:
                self.log_printf("WARNING", "task is already running.")
                return
            row = self.taskListWidget.currentRow()
            if not (0 <= row < len(self._tasks)):
                self.log_printf("WARNING", "please select a task first.")
                return
            self.taskCtl.startTask(self._tasks[row]["name"],
                                   self._tasks[row]["type"],
                                   self._tasks[row]["target"])
            self._taskStatusTimer.start()
            self.updateTaskStatus()
        else:
            self.log_printf("ERROR", "task control is not ready.")

    def taskStopButtonClicked(self):
        self.log_printf("DEBUG", "stop button clicked.")
        if self.taskCtl:
            self.taskCtl.stopTask()
            self._taskStatusTimer.stop()
            self.updateTaskStatus()
        else:
            self.log_printf("ERROR", "task control is not ready.")
    
    def taskListAddButtonClicked(self):
        """添加一条新任务，默认名称为 new task，并选中该任务。"""
        self._addTaskItem(u"new task")
        self.taskListWidget.setCurrentRow(len(self._tasks) - 1)
        self.log_printf("INFO", u"已添加任务: new task")

    def taskListDelButtonClicked(self):
        """删除任务列表中选中的任务，并将改动写入 config.json。"""
        row = self.taskListWidget.currentRow()
        if not (0 <= row < len(self._tasks)):
            self.log_printf("WARNING", u"请先在任务列表中选择要删除的任务")
            return
        name = self._tasks[row]["name"]
        self.taskListWidget.takeItem(row)
        del self._tasks[row]
        if self.taskCtl.saveConfig():
            self.log_printf("INFO", u"已删除任务: %s", name)

    def taskConfigSaveButtonClicked(self):
        """将任务列表中的任务配置写入 config.json，并提示保存成功。"""
        if self.taskCtl.saveConfig():
            self.log_printf("INFO", u"保存成功，配置已写入 config.json")
    
    