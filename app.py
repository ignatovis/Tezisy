"""
Веб-приложение «Анализ тезисов» — Flask.
Загрузка текста/docx → анализ по чек-листу → результат.
"""

import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from text_analyzer import analyze_text, read_docx


class PrefixMiddleware:
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix.rstrip('/')

    def __call__(self, environ, start_response):
        environ['SCRIPT_NAME'] = self.prefix
        return self.app(environ, start_response)


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tezisy-dev-key-change-in-prod')

prefix = os.environ.get('URL_PREFIX', '')
if prefix:
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=prefix)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'docx', 'txt'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    mode = request.form.get('mode', 'auto')
    if mode not in ('smr', 'rns'):
        mode = None

    text = ''
    source_name = ''

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        if not allowed_file(file.filename):
            flash('Допустимые форматы: .docx, .txt', 'error')
            return redirect(url_for('index'))

        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        source_name = file.filename

        try:
            if filepath.endswith('.docx'):
                text = read_docx(filepath)
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
        except Exception as e:
            flash(f'Ошибка чтения файла: {e}', 'error')
            return redirect(url_for('index'))
        finally:
            try:
                os.remove(filepath)
            except OSError:
                pass

    elif request.form.get('text', '').strip():
        text = request.form['text'].strip()
        source_name = 'Вставленный текст'
    else:
        flash('Вставьте текст или загрузите файл', 'error')
        return redirect(url_for('index'))

    author = request.form.get('author', '').strip() or 'Не указан'

    result = analyze_text(text, mode=mode)
    result['source_name'] = source_name
    result['author'] = author
    result['original_text'] = text[:3000] + ('...' if len(text) > 3000 else '')

    return render_template('result.html', result=result)


@app.route('/help')
def help_page():
    return render_template('help.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
