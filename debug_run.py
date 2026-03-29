"""
调试启动脚本 - 捕获所有异常并写入日志文件
"""
import sys
import os
import traceback
import logging

# 设置日志文件
log_file = os.path.join(os.path.dirname(__file__), "crash.log")
logging.basicConfig(
    filename=log_file,
    filemode="w",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
log = logging.getLogger()

# 同时输出到控制台
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG)
log.addHandler(console)

def global_except_hook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.critical(f"UNCAUGHT EXCEPTION:\n{msg}")

sys.excepthook = global_except_hook

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    import PyQt6.QtCore as QtCore

    # 捕获 Qt 消息
    def qt_msg_handler(mode, context, message):
        level_map = {
            QtCore.QtMsgType.QtDebugMsg:    log.debug,
            QtCore.QtMsgType.QtInfoMsg:     log.info,
            QtCore.QtMsgType.QtWarningMsg:  log.warning,
            QtCore.QtMsgType.QtCriticalMsg: log.error,
            QtCore.QtMsgType.QtFatalMsg:    log.critical,
        }
        fn = level_map.get(mode, log.warning)
        fn(f"[Qt] {context.file}:{context.line} - {message}")

    QtCore.qInstallMessageHandler(qt_msg_handler)

    app = QApplication(sys.argv)

    log.info("QApplication created")

    from src.ui.main_window import MainWindow
    log.info("MainWindow imported")

    w = MainWindow()
    log.info("MainWindow created")

    w.show()
    log.info("MainWindow shown, entering event loop")

    ret = app.exec()
    log.info(f"Event loop exited with code {ret}")
    sys.exit(ret)

except Exception as e:
    log.critical(f"STARTUP CRASH:\n{traceback.format_exc()}")
    input("Press Enter to exit...")
