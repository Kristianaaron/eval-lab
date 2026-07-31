from order import subtotal
from tax import tax
def total_with_tax(items, rate):
    sub = subtotal(items)
    return sub + tax(sub, rate)
