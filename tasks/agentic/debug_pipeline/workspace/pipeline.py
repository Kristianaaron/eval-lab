data = [{'name': 'a', 'val': 1}, {'name': 'b', 'val': None}, {'name': 'c', 'val': 3}]
total = 0
for row in data:
    total += row['val']
print(total)
print('DONE')
