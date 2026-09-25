"""
Веб-приложение «Анализ тезисов» — Flask.
Загрузка текста/docx → анализ по чек-листу → результат.
История анализов и отчёты по ответственным.
"""

import os
import uuid
import functools
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from text_analyzer import analyze_text, read_docx
import history


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
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'tezisy-admin-2024')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    colleagues = history.load_colleagues()
    return render_template('index.html', colleagues=colleagues)


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
    project = request.form.get('project', '').strip() or 'Не указан'

    result = analyze_text(text, mode=mode)
    result['source_name'] = source_name
    result['author'] = author
    result['project'] = project
    result['original_text'] = text[:3000] + ('...' if len(text) > 3000 else '')

    entry_id = history.save_analysis(
        author=author,
        project=project,
        source_name=source_name,
        mode=result['mode'],
        mode_label=result['mode_label'],
        result=result,
        original_text=text,
        visibility='private',
    )
    result['entry_id'] = entry_id

    return render_template('result.html', result=result)


@app.route('/publish/<entry_id>', methods=['POST'])
def publish_entry(entry_id):
    history.set_visibility(entry_id, 'published')
    flash('Тезисы опубликованы — теперь они видны в отчётах для руководства', 'success')
    return redirect(url_for('reports'))


@app.route('/reports')
def reports():
    authors = history.get_authors_summary()
    return render_template('reports.html', authors=authors)


def _calc_period_stats(entry_list):
    if not entry_list:
        return {
            'avg_score': 0, 'avg_class': 'bad', 'count': 0,
            'section_avgs': [], 'total_stats': {'good': 0, 'partial': 0, 'weak': 0, 'missing': 0},
        }

    total = sum(e['overall_score'] for e in entry_list)
    avg = round(total / len(entry_list), 1)

    if avg >= 80:
        cls = 'good'
    elif avg >= 60:
        cls = 'partial'
    elif avg >= 40:
        cls = 'weak'
    else:
        cls = 'bad'

    sec_map = {}
    for entry in entry_list:
        for sec in entry.get('sections', []):
            key = sec['num']
            if key not in sec_map:
                sec_map[key] = {'num': sec['num'], 'title': sec['title'], 'scores': []}
            sec_map[key]['scores'].append(sec['score'])

    for v in sec_map.values():
        v['avg'] = round(sum(v['scores']) / len(v['scores']), 1)
        if v['avg'] >= 70:
            v['status'] = 'good'
        elif v['avg'] >= 40:
            v['status'] = 'partial'
        elif v['avg'] > 0:
            v['status'] = 'weak'
        else:
            v['status'] = 'not_found'

    stats = {'good': 0, 'partial': 0, 'weak': 0, 'missing': 0}
    for entry in entry_list:
        s = entry.get('stats', {})
        stats['good'] += s.get('good', 0)
        stats['partial'] += s.get('partial', 0)
        stats['weak'] += s.get('weak', 0)
        stats['missing'] += s.get('missing', 0)

    return {
        'avg_score': avg, 'avg_class': cls, 'count': len(entry_list),
        'section_avgs': sorted(sec_map.values(), key=lambda x: x['num']),
        'total_stats': stats,
    }


@app.route('/report/<path:author>')
def report_author(author):
    entries = history.get_author_history(author)
    if not entries:
        flash(f'Нет данных для «{author}»', 'error')
        return redirect(url_for('reports'))

    current_entries = [e for e in entries if e.get('period') == 'current']
    old_entries = [e for e in entries if e.get('period') == 'old']

    periods = {
        'current': _calc_period_stats(current_entries),
        'old': _calc_period_stats(old_entries),
        'all': _calc_period_stats(entries),
    }

    active = periods['current'] if current_entries else periods['all']
    projects = list({e['project'] for e in entries if e.get('project') and e['project'] != 'Не указан'})

    return render_template('report_author.html',
                           author=author,
                           entries=entries,
                           current_entries=current_entries,
                           old_entries=old_entries,
                           periods=periods,
                           avg_score=active['avg_score'],
                           avg_class=active['avg_class'],
                           count=len(current_entries),
                           count_old=len(old_entries),
                           section_avgs=active['section_avgs'],
                           projects=projects,
                           total_stats=active['total_stats'],
                           score_reset_date=history.SCORE_RESET_DATE)


@app.route('/help')
def help_page():
    return render_template('help.html')


# --- Admin panel ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))
        flash('Неверный пароль', 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_panel():
    entries = history.get_all()
    entries.sort(key=lambda x: x['timestamp'], reverse=True)
    colleagues = history.load_colleagues()
    return render_template('admin.html', entries=entries, colleagues=colleagues)


@app.route('/admin/delete/<entry_id>', methods=['POST'])
@admin_required
def admin_delete(entry_id):
    history.delete_entry(entry_id)
    flash('Запись удалена', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/edit/<entry_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit(entry_id):
    entry = history.get_entry(entry_id)
    if not entry:
        flash('Запись не найдена', 'error')
        return redirect(url_for('admin_panel'))

    if request.method == 'POST':
        updates = {
            'author': request.form.get('author', entry['author']).strip(),
            'project': request.form.get('project', entry['project']).strip(),
            'visibility': request.form.get('visibility', entry.get('visibility', 'published')),
        }
        history.update_entry(entry_id, updates)
        flash('Запись обновлена', 'success')
        return redirect(url_for('admin_panel'))

    colleagues = history.load_colleagues()
    return render_template('admin_edit.html', entry=entry, colleagues=colleagues)


@app.route('/admin/visibility/<entry_id>/<visibility>', methods=['POST'])
@admin_required
def admin_visibility(entry_id, visibility):
    if visibility in ('published', 'private'):
        history.set_visibility(entry_id, visibility)
    return redirect(url_for('admin_panel'))


@app.route('/admin/colleagues', methods=['POST'])
@admin_required
def admin_colleagues():
    action = request.form.get('action')
    if action == 'add':
        name = request.form.get('name', '').strip()
        if name:
            history.add_colleague(name)
            flash(f'Добавлен: {name}', 'success')
    elif action == 'delete':
        name = request.form.get('name', '').strip()
        colleagues = history.load_colleagues()
        colleagues = [c for c in colleagues if c != name]
        history.save_colleagues(colleagues)
        flash(f'Удалён: {name}', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/api/colleagues')
def api_colleagues():
    return jsonify(history.load_colleagues())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
