"""Check exact staged paths and inspect staged text; does not stage or upload."""
import csv
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE_AUDIT = 'data/summary/2022_collection_file_audit.csv'
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
        try:
            text = blob.decode('utf-8')
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
        elif name.endswith(('.csv', '.env', '.docx', '.png', '.log', '.parquet')):
            problems.append((name, 'prohibited artifact type'))
    if problems:
        raise SystemExit(str(problems))
    print(f'PASS: {len(tracked)} staged paths match the explicit allowlist; text checks passed.')
    print('Review the staged diff and ownership permission separately before any private upload.')


if __name__ == '__main__':
    main()
