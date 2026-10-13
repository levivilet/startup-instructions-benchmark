"""Measure instructions from fresh-profile launch to first mapped main window."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
from counters import Capture

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = {
    'version': 1, 'metric': 'retired hardware instructions (user and kernel)',
    'boundary': 'launch through first visible normal main window',
    'accounting': 'per-CPU cgroup; includes all descendants, including detached and exited tasks',
    'profile': 'fresh HOME and XDG directories every trial, no bootstrap launch',
    'cache': 'warm OS filesystem caches permitted; application profiles always fresh',
    'pollSeconds': .02, 'timeoutSeconds': 120,
    'launcher': 'includes child cgroup-entry and exec overhead; controller and desktop excluded',
    'cutoff': 'perf disable acknowledgement before shutdown; includes polling/control latency',
}


def command_for(editor, home):
    binary = str(ROOT / '.tmp/apps' / editor['id'] / editor['binary'])
    id = editor['id']
    if id == 'geany':
        return ['geany', '--new-instance']
    args = []
    if id in {'lvce', 'vscode', 'basic-electron'}:
        args += ['--no-sandbox', '--disable-gpu', '--ozone-platform=x11']
    if id in {'lvce', 'vscode', 'zed'}:
        args += ['--user-data-dir', str(home / 'profile')]
    if id == 'vscode':
        args += ['--disable-extensions', '--skip-welcome', '--skip-release-notes', '--disable-workspace-trust']
    if id == 'lapce':
        args += ['--new', '--wait']
    if id == 'basic-electron':
        args += [str(ROOT / 'basic-electron')]
    return [binary, *args]


def visible_window(pids):
    for pid in pids:
        search = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(pid)],
                                capture_output=True, text=True)
        for window in search.stdout.split():
            props = subprocess.check_output(['xprop', '-id', window, '_NET_WM_WINDOW_TYPE',
                                             'WM_NAME', 'WM_CLASS', '_NET_WM_PID'], text=True)
            if '_NET_WM_WINDOW_TYPE_NORMAL' in props:
                return {'windowId': window, 'pid': pid, 'properties': props}
    return None


def trial(editor, perf):
    with tempfile.TemporaryDirectory(prefix='startup-trial-') as directory:
        d = Path(directory)
        home = d / 'home'
        home.mkdir()
        env = {**os.environ, 'HOME': str(home), 'LC_ALL': 'C', 'LIBGL_ALWAYS_SOFTWARE': '1',
               'GALLIUM_DRIVER': 'llvmpipe', 'ZED_ALLOW_EMULATED_GPU': '1',
               'ELECTRON_OZONE_PLATFORM_HINT': 'x11'}
        for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state')]:
            env[key] = str(home / name)
            (home / name).mkdir()
        command = command_for(editor, home)
        try:
            with Capture(perf, d) as capture:
                with (d / 'stdout').open('w') as stdout, (d / 'stderr').open('w') as stderr:
                    start = time.monotonic()
                    child = capture.launch(command, env, stdout, stderr)
                    while True:
                        pids = capture.pids()
                        if not pids:
                            raise RuntimeError(f'editor exited before main window: {child.poll()}')
                        window = visible_window(pids)
                        if window:
                            observed = time.monotonic()
                            capture.cutoff()
                            result = capture.finish()
                            result.update(valid=True, readiness=window, launchToWindowSeconds=observed-start,
                                          launchToCutoffSeconds=capture.disabled_at-start,
                                          pidsAtCutoff=pids, command=command)
                            break
                        if time.monotonic() - start > PROTOCOL['timeoutSeconds']:
                            raise RuntimeError('main window readiness timeout')
                        time.sleep(PROTOCOL['pollSeconds'])
                
            child.wait(timeout=5)
            return result
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            return {'valid': False, 'error': str(error), 'command': command,
                    **{name: (d / name).read_text(errors='replace')[-8000:]
                       for name in ['stdout', 'stderr', 'perf.log'] if (d / name).exists()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor', required=True)
    parser.add_argument('--perf', required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three trials required')
    editor = next(e for e in json.loads((ROOT / 'config/editors.lock.json').read_text()) if e['id'] == args.editor)
    host = {'machine': platform.machine(), 'kernel': platform.release(), 'cpuinfo': Path('/proc/cpuinfo').read_text(),
            'perf': subprocess.check_output([args.perf, '--version'], text=True).strip(),
            'eventSources': sorted(p.name for p in Path('/sys/bus/event_source/devices').iterdir()),
            'paranoid': Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip(),
            'runUrl': os.environ.get('BENCHMARK_RUN_URL'), 'commit': os.environ.get('BENCHMARK_COMMIT')}
    if host['machine'] != 'aarch64':
        raise SystemExit('requires Linux ARM64')
    if editor.get('package'):
        host['packageVersion'] = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', editor['package']], text=True)
    trials = [dict(trial(editor, args.perf), repeat=i+1) for i in range(args.repeats)]
    Path('results').mkdir(exist_ok=True)
    Path('results/results.json').write_text(json.dumps(dict(editor=editor, protocol=PROTOCOL, host=host, trials=trials), indent=2)+'\n')
    if not all(t['valid'] for t in trials):
        raise SystemExit('invalid trials; cannot publish complete report')

if __name__ == '__main__':
    main()
