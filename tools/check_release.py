"""Verify the exact staged release paths, text, and approved figure."""
import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE_AUDIT = 'data/summary/2022_collection_file_audit.csv'
TREND_FIGURE = 'results/figures/monthly_hashtag_trends_2015_2025.png'
TREND_FIGURE_SHA256 = '3767b9a47a43b58465847f31539fa7bcebf538df7c9fa9b604e497549d3d18ae'
TREND_COUNTS = {
    'data/historical/x_boycott_monthly_counts_2015_2025.csv',
    'data/historical/x_cancel_monthly_counts_2015_2025.csv',
}
AUDIT_HEADER = [
    'collection', 'stored_rows', 'distinct_post_ids', 'duplicate_id_rows',
    'missing_id_rows', 'invalid_timestamp_rows', 'outside_2022_utc_rows',
]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    expected = set(git('show', ':RELEASE_FILES.txt').decode().splitlines())
    tracked = set(git('ls-files', '-z').decode().split('\0')) - {''}
    if tracked != expected:
        raise SystemExit(f'Allowlist mismatch: extra={sorted(tracked-expected)} missing={sorted(expected-tracked)}')
    patterns = [
        re.compile(r'(?i)(?:gh[pousr]_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{16,}'),
        re.compile(r'AAAAA[A-Za-z0-9%_\-]{30,}'),
        re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        re.compile(r'\b[0-9]{17,20}\b'),
        re.compile(r'https?://(?:www\.)?(?:x|twitter)\.com/[^\s/]+/status/\d+'),
    ]
    problems = []
    for name in sorted(tracked):
        blob = git('show', ':'+name)
        if name == TREND_FIGURE:
            if hashlib.sha256(blob).hexdigest() != TREND_FIGURE_SHA256:
                problems.append((name, 'figure fingerprint differs from the reviewed original'))
            continue
        try:
            text = blob.decode('utf-8-sig')
        except UnicodeDecodeError:
            problems.append((name, 'unexpected binary'))
            continue
        if any(pattern.search(text) for pattern in patterns):
            problems.append((name, 'credential/identifier pattern; inspect locally'))
        if name.endswith('.ipynb'):
            book = json.loads(text)
            if any(c.get('outputs') or c.get('execution_count') is not None for c in book['cells']):
                problems.append((name, 'notebook output/execution state present'))
        if name == FILE_AUDIT:
            rows = list(csv.reader(io.StringIO(text)))
            if (len(rows) != 3 or rows[0] != AUDIT_HEADER
                    or [row[:1] for row in rows[1:]] != [['cancel'], ['boycott']]
                    or any(len(row) != len(AUDIT_HEADER)
                           or any(not re.fullmatch(r'[0-9]{1,8}', value) for value in row[1:])
                           for row in rows[1:])):
                problems.append((name, 'expected two file-audit rows with numeric counters only'))
        elif name in TREND_COUNTS:
            rows = list(csv.reader(io.StringIO(text)))
            months = [f'{year}-{month:02d}' for year in range(2015, 2026) for month in range(1, 13)]
            if (len(rows) != 133 or rows[0] != ['month', 'monthly_count']
                    or any(len(row) != 2 or row[0] != month
                           or not re.fullmatch(r'[0-9]{1,8}', row[1])
                           for month, row in zip(months, rows[1:]))):
                problems.append((name, 'expected 132 consecutive months and aggregate counts only'))
        elif name.endswith(('.csv', '.env', '.docx', '.png', '.log', '.parquet')):
            problems.append((name, 'prohibited artifact type'))
    if problems:
        raise SystemExit(str(problems))
    print(f'PASS: {len(tracked)} staged paths match the allowlist; text and asset checks passed.')
    print('Review the staged diff and ownership permission separately before any private upload.')


if __name__ == '__main__':
    main()
