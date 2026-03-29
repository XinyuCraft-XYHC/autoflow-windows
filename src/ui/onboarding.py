"""
首次启动流程：免责声明 + 新手引导
"""
import json
import os
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QLinearGradient
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QCheckBox, QStackedWidget,
    QApplication, QGraphicsOpacityEffect
)

# 标记文件路径（记录用户是否已同意免责声明）
_LOCAL = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
_FLAG_FILE = os.path.join(_LOCAL, "XinyuCraft", "AutoFlow", "onboarding_done.json")


def _load_flags() -> dict:
    try:
        if os.path.exists(_FLAG_FILE):
            with open(_FLAG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_flags(flags: dict):
    try:
        os.makedirs(os.path.dirname(_FLAG_FILE), exist_ok=True)
        with open(_FLAG_FILE, "w", encoding="utf-8") as f:
            json.dump(flags, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def should_show_disclaimer() -> bool:
    return not _load_flags().get("disclaimer_accepted", False)


def should_show_tutorial() -> bool:
    return not _load_flags().get("tutorial_done", False)


def mark_disclaimer_accepted():
    flags = _load_flags()
    flags["disclaimer_accepted"] = True
    _save_flags(flags)


def mark_tutorial_done():
    flags = _load_flags()
    flags["tutorial_done"] = True
    _save_flags(flags)


# ─────────────────── 免责声明对话框 ───────────────────

class DisclaimerDialog(QDialog):
    """首次使用免责声明弹窗，需要用户勾选并点击同意才能使用"""

    DISCLAIMER_TEXT = """
AutoFlow 免责声明

请在使用本软件之前，仔细阅读以下免责声明。

一、软件性质
AutoFlow（以下简称"本软件"）是一款 Windows 平台的自动化工具，用于帮助用户通过可视化方式构建自动化任务流程。本软件由广州新遇绘创美术工艺有限公司提供。

二、使用风险
1. 本软件具备模拟鼠标点击、键盘操作、执行系统命令、操作文件等高权限功能，使用不当可能导致数据丢失、系统状态变更或其他不可预料的后果。
2. 用户在配置自动化任务时，应充分了解每个功能块的作用，并在安全环境中测试验证。
3. 对于因用户误操作、错误配置或意外情况导致的数据损失、系统问题，本公司不承担责任。

三、合法使用
1. 本软件仅供合法用途，用户不得将本软件用于任何违反法律法规、侵犯他人权益或损害社会公共利益的行为。
2. 任何利用本软件进行恶意操作、非法入侵、欺诈等违法行为，责任由用户自行承担。
3. 禁止在未经授权的计算机或网络上使用本软件的自动化功能。

四、数据安全
1. 本软件运行的所有操作均在本地执行，不会自动上传用户数据到云端。
2. 用户应妥善保管项目文件，建议定期备份重要数据。

五、免责范围
在适用法律允许的最大范围内，本公司对于因使用或无法使用本软件而导致的任何直接、间接、偶然、特殊或后果性损害（包括但不限于数据丢失、利润损失、业务中断），不承担任何责任。

六、条款更新
本公司保留随时修改本免责声明的权利，修改后的条款将在软件更新时通知用户。继续使用本软件即视为接受新的条款。

如您不同意以上条款，请立即停止使用本软件。
""".strip()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用前请阅读 — 免责声明")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumSize(620, 520)
        self.resize(680, 580)
        self._accepted = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # 标题
        title = QLabel("📋  使用须知 · 免责声明")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #89B4FA;")
        root.addWidget(title)

        # 副标题
        sub = QLabel("请仔细阅读以下内容，滚动至底部后方可同意。")
        sub.setStyleSheet("font-size: 12px; color: #6C7086;")
        root.addWidget(sub)

        # 分割线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        root.addWidget(sep)

        # 正文滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        text_label = QLabel(self.DISCLAIMER_TEXT)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            "font-size: 12px; line-height: 1.6; padding: 8px 4px;"
            "color: #BAC2DE;"
        )
        text_label.setTextFormat(Qt.TextFormat.PlainText)
        scroll.setWidget(text_label)
        root.addWidget(scroll)

        # 勾选框
        self._agree_cb = QCheckBox(
            "我已阅读并理解上述免责声明，同意遵守相关条款，并承担使用本软件的相应责任。"
        )
        self._agree_cb.setStyleSheet("font-size: 12px; color: #CDD6F4;")
        self._agree_cb.stateChanged.connect(self._on_check_changed)
        root.addWidget(self._agree_cb)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._decline_btn = QPushButton("不同意，退出")
        self._decline_btn.setObjectName("btn_danger")
        self._decline_btn.setFixedHeight(36)
        self._decline_btn.clicked.connect(self._on_decline)
        btn_row.addWidget(self._decline_btn)

        self._accept_btn = QPushButton("✓  我已阅读，同意使用")
        self._accept_btn.setObjectName("btn_primary")
        self._accept_btn.setFixedHeight(36)
        self._accept_btn.setEnabled(False)
        self._accept_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._accept_btn)

        root.addLayout(btn_row)

    def _on_check_changed(self, state):
        self._accept_btn.setEnabled(state == Qt.CheckState.Checked.value)

    def _on_accept(self):
        self._accepted = True
        mark_disclaimer_accepted()
        self.accept()

    def _on_decline(self):
        self._accepted = False
        self.reject()

    def was_accepted(self) -> bool:
        return self._accepted

    def closeEvent(self, event):
        # 强制关闭 = 拒绝
        if not self._accepted:
            self.reject()
        super().closeEvent(event)


