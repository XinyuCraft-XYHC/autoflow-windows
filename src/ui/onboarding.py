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

from ..i18n import tr

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


def _get_tutorial_steps():
    """动态返回新手引导步骤（每次调用时从 tr() 获取当前语言内容）"""
    return [
        {
            "icon": tr("tutorial.step0.icon"),
            "title": tr("tutorial.step0.title"),
            "body": tr("tutorial.step0.body"),
        },
        {
            "icon": tr("tutorial.step1.icon"),
            "title": tr("tutorial.step1.title"),
            "body": tr("tutorial.step1.body"),
        },
        {
            "icon": tr("tutorial.step2.icon"),
            "title": tr("tutorial.step2.title"),
            "body": tr("tutorial.step2.body"),
        },
        {
            "icon": tr("tutorial.step3.icon"),
            "title": tr("tutorial.step3.title"),
            "body": tr("tutorial.step3.body"),
        },
        {
            "icon": tr("tutorial.step4.icon"),
            "title": tr("tutorial.step4.title"),
            "body": tr("tutorial.step4.body"),
        },
        {
            "icon": tr("tutorial.step5.icon"),
            "title": tr("tutorial.step5.title"),
            "body": tr("tutorial.step5.body"),
        },
    ]


# ─────────────────── 免责声明对话框 ───────────────────

class DisclaimerDialog(QDialog):
    """首次使用免责声明弹窗，需要用户勾选并点击同意才能使用"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("disclaimer.window_title"))
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
        title = QLabel(tr("disclaimer.heading"))
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #89B4FA;")
        root.addWidget(title)

        # 副标题
        sub = QLabel(tr("disclaimer.subtitle"))
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
        text_label = QLabel(tr("disclaimer.text"))
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            "font-size: 12px; line-height: 1.6; padding: 8px 4px;"
            "color: #BAC2DE;"
        )
        text_label.setTextFormat(Qt.TextFormat.PlainText)
        scroll.setWidget(text_label)
        root.addWidget(scroll)

        # 勾选框
        self._agree_cb = QCheckBox(tr("disclaimer.agree_cb"))
        self._agree_cb.setStyleSheet("font-size: 12px; color: #CDD6F4;")
        self._agree_cb.stateChanged.connect(self._on_check_changed)
        root.addWidget(self._agree_cb)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._decline_btn = QPushButton(tr("disclaimer.decline_btn"))
        self._decline_btn.setObjectName("btn_danger")
        self._decline_btn.setFixedHeight(36)
        self._decline_btn.clicked.connect(self._on_decline)
        btn_row.addWidget(self._decline_btn)

        self._accept_btn = QPushButton(tr("disclaimer.accept_btn"))
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

class TutorialDialog(QDialog):
    """新手引导对话框，多步骤卡片式呈现"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("tutorial.window_title"))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumSize(560, 420)
        self.resize(600, 460)
        self._step = 0
        self._total = 6  # _TUTORIAL_STEPS 步骤固定为 6
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

        self._skip_btn = QPushButton(tr("tutorial.skip_btn"))
        self._skip_btn.setObjectName("btn_flat")
        self._skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(self._skip_btn)
        btn_row.addStretch()

        self._prev_btn = QPushButton(tr("tutorial.prev_btn"))
        self._prev_btn.setObjectName("btn_flat")
        self._prev_btn.setFixedWidth(100)
        self._prev_btn.clicked.connect(self._prev)
        btn_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton(tr("tutorial.next_btn"))
        self._next_btn.setObjectName("btn_primary")
        self._next_btn.setFixedWidth(120)
        self._next_btn.clicked.connect(self._next)
        btn_row.addWidget(self._next_btn)

        root.addLayout(btn_row)

    def _update_step(self):
        steps = _get_tutorial_steps()
        step = steps[self._step]
        self._icon_lbl.setText(step["icon"])
        self._title_lbl.setText(step["title"])
        self._body_lbl.setText(step["body"])
        self._step_lbl.setText(tr("tutorial.step_label").format(step=self._step + 1, total=self._total))

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
        self._next_btn.setText(tr("tutorial.finish_btn") if is_last else tr("tutorial.next_btn"))

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
