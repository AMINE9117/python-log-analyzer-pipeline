import logging
import os
import tempfile
import unittest

import matplotlib
matplotlib.use('Agg')  # pas de fenêtre pendant les tests

from processing import extract_transform as et
from serving import dashboard
from serving import statistics
from storage import store

# Pas d'écriture dans logs/ pendant les tests
logging.disable(logging.CRITICAL)

HEADER = 'May 24 01:14:12 ns sshd[1]: '
ROWS = [
    HEADER + 'Accepted password for alice from 10.0.0.1 port 1 ssh2',
    HEADER + 'Accepted password for alice from 10.0.0.1 port 1 ssh2',
    HEADER + 'Accepted password for bob from 10.0.0.2 port 1 ssh2',
    HEADER + 'Failed password for root from 1.1.1.1 port 1 ssh2',
    HEADER + 'message repeated 3 times: [ Failed password for root from 1.1.1.1 port 1 ssh2]',
    HEADER + 'Invalid user admin from 2.2.2.2 port 1',
    HEADER + 'Failed password for invalid user admin from 2.2.2.2 port 1 ssh2',
    HEADER + 'Connection closed by 3.3.3.3 port 1 [preauth]',
]


def sample_events():
    events = et.transform(ROWS)
    for event in events:
        if event['status'] == 'failure':
            event['country'] = {'1.1.1.1': 'AU', '2.2.2.2': ''}[event['ip']]
    return events


class TestStatistics(unittest.TestCase):

    def test_statistics(self):
        stats = statistics.compute_statistics(sample_events())
        self.assertEqual(stats['total_lines'], 8)
        self.assertEqual(stats['successful_logins'], 3)
        self.assertEqual(stats['successes_by_user'], [('alice', 2), ('bob', 1)])
        self.assertEqual(stats['failed_logins'], 5)  # 1 + 3 (repeated) + 1 (invalid)
        self.assertEqual(stats['failures_by_country'], [('AU', 4), ('Unknown', 1)])
        self.assertEqual(stats['invalid_user_attempts'], 1)  # "Invalid user" non compté en double
        self.assertEqual(stats['invalid_users'], [('admin', 1)])
        self.assertEqual(stats['distinct_ips'], 5)


class TestStorage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events_file = os.path.join(self.tmp.name, 'events.csv')
        self.state_file = os.path.join(self.tmp.name, 'state.json')
        self.data_dir = os.path.join(self.tmp.name, 'data')
        os.makedirs(self.data_dir)
        with open(os.path.join(self.data_dir, 'auth.log'), 'w') as f:
            f.write('x\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_load_events(self):
        events = sample_events()
        self.assertTrue(store.save_events(events, et.EVENT_FIELDS, self.data_dir,
                                          self.events_file, self.state_file))
        loaded = store.load_events(self.events_file)
        self.assertEqual(len(loaded), len(events))
        self.assertEqual(loaded[4]['count'], 3)
        self.assertTrue(loaded[6]['invalid_user'])
        # mêmes statistiques avant et après la sauvegarde
        self.assertEqual(statistics.compute_statistics(loaded), statistics.compute_statistics(events))

    def test_up_to_date(self):
        self.assertFalse(store.is_up_to_date(self.data_dir, self.state_file, self.events_file))
        store.save_events(sample_events(), et.EVENT_FIELDS, self.data_dir, self.events_file, self.state_file)
        self.assertTrue(store.is_up_to_date(self.data_dir, self.state_file, self.events_file))
        with open(os.path.join(self.data_dir, 'auth.log.1'), 'w') as f:
            f.write('new file\n')
        self.assertFalse(store.is_up_to_date(self.data_dir, self.state_file, self.events_file))

    def test_corrupted_json(self):
        path = os.path.join(self.tmp.name, 'bad.json')
        with open(path, 'w') as f:
            f.write('{not json')
        self.assertEqual(store.load_json(path, {}), {})

    def test_dashboard_file_created(self):
        output = os.path.join(self.tmp.name, 'dashboard.png')
        stats = statistics.compute_statistics(sample_events())
        self.assertEqual(dashboard.build_dashboard(stats, output, show=False), output)
        self.assertTrue(os.path.getsize(output) > 0)


if __name__ == '__main__':
    unittest.main()
