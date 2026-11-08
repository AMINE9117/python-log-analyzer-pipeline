import logging
import gzip
import os
import tempfile
import unittest

from ingestion import read

# Pas d'écriture dans logs/ pendant les tests
logging.disable(logging.CRITICAL)

"""
Tests du module ingestion.
Lancer depuis la racine du projet : python -m unittest discover -s tests -v
"""


class TestIngestion(unittest.TestCase):
    # unittest impose une classe de test : c'est la seule classe du projet,
    # elle sert uniquement à regrouper les tests (pas de POO dans l'application).

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def test_read_normal_file(self):
        path = self.write('auth.log.1', 'line 1\nline 2\n')
        self.assertEqual(read.read_file(path), ['line 1', 'line 2'])

    def test_read_gz_file(self):
        path = os.path.join(self.dir, 'auth.log.2.gz')
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            f.write('gz line 1\ngz line 2\n')
        self.assertEqual(read.read_file(path), ['gz line 1', 'gz line 2'])

    def test_corrupted_gz_returns_empty_list(self):
        path = self.write('broken.log.gz', 'this is not gzip data')
        self.assertEqual(read.read_file(path), [])

    def test_empty_file(self):
        path = self.write('empty.log', '')
        self.assertEqual(read.read_file(path), [])

    def test_missing_file(self):
        self.assertEqual(read.read_file(os.path.join(self.dir, 'nope.log')), [])

    def test_missing_directory(self):
        self.assertEqual(read.ingest(os.path.join(self.dir, 'nope')), [])

    def test_ingest_reads_all_files(self):
        self.write('auth.log', 'a\n')
        self.write('auth.log.1', 'b\nc\n')
        with gzip.open(os.path.join(self.dir, 'auth.log.2.gz'), 'wt', encoding='utf-8') as f:
            f.write('d\n')
        self.write('notes.md', 'ignored\n')  # pas un fichier de logs
        rows = read.ingest(self.dir)
        self.assertEqual(sorted(rows), ['a', 'b', 'c', 'd'])

    def test_ingest_skips_corrupted_file(self):
        self.write('auth.log', 'ok\n')
        self.write('bad.log.gz', 'not gzip')
        self.assertEqual(read.ingest(self.dir), ['ok'])


if __name__ == '__main__':
    unittest.main()
