"""
AutoFlow UI 特效模块
提供：淡入淡出、滑动、弹出、脉冲、侧边栏展开等动画效果
"""
import sys
from typing import Optional, Callable

from PyQt6.QtCore import (
    QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
    QSequentialAnimationGroup, QTimer, Qt, pyqtProperty, QRect, QSize,
    QPoint, QAbstractAnimation
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect, QStackedWidget, QLabel, QPushButton


# ─────────────────── 淡入淡出动画 ───────────────────

def fade_in(widget: QWidget, duration: int = 200,
            on_finished=None) -> QPropertyAnimation:
    """让 widget 从透明淡入到不透明"""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start()
    return anim


def fade_out(widget: QWidget, duration: int = 150,
             on_finished=None) -> QPropertyAnimation:
    """让 widget 淡出到透明（完成后隐藏）"""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(effect.opacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)

    def _hide():
        widget.hide()
        if on_finished:
            on_finished()

    anim.finished.connect(_hide)
    anim.start()
    return anim


class FadeStackedWidget(QStackedWidget):
    """
    带淡入淡出动画的 QStackedWidget。
    切换页面时，旧页面淡出，新页面淡入。
    """

    def __init__(self, parent=None, duration: int = 180):
        super().__init__(parent)
        self._duration  = duration
        self._animating = False
        self._pending   = None    # (new_widget,)

    def setCurrentWidget(self, widget: QWidget):
        if widget is self.currentWidget():
            return
        if self._animating:
            # 排队等待
            self._pending = widget
            return

        old = self.currentWidget()
        if old is None:
            super().setCurrentWidget(widget)
            fade_in(widget, self._duration)
            return

        self._animating = True
        new = widget

        # 先淡出旧页面
        def _switch():
            super(FadeStackedWidget, self).setCurrentWidget(new)
            new.show()

            def _done():
                self._animating = False
                if self._pending and self._pending is not self.currentWidget():
                    pending = self._pending
                    self._pending = None
                    self.setCurrentWidget(pending)

            fade_in(new, self._duration, on_finished=_done)

        fade_out(old, self._duration, on_finished=_switch)

    def setCurrentIndex(self, index: int):
        w = self.widget(index)
        if w:
            self.setCurrentWidget(w)


# ─────────────────── 按钮波纹/缩放动画辅助 ───────────────────

def animate_button_press(button: QWidget, scale_down: float = 0.95,
                          duration: int = 80):
    """模拟按钮点击反馈（透明度变化）"""
    effect = button.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(button)
        button.setGraphicsEffect(effect)

    anim_down = QPropertyAnimation(effect, b"opacity", button)
    anim_down.setDuration(duration)
    anim_down.setStartValue(1.0)
    anim_down.setEndValue(0.7)
    anim_down.setEasingCurve(QEasingCurve.Type.OutCubic)

    anim_up = QPropertyAnimation(effect, b"opacity", button)
    anim_up.setDuration(duration)
    anim_up.setStartValue(0.7)
    anim_up.setEndValue(1.0)
    anim_up.setEasingCurve(QEasingCurve.Type.InCubic)

    seq = QSequentialAnimationGroup(button)
    seq.addAnimation(anim_down)
    seq.addAnimation(anim_up)
    seq.start()
    return seq


# ─────────────────── 滑入动画 ───────────────────

def slide_in_from_right(widget: QWidget, duration: int = 250):
    """从右侧滑入（结合透明度）"""
    parent = widget.parentWidget()
    if parent is None:
        fade_in(widget, duration)
        return

    original_geo = widget.geometry()
    start_x = original_geo.x() + 60
    start_geo = QRect(start_x, original_geo.y(),
                      original_geo.width(), original_geo.height())

    widget.setGeometry(start_geo)
    widget.show()

    # 几何动画
    anim_geo = QPropertyAnimation(widget, b"geometry", widget)
    anim_geo.setDuration(duration)
    anim_geo.setStartValue(start_geo)
    anim_geo.setEndValue(original_geo)
    anim_geo.setEasingCurve(QEasingCurve.Type.OutCubic)

    # 同时淡入
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    anim_fade = QPropertyAnimation(effect, b"opacity", widget)
    anim_fade.setDuration(duration)
    anim_fade.setStartValue(0.0)
    anim_fade.setEndValue(1.0)
    anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    grp = QParallelAnimationGroup(widget)
    grp.addAnimation(anim_geo)
    grp.addAnimation(anim_fade)
    grp.start()
    return grp


def slide_in_from_bottom(widget: QWidget, offset: int = 30, duration: int = 280):
    """从下方滑入（结合透明度淡入）"""
    parent = widget.parentWidget()
    if parent is None:
        fade_in(widget, duration)
        return

    original_geo = widget.geometry()
    start_geo = QRect(original_geo.x(), original_geo.y() + offset,
                      original_geo.width(), original_geo.height())

    widget.setGeometry(start_geo)
    widget.show()

    anim_geo = QPropertyAnimation(widget, b"geometry", widget)
    anim_geo.setDuration(duration)
    anim_geo.setStartValue(start_geo)
    anim_geo.setEndValue(original_geo)
    anim_geo.setEasingCurve(QEasingCurve.Type.OutBack)

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)
    anim_fade = QPropertyAnimation(effect, b"opacity", widget)
    anim_fade.setDuration(duration)
    anim_fade.setStartValue(0.0)
    anim_fade.setEndValue(1.0)
    anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    grp = QParallelAnimationGroup(widget)
    grp.addAnimation(anim_geo)
    grp.addAnimation(anim_fade)
    grp.start()
    return grp


