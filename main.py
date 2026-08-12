"""
Точка входа: чтение .mpp → анализ → HTML-отчёт.

Использование:
    python main.py "график.mpp" --mode smr
    python main.py "график.mpp" --mode rns -o отчёт.html
    python main.py "график.mpp" --mode smr --name "Проект X" --date "01.08.2026"
"""

import argparse
import os
import sys
from datetime import datetime

from read_mpp import read_mpp, shutdown
from analyzer import analyze
from report import generate_html


def main():
    parser = argparse.ArgumentParser(description='Тезисы — генерация отчёта из .mpp')
    parser.add_argument('mpp_file', help='Путь к файлу MS Project (.mpp)')
    parser.add_argument('--mode', '-m', required=True, choices=['smr', 'rns'],
                        help='Режим: smr (СМР) или rns (до РНС)')
    parser.add_argument('--output', '-o', help='Путь к выходному HTML-файлу')
    parser.add_argument('--name', '-n', help='Название проекта (по умолчанию — из .mpp)')
    parser.add_argument('--date', '-d', help='Дата актуализации (дд.мм.гггг, по умолчанию — из .mpp)')

    args = parser.parse_args()

    if not os.path.exists(args.mpp_file):
        print(f'Ошибка: файл не найден: {args.mpp_file}')
        sys.exit(1)

    if not args.output:
        base = os.path.splitext(os.path.basename(args.mpp_file))[0]
        date_str = datetime.now().strftime('%Y%m%d')
        args.output = f'{date_str}_Тезисы_{base}_{args.mode.upper()}.html'

    print(f'Чтение {args.mpp_file}...')
    mpp_data = read_mpp(args.mpp_file)
    print(f'  Задач: {mpp_data["stats"]["total_tasks"]}, '
          f'критических: {mpp_data["stats"]["critical_tasks"]}')

    print(f'Анализ (режим {args.mode.upper()})...')
    analysis = analyze(mpp_data, args.mode,
                       project_name=args.name,
                       report_date=args.date)

    print(f'Генерация отчёта...')
    output_path = generate_html(analysis, args.output)
    print(f'Готово: {output_path}')

    shutdown()


if __name__ == '__main__':
    main()
