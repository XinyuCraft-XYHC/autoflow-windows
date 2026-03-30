# AutoFlow 打包脚本 (PyInstaller + Inno Setup)
# 运行：python build.py
# 产物：
#   dist/AutoFlow_v{VERSION}/          -- onedir 文件夹（可直接运行）
#   dist/AutoFlow_v{VERSION}_Setup.exe -- Inno Setup 安装包

import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── 从 version.py 动态读取版本号，避免手动维护两处 ──
_ver_ns: dict = {}
with open(os.path.join(ROOT, "src", "version.py"), encoding="utf-8") as _f:
    exec(_f.read(), _ver_ns)
VERSION     = _ver_ns["VERSION"]
DIR_NAME    = f"AutoFlow_v{VERSION}"
SETUP_NAME  = f"AutoFlow_v{VERSION}_Setup.exe"
ISCC_PATH   = r"C:\InnoSetup6\ISCC.exe"

# ── Step 1：PyInstaller onedir 打包 ──
print(f"[1/2] 开始打包 AutoFlow v{VERSION}（onedir 模式）...")
cmd_pyinstaller = [
    sys.executable, "-m", "PyInstaller",
    "--clean",
    "--noconfirm",
    "AutoFlow.spec"
]

result = subprocess.run(cmd_pyinstaller, cwd=ROOT)
if result.returncode != 0:
    print("\n[ERR] PyInstaller 打包失败，请检查依赖是否安装完整")
    sys.exit(1)

dir_path = os.path.join(ROOT, "dist", DIR_NAME)
exe_path = os.path.join(dir_path, f"AutoFlow_v{VERSION}.exe")
if not os.path.exists(exe_path):
    print(f"\n[ERR] 找不到打包产物: {exe_path}")
    sys.exit(1)

dir_size = sum(
    os.path.getsize(os.path.join(dp, f))
    for dp, _, files in os.walk(dir_path)
    for f in files
) / 1024 / 1024
print(f"\n[OK] onedir 打包成功！目录: dist/{DIR_NAME}/  ({dir_size:.0f} MB 展开)")

# ── Step 2：Inno Setup 生成安装包 ──
if not os.path.exists(ISCC_PATH):
    print(f"\n[WARN] 未找到 Inno Setup: {ISCC_PATH}")
    print("       如需生成安装包，请安装 Inno Setup 6 到 C:\\InnoSetup6\\")
    print("       仅输出 onedir 文件夹，跳过安装包生成。")
    sys.exit(0)

print(f"\n[2/2] 正在用 Inno Setup 生成安装包 {SETUP_NAME}...")
cmd_iscc = [
    ISCC_PATH,
    f"/DAPP_VERSION={VERSION}",   # 传版本号给 .iss 脚本
    "installer.iss"
]

result2 = subprocess.run(cmd_iscc, cwd=ROOT)
if result2.returncode != 0:
    print("\n[ERR] Inno Setup 编译失败")
    sys.exit(1)

setup_path = os.path.join(ROOT, "dist", SETUP_NAME)
if os.path.exists(setup_path):
    setup_size = os.path.getsize(setup_path) / 1024 / 1024
    print(f"\n[OK] 安装包生成成功！")
    print(f"     dist/{DIR_NAME}/           ({dir_size:.0f} MB 展开，直接运行)")
    print(f"     dist/{SETUP_NAME}  ({setup_size:.1f} MB，分发用安装包)")
else:
    print(f"\n[WARN] 安装包文件未找到: {setup_path}")
