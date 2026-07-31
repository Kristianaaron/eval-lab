Below is a Python function. Determine its worst-case time complexity in big-O terms and return a JSON object {"complexity": "O(...)"} containing only the complexity string.
```python
def compute(n):
    s = 0
    for i in range(n):
        for j in range(n):
            s += i * j
    return s
```
