"""
Аналитический движок: формирует блоки тезисов по ТЗ.

Блоки:
  2.1 Заголовок, 2.2 Ключевые метрики, 2.3 Ближайшие события
  3.x Блоки СМР (3.1–3.6)
  4.x Блоки РНС (4.1–4.6)
  5.1 Управленческие решения
"""

from collections import defaultdict
from datetime import datetime


DEVIATION_THRESHOLD = 14
LOW_PERCENT_THRESHOLD = 50
AHEAD_THRESHOLD = -14
SLACK_DISPLAY_THRESHOLD = 90


def analyze(mpp_data, mode, project_name=None, report_date=None):
    tasks = mpp_data['tasks']
    relations = mpp_data['relations']
    props = mpp_data['project_properties']

    work_tasks = {tid: t for tid, t in tasks.items()
                  if not t.get('summary') and t.get('name')}

    if not project_name:
        project_name = props.get('title') or 'Без названия'
    if not report_date:
        report_date = props.get('status_date') or datetime.now().strftime('%d.%m.%Y')

    result = {
        'mode': mode,
        'header': _block_header(project_name, report_date, mode),
        'metrics': _block_metrics(work_tasks, mode),
        'events': _block_events(work_tasks),
    }

    if mode == 'smr':
        result['mode_blocks'] = _blocks_smr(work_tasks, relations, tasks)
    else:
        result['mode_blocks'] = _blocks_rns(work_tasks, relations, tasks)

    result['decisions'] = _block_decisions(result, mode)
    return result


def _block_header(project_name, report_date, mode):
    date_str = _format_date(report_date)
    mode_label = 'СМР' if mode == 'smr' else 'до РНС'
    return {
        'project_name': project_name,
        'report_date': date_str,
        'mode_label': mode_label,
        'text': f'Отчёт по проекту «{project_name}», актуализация от {date_str}, режим {mode_label}',
    }


def _block_metrics(work_tasks, mode='smr'):
    if not work_tasks:
        return {'text': 'Нет данных для анализа', 'items': []}

    pcts = [t['percent_complete'] for t in work_tasks.values() if t.get('percent_complete') is not None]
    avg_pct = round(sum(pcts) / len(pcts), 1) if pcts else 0

    critical_count = sum(1 for t in work_tasks.values() if t.get('critical'))
    total_count = len(work_tasks)

    target_kw = 'РНС' if mode == 'rns' else 'ЗОС'
    key_milestone = _find_key_milestone(work_tasks, target_kw)

    return {
        'avg_percent': avg_pct,
        'critical_count': critical_count,
        'total_count': total_count,
        'final_milestone_deviation': key_milestone,
        'items': [
            f'Средний % завершения: {avg_pct}%',
            f'Критических задач: {critical_count} из {total_count}',
        ] + ([f'Отклонение итоговой вехи «{key_milestone["name"]}»: {_days_str(key_milestone["deviation"])}'] if key_milestone else []),
    }


def _find_key_milestone(work_tasks, keyword):
    candidates = []
    for t in work_tasks.values():
        if not t.get('milestone'):
            continue
        cf = t.get('custom_fields') or {}
        typ = cf.get('Тип обязательства', '')
        name_upper = (t.get('name') or '').upper()
        fv = t.get('finish_variance')
        if fv is None:
            continue
        if typ == 'ГРП' and keyword.upper() in name_upper:
            candidates.append({'name': t['name'], 'deviation': fv, 'priority': 0})
        elif keyword.upper() in name_upper:
            prio = 1 if t.get('critical') else 2
            candidates.append({'name': t['name'], 'deviation': fv, 'priority': prio})

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x['priority'], -abs(x['deviation'])))
    return candidates[0]


