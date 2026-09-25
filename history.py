"""
Persistent JSON history store for thesis analyses.
"""

import json
import os
import uuid
from datetime import datetime
from threading import Lock

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
HISTORY_FILE = os.path.join(_DATA_DIR, 'history.json')
COLLEAGUES_FILE = os.path.join(_DATA_DIR, 'colleagues.json')
_lock = Lock()

SCORE_RESET_DATE = '2026-09-28'


def _is_current_period(timestamp_str):
    return timestamp_str[:10] >= SCORE_RESET_DATE


def _ensure_dir():
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)


def _load():
    _ensure_dir()
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(data):
    _ensure_dir()
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_analysis(author, project, source_name, mode, mode_label, result,
                   original_text='', visibility='published'):
    entry = {
        'id': uuid.uuid4().hex[:12],
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'author': author,
        'project': project,
        'source_name': source_name,
        'mode': mode,
        'mode_label': mode_label,
        'overall_score': result['overall_score'],
        'verdict': result['verdict'],
        'verdict_class': result['verdict_class'],
        'sections': result['sections'],
        'stats': result['stats'],
        'text_stats': result['text_stats'],
        'original_text': original_text[:5000],
        'visibility': visibility,
    }
    with _lock:
        data = _load()
        data.append(entry)
        _save(data)
    return entry['id']


def get_all():
    with _lock:
        return _load()


def get_authors_summary(include_private=False):
    data = _load()
    if not include_private:
        data = [e for e in data if e.get('visibility', 'published') == 'published']
    authors = {}
    for entry in data:
        name = entry['author']
        if name not in authors:
            authors[name] = {'author': name, 'current': [], 'old': []}
        if _is_current_period(entry['timestamp']):
            authors[name]['current'].append(entry)
        else:
            authors[name]['old'].append(entry)

    result = []
    for name, info in authors.items():
        current = info['current']
        old = info['old']
        all_entries = current + old

        if not all_entries:
            continue

        count_current = len(current)
        count_old = len(old)
        total_score = sum(e['overall_score'] for e in current)
        avg = round(total_score / count_current, 1) if count_current else 0

        if count_current:
            last = max(current, key=lambda x: x['timestamp'])
        else:
            last = max(old, key=lambda x: x['timestamp'])

        if not count_current:
            verdict_class = 'old'
        elif avg >= 80:
            verdict_class = 'good'
        elif avg >= 60:
            verdict_class = 'partial'
        elif avg >= 40:
            verdict_class = 'weak'
        else:
            verdict_class = 'bad'

        result.append({
            'author': name,
            'count': count_current,
            'count_old': count_old,
            'avg_score': avg,
            'verdict_class': verdict_class,
            'last_date': last['timestamp'][:10],
            'projects': list({e['project'] for e in all_entries if e.get('project')}),
        })

    result.sort(key=lambda x: x['avg_score'], reverse=True)
    return result


def get_author_history(author, include_private=False):
    data = _load()
    entries = [e for e in data if e['author'] == author]
    if not include_private:
        entries = [e for e in entries if e.get('visibility', 'published') == 'published']
    for e in entries:
        e['period'] = 'current' if _is_current_period(e['timestamp']) else 'old'
    entries.sort(key=lambda x: x['timestamp'], reverse=True)
    return entries


def get_entry(entry_id):
    data = _load()
    for e in data:
        if e['id'] == entry_id:
            return e
    return None


def update_entry(entry_id, updates):
    with _lock:
        data = _load()
        for e in data:
            if e['id'] == entry_id:
                e.update(updates)
                break
        _save(data)


def set_visibility(entry_id, visibility):
    update_entry(entry_id, {'visibility': visibility})


def delete_entry(entry_id):
    with _lock:
        data = _load()
        data = [e for e in data if e['id'] != entry_id]
        _save(data)


def load_colleagues():
    if not os.path.exists(COLLEAGUES_FILE):
        return []
    with open(COLLEAGUES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return sorted(data.get('colleagues', []))


def save_colleagues(colleagues):
    os.makedirs(os.path.dirname(COLLEAGUES_FILE), exist_ok=True)
    with open(COLLEAGUES_FILE, 'w', encoding='utf-8') as f:
        json.dump({'colleagues': sorted(set(colleagues))}, f, ensure_ascii=False, indent=2)


def add_colleague(name):
    colleagues = load_colleagues()
    if name not in colleagues:
        colleagues.append(name)
        save_colleagues(colleagues)
