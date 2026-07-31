import sys; sys.path.insert(0, '.')
from app import run
r = run()
assert r.value == 5, r
print('PASS')