def _block_events(work_tasks):
    completed_milestones = []
    completed_tasks = []
    finishing_soon = []
    starting_soon = []
    errors = []

    for t in work_tasks.values():
        cf = t.get('custom_fields') or {}
        event_status = cf.get('События в срок до 1 месяца', '')
        typ = cf.get('Тип обязательства', '')
        name = t.get('name', '')
        fv = t.get('finish_variance') or 0
        sv = t.get('start_variance') or 0
        slack = t.get('free_slack_days')

        if not event_status:
            continue

        status_lower = event_status.lower().strip()

        if status_lower == 'завершено':
            phrase = _phrase_completed(t, fv)
            if t.get('milestone') and typ == 'ГРП':
                completed_milestones.append(phrase)
            else:
                completed_tasks.append(phrase)
        elif 'завершение' in status_lower:
            finishing_soon.append(_phrase_finishing(t, fv, slack))
        elif 'начало' in status_lower:
            starting_soon.append(_phrase_starting(t, sv, slack))
        else:
            errors.append(f'{name}: неизвестный статус «{event_status}»')

    return {
        'completed_milestones': completed_milestones,
        'completed_tasks': completed_tasks,
        'finishing_soon': finishing_soon,
        'starting_soon': starting_soon,
        'errors': errors,
    }


def _phrase_completed(t, fv):
    name = t['name']
    if fv and fv < 0:
        return f'{name} с опережением {abs(fv):.0f} дней'
    elif fv and fv > 0:
        return f'{name} с задержкой {fv:.0f} дней'
    return f'{name} в срок'


def _phrase_finishing(t, fv, slack):
    name = t['name']
    parts = [name]
    if fv and fv > 0:
        parts.append(f'с задержкой {fv:.0f} дней')
    elif fv and fv < 0:
        parts.append(f'с опережением {abs(fv):.0f} дней')
    if slack is not None and 0 < slack <= SLACK_DISPLAY_THRESHOLD:
        parts.append(f'имеем временной резерв {slack:.0f} дней')
    return ', '.join(parts)


def _phrase_starting(t, sv, slack):
    name = t['name']
    parts = [name]
    if sv and sv > 0:
        parts.append(f'задержка начала {sv:.0f} дней')
    if slack is not None and 0 < slack <= SLACK_DISPLAY_THRESHOLD:
        parts.append(f'имеем {slack:.0f} дней резерва')
    return ', '.join(parts)


# ── Блоки СМР ──

def _blocks_smr(work_tasks, relations, all_tasks):
    return {
        '3.1': _smr_decomposition(work_tasks),
        '3.2': _smr_by_zones(work_tasks),
        '3.3': _smr_critical_low_pct(work_tasks),
        '3.4': _smr_time_reserve(work_tasks),
        '3.5': _smr_ahead_zones(work_tasks),
        '3.6': _smr_final_milestones(work_tasks),
    }


def _smr_decomposition(work_tasks):
    delayed = [t for t in work_tasks.values()
               if (t.get('finish_variance') or 0) > DEVIATION_THRESHOLD]
    delayed.sort(key=lambda t: t.get('finish_variance', 0), reverse=True)

    groups = _group_tasks(delayed)
    items = []
    for group_name, group_tasks in groups.items():
        max_dev = max(t.get('finish_variance', 0) for t in group_tasks)
        top = sorted(group_tasks, key=lambda t: t.get('finish_variance', 0), reverse=True)[:3]
        details = ', '.join(f'{t["name"]} – {t["finish_variance"]:.0f} дн.' for t in top)
        items.append(
            f'По направлению «{group_name}» максимальное отклонение составляет '
            f'{max_dev:.0f} дней, основные задержки: {details}'
        )

    return {'title': 'Декомпозиция отклонений', 'count': len(delayed), 'items': items}


