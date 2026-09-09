import re
from html import unescape

html = open('data/diagnostico/dom_detalhe_LR164029.html', encoding='utf-8').read()

# procura palavras-chave de aplicações/veículos com contexto
palavras = ['Aplica', 'Ve','culo', 'Modelo', 'Montagem', 'LAN', 'motor',
            'quilo', 'kW', 'Pot', 'kcal', 'cilindr', 'Periganza', 'ano']
pats = ['Aplica', r'Ve.g?culo', 'Modelo do ve', 'ano de fabrica', 'Pot']
for p in pats:
    for m in re.finditer(p, html):
        s = max(0, m.start()-200); e = min(len(html), m.end()+200)
        t = re.sub(r'<[^>]+>', ' | ', html[s:e]); t = ' '.join(unescape(t).split())
        print(f'[{p}] ...{t[:260]}...')
        print()