from flask import Flask, jsonify, request, render_template, send_file
from io import BytesIO
from engine import CATALOG, THEMES, validate, scene, svg, powerpoint
from notebook_import import import_notebook

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024

@app.get('/')
def index():
    return render_template('index.html')

@app.get('/api/config')
def config():
    return jsonify(templates=CATALOG, themes=THEMES)

@app.post('/api/preview')
def preview():
    deck = validate(request.get_json())
    start=deck.get('previewSlideNumber',1)
    return jsonify(slides=[svg(scene(s, THEMES[deck['theme']], start+i, deck)) for i, s in enumerate(deck['slides'])])

@app.post('/api/generate')
def generate():
    deck = validate(request.get_json())
    return send_file(BytesIO(powerpoint(deck)), mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation', as_attachment=True, download_name='presentation.pptx')

@app.post('/api/import-notebook')
def import_notebook_file():
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename.lower().endswith('.xlsx'):
        raise ValueError('Choose the KestrelIQ Notebook .xlsx template.')
    data = uploaded.read()
    if not data or len(data) > 25 * 1024 * 1024:
        raise ValueError('Choose a non-empty Notebook workbook under 25 MB.')
    deck = import_notebook(data)
    return jsonify(validate(deck))

@app.errorhandler(ValueError)
def invalid(error):
    return jsonify(error=str(error)), 400

@app.errorhandler(413)
def too_large(error):
    return jsonify(error='Project exceeds the 40 MB limit.'), 413

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050, debug=False)
