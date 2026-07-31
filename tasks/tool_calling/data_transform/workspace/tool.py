import sys
names = [l.strip() for l in open('names.txt') if l.strip()]
allowed = set(l.strip() for l in open('allowed.txt') if l.strip())
for n in names:
    if n in allowed:
        print(n.upper())
