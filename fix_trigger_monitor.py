"""修复 trigger_monitor.py 中被损坏的 _fire 调用"""
import re

with open('src/engine/trigger_monitor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken f-strings inside _fire calls
# Pattern 1: list(new, trig) -> list(new)
content = content.replace('list(new, trig)', 'list(new)')
# Pattern 2: list(removed, trig) -> list(removed)
content = content.replace('list(removed, trig)', 'list(removed)')
# Pattern 3: now.strftime('%H:%M', trig) -> now.strftime('%H:%M')
content = content.replace("now.strftime('%H:%M', trig)", "now.strftime('%H:%M')")

# Fix all broken _fire calls (missing closing parenthesis)
lines = content.split('\n')
result = []
for line in lines:
    stripped = line.rstrip()
    if 'self._fire(task_id,' in stripped:
        # Count unmatched open parens
        open_count = stripped.count('(')
        close_count = stripped.count(')')
        if open_count > close_count:
            stripped += ')' * (open_count - close_count)
        line = stripped
    result.append(line)

new_content = '\n'.join(result)
with open('src/engine/trigger_monitor.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Fixed trigger_monitor.py')
