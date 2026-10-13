import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from counters import parse_counter
import report


def result(editor):
    trial = dict(valid=True, instructions=100, launchToWindowSeconds=.1,
                 launchToCutoffSeconds=.11, source='perf cgroup', readiness={'windowId': '1'},
                 cutoffAcknowledged=True, rawCounter='100;;instructions;startup-test;1234;100.00;;\n')
    return dict(editor=editor, protocol={'version': 1}, host={'machine': 'aarch64'},
                trials=[dict(trial, repeat=i+1) for i in range(3)])


class MetricsTest(unittest.TestCase):
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
