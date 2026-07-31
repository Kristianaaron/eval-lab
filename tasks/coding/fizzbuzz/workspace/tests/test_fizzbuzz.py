from solution import fizzbuzz

def test_fizzbuzz():
    assert fizzbuzz(15) == [1, 2, 'Fizz', 4, 'Buzz', 'Fizz', 7, 8, 'Fizz', 'Buzz', 11, 'Fizz', 13, 14, 'FizzBuzz']
    assert fizzbuzz(1) == [1]
    print('PASS')

if __name__ == '__main__':
    test_fizzbuzz()