def _smr_by_zones(work_tasks):
    zones = defaultdict(list)
    for t in work_tasks.values():
        zone = _get_zone(t)
        if zone:
            zones[zone].append(t)

    if not zones:
        return {'title': 'Группировка по корпусам/зонам', 'items': ['Данные по корпусам/зонам отсутствуют'], 'data': []}

    if len(zones) == 1:
        zone_name = list(zones.keys())[0]
        return {'title': 'Группировка по корпусам/зонам',
                'items': [f'Проект с одним корпусом «{zone_name}», группировка не требуется'], 'data': []}

    zone_stats = []
    for zone_name, ztasks in zones.items():
        devs = [t.get('finish_variance', 0) for t in ztasks if t.get('finish_variance') is not None]
        pcts = [t.get('percent_complete', 0) for t in ztasks if t.get('percent_complete') is not None]
        avg_dev = sum(devs) / len(devs) if devs else 0
        max_dev = max(devs) if devs else 0
        avg_pct = sum(pcts) / len(pcts) if pcts else 0
        zone_stats.append({
            'zone': zone_name, 'avg_dev': round(avg_dev, 1), 'max_dev': round(max_dev, 1),
            'avg_pct': round(avg_pct, 1), 'count': len(ztasks)
        })

    zone_stats.sort(key=lambda z: z['max_dev'], reverse=True)

    items = []
    for z in zone_stats:
        if z['max_dev'] > DEVIATION_THRESHOLD:
            items.append(f'Отстающий корпус «{z["zone"]}»: макс. отклонение {z["max_dev"]:.0f} дней, '
                         f'средний % завершения {z["avg_pct"]:.0f}%')
        elif z['max_dev'] < AHEAD_THRESHOLD:
            items.append(f'Опережающий корпус «{z["zone"]}»: опережение {abs(z["max_dev"]):.0f} дней')

    if not items:
        items.append('Значимых отклонений по корпусам не выявлено')

    return {'title': 'Группировка по корпусам/зонам', 'items': items, 'data': zone_stats}


def _smr_critical_low_pct(work_tasks):
    critical_low = [t for t in work_tasks.values()
                    if t.get('critical') and (t.get('percent_complete') or 0) < LOW_PERCENT_THRESHOLD]
    critical_low.sort(key=lambda t: t.get('percent_complete', 0))

    items = []
    for t in critical_low[:10]:
        pct = t.get('percent_complete', 0)
        fv = t.get('finish_variance', 0)
        resp = t.get('resource_names') or ''
        line = f'{t["name"]}: завершено {pct:.0f}%, отклонение {_days_str(fv)}'
        if resp:
            line += f' (отв.: {resp})'
        items.append(line)

    if not items:
        items.append('Критических задач с низким % завершения нет')

    return {'title': 'Критические задачи с низким % завершения', 'count': len(critical_low), 'items': items}


def _smr_time_reserve(work_tasks):
    reserve_tasks = [t for t in work_tasks.values()
                     if not t.get('critical')
                     and (t.get('total_slack_days') or 0) > 0
                     and (t.get('percent_complete') or 0) < 100]
    reserve_tasks.sort(key=lambda t: t.get('total_slack_days', 0), reverse=True)

    items = []
    for t in reserve_tasks[:10]:
        slack = t.get('total_slack_days', 0)
        if slack > SLACK_DISPLAY_THRESHOLD:
            continue
        fv = t.get('finish_variance', 0)
        line = f'{t["name"]}: временной резерв {slack:.0f} дней'
        if fv and fv > 0:
            line += f', отклонение {_days_str(fv)}'
        items.append(line)

    if not items:
        items.append('Задач с информативным временным резервом не выявлено')

    return {'title': 'Временной резерв по некритическим задачам', 'count': len(reserve_tasks), 'items': items}


def _smr_ahead_zones(work_tasks):
    ahead = [t for t in work_tasks.values()
             if (t.get('finish_variance') or 0) < AHEAD_THRESHOLD]
    ahead.sort(key=lambda t: t.get('finish_variance', 0))

    items = []
    for t in ahead[:10]:
        items.append(f'Опережение по «{t["name"]}» составляет {abs(t["finish_variance"]):.0f} дней, '
                     f'может служить ресурсным резервом')

    if not items:
        items.append('Зон значимого опережения не выявлено')

    return {'title': 'Зоны опережения и временного резерва', 'items': items, 'count': len(ahead)}


