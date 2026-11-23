import unittest
from nexus_repacks.downloads import clean_line, parse_progress


class ProgressTests(unittest.TestCase):
    def test_torrent_readout(self):
        p=parse_progress('[#46f934 12MiB/72GiB(0%) CN:6 SD:1 DL:2.4MiB ETA:8h27m33s]')
        self.assertAlmostEqual(p['ratio'],12/(72*1024))
        self.assertEqual((p['connections'],p['seeders'],p['speed'],p['eta']),('6','1','2.4MiB','8h27m33s'))

    def test_precise_progress_is_not_rounded_to_integer_percent(self):
        self.assertAlmostEqual(parse_progress('[#abc123 512KiB/1MiB(50%) CN:1 DL:1MiB ETA:1s]')['ratio'],.5)

    def test_metadata_with_unknown_total_has_no_invented_percentage(self):
        p=parse_progress('[#abc123 0B/0B(0%) CN:0 SD:0 DL:0B]')
        self.assertIsNone(p['ratio'])
        self.assertEqual(p['eta'],'—')

    def test_ansi_and_nonprogress_messages(self):
        self.assertEqual(clean_line('\x1b[1;32mNOTICE\x1b[0m'),'NOTICE')
        self.assertEqual(parse_progress('Downloading 1 item(s)'),{})

    def test_file_location_is_preserved(self):
        self.assertEqual(parse_progress('FILE: C:/Games/example.zip'),{'file':'C:/Games/example.zip'})