# ─────────────────── 新手引导 ───────────────────

_TUTORIAL_STEPS = [
    {
        "icon": "🎉",
        "title": "欢迎使用 AutoFlow！",
        "body": (
            "AutoFlow 是一款积木式 Windows 自动化工具。\n\n"
            "你可以通过「触发器」设定任务触发时机，再用「功能块」描述任务要做什么——\n"
            "无需编写代码，像拼积木一样搭建自动化流程。\n\n"
            "接下来，我们用几步简单介绍核心功能。"
        ),
    },
    {
        "icon": "📁",
        "title": "第一步：创建/打开项目",
        "body": (
            "AutoFlow 以「项目」管理你的自动化任务。\n\n"
            "• 点击左侧侧边栏的「新建项目」（Ctrl+N）创建新项目\n"
            "• 点击「打开项目」（Ctrl+O）加载已有的 .afp 文件\n"
            "• 项目会自动保存到 AppData 目录，支持自动保存\n\n"
            "你可以在一个项目中创建多个任务，任务之间可以互相联动。"
        ),
    },
    {
        "icon": "⚡",
        "title": "第二步：添加触发器",
        "body": (
            "「触发器」决定什么情况下执行任务。\n\n"
            "支持多种触发方式：\n"
            "• ⏰ 定时触发（每天 8:00、每隔 30 分钟…）\n"
            "• ⌨ 热键触发（按下指定按键组合）\n"
            "• 📋 剪贴板变化触发\n"
            "• 🖥 程序启动/关闭触发\n"
            "• 📁 文件变化触发\n"
            "• 以及 20 多种其他触发器\n\n"
            "一个任务可以同时拥有多个触发器。"
        ),
    },
    {
        "icon": "📦",
        "title": "第三步：添加功能块",
        "body": (
            "「功能块」是任务实际执行的步骤，像积木一样按顺序拼接。\n\n"
            "常用功能块：\n"
            "• 🖱 鼠标操作（移动、点击、拖动）\n"
            "• ⌨ 键盘操作（输入文字、按下按键）\n"
            "• 📋 剪贴板读写\n"
            "• 🔔 系统通知\n"
            "• 🔄 条件判断和循环控制\n"
            "• 💻 执行命令、启动程序\n"
            "• 🤖 AI 大模型对话（需配置 API Key）\n\n"
            "支持变量替换（用 {{变量名}} 引用变量）和条件约束。"
        ),
    },
    {
        "icon": "▶",
        "title": "第四步：运行与调试",
        "body": (
            "配置好触发器和功能块后，就可以运行了！\n\n"
            "• 点击任务编辑页顶部的「▶ 立即运行」手动测试\n"
            "• 右下角「运行日志」面板实时显示执行情况\n"
            "• 发现问题？用「⏹ 停止」或强制终止快捷键中断任务\n"
            "• 操作失误？按 Ctrl+Z 撤回，或查看「操作历史」\n\n"
            "保存项目后，触发器会在后台自动监控，符合条件时自动执行！"
        ),
    },
    {
        "icon": "✅",
        "title": "准备好了！",
        "body": (
            "你已经了解了 AutoFlow 的核心用法。\n\n"
            "💡 小提示：\n"
            "• 设置 → 按键 可自定义坐标选点和强制终止快捷键\n"
            "• 设置 → AI 可配置大模型 API Key 启用 AI 功能块\n"
            "• 右键任务列表可重命名、复制、分组管理\n"
            "• 官网和文档：https://autoflow.xinyucreative.com\n\n"
            "祝你使用愉快！点击「开始使用」进入主界面。"
        ),
    },
]


