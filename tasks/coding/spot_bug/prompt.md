The following function intends to return the sum of even numbers in a list but has a bug.
```python
def sum_even(nums):
    total = 0
    for n in nums:
        if n % 2 == 0:
            total += n
        return total
```
Return a JSON object {"line": N} where N is the 1-based line number of the statement that causes the bug, and nothing else.
