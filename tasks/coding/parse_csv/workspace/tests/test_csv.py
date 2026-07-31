from solution import parse_csv

def t():
    raw = 'name,age\nann,30\nbob,25'
    out = parse_csv(raw)
    assert out == [{'name':'ann','age':'30'},{'name':'bob','age':'25'}], out
    print('PASS')

if __name__ == '__main__':
    t()