class TutorialDialog(QDialog):
    """新手引导对话框，多步骤卡片式呈现"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新手引导")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumSize(560, 420)
        self.resize(600, 460)
        self._step = 0
        self._total = len(_TUTORIAL_STEPS)
        self._build_ui()
        self._update_step()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部渐变色块
        self._header = QWidget()
        self._header.setFixedHeight(90)
        self._header.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #1e3a5f, stop:1 #1a1a2e);"
        )
        h_layout = QHBoxLayout(self._header)
        h_layout.setContentsMargins(28, 12, 28, 12)
        h_layout.setSpacing(12)

        self._icon_lbl = QLabel()
        self._icon_lbl.setStyleSheet("font-size: 36px;")
        self._icon_lbl.setFixedWidth(50)
        h_layout.addWidget(self._icon_lbl)

        v_hdr = QVBoxLayout()
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #89B4FA;")
        v_hdr.addWidget(self._title_lbl)
        self._step_lbl = QLabel()
        self._step_lbl.setStyleSheet("font-size: 11px; color: #6C7086;")
        v_hdr.addWidget(self._step_lbl)
        h_layout.addLayout(v_hdr)
        h_layout.addStretch()
        root.addWidget(self._header)

        # 内容区
        content_wrap = QWidget()
        content_wrap.setStyleSheet("background: transparent;")
        cw_layout = QVBoxLayout(content_wrap)
        cw_layout.setContentsMargins(28, 20, 28, 12)
        self._body_lbl = QLabel()
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setStyleSheet(
            "font-size: 13px; line-height: 1.7; color: #CDD6F4;"
        )
        self._body_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._body_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        cw_layout.addWidget(self._body_lbl)
        cw_layout.addStretch()
        root.addWidget(content_wrap, 1)

        # 步骤进度点
        dots_row = QHBoxLayout()
        dots_row.setContentsMargins(28, 0, 28, 0)
        dots_row.addStretch()
        self._dots = []
        for i in range(self._total):
            dot = QLabel("●")
            dot.setFixedWidth(18)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dots_row.addWidget(dot)
            self._dots.append(dot)
        dots_row.addStretch()
        root.addLayout(dots_row)

        # 按钮行
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244; margin: 0 0;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 16)
        btn_row.setSpacing(8)

        self._skip_btn = QPushButton("跳过引导")
        self._skip_btn.setObjectName("btn_flat")
        self._skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(self._skip_btn)
        btn_row.addStretch()

        self._prev_btn = QPushButton("◀  上一步")
        self._prev_btn.setObjectName("btn_flat")
        self._prev_btn.setFixedWidth(100)
        self._prev_btn.clicked.connect(self._prev)
        btn_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("下一步  ▶")
        self._next_btn.setObjectName("btn_primary")
        self._next_btn.setFixedWidth(120)
        self._next_btn.clicked.connect(self._next)
        btn_row.addWidget(self._next_btn)

        root.addLayout(btn_row)

    def _update_step(self):
        step = _TUTORIAL_STEPS[self._step]
        self._icon_lbl.setText(step["icon"])
        self._title_lbl.setText(step["title"])
        self._body_lbl.setText(step["body"])
        self._step_lbl.setText(f"步骤 {self._step + 1} / {self._total}")

        # 更新进度点颜色
        for i, dot in enumerate(self._dots):
            if i < self._step:
                dot.setStyleSheet("color: #45475A; font-size: 10px;")
            elif i == self._step:
                dot.setStyleSheet("color: #89B4FA; font-size: 12px;")
            else:
                dot.setStyleSheet("color: #313244; font-size: 10px;")

        self._prev_btn.setEnabled(self._step > 0)
        is_last = self._step == self._total - 1
        self._next_btn.setText("🚀 开始使用" if is_last else "下一步  ▶")

    def _prev(self):
        if self._step > 0:
            self._step -= 1
            self._update_step()

    def _next(self):
        if self._step < self._total - 1:
            self._step += 1
            self._update_step()
        else:
            self._finish()

    def _on_skip(self):
        self._finish()

    def _finish(self):
        mark_tutorial_done()
        self.accept()
