"""
Seed history from existing Word thesis files.
Splits each file into individual theses by date markers,
extracts project name from each, and saves separately.

Run once: python seed_history.py
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from text_analyzer import analyze_text, read_docx
import history

THESIS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'Тезисы для анализа')

DATE_RE = re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s*$', re.MULTILINE)

PROJECT_PATTERNS = [
    re.compile(r'по проект[а-яё]*\s+[«"]([^»"]+)[»"]', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+((?:ЖК|МФК|БЦ)\s+[\w\s\-]+)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+([\w][\w\s\-]*\d[\w\s\-]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Seliger\s+City[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Jois[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Domenic[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(City\s*Bay[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Знаки[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Топ\s*[Тт]ауэр[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Тверск[а-яё]*[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]*\s+(Климашкин[а-яё]*[^,.\n]*)', re.IGNORECASE),
    re.compile(r'по проект[а-яё]+\s+([\w][\w\s\-]{2,30})', re.IGNORECASE),
    re.compile(r'по\s+(Тушино[^,.\n]*)', re.IGNORECASE),
]


def split_by_date(text):
    matches = list(DATE_RE.finditer(text))
    if not matches:
        return [('', text)]

    chunks = []
    for i, m in enumerate(matches):
        date_str = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()
        if len(chunk_text) > 50:
            chunks.append((date_str, chunk_text))

    return chunks


def extract_project(text):
    first_500 = text[:500]
    for pat in PROJECT_PATTERNS:
        m = pat.search(first_500)
        if m:
            name = m.group(1).strip().rstrip('.')
            if len(name) > 3:
                return name
    return 'Не указан'


def seed():
    if not os.path.isdir(THESIS_DIR):
        print(f'Directory not found: {THESIS_DIR}')
        return

    existing = history.get_all()
    existing_keys = {(e.get('source_name', ''), e.get('project', ''))
                     for e in existing}

    count = 0
    for fname in sorted(os.listdir(THESIS_DIR)):
        if not fname.endswith('.docx') or fname.startswith('Анализ_'):
            continue

        filepath = os.path.join(THESIS_DIR, fname)
        author = fname.replace('.docx', '').strip()
        if author.endswith('.'):
            author = author[:-1] + '.'

        print(f'\n=== {author} ({fname}) ===')

        try:
            full_text = read_docx(filepath)
        except Exception as e:
            print(f'  ERROR reading: {e}')
            continue

        chunks = split_by_date(full_text)
        print(f'  Found {len(chunks)} thesis(es)')

        for date_str, chunk_text in chunks:
            project = extract_project(chunk_text)
            source_label = f'{fname} [{date_str}]' if date_str else fname

            key = (source_label, project)
            if key in existing_keys:
                print(f'  skip (exists): {date_str} / {project}')
                continue

            result = analyze_text(chunk_text)

            history.save_analysis(
                author=author,
                project=project,
                source_name=source_label,
                mode=result['mode'],
                mode_label=result['mode_label'],
                result=result,
                original_text=chunk_text,
            )
            count += 1
            print(f'  + {date_str:>10} | {project:<30} | score={result["overall_score"]:5.1f} | {result["mode"]}')

    print(f'\nDone. Added {count} entries total.')


if __name__ == '__main__':
    seed()