def _smr_final_milestones(work_tasks):
    items = []
    for keyword in ['ЗОС', 'РНВ']:
        for t in work_tasks.values():
            if _is_final_milestone(t, keyword):
                fv = t.get('finish_variance', 0)
                finish = _format_date(t.get('finish'))
                items.append(f'Текущий прогноз {keyword} – {finish} (отклонение {_days_str(fv)})')

    if not items:
        items.append('Финальные вехи ЗОС/РНВ не найдены')

    return {'title': 'Влияние на финальные вехи (ЗОС/РНВ)', 'items': items}


# ── Блоки РНС ──

def _blocks_rns(work_tasks, relations, all_tasks):
    return {
        '4.1': _rns_critical_path(work_tasks),
        '4.2': _rns_shift_causes(work_tasks, all_tasks),
        '4.3': _rns_cascade(work_tasks, relations, all_tasks),
        '4.4': _rns_mpt_obligations(work_tasks),
        '4.5': _rns_uncertainty(work_tasks),
        '4.6': _rns_forecast(work_tasks),
    }


def _rns_critical_path(work_tasks):
    critical_milestones = _collect_key_milestones(work_tasks)
    critical_milestones.sort(key=lambda t: t.get('finish', ''))

    delayed = [t for t in critical_milestones if (t.get('finish_variance') or 0) > 0]
    on_track = [t for t in critical_milestones if (t.get('finish_variance') or 0) <= 0]

    summary_parts = []
    if not critical_milestones:
        summary_parts.append('Критические вехи на пути к РНС не идентифицированы.')
    else:
        summary_parts.append(f'На критическом пути к РНС находится {len(critical_milestones)} '
                             f'{_noun_form(len(critical_milestones), "веха", "вехи", "вех")}.')
        if delayed:
            max_dev = max(t.get('finish_variance', 0) for t in delayed)
            summary_parts.append(f'Из них {len(delayed)} '
                                 f'{_noun_form(len(delayed), "отстаёт", "отстают", "отстают")} '
                                 f'от плана (максимальное отклонение {max_dev:.0f} дней).')
        if on_track:
            summary_parts.append(f'{len(on_track)} — в графике или с опережением.')

    details = []
    for t in delayed[:5]:
        finish = _format_date(t.get('finish'))
        bl_finish = _format_date(t.get('baseline_finish'))
        fv = t.get('finish_variance', 0)
        deadline = _format_date(t.get('deadline'))
        line = f'«{t["name"]}»: прогноз {finish} вместо {bl_finish} ({_days_str(fv)})'
        if deadline and deadline != '—':
            line += f', крайний срок {deadline}'
        details.append(line)

    return {'title': 'Критический путь до РНС',
            'summary': ' '.join(summary_parts),
            'items': details if details else ['Все вехи в графике.'],
            'count': len(critical_milestones)}


def _collect_key_milestones(work_tasks):
    by_grp = [t for t in work_tasks.values()
              if t.get('critical') and t.get('milestone')
              and (t.get('custom_fields') or {}).get('Тип обязательства') == 'ГРП']
    if by_grp:
        return by_grp

    by_deadline = [t for t in work_tasks.values()
                   if t.get('critical') and t.get('milestone') and t.get('deadline')]
    if by_deadline:
        return by_deadline

    return [t for t in work_tasks.values()
            if t.get('critical') and t.get('milestone')]


