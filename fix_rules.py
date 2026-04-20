import sys
filepath = r'e:\shanghaitech\ai_hospital\jwb\bme1325_formal_jwb_wym-main_final\backend\app\agents\internal_medicine\rules.py'
with open(filepath, 'rb') as f:
    content = f.read()

bad_seq = b'for term in ["chest", "heart", "cardiac", "\xe5\xbf\x83", "\xe8\x83\xb8"])):'
good_seq = b'for term in ["chest", "heart", "cardiac", "\xe5\xbf\x83", "\xe8\x83\xb8"]):'
if bad_seq in content:
    content = content.replace(bad_seq, good_seq, 1)
    with open(filepath, 'wb') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Pattern not found, checking raw content around line 312...')
    lines = content.split(b'\n')
    print(repr(lines[311]))
