from solution import binary_search

def t():
    assert binary_search([1,3,5,7,9], 5) == 2
    assert binary_search([1,3,5,7,9], 9) == 4
    assert binary_search([1,3,5,7,9], 4) == -1
    assert binary_search([], 1) == -1
    print('PASS')

if __name__ == '__main__':
    t()
