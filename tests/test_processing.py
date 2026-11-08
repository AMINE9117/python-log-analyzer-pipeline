import logging
import unittest

from processing import extract_transform as et

# Pas d'écriture dans logs/ pendant les tests
logging.disable(logging.CRITICAL)

HEADER = 'May 24 01:14:12 ns sshd[1351821]: '


class TestProcessing(unittest.TestCase):

    def test_accepted(self):
        e = et.extract(HEADER + 'Accepted password for adminesisa from 10.10.33.81 port 59176 ssh2')
        self.assertEqual(e['event_type'], 'accepted')
        self.assertEqual(e['status'], 'success')
        self.assertEqual(e['user'], 'adminesisa')
        self.assertEqual(e['ip'], '10.10.33.81')
        self.assertFalse(e['invalid_user'])

    def test_failed_existing_user(self):
        e = et.extract(HEADER + 'Failed password for root from 45.148.10.147 port 8868 ssh2')
        self.assertEqual(e['event_type'], 'failed')
        self.assertEqual(e['status'], 'failure')
        self.assertEqual(e['user'], 'root')
        self.assertEqual(e['reason'], 'wrong password')
        self.assertFalse(e['invalid_user'])

    def test_failed_invalid_user(self):
        e = et.extract(HEADER + 'Failed password for invalid user admin from 1.2.3.4 port 22 ssh2')
        self.assertEqual(e['event_type'], 'failed_invalid_user')
        self.assertEqual(e['user'], 'admin')
        self.assertEqual(e['ip'], '1.2.3.4')
        self.assertTrue(e['invalid_user'])
        self.assertEqual(e['reason'], 'invalid user')

    def test_failed_invalid_empty_user(self):
        e = et.extract(HEADER + 'Failed none for invalid user  from 193.46.255.86 port 50721 ssh2')
        self.assertEqual(e['event_type'], 'failed_invalid_user')
        self.assertEqual(e['user'], '')
        self.assertEqual(e['ip'], '193.46.255.86')

    def test_invalid_user_announce_is_not_a_failure(self):
        # La ligne "Invalid user" annonce la tentative : elle ne doit pas être comptée en double
        e = et.extract(HEADER + 'Invalid user test from 1.2.3.4 port 22')
        self.assertEqual(e['event_type'], 'invalid_user')
        self.assertEqual(e['status'], '')

    def test_message_repeated(self):
        e = et.extract(HEADER + 'message repeated 4 times: [ Failed password for root from 1.2.3.4 port 1 ssh2]')
        self.assertEqual(e['event_type'], 'failed')
        self.assertEqual(e['count'], 4)

    def test_other_event_with_ip(self):
        e = et.extract(HEADER + 'Connection closed by 127.0.0.1 port 40940 [preauth]')
        self.assertEqual(e['event_type'], 'other')
        self.assertEqual(e['ip'], '127.0.0.1')

    def test_single_digit_day(self):
        e = et.extract('May  3 00:01:21 ns sshd[975159]: Invalid user x from 1.2.3.4 port 22')
        self.assertEqual(e['day'], '3')

    def test_invalid_line_does_not_crash(self):
        events = et.transform(['garbage', '', HEADER + 'Failed password for root from 1.2.3.4 port 1 ssh2'])
        self.assertEqual([e['event_type'] for e in events], ['unparsed', 'unparsed', 'failed'])


if __name__ == '__main__':
    unittest.main()
