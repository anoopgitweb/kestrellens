"""Start with either standard installed dependencies or the local dependency folder."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '.packages'))
from app import app
if __name__ == '__main__':
    print('Slide Studio is ready at http://127.0.0.1:5050')
    app.run(host='127.0.0.1', port=5050, debug=False)
