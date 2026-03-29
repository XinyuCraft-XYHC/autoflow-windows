"""给 trigger_monitor.py 中 _check_xxx 方法里的 _fire 调用加上 trig 参数"""

with open('src/engine/trigger_monitor.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Methods that have trig parameter - lines 355-800 (approx)
# Track state
in_trig_method = False
result = []

for line in lines:
    stripped = line.rstrip()
    
    # Detect method boundaries
    if stripped.startswith('    def '):
        # Check if this method signature contains "trig:" 
        in_trig_method = 'trig:' in stripped or ('trig,' in stripped)
    
    # Add trig to _fire calls in methods that have trig
    if (in_trig_method 
            and 'self._fire(task_id,' in stripped 
            and not stripped.endswith(', trig)')
            and stripped.endswith(')')):
        # Replace closing paren with ', trig)'
        stripped = stripped[:-1] + ', trig)'
        line = stripped + '\n'
    
    result.append(line)

with open('src/engine/trigger_monitor.py', 'w', encoding='utf-8') as f:
    f.writelines(result)

print('Done - added trig to _fire calls')