def _rns_shift_causes(work_tasks, all_tasks):
    delayed_milestones = []
    for t in work_tasks.values():
        cf = t.get('custom_fields') or {}
        is_grp = cf.get('Тип обязательства') == 'ГРП'
        is_key = is_grp or t.get('deadline')
        if (t.get('critical') and t.get('milestone') and is_key
                and (t.get('finish_variance') or 0) > 0):
            delayed_milestones.append(t)

    if not delayed_milestones:
        return {'title': 'Анализ причин сдвигов',
                'summary': 'Сдвигов по ключевым вехам не выявлено.',
                'items': []}

    cause_groups = []
    for m in delayed_milestones:
        children = [t for t in all_tasks.values()
                    if t.get('parent_id') == m.get('parent_id')
                    and not t.get('summary') and not t.get('milestone')
                    and (t.get('finish_variance') or 0) > 0]
        children.sort(key=lambda t: t.get('finish_variance', 0), reverse=True)
        if children:
            cause_groups.append((m, children[:3]))

    summary_parts = [f'Выявлены задержки по {len(delayed_milestones)} '
                     f'{_noun_form(len(delayed_milestones), "ключевой вехе", "ключевым вехам", "ключевым вехам")}.']

    details = []
    for m, causes in cause_groups[:3]:
        cause_names = ', '.join(f'«{c["name"]}» ({c["finish_variance"]:.0f} дн.)' for c in causes)
        details.append(f'Сдвиг «{m["name"]}» на {m["finish_variance"]:.0f} дней. '
                       f'Причины: {cause_names}')

    if cause_groups:
        top_cause = cause_groups[0][1][0]
        summary_parts.append(f'Основная причина — задержка на этапе «{top_cause["name"]}» '
                             f'(+{top_cause["finish_variance"]:.0f} дн.).')

    return {'title': 'Анализ причин сдвигов',
            'summary': ' '.join(summary_parts),
            'items': details}


def _rns_cascade(work_tasks, relations, all_tasks):
    rns_key = _find_key_milestone(work_tasks, 'РНС')
    if not rns_key:
        return {'title': 'Каскадное влияние сдвигов',
                'summary': 'Веха РНС не найдена, каскадный анализ невозможен.',
                'items': []}

    rns_task = next((t for t in work_tasks.values() if t.get('name') == rns_key['name']), None)
    if not rns_task:
        return {'title': 'Каскадное влияние сдвигов',
                'summary': 'Веха РНС не найдена, каскадный анализ невозможен.',
                'items': []}

    chain = _trace_predecessors(rns_task['id'], relations, all_tasks, max_depth=8)
    delayed = [c for c in chain if (c.get('finish_variance') or 0) > 0]
    delayed.sort(key=lambda c: c.get('finish_variance', 0), reverse=True)

    rns_fv = rns_task.get('finish_variance', 0)

    if not delayed:
        return {'title': 'Каскадное влияние сдвигов',
                'summary': 'Каскадного влияния на дату РНС не выявлено. '
                           'Все предшествующие задачи в графике.',
                'items': []}

    unique_delays = {}
    for c in delayed:
        if c['name'] not in unique_delays:
            unique_delays[c['name']] = c

    top = list(unique_delays.values())[:5]
    chain_str = ' → '.join(f'«{c["name"]}»' for c in top)

    summary = (f'Каскад задержек: {chain_str} — приводит к смещению РНС на '
               f'{rns_fv:.0f} дней. В цепочке {len(unique_delays)} '
               f'{_noun_form(len(unique_delays), "задача", "задачи", "задач")} с отклонениями.')

    details = []
    for c in top[:3]:
        details.append(f'«{c["name"]}»: отклонение {_days_str(c["finish_variance"])}')

    return {'title': 'Каскадное влияние сдвигов',
            'summary': summary,
            'items': details}


def _rns_mpt_obligations(work_tasks):
    mpt_tasks = [t for t in work_tasks.values()
                 if t.get('name') and ('МПТ' in t['name'].upper() or 'ковенант' in t['name'].lower())]

    risks = [t for t in mpt_tasks if (t.get('finish_variance') or 0) > 0]
    on_track = [t for t in mpt_tasks if (t.get('finish_variance') or 0) <= 0]

    if not mpt_tasks:
        return {'title': 'Обязательства по МПТ / ковенантам',
                'summary': 'Задачи МПТ и ковенанты в графике не найдены.',
                'items': []}

    summary_parts = [f'Всего {len(mpt_tasks)} '
                     f'{_noun_form(len(mpt_tasks), "задача", "задачи", "задач")} по МПТ/ковенантам.']

    if risks:
        max_risk_dev = max(t.get('finish_variance', 0) for t in risks)
        summary_parts.append(f'Выявлено {len(risks)} '
                             f'{_noun_form(len(risks), "риск", "риска", "рисков")}: '
                             f'отклонение до {max_risk_dev:.0f} дней.')
    else:
        summary_parts.append('Все в графике, рисков не выявлено.')

    if on_track:
        summary_parts.append(f'{len(on_track)} '
                             f'{_noun_form(len(on_track), "задача", "задачи", "задач")} без отклонений.')

    details = []
    for t in risks[:3]:
        fv = t.get('finish_variance', 0)
        finish = _format_date(t.get('finish'))
        details.append(f'РИСК: «{t["name"]}» — отклонение {fv:.0f} дней, прогноз {finish}')

    return {'title': 'Обязательства по МПТ / ковенантам',
            'summary': ' '.join(summary_parts),
            'items': details,
            'risk_count': len(risks)}


