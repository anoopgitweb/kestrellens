from flask import Flask, jsonify, request, render_template, send_file
from io import BytesIO
from engine import CATALOG, THEMES, validate, scene, svg, powerpoint

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
    return jsonify(slides=[svg(scene(s, THEMES[deck['theme']], i + 1)) for i, s in enumerate(deck['slides'])])

@app.post('/api/generate')
def generate():
    deck = validate(request.get_json())
    return send_file(BytesIO(powerpoint(deck)), mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation', as_attachment=True, download_name='presentation.pptx')

@app.errorhandler(ValueError)
def invalid(error):
    return jsonify(error=str(error)), 400

@app.errorhandler(413)
def too_large(error):
    return jsonify(error='Project exceeds the 40 MB limit.'), 413

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050, debug=False)
