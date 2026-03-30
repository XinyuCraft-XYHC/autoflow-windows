"""
任务编辑页面
包含：任务信息、触发器列表、功能块列表
"""
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QCheckBox, QSplitter, QFrame,
    QScrollArea, QFormLayout, QSizePolicy, QApplication, QDialog
)

from ..engine.models import Task
from .block_editor import BlockListWidget
from .trigger_editor import TriggerListWidget
from ..i18n import tr, add_language_observer, remove_language_observer


class TaskEditorPage(QWidget):
    """单个任务的完整编辑器"""

    changed     = pyqtSignal()      # 任务内容变化
    run_task    = pyqtSignal(str)   # task_id
    stop_task   = pyqtSignal(str)   # task_id
    run_single  = pyqtSignal(str, object)   # (task_id, Block) 运行单块
    run_from    = pyqtSignal(str, int)      # (task_id, start_idx) 从某块开始运行

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self._running = False
        self._loading = False   # 加载期间屏蔽 changed 信号
        self._build_ui()
        self._load_task()
        # 注册语言变更观察者
        add_language_observer(self._retranslate)

    def __del__(self):
        try:
            remove_language_observer(self._retranslate)
        except Exception:
            pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── 顶部标题栏 ──
        top = QHBoxLayout()
        top.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("task.name_ph"))
        self._name_edit.setStyleSheet("""
            QLineEdit {
                font-size: 18px; font-weight: bold;
                background: transparent; border: none;
                border-bottom: 2px solid #45475A;
                border-radius: 0; padding: 4px 2px;
                color: #CDD6F4;
            }
            QLineEdit:focus { border-bottom-color: #89B4FA; }
        """)
        self._name_edit.textChanged.connect(self._on_name_changed)
        top.addWidget(self._name_edit)
        top.addStretch()

        self._enabled_cb = QCheckBox(tr("task.enabled"))
        self._enabled_cb.setChecked(True)
        self._enabled_cb.stateChanged.connect(self._on_changed)
        top.addWidget(self._enabled_cb)

        self._run_btn = QPushButton(tr("task.run_btn"))
        self._run_btn.setObjectName("btn_success")
        self._run_btn.setFixedHeight(36)
        self._run_btn.clicked.connect(lambda: self.run_task.emit(self.task.id))
        top.addWidget(self._run_btn)

        self._stop_btn = QPushButton(tr("task.stop_btn"))
        self._stop_btn.setObjectName("btn_danger")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(lambda: self.stop_task.emit(self.task.id))
        top.addWidget(self._stop_btn)

        root.addLayout(top)

        # ── 任务 ID 信息栏（灰色小字 + 复制按钮 + 命令行说明按钮）──
        id_bar = QHBoxLayout()
        id_bar.setSpacing(6)
        self._id_prefix_lbl = QLabel("ID：")
        self._id_prefix_lbl.setStyleSheet("font-size: 11px; color: #6C7086;")
        id_bar.addWidget(self._id_prefix_lbl)

        self._id_lbl = QLabel(self.task.id)
        self._id_lbl.setStyleSheet(
            "font-size: 11px; color: #6C7086; font-family: monospace;"
        )
        self._id_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        id_bar.addWidget(self._id_lbl)

        self._copy_id_btn = QPushButton("复制")
        self._copy_id_btn.setFixedSize(44, 20)
        self._copy_id_btn.setStyleSheet(
            "QPushButton { font-size:10px; border-radius:3px; padding:1px 6px; "
            "background:#313244; color:#CDD6F4; border:1px solid #45475A; }"
            "QPushButton:hover { background:#45475A; }"
        )
        self._copy_id_btn.clicked.connect(self._copy_task_id)
        id_bar.addWidget(self._copy_id_btn)

        self._cmd_hint_btn = QPushButton("⌨ 命令行")
        self._cmd_hint_btn.setFixedSize(64, 20)
        self._cmd_hint_btn.setStyleSheet(
            "QPushButton { font-size:10px; border-radius:3px; padding:1px 6px; "
            "background:#1e3a5f; color:#89B4FA; border:1px solid #89B4FA; }"
            "QPushButton:hover { background:#2a4f7a; }"
        )
        self._cmd_hint_btn.clicked.connect(self._show_cmd_hint)
        id_bar.addWidget(self._cmd_hint_btn)

        id_bar.addStretch()
        root.addLayout(id_bar)
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText(tr("task.desc_ph"))
        self._desc_edit.textChanged.connect(self._on_changed)
        root.addWidget(self._desc_edit)

        # ── 主体分割器（触发器 | 功能块） ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet("QSplitter::handle { background: #313244; border-radius: 2px; }")

        # 左：触发器
        left = QWidget()
        left.setMinimumWidth(260)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        self._trigger_editor = TriggerListWidget()
        self._trigger_editor.changed.connect(self._on_changed)
        ll.addWidget(self._trigger_editor)
        splitter.addWidget(left)

        # 右：功能块
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self._block_editor = BlockListWidget()
        self._block_editor.changed.connect(self._on_changed)
        self._block_editor.run_single_block.connect(
            lambda blk: self.run_single.emit(self.task.id, blk)
        )
        self._block_editor.run_from_block.connect(
            lambda idx: self.run_from.emit(self.task.id, idx)
        )
        rl.addWidget(self._block_editor)
        splitter.addWidget(right)

        # 暴露 _block_list 别名供 main_window 使用
        self._block_list = self._block_editor

        # 触发器与功能块选中互斥：任意一方有选中，另一方自动清除
        self._trigger_editor.selection_changed.connect(self._on_trigger_selection_changed)
        self._block_editor.selection_changed.connect(self._on_block_selection_changed)

        splitter.setSizes([300, 600])
        root.addWidget(splitter)

    def _on_trigger_selection_changed(self):
        """触发器侧有选中 → 清除功能块侧选中（互斥）"""
        if self._trigger_editor._selected_ids:
            self._block_editor.clear_selection()

    def _on_block_selection_changed(self):
        """功能块侧有选中 → 清除触发器侧选中（互斥）"""
        if self._block_editor._selected_ids:
            self._trigger_editor.clear_selection()

    def _copy_task_id(self):
        """复制任务 ID 到剪贴板"""
        QApplication.clipboard().setText(self.task.id)
        self._copy_id_btn.setText("✓")
        QTimer.singleShot(1500, lambda: self._copy_id_btn.setText("复制"))

    def _show_cmd_hint(self):
        """弹窗展示命令行调用方式"""
        import sys as _sys, os as _os
        if getattr(_sys, "frozen", False):
            exe = _sys.argv[0]
            exe_disp = _os.path.basename(exe)
            cmd_text = f'"{exe}" --run-task {self.task.id}'
            cmd_display = f'{exe_disp} --run-task {self.task.id}'
        else:
            cmd_text = f'python main.py --run-task {self.task.id}'
            cmd_display = cmd_text

        dlg = QDialog(self)
        dlg.setWindowTitle("命令行调用")
        dlg.setMinimumWidth(460)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 16, 20, 16)

        title = QLabel(f"⌨️  命令行运行任务「{self.task.name}」")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        lay.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #45475A;")
        lay.addWidget(sep)

        for label, text, full in [
            ("任务 ID：", self.task.id, self.task.id),
            ("命令：", cmd_display, cmd_text),
        ]:
            row_lbl = QLabel(label)
            row_lbl.setStyleSheet("font-size: 11px; color: #6C7086;")
            lay.addWidget(row_lbl)
            row = QHBoxLayout()
            edit = QLineEdit(text)
            edit.setReadOnly(True)
            edit.setStyleSheet(
                "QLineEdit { background:#181825; border:1px solid #45475A; "
                "border-radius:4px; padding:4px 8px; font-family:monospace; }"
            )
            row.addWidget(edit)
            _full = full  # 闭包捕获
            _btn  = QPushButton("复制")
            _btn.setFixedWidth(52)
            def _copy(_b=_btn, _t=_full):
                QApplication.clipboard().setText(_t)
                _b.setText("✓")
                QTimer.singleShot(1500, lambda: _b.setText("复制"))
            _btn.clicked.connect(_copy)
            row.addWidget(_btn)
            lay.addLayout(row)

        hint = QLabel(
            "💡 将 AutoFlow 安装目录加入系统 PATH 后，\n"
            "可在任意位置的命令行中直接使用 <code>AutoFlow --run-task &lt;id&gt;</code>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6C7086; font-size: 11px;")
        lay.addWidget(hint)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("btn_primary")
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
        dlg.exec()

    def _retranslate(self):
        """语言切换后刷新所有文字"""
        self._name_edit.setPlaceholderText(tr("task.name_ph"))
        self._desc_edit.setPlaceholderText(tr("task.desc_ph"))
        self._enabled_cb.setText(tr("task.enabled"))
        if not self._running:
            self._run_btn.setText(tr("task.run_btn"))
        self._stop_btn.setText(tr("task.stop_btn"))
        # 传递给子组件
        self._trigger_editor.retranslate()
        self._block_editor.retranslate()

    def save_to_task(self):
        """将UI当前内容写回 task 对象"""
        self.task.name        = self._name_edit.text() or tr("task.unnamed")
        self.task.description = self._desc_edit.text()
        self.task.enabled     = self._enabled_cb.isChecked()
        self.task.triggers    = self._trigger_editor.get_triggers()
        self.task.blocks      = self._block_editor.get_blocks()

    def _on_name_changed(self, text):
        self.task.name = text or tr("task.unnamed")
        if not self._loading:
            self.changed.emit()

    def _on_changed(self):
        if self._loading:
            return
        self.save_to_task()
        self.changed.emit()

    def _load_task(self):
        self._loading = True
        self._name_edit.setText(self.task.name)
        self._desc_edit.setText(self.task.description)
        self._enabled_cb.setChecked(self.task.enabled)
        self._trigger_editor.set_triggers(self.task.triggers)
        self._block_editor.set_blocks(self.task.blocks)
        self._loading = False

    def set_running(self, running: bool):
        self._running = running
        self._run_btn.setVisible(not running)
        self._stop_btn.setVisible(running)