def _rns_uncertainty(work_tasks):
    total = len(work_tasks)
    no_baseline = [t for t in work_tasks.values()
                   if not t.get('baseline_start') and not t.get('baseline_finish')
                   and (t.get('percent_complete') or 0) < 100]

    if not no_baseline:
        return {'title': 'Зоны неопределённости',
                'summary': 'Все задачи имеют сохранённый базовый план. Анализ отклонений корректен.',
                'items': [], 'count': 0}

    pct = round(len(no_baseline) / total * 100) if total else 0

    groups = defaultdict(int)
    for t in no_baseline:
        name = t.get('name', '')
        for kw in ['МПТ', 'оснащ', 'продаж', 'земел', 'кредит', 'тендер', 'проект',
                    'концепц', 'благоустр', 'фасад']:
            if kw.lower() in name.lower():
                groups[kw] += 1
                break
        else:
            groups['прочие'] += 1

    top_groups = sorted(groups.items(), key=lambda x: x[1], reverse=True)[:3]
    group_str = ', '.join(f'{k} ({v})' for k, v in top_groups)

    summary = (f'{len(no_baseline)} {_noun_form(len(no_baseline), "задача", "задачи", "задач")} '
               f'({pct}%) не имеют базового плана, что ограничивает анализ отклонений. '
               f'Основные направления: {group_str}.')

    details = []
    critical_no_bl = [t for t in no_baseline if t.get('critical')]
    if critical_no_bl:
        details.append(f'Из них {len(critical_no_bl)} на критическом пути — '
                       f'приоритет для фиксации baseline')
    for t in no_baseline[:3]:
        details.append(f'«{t["name"]}»')

    return {'title': 'Зоны неопределённости',
            'summary': summary,
            'items': details, 'count': len(no_baseline)}


def _rns_forecast(work_tasks):
    rns = _find_key_milestone(work_tasks, 'РНС')
    if not rns:
        return {'title': 'Прогноз даты РНС',
                'summary': 'Веха РНС не найдена в графике.',
                'items': []}

    rns_task = next((t for t in work_tasks.values() if t.get('name') == rns['name']), None)
    if not rns_task:
        return {'title': 'Прогноз даты РНС',
                'summary': 'Веха РНС не найдена.',
                'items': []}

    finish = _format_date(rns_task.get('finish'))
    bl_finish = _format_date(rns_task.get('baseline_finish'))
    deadline = _format_date(rns_task.get('deadline'))
    fv = rns_task.get('finish_variance', 0)

    summary_parts = [f'Прогнозная дата получения РНС — {finish}.']

    if fv > 0:
        summary_parts.append(f'Это на {abs(fv):.0f} дней позже базового плана ({bl_finish}).')
        if deadline and deadline != '—':
            summary_parts.append(f'Крайний срок — {deadline}. '
                                 f'Отклонение от крайнего срока требует компенсационных мероприятий.')
    elif fv < 0:
        summary_parts.append(f'Опережение базового плана на {abs(fv):.0f} дней.')
    else:
        summary_parts.append('Проект идёт в соответствии с базовым планом.')
        if deadline and deadline != '—':
            summary_parts.append(f'Крайний срок — {deadline}.')

    return {'title': 'Прогноз даты РНС',
            'summary': ' '.join(summary_parts),
            'items': []}


