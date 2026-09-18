"""
Persistent JSON history store for thesis analyses.
"""

import json
import os
import uuid
from datetime import datetime
from threading import Lock

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'history.json')
_lock = Lock()


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
                   original_text=''):
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
    }
    with _lock:
        data = _load()
        data.append(entry)
        _save(data)
    return entry['id']


def get_all():
    with _lock:
        return _load()


def get_authors_summary():
    data = _load()
    authors = {}
    for entry in data:
        name = entry['author']
        if name not in authors:
            authors[name] = {'author': name, 'analyses': [], 'total_score': 0}
        authors[name]['analyses'].append(entry)
        authors[name]['total_score'] += entry['overall_score']

    result = []
    for name, info in authors.items():
        count = len(info['analyses'])
        avg = round(info['total_score'] / count, 1) if count else 0
        last = max(info['analyses'], key=lambda x: x['timestamp'])

        if avg >= 80:
            verdict_class = 'good'
        elif avg >= 60:
            verdict_class = 'partial'
        elif avg >= 40:
            verdict_class = 'weak'
        else:
            verdict_class = 'bad'

        result.append({
            'author': name,
            'count': count,
            'avg_score': avg,
            'verdict_class': verdict_class,
            'last_date': last['timestamp'][:10],
            'projects': list({e['project'] for e in info['analyses'] if e.get('project')}),
        })

    result.sort(key=lambda x: x['avg_score'], reverse=True)
    return result


def get_author_history(author):
    data = _load()
    entries = [e for e in data if e['author'] == author]
    entries.sort(key=lambda x: x['timestamp'], reverse=True)
    return entries


def delete_entry(entry_id):
    with _lock:
        data = _load()
        data = [e for e in data if e['id'] != entry_id]
        _save(data)
