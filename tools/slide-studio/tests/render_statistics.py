"""Generate an isolated visual review without changing the user's project."""
from test_app import app, sample
from pathlib import Path
slides=[]
for kind,content,names in [
    ('descriptive','12\n14\n15\n15\n16\n17\n18\n20\n22\n45',''),
    ('histogram','12\n14\n15\n15\n16\n17\n18\n20\n22\n45',''),
    ('boxplot','A | 12\nA | 14\nA | 15\nA | 16\nA | 18\nA | 45\nB | 8\nB | 10\nB | 11\nB | 13\nB | 15\nB | 17',''),
    ('pareto','Delivery | 45\nQuality | 25\nBilling | 15\nSupport | 10\nOther | 5',''),
    ('correlation','1 | 2\n2 | 4\n3 | 5\n4 | 4\n5 | 5\n6 | 7',''),
    ('matrix','1 | 8 | 10\n2 | 6 | 20\n3 | 7 | 30\n4 | 3 | 40\n5 | 2 | 50\n6 | 1 | 60','Volume | Wait time | Revenue')]:
    s=sample()['slides'][4]
    s.update(chartType=kind,content=content,seriesNames=names,title=kind.title(),subtitle='Illustrative data')
    slides.append(s)
deck={'theme':'ocean','slides':slides}
with app.test_client() as client:
    response=client.post('/api/preview',json=deck)
    assert response.status_code==200,response.data
    Path('static/statistics-review.html').write_text('<!doctype html><title>Statistics review</title><style>body{background:#dde2ec;margin:20px}svg{display:block;width:900px;margin:20px auto}</style>'+''.join(response.json['slides']),encoding='utf-8')
