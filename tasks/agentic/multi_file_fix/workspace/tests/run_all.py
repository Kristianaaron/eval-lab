import sys; sys.path.insert(0, 'src')
from order import subtotal
from tax import tax
from main import total_with_tax

items = [{'price': 10, 'qty': 2}, {'price': 5, 'qty': 3}]
assert subtotal(items) == 35, subtotal(items)
assert tax(100, 0.2) == 20.0, tax(100, 0.2)
assert abs(total_with_tax(items, 0.1) - 38.5) < 1e-9, total_with_tax(items, 0.1)
print('PASS')
