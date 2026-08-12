"""
Генерация HTML-отчёта из результатов анализа.
"""

import html


def generate_html(analysis, output_path):
    mode = analysis['mode']
    header = analysis['header']
    metrics = analysis['metrics']
    events = analysis['events']
    blocks = analysis.get('mode_blocks', {})
    decisions = analysis['decisions']

    mode_title = 'Стадия СМР' if mode == 'smr' else 'До РНС'

    sections_html = []

    sections_html.append(_section('Ключевые метрики', _render_metrics(metrics), icon='📊'))
    sections_html.append(_section('Ближайшие события (горизонт 1 месяц)', _render_events(events), icon='📅'))

    if mode == 'smr':
        block_order = ['3.1', '3.2', '3.3', '3.4', '3.5', '3.6']
    else:
        block_order = ['4.1', '4.2', '4.3', '4.4', '4.5', '4.6']

    block_icons = {
        '3.1': '🔍', '3.2': '🏗', '3.3': '⚠️', '3.4': '⏱', '3.5': '✅', '3.6': '🎯',
        '4.1': '🛤', '4.2': '📋', '4.3': '🔗', '4.4': '📜', '4.5': '❓', '4.6': '📆',
    }

    for key in block_order:
        block = blocks.get(key, {})
        title = f'{key} {block.get("title", "")}'
        icon = block_icons.get(key, '📌')
        content = _render_block(block)
        if key == '3.2' and block.get('data'):
            content += _render_zone_table(block['data'])
        sections_html.append(_section(title, content, icon=icon))

    sections_html.append(_section(
        decisions['title'],
        _render_decisions(decisions['items']),
        icon='💡',
        css_class='decisions'
    ))

    body = '\n'.join(sections_html)

    page = HTML_TEMPLATE.format(
        title=_esc(header['text']),
        project_name=_esc(header['project_name']),
        report_date=_esc(header['report_date']),
        mode_label=_esc(header['mode_label']),
        mode_title=_esc(mode_title),
        body=body,
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(page)

    return output_path


def _esc(text):
    return html.escape(str(text)) if text else ''


def _section(title, content, icon='📌', css_class=''):
    cls = f' {css_class}' if css_class else ''
    return f'''
    <div class="section{cls}">
        <h2>{icon} {_esc(title)}</h2>
        {content}
    </div>'''


def _render_metrics(metrics):
    items = metrics.get('items', [])
    parts = []
    for item in items:
        if 'Критических' in item:
            parts.append(f'<div class="metric metric-warn">{_esc(item)}</div>')
        elif 'Отклонение' in item:
            parts.append(f'<div class="metric metric-alert">{_esc(item)}</div>')
        else:
            parts.append(f'<div class="metric">{_esc(item)}</div>')
    return '<div class="metrics-grid">' + ''.join(parts) + '</div>'


def _render_events(events):
    parts = []

    if events['completed_milestones']:
        parts.append('<h3>Завершённые вехи</h3>')
        parts.append(_render_list(events['completed_milestones'], css='completed'))

    if events['completed_tasks']:
        parts.append('<h3>Завершённые задачи</h3>')
        parts.append(_render_list(events['completed_tasks'], css='completed'))

    if events['finishing_soon']:
        parts.append('<h3>Завершение в течение месяца</h3>')
        parts.append(_render_list(events['finishing_soon'], css='finishing'))

    if events['starting_soon']:
        parts.append('<h3>Начало в пределах месяца</h3>')
        parts.append(_render_list(events['starting_soon'], css='starting'))

    if events['errors']:
        parts.append('<h3>Ошибки данных</h3>')
        parts.append(_render_list(events['errors'], css='error'))

    if not parts:
        parts.append('<p class="empty">Нет событий в горизонте 1 месяц</p>')

    return '\n'.join(parts)


def _render_block(block):
    parts = []
    summary = block.get('summary', '')
    if summary:
        parts.append(f'<p class="thesis-summary">{_esc(summary)}</p>')
    items = block.get('items', [])
    if items:
        parts.append(_render_list(items))
    if not parts:
        parts.append('<p class="empty">Нет данных</p>')
    return '\n'.join(parts)


def _render_list(items, css=''):
    if not items:
        return '<p class="empty">Нет данных</p>'
    cls = f' class="{css}"' if css else ''
    li = ''.join(f'<li{cls}>{_esc(item)}</li>' for item in items)
    return f'<ul>{li}</ul>'


def _render_zone_table(zone_data):
    rows = ''
    for z in zone_data:
        dev_class = 'td-alert' if z['max_dev'] > 14 else ('td-ok' if z['max_dev'] < -14 else '')
        rows += f'''<tr>
            <td>{_esc(z["zone"])}</td>
            <td>{z["count"]}</td>
            <td class="{dev_class}">{z["max_dev"]:.0f}</td>
            <td>{z["avg_dev"]:.0f}</td>
            <td>{z["avg_pct"]:.0f}%</td>
        </tr>'''

    return f'''
    <table class="zone-table">
        <thead><tr>
            <th>Корпус/зона</th><th>Задач</th><th>Макс. откл. (дн.)</th>
            <th>Ср. откл. (дн.)</th><th>Ср. %</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>'''


def _render_decisions(items):
    if not items:
        return '<p class="empty">Нет предложений</p>'
    li = ''.join(f'<li class="decision">{_esc(item)}</li>' for item in items)
    return f'<ol class="decisions-list">{li}</ol>'


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
            background: #f4f6f8;
            color: #2c3e50;
            line-height: 1.6;
            padding: 0;
        }}

        .header {{
            background: linear-gradient(135deg, #1a365d 0%, #2b6cb0 100%);
            color: white;
            padding: 2rem 2.5rem;
            margin-bottom: 1.5rem;
        }}
        .header h1 {{
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}
        .header-meta {{
            display: flex;
            gap: 2rem;
            font-size: 0.95rem;
            opacity: 0.9;
        }}
        .header-meta span {{
            display: flex;
            align-items: center;
            gap: 0.3rem;
        }}
        .mode-badge {{
            background: rgba(255,255,255,0.2);
            padding: 0.2rem 0.8rem;
            border-radius: 4px;
            font-weight: 600;
        }}

        .container {{
            max-width: 960px;
            margin: 0 auto;
            padding: 0 1.5rem 3rem;
        }}

        .section {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem 2rem;
            margin-bottom: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .section h2 {{
            font-size: 1.15rem;
            color: #1a365d;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e2e8f0;
        }}
        .section h3 {{
            font-size: 0.95rem;
            color: #4a5568;
            margin: 1rem 0 0.5rem;
            font-weight: 600;
        }}

        .section.decisions {{
            border-left: 4px solid #d69e2e;
            background: #fffff0;
        }}
        .section.decisions h2 {{
            color: #744210;
            border-bottom-color: #f6e05e;
        }}

        .metrics-grid {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        .metric {{
            background: #edf2f7;
            padding: 0.75rem 1.25rem;
            border-radius: 6px;
            font-weight: 500;
            flex: 1;
            min-width: 200px;
            text-align: center;
        }}
        .metric-warn {{
            background: #fefcbf;
            color: #744210;
        }}
        .metric-alert {{
            background: #fed7d7;
            color: #9b2c2c;
        }}

        ul {{
            list-style: none;
            padding: 0;
        }}
        ul li {{
            padding: 0.5rem 0 0.5rem 1.5rem;
            position: relative;
            border-bottom: 1px solid #f7fafc;
        }}
        ul li:last-child {{ border-bottom: none; }}
        ul li::before {{
            content: "•";
            position: absolute;
            left: 0.3rem;
            color: #a0aec0;
            font-weight: bold;
        }}

        li.completed::before {{ content: "✓"; color: #38a169; }}
        li.finishing::before {{ content: "→"; color: #d69e2e; }}
        li.starting::before {{ content: "▶"; color: #3182ce; }}
        li.error::before {{ content: "✗"; color: #e53e3e; }}
        li.error {{ color: #e53e3e; }}

        ol.decisions-list {{
            padding-left: 1.5rem;
        }}
        ol.decisions-list li {{
            padding: 0.5rem 0;
            border-bottom: 1px solid #fefcbf;
        }}
        ol.decisions-list li:last-child {{ border-bottom: none; }}

        .zone-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
            font-size: 0.9rem;
        }}
        .zone-table th {{
            background: #edf2f7;
            padding: 0.6rem 0.8rem;
            text-align: left;
            font-weight: 600;
            color: #4a5568;
        }}
        .zone-table td {{
            padding: 0.5rem 0.8rem;
            border-bottom: 1px solid #e2e8f0;
        }}
        .td-alert {{
            color: #e53e3e;
            font-weight: 600;
        }}
        .td-ok {{
            color: #38a169;
            font-weight: 600;
        }}

        .thesis-summary {{
            font-size: 1.05rem;
            line-height: 1.7;
            color: #1a202c;
            margin-bottom: 0.75rem;
            padding: 0.5rem 0;
        }}

        .empty {{
            color: #a0aec0;
            font-style: italic;
            padding: 0.5rem 0;
        }}

        .footer {{
            text-align: center;
            color: #a0aec0;
            font-size: 0.8rem;
            padding: 2rem 0;
        }}

        @media print {{
            body {{ background: white; }}
            .header {{ background: #1a365d !important; -webkit-print-color-adjust: exact; }}
            .section {{ box-shadow: none; border: 1px solid #e2e8f0; page-break-inside: avoid; }}
        }}

        @media (max-width: 640px) {{
            .header {{ padding: 1.5rem; }}
            .header-meta {{ flex-direction: column; gap: 0.5rem; }}
            .metrics-grid {{ flex-direction: column; }}
            .container {{ padding: 0 1rem 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{project_name}</h1>
        <div class="header-meta">
            <span>📅 Актуализация: {report_date}</span>
            <span class="mode-badge">{mode_title}</span>
        </div>
    </div>
    <div class="container">
        {body}
        <div class="footer">
            Сформировано автоматически · Тезисы v1.0
        </div>
    </div>
</body>
</html>'''
