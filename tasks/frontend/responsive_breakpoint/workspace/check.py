import re
css = open('style.css').read()
assert '@media' in css, 'no media query'
assert 'max-width: 480px' in css, 'missing breakpoint'
assert 'grid-template-columns' in css, 'missing column rule'
print('PASS')
