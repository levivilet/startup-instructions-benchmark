import copy
import hashlib
import json
import os
from unittest.mock import Mock, patch
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from counters import Capture, parse_counter
from install import checksum, extract
import report
import benchmark
import switch_experiment
from benchmark import is_main_window


def result(editor):
    trial = dict(valid=True, instructions=100, launchToWindowSeconds=.1,
                 launchToCutoffSeconds=.11, source='perf cgroup', readiness={'windowId': '1'},
                 cutoffAcknowledged=True, rawCounter='100;;instructions;startup-test;1234;100.00;;\n')
    return dict(editor=editor, protocol={'version': 1}, host={'machine': 'aarch64'},
                trials=[dict(trial, repeat=i+1) for i in range(3)])


class MetricsTest(unittest.TestCase):
    def test_installer_supports_sha512_and_nested_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'idea.sh'
            source.write_text('#!/bin/sh\n')
            archive = root / 'idea.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(source, arcname='idea-IU/bin/idea.sh')
            self.assertEqual(checksum(archive, 'sha512'), hashlib.sha512(archive.read_bytes()).hexdigest())
            destination = root / 'extracted'
            extract({'id': 'intellij', 'binary': 'bin/idea.sh', 'binaryGlob': 'idea-*/bin/idea.sh'},
                    archive, destination)
            self.assertTrue((destination / 'idea-IU/bin/idea.sh').stat().st_mode & 0o111)

    def test_added_editor_launchers_use_isolated_profiles(self):
        home = Path('/tmp/startup-profile')
        entries = {entry['id']: entry for entry in report.EDITORS}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            intellij_binary = root / '.tmp/apps/intellij/idea-IU-253.28294.334/bin/idea.sh'
            intellij_binary.parent.mkdir(parents=True)
            intellij_binary.touch()
            with patch.object(benchmark, 'ROOT', root):
                intellij = benchmark.command_for(entries['intellij'], home)
                self.assertEqual(intellij[0], str(intellij_binary))
                self.assertIn(f'-Didea.config.path={home / "config" / "intellij"}', intellij)
                self.assertIn('dontReopenProjects', intellij)

                eclipse = benchmark.command_for(entries['eclipse'], home)
                self.assertEqual(eclipse[0], str(root / '.tmp/apps/eclipse/eclipse/eclipse'))
                self.assertIn(str(home / 'workspace'), eclipse)
                self.assertIn(str(home / 'config' / 'eclipse'), eclipse)

                cursor = benchmark.command_for(entries['cursor'], home)
                self.assertEqual(cursor[0], str(root / '.tmp/apps/cursor/usr/share/cursor/cursor'))
                self.assertIn(str(home / 'profile'), cursor)
                self.assertIn(str(home / 'extensions'), cursor)

    def test_electron_switch_sets_are_applied_before_app_argument(self):
        home = Path('/tmp/startup-profile')
        editor = next(entry for entry in report.EDITORS if entry['id'] == 'basic-electron')
        switches = benchmark.ELECTRON_SWITCH_SETS['disable-http-cache+disable-http2']
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(benchmark, 'ROOT', Path(directory)):
                command = benchmark.command_for(editor, home, switches)
        app_argument = command.index(str(Path(directory) / 'basic-electron'))
        self.assertEqual(command[command.index('--disable-gpu') + 2:app_argument], switches)
        self.assertEqual(benchmark.ELECTRON_SWITCH_SETS['baseline'], [])

    def test_switch_experiment_order_is_repeatable_and_covers_each_configuration(self):
        first = switch_experiment.execution_order()
        self.assertEqual(first, switch_experiment.execution_order())
        self.assertEqual(len(first), switch_experiment.ROUNDS)
        for switch_sets in first:
            self.assertEqual(set(switch_sets), set(switch_experiment.SWITCH_SETS))

    def test_main_window_type_defaults_and_rejections(self):
        mapped = 'WM_STATE(WM_STATE):\n    window state: Normal\n'
        missing = '_NET_WM_WINDOW_TYPE:  not found.\nWM_TRANSIENT_FOR:  not found.\n'
        self.assertTrue(is_main_window(mapped + missing))
        self.assertTrue(is_main_window(mapped + '_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_NORMAL'))
        self.assertFalse(is_main_window(missing))
        self.assertFalse(is_main_window(mapped + '_NET_WM_WINDOW_TYPE: not found.\nWM_TRANSIENT_FOR(WINDOW): window id # 0x123'))
        for kind in ['SPLASH', 'DIALOG', 'UTILITY', 'MENU']:
            self.assertFalse(is_main_window(mapped + f'_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_{kind}'))

    def test_control_acknowledgement_formats(self):
        for ack in [b'ack\n', b'ack\n\x00', b'wrong\n']:
            control_read, control_write = os.pipe()
            ack_read, ack_write = os.pipe()
            try:
                os.write(ack_write, ack)
                capture = Capture('unused', '.')
                capture.fds = [control_write, ack_read]
                capture.process = Mock()
                capture.process.poll.return_value = None
                if ack.startswith(b'ack'):
                    capture.control('disable')
                else:
                    with self.assertRaises(RuntimeError):
                        capture.control('disable')
                self.assertEqual(os.read(control_read, 256), b'disable\n')
            finally:
                for fd in [control_read, control_write, ack_read, ack_write]:
                    os.close(fd)

    def test_counter_rejects_unsupported_zero_and_multiplexing(self):
        self.assertEqual(parse_counter('123;;instructions;group;100;100.00;;'), 123)
        for count, running in [('<not supported>', '100'), ('0', '100'), ('123', '50'), ('123', 'nan')]:
            with self.assertRaises(ValueError):
                parse_counter(f'{count};;instructions;group;100;{running};;')
        with self.assertRaises(ValueError):
            parse_counter('123;;instructions;group;100;100;;\n123;;instructions;group;100;100;;')

    def test_cutoff_and_raw_evidence(self):
        editor = report.EDITORS[0]
        data = result(editor)
        report.validate_result(data, editor['id'])
        for changes in [dict(cutoffAcknowledged=False), dict(launchToCutoffSeconds=.01),
                        dict(instructions=101), dict(valid=False), dict(readiness=None)]:
            broken = copy.deepcopy(data)
            broken['trials'][0].update(changes)
            with self.assertRaises(ValueError):
                report.validate_result(broken, editor['id'])
        data['trials'].pop()
        with self.assertRaises(ValueError):
            report.validate_result(data, editor['id'])

    def test_missing_and_wrong_version_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                report.load_results(root)
            for editor in report.EDITORS:
                path = root / ('startup-' + editor['id'])
                path.mkdir()
                (path / 'results.json').write_text(json.dumps(result(editor)))
            self.assertEqual(len(report.load_results(root)), len(report.EDITORS))
            path = root / ('startup-' + report.EDITORS[0]['id']) / 'results.json'
            broken = result(dict(report.EDITORS[0], version='wrong'))
            path.write_text(json.dumps(broken))
            with self.assertRaises(ValueError):
                report.load_results(root)

    def test_chart_and_report_order_and_median(self):
        items = []
        for editor, counts in [(report.EDITORS[0], [100, 300, 200]), (report.EDITORS[1], [50, 40, 60])]:
            data = result(editor)
            for trial, count in zip(data['trials'], counts):
                trial['instructions'] = count
                trial['rawCounter'] = f'{count};;instructions;group;100;100;;'
            items.append(dict(editor=editor, data=data))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report.build_report(items, root, 'https://example.test/run', 'commit')
            payload = json.loads((root / 'report.json').read_text())
            self.assertEqual([e['medianInstructions'] for e in payload['editors']], [50, 200])
            chart = report.build_median_chart(payload['editors'])
            self.assertLess(chart.index('VS Code'), chart.index('LVCE Editor'))
            raw = json.loads((root / 'raw/lvce.json').read_text())
            self.assertEqual(raw, items[0]['data'])
