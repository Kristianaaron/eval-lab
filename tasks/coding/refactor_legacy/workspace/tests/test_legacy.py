from legacy import apply_discount

def t():
    assert abs(apply_discount(100, 0.1) - 90.0) < 1e-9
    try:
        apply_discount(100, 1.5)
        raise AssertionError('expected ValueError')
    except ValueError:
        pass
    try:
        apply_discount(100, -0.2)
        raise AssertionError('expected ValueError')
    except ValueError:
        pass
    print('PASS')

if __name__ == '__main__':
    t()
