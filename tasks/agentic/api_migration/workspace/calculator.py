class Calculator:
    def add(self, x, y):
        return _Result(x + y)
class _Result:
    def __init__(self, value):
        self.value = value
