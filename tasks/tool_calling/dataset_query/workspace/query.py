import json
qs = [l.strip() for l in open('input.txt') if l.strip()]
data = json.load(open('data.json'))
for q in qs:
    print(data.get(q, 'UNKNOWN'))