# ─────────────────── 对话框弹出动画 ───────────────────

def animate_dialog_show(dialog: QWidget, duration: int = 200):
    """对话框弹出时的放大+淡入动画"""
    effect = QGraphicsOpacityEffect(dialog)
    dialog.setGraphicsEffect(effect)
    effect.setOpacity(0.0)

    anim_fade = QPropertyAnimation(effect, b"opacity", dialog)
    anim_fade.setDuration(duration)
    anim_fade.setStartValue(0.0)
    anim_fade.setEndValue(1.0)
    anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim_fade.start()
    return anim_fade


# ─────────────────── 状态栏 Toast 通知 ───────────────────

class StatusToast(QLabel):
    """
    漂浮在主窗口右下角的短暂 Toast 提示。
    show_toast(parent, message) 即可使用。
    """

    def __init__(self, parent: QWidget, message: str,
                 duration_ms: int = 2500, color: str = "#89B4FA"):
        super().__init__(message, parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color}22;
                color: {color};
                border: 1px solid {color}55;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        self.adjustSize()
        self._place(parent)
        self._duration = duration_ms
        self._anim_in  = None
        self._anim_out = None

    def _place(self, parent: QWidget):
        pr = parent.rect()
        geo = self.geometry()
        x = parent.mapToGlobal(QPoint(pr.right() - geo.width() - 20,
                                      pr.bottom() - geo.height() - 40))
        self.move(x)

    def show_animated(self):
        self.show()
        self._anim_in = fade_in(self, 200)
        QTimer.singleShot(self._duration, self._start_fadeout)

    def _start_fadeout(self):
        self._anim_out = fade_out(self, 300, on_finished=self.deleteLater)


def show_toast(parent: QWidget, message: str,
               duration_ms: int = 2500, color: str = "#89B4FA"):
    """在 parent 右下角显示 Toast 提示"""
    toast = StatusToast(parent, message, duration_ms, color)
    toast.show_animated()
    return toast


# ─────────────────── 脉冲高亮动画（强调某个控件）───────────────────

def pulse_highlight(widget: QWidget, color: str = "#89B4FA",
                    cycles: int = 2, duration: int = 300):
    """脉冲高亮动画：让控件透明度快速闪烁几次，用于引导用户注意"""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    seq = QSequentialAnimationGroup(widget)
    for _ in range(cycles):
        a1 = QPropertyAnimation(effect, b"opacity")
        a1.setDuration(duration // 2)
        a1.setStartValue(1.0)
        a1.setEndValue(0.4)
        a1.setEasingCurve(QEasingCurve.Type.InOutSine)

        a2 = QPropertyAnimation(effect, b"opacity")
        a2.setDuration(duration // 2)
        a2.setStartValue(0.4)
        a2.setEndValue(1.0)
        a2.setEasingCurve(QEasingCurve.Type.InOutSine)

        seq.addAnimation(a1)
        seq.addAnimation(a2)

    seq.start()
    return seq


# ─────────────────── 侧边栏按钮高亮动画 ───────────────────

def animate_sidebar_btn_click(btn: QPushButton, accent: str = "#89B4FA",
                               duration: int = 120):
    """侧边栏按钮点击时的淡入淡出反馈"""
    animate_button_press(btn, duration=duration)
