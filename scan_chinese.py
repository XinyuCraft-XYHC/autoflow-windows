import re
import sys

def find_code_chinese(filepath):
    with open(filepath, encoding='utf-8') as f:
        lines = f.readlines()
    results = []
    in_docstring = False
    docstring_char = None
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 追踪多行字符串（文档注释）
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                char = stripped[:3]
                # 如果同一行结束了
                rest = stripped[3:]
                if char in rest:
                    pass  # 单行文档字符串
                else:
                    in_docstring = True
                    docstring_char = char
                    continue
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue
        
        # 跳过纯注释行
        if stripped.startswith('#'):
            continue
        # 移除行尾注释
        code_part = re.sub(r'(?<!\\)#[^"\']*$', '', line)
        # 检查是否含中文
        if re.search(r'[\u4e00-\u9fff]', code_part):
            results.append((i, line.rstrip()))
    return results

files = [
    ('settings_page.py', 'src/ui/settings_page.py'),
    ('block_editor.py', 'src/ui/block_editor.py'),
    ('trigger_editor.py', 'src/ui/trigger_editor.py'),
    ('constraint_editor.py', 'src/ui/constraint_editor.py'),
    ('update_dialog.py', 'src/ui/update_dialog.py'),
    ('theme_market.py', 'src/ui/theme_market.py'),
    ('language_market.py', 'src/ui/language_market.py'),
    ('plugin_market.py', 'src/ui/plugin_market.py'),
    ('main_window.py', 'src/ui/main_window.py'),
    ('onboarding.py', 'src/ui/onboarding.py'),
]

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

for name, path in files:
    results = find_code_chinese(path)
    print(f'--- {name}: {len(results)} lines ---')
    for lineno, content in results[:50]:
        safe = content.encode('utf-8', errors='replace').decode('utf-8')
        print(f'  {lineno}: {safe[:150]}')
    if len(results) > 50:
        print(f'  ... and {len(results)-50} more')
    print()
