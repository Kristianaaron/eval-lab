html = open('index.html').read()
assert 'aria-label="Search"' in html, 'missing aria-label'
assert '#333333' in html or 'color:#333' in html, 'contrast not fixed'
print('PASS')
