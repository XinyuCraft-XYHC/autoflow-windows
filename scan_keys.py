import sys, re
sys.stdout.reconfigure(encoding='utf-8')
content = open('src/i18n.py', encoding='utf-8').read()
all_keys = re.findall(r'"([\w.]+)"\s*:', content)
prefixes = ('settings.', 'update.', 'market.', 'constraint.', 'trigger.')
filtered = [k for k in all_keys if any(k.startswith(p) for p in prefixes)]
for k in sorted(set(filtered)):
    print(k)
