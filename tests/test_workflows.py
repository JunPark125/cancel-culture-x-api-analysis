"""Offline behavioral tests using invented API responses and temporary files."""
import csv
import json
import os
import socket
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import requests

from src.api_collection import collect_x_posts_2022 as collector
from src.api_collection import backfill_x_posts_2022 as backfill
from src.api_collection import historical_counts as history
from src.analysis.historical_counts import aggregate_counts
from src.analysis import build_collected_monthly_counts as monthly
from src.analysis import build_monthly_gap_report as gaps
from src.analysis import quality_check as quality
from src.preprocessing import build_professor_submission as exports


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['socket.socket.connect', 'socket.socket.connect_ex', 'socket.create_connection']:
            guard = patch(name, side_effect=AssertionError('Network access prohibited in tests'))
            guard.start()
            self.addCleanup(guard.stop)
        self.posts = json.loads((Path(__file__).resolve().parents[1] /
                                 'data/sample/synthetic_posts.json').read_text())['data']

    def raw_row(self, post):
        return collector.tweet_to_raw_row(post, hashtag_type='cancel', query='#cancel -is:retweet lang:en',
                                         window_start='2022-01-01T00:00:00Z',
                                         window_end='2023-01-01T00:00:00Z')

    def test_month_windows_are_contiguous_and_clip_partial_months(self):
        windows = collector.monthly_windows('2022-01-17T00:00:00Z', '2023-01-01T00:00:00Z')
        self.assertEqual(len(windows), 12)
        self.assertEqual(windows[0][0], '2022-01-17T00:00:00Z')
        self.assertEqual(windows[-1][1], '2023-01-01T00:00:00Z')
        self.assertTrue(all(a[1] == b[0] for a, b in zip(windows, windows[1:])))

    def test_duplicate_suppression_survives_reload_and_uses_full_text(self):
        path = self.root / 'raw.csv'
        row = self.raw_row(self.posts[1])
        self.assertIn('full-length', row['post_text_full'])
        self.assertEqual(row['repost_count'], 0)
        self.assertEqual(collector.append_unique_raw_rows(path, [row, row], set()), 1)
        ids = collector.load_existing_post_ids(path)
        self.assertEqual(collector.append_unique_raw_rows(path, [row], ids), 0)
        with path.open() as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 1)

    def test_pagination_checkpoint_resume_and_completed_skip(self):
        path = self.root / 'raw.csv'
        cp = self.root / 'checkpoint.json'
        save = collector.save_checkpoint
        state = collector.default_checkpoint()
        kwargs = dict(session=Mock(), state=state, hashtag_type='cancel', query='#cancel',
                      raw_path=path, window_start='2022-01-01T00:00:00Z',
                      window_end='2022-02-01T00:00:00Z', max_results=500,
                      existing_post_ids=set(), expected_count=0, quiet=True)
        with patch.object(collector, 'save_checkpoint', side_effect=lambda s: save(s, cp)), \
             patch.object(collector, 'write_collection_log'), \
             patch.object(collector, 'get_json_with_retries', side_effect=[
                 {'data': [self.posts[0]], 'meta': {'next_token': 'synthetic-page-two'}},
                 collector.ApiRequestError('synthetic interruption')]):
            with self.assertRaises(collector.ApiRequestError):
                collector.collect_month_window(**kwargs)
        self.assertEqual(collector.load_checkpoint(cp)['hashtags']['cancel']['2022-01']['next_token'],
                         'synthetic-page-two')
        kwargs['state'] = collector.load_checkpoint(cp)
        kwargs['existing_post_ids'] = collector.load_existing_post_ids(path)
        with patch.object(collector, 'save_checkpoint', side_effect=lambda s: save(s, cp)), \
             patch.object(collector, 'write_collection_log'), \
             patch.object(collector, 'get_json_with_retries', return_value={
                 'data': [self.posts[0], self.posts[1]], 'meta': {}}) as get:
            collector.collect_month_window(**kwargs)
            self.assertEqual(get.call_args.args[1]['next_token'], 'synthetic-page-two')
            collector.collect_month_window(**kwargs)
            self.assertEqual(get.call_count, 1)
        self.assertEqual(len(collector.load_existing_post_ids(path)), 2)
        self.assertEqual(collector.load_checkpoint(cp)['hashtags']['cancel']['2022-01']['status'], 'completed')
        self.assertFalse(cp.with_suffix('.tmp').exists())

    def test_retry_wait_and_success(self):
        response = Mock(status_code=429, headers={'retry-after': '2'}, reason='synthetic rate limit', text='')
        success = Mock(status_code=200)
        success.json.return_value = {'data': []}
        session = Mock()
        session.get.side_effect = [response, success]
        with patch.object(collector, 'write_failed_request'), patch.object(collector, 'write_collection_log'), \
             patch.object(collector.time, 'sleep') as sleep:
            self.assertEqual(collector.get_json_with_retries(session, {}, {}), {'data': []})
            sleep.assert_called_once_with(12)
        self.assertEqual(session.get.call_count, 2)

    def test_transport_retries_are_bounded(self):
        session = Mock()
        session.get.side_effect = requests.Timeout('synthetic timeout')
        with patch.object(collector, 'write_failed_request'), patch.object(collector, 'write_collection_log'), \
             patch.object(collector.time, 'sleep'):
            with self.assertRaises(collector.ApiRequestError):
                collector.get_json_with_retries(session, {}, {})
        self.assertEqual(session.get.call_count, collector.MAX_RETRIES)

    def test_permanent_http_failure_and_invalid_json_do_not_retry(self):
        for status, error in [(401, None), (200, ValueError('synthetic invalid JSON'))]:
            with self.subTest(status=status):
                response = Mock(status_code=status, reason='synthetic', text='synthetic')
                if error:
                    response.json.side_effect = error
                session = Mock()
                session.get.return_value = response
                with patch.object(collector, 'write_failed_request'):
                    with self.assertRaises(collector.ApiRequestError):
                        collector.get_json_with_retries(session, {}, {})
                session.get.assert_called_once()

    def test_rate_limit_selects_later_header(self):
        response = Mock(headers={'retry-after': '2', 'x-rate-limit-reset': '1010'})
        with patch.object(collector.time, 'time', return_value=1000):
            self.assertEqual(collector.rate_limit_wait_seconds(response), 20)

    def test_backfill_subdivision_and_underfill(self):
        windows = backfill.windows_for_month('2022-01', 'auto', selected_days={date(2022, 1, 5)},
                                              daily_counts_by_day={'2022-01-05': 401})
        self.assertEqual(len(windows), 24)
        self.assertEqual(windows[0][0], '2022-01-05T00:00:00Z')
        self.assertEqual(windows[-1][1], '2022-01-06T00:00:00Z')
        self.assertTrue(backfill.is_underfilled(79, 100, .8))
        self.assertFalse(backfill.is_underfilled(80, 100, .8))
        self.assertIsNone(backfill.expected_count_for_window(*windows[0], {'2022-01-05': 401}))
        self.assertNotEqual(backfill.checkpoint_key('cancel', '2022-01', 'start', 'end1'),
                            backfill.checkpoint_key('cancel', '2022-01', 'start', 'end2'))

    def test_backfill_records_underfilled_window(self):
        state = backfill.default_checkpoint()
        with patch.object(backfill, 'save_checkpoint'), patch.object(backfill, 'write_backfill_log'), \
             patch.object(backfill, 'get_json_with_retries', return_value={'data': [self.posts[0]], 'meta': {}}):
            backfill.backfill_window(session=Mock(), state=state, hashtag_type='cancel', query='#cancel',
                target_month='2022-01', window_start='2022-01-05T00:00:00Z', window_end='2022-01-06T00:00:00Z',
                raw_path=self.root/'raw.csv', existing_post_ids=set(), max_results=500,
                expected_total=10, expected_window_count=10, min_completion_ratio=.8,
                request_clock={}, request_interval_seconds=0, quiet=True, ignore_checkpoint=False)
        entry = next(iter(state['targets'].values()))
        self.assertEqual(entry['status'], 'underfilled')
        self.assertEqual(entry['rows_written'], 1)

    def test_counts_pagination_and_aggregation_preserve_totals(self):
        first = Mock(status_code=200)
        first.json.return_value = {'data': [{'start': '2022-01-01T00:00:00Z',
            'end': '2022-01-02T00:00:00Z', 'tweet_count': 2}], 'meta': {'next_token': 'synthetic-next'}}
        second = Mock(status_code=200)
        second.json.return_value = {'data': [{'start': '2022-02-01T00:00:00Z',
            'end': '2022-02-02T00:00:00Z', 'tweet_count': 3}], 'meta': {}}
        with patch.object(history.requests, 'get', side_effect=[first, second]) as get, \
             patch.object(history.time, 'sleep'):
            frame, pages = history.fetch_counts_all('#cancel', '2022-01-01T00:00:00Z',
                                                     '2023-01-01T00:00:00Z', 'synthetic-credential')
        self.assertEqual(get.call_args.kwargs['params']['next_token'], 'synthetic-next')
        daily, monthly_table, yearly = aggregate_counts(frame)
        self.assertEqual(pages, 2)
        self.assertEqual(daily.tweet_count.sum(), 5)
        self.assertEqual(monthly_table.monthly_count.tolist(), [2, 3])
        self.assertEqual(yearly.yearly_count.tolist(), [5])

    def test_processing_quality_gaps_and_exports(self):
        raw = self.root/'raw.csv'
        rows = [self.raw_row(post) for post in self.posts]
        rows += [rows[0].copy(), dict(rows[0], post_id='synthetic-outside', created_at='2023-01-01T00:00:00Z'),
                 dict(rows[0], post_id='synthetic-invalid', created_at='not-a-date', author_id='')]
        with raw.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=collector.RAW_MASTER_COLUMNS)
            writer.writeheader(); writer.writerows(rows)
        config = {'cancel': {'raw_master_path': raw, 'professor_submission_path': self.root/'export.csv',
                             'expected_count': 10}}
        with patch.object(monthly, 'HASHTAG_CONFIG', config), patch.object(monthly, 'REPORTS_DIR', self.root), \
             patch.object(quality, 'HASHTAG_CONFIG', config), patch.object(exports, 'HASHTAG_CONFIG', config):
            path = monthly.build_collected_monthly_counts('cancel')
            counts = pd.read_csv(path)
            # The original CLI emits observed months; the notebook fills all 12.
            self.assertEqual(len(counts), 2)
            self.assertEqual(counts.collected_rows.sum(), 4)
            self.assertEqual(counts.unique_post_count.sum(), 3)
            report = quality.quality_row('cancel')
            self.assertEqual(report['duplicate_post_ids'], 1)
            self.assertEqual(report['rows_outside_2022'], 1)
            self.assertEqual(report['missing_created_at'], 1)
            self.assertEqual(report['missing_author_id'], 1)
            with self.assertRaises(ValueError):
                exports.build_professor_submission('cancel')
            pd.DataFrame(rows[:3][::-1]).to_csv(raw, index=False)
            output = exports.build_professor_submission('cancel')
            simplified = pd.read_csv(output)
            self.assertEqual(simplified.timestamp.tolist(), ['2022-01-05', '2022-01-06', '2022-02-01'])
            self.assertIn('full-length', simplified.post_text.iloc[1])
        expected = self.root/'baseline.csv'
        expected.write_text('month,monthly_count\n2022-01,5\n2022-02,1\n')
        with patch.object(gaps, 'INPUTS', {'cancel': {'expected_path': expected, 'collected_path': path}}):
            gap_rows = gaps.build_rows()
        self.assertEqual(gap_rows[0]['missing_count'], 3)
        self.assertEqual(gap_rows[1]['missing_count'], 0)
        self.assertEqual(gaps.classify_gap(-1, 1.1)[0], 'over_collected')

    def test_live_guards_and_backfill_dry_run(self):
        with patch('sys.argv', ['collector']), patch.object(collector, 'create_session') as create:
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                collector.main()
            create.assert_not_called()
        with patch('sys.argv', ['counts', '--hashtag', 'cancel']), patch.object(history.requests, 'get') as get:
            with self.assertRaises(SystemExit):
                history.main()
            get.assert_not_called()
        gap = self.root/'gap.csv'
        gap.write_text('hashtag_type,month,expected_count,collected_unique_posts,missing_count,collection_rate\n'
                       'cancel,2022-01,2000,0,2000,0\n')
        with patch('sys.argv', ['backfill', '--dry-run', '--gap-report', str(gap)]), \
             patch.object(backfill, 'create_session') as create, patch.object(backfill, 'load_local_token_files') as token:
            self.assertEqual(backfill.main(), 0)
            create.assert_not_called()
            token.assert_not_called()

    def test_plot_retains_outer_join_zero_fill_behavior(self):
        with patch.dict(os.environ, {'MPLCONFIGDIR': str(self.root/'matplotlib')}):
            import matplotlib
            matplotlib.use('Agg')
            from src.visualization.monthly_trends import plot_monthly_trends
            import matplotlib.pyplot as plt
            figure = plot_monthly_trends(
                pd.DataFrame({'month': ['2022-02'], 'monthly_count': [3]}),
                pd.DataFrame({'month': ['2022-01'], 'monthly_count': [2]}),
                'SYNTHETIC test only (2022-01 to 2022-02)')
            self.assertEqual(figure.axes[0].lines[0].get_ydata().tolist(), [0, 3])
            self.assertEqual(figure.axes[0].lines[1].get_ydata().tolist(), [2, 0])
            figure.savefig(self.root/'synthetic.png')
            self.assertGreater((self.root/'synthetic.png').stat().st_size, 0)
            plt.close(figure)


if __name__ == '__main__':
    unittest.main()