# ── Управленческие решения ──

def _block_decisions(result, mode):
    items = []
    blocks = result.get('mode_blocks', {})

    if mode == 'smr':
        decomp = blocks.get('3.1', {})
        if decomp.get('count', 0) > 0:
            items.append('Для сокращения отставания по критическим направлениям предлагается '
                         'увеличить ресурсное обеспечение и рассмотреть параллельное выполнение работ')

        ahead = blocks.get('3.5', {})
        if ahead.get('count', 0) > 0:
            items.append('За счёт опережения по ряду направлений можно перебросить ресурсы '
                         'на отстающие зоны')

        critical = blocks.get('3.3', {})
        if critical.get('count', 0) > 3:
            items.append(f'Выявлено {critical["count"]} критических задач с низким % завершения — '
                         f'необходим пристальный контроль и еженедельная отчётность по ним')
    else:
        rns_forecast = blocks.get('4.6', {})
        for item in rns_forecast.get('items', []):
            if 'позже' in item:
                items.append('Прогнозная дата РНС смещена — необходимо рассмотреть компенсационные мероприятия '
                             'и/или запросить корректировку обязательств')
                break

        mpt = blocks.get('4.4', {})
        for item in mpt.get('items', []):
            if 'РИСК' in item:
                items.append('Выявлены риски по обязательствам МПТ — необходимо запросить '
                             'план мероприятий по смягчению')
                break

        uncertainty = blocks.get('4.5', {})
        if uncertainty.get('count', 0) > 5:
            items.append(f'Обнаружено {uncertainty["count"]} задач без базового плана — '
                         f'необходимо зафиксировать baseline для корректного анализа отклонений')

    if not items:
        items.append('Значимых отклонений не выявлено, график в допустимых пределах')

    return {'title': 'Управленческие решения и предложения', 'items': items}


# ── Утилиты ──

def _get_zone(task):
    cf = task.get('custom_fields') or {}
    return cf.get('Корпус_зона') or cf.get('Корпус/зона') or cf.get('Корпус')


def _group_tasks(tasks_list):
    groups = defaultdict(list)
    for t in tasks_list:
        zone = _get_zone(t)
        if zone:
            groups[zone].append(t)
        else:
            name = t.get('name', '')
            for kw in ['Фасад', 'ВИС', 'Отделка', 'Монолит', 'Кровля',
                        'Фундамент', 'Инженер', 'Благоустр', 'ПСД', 'Проект']:
                if kw.lower() in name.lower():
                    groups[kw].append(t)
                    break
            else:
                groups['Прочие'].append(t)
    return dict(groups)


def _is_final_milestone(task, keyword):
    if not task.get('milestone'):
        return False
    name = (task.get('name') or '').upper()
    return keyword.upper() in name


def _trace_predecessors(task_id, relations, all_tasks, max_depth=5):
    chain = []
    visited = set()

    def _trace(tid, depth):
        if depth <= 0 or tid in visited:
            return
        visited.add(tid)
        for rel in relations:
            if rel['to'] == tid and rel['from'] in all_tasks:
                pred = all_tasks[rel['from']]
                if not pred.get('summary'):
                    chain.append(pred)
                    _trace(rel['from'], depth - 1)

    _trace(task_id, max_depth)
    chain.sort(key=lambda t: t.get('finish', ''))
    return chain


def _noun_form(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def _days_str(days):
    if days is None or days == 0:
        return 'в срок'
    if days > 0:
        return f'+{days:.0f} дн.'
    return f'{days:.0f} дн. (опережение)'


def _format_date(date_str):
    if not date_str:
        return '—'
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(str(date_str)[:19], fmt)
            return dt.strftime('%d.%m.%Y')
        except (ValueError, AttributeError):
            continue
    return str(date_str)[:10] if len(str(date_str)) >= 10 else str(date_str)
