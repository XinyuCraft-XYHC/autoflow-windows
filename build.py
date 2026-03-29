# AutoFlow 打包脚本 (PyInstaller)
# 运行：python build.py

import subprocess
import sys
import os

ROOT = os.path.dirname(__file__)

# 从 version.py 动态读取版本号，避免手动维护两处
_ver_ns: dict = {}
with open(os.path.join(ROOT, "src", "version.py"), encoding="utf-8") as _f:
    exec(_f.read(), _ver_ns)
VERSION = _ver_ns["VERSION"]
EXE     = f"AutoFlow_v{VERSION}.exe"

# 使用 spec 文件打包（比命令行方式更可靠，支持 collect_submodules）
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--clean",      # 清除缓存，保证干净构建
    "--noconfirm",  # 不询问覆盖
    "AutoFlow.spec"
]

print(f"开始打包 AutoFlow v{VERSION} (使用 spec 文件)...")
result = subprocess.run(cmd, cwd=ROOT)
if result.returncode == 0:
    print(f"\n[OK] 打包成功！输出: dist/{EXE}")
else:
    print("\n[ERR] 打包失败，请检查依赖是否安装完整")
    sys.exit(1)
