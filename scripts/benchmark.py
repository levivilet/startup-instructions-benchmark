"""Measure instructions from fresh-profile launch to first mapped main window."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from counters import Capture

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = {
    'version': 2, 'metric': 'retired hardware instructions (user and kernel)',
    'boundary': 'launch through first visible normal main window',
    'accounting': 'per-CPU cgroup; includes all descendants, including detached and exited tasks',
    'profile': 'fresh HOME and XDG directories every trial, no bootstrap launch',
    'cache': 'warm OS filesystem caches permitted; application profiles always fresh',
    'pollSeconds': .02, 'timeoutSeconds': 120,
    'launcher': 'includes child cgroup-entry, privilege drop and exec overhead; controller and desktop excluded',
    'cutoff': 'perf disable acknowledgement before shutdown; includes polling/control latency',
}

ELECTRON_SWITCH_SETS = {
    'baseline': [],
    'disable-background-networking': ['--disable-background-networking'],
    'disable-http-cache': ['--disable-http-cache'],
    'disable-http2': ['--disable-http2'],
    'disable-http-cache+disable-http2': ['--disable-http-cache', '--disable-http2'],
}


def command_for(editor, home, extra_switches=(), verify_render_and_exit=False):
    app = ROOT / '.tmp/apps' / editor['id']
    binary_path = app / editor['binary']
    if not binary_path.exists() and editor.get('binaryGlob'):
        matches = list(app.glob(editor['binaryGlob']))
        if len(matches) == 1:
            binary_path = matches[0]
    binary = str(binary_path)
    id = editor['id']
    if id == 'geany':
        return ['geany', '--new-instance']
    args = []
    if id in {'lvce', 'vscode', 'basic-electron', 'cursor'}:
        args += ['--no-sandbox', '--disable-gpu', '--ozone-platform=x11']
    if id in {'lvce', 'vscode', 'zed', 'cursor'}:
        args += ['--user-data-dir', str(home / 'profile')]
    if id in {'vscode', 'cursor'}:
        args += ['--disable-extensions', '--skip-welcome', '--skip-release-notes', '--disable-workspace-trust']
    if id == 'cursor':
        args += ['--extensions-dir', str(home / 'extensions')]
    if id == 'intellij':
        args += [f'-Didea.config.path={home / "config" / "intellij"}',
                 f'-Didea.system.path={home / "cache" / "intellij"}',
                 f'-Didea.plugins.path={home / "data" / "intellij" / "plugins"}',
                 f'-Didea.log.path={home / "state" / "intellij"}', 'dontReopenProjects']
    if id == 'eclipse':
        args += ['-nosplash', '-consoleLog', '-data', str(home / 'workspace'),
                 '-configuration', str(home / 'config' / 'eclipse')]
    if id == 'lapce':
        args += ['--new', '--wait']
    if id == 'basic-electron':
        args += extra_switches
    if id == 'basic-electron':
        args += [str(ROOT / 'basic-electron')]
        if verify_render_and_exit:
            args += ['--benchmark-verify-render']
    return [binary, *args]


def is_main_window(properties):
    # EWMH: managed windows without type or transient-parent hints default
    # to NORMAL. Zed uses this valid omission instead of an explicit atom.
    lines = properties.splitlines()
    type_line = next((line for line in lines if line.startswith('_NET_WM_WINDOW_TYPE')), '')
    transient_line = next((line for line in lines if line.startswith('WM_TRANSIENT_FOR')), '')
    managed = 'window state: Normal' in properties
    normal = '_NET_WM_WINDOW_TYPE_NORMAL' in type_line
    default_normal = (type_line.partition(':')[2].strip() == 'not found.' and
                      transient_line.partition(':')[2].strip() == 'not found.')
    return managed and (normal or default_normal)


def visible_window(pids):
    for pid in pids:
        search = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(pid)],
                                capture_output=True, text=True)
        for window in search.stdout.split():
            props = subprocess.check_output(['xprop', '-id', window, '_NET_WM_WINDOW_TYPE',
                                             'WM_NAME', 'WM_CLASS', '_NET_WM_PID', 'WM_TRANSIENT_FOR', 'WM_STATE'], text=True)
            if is_main_window(props):
                return {'windowId': window, 'pid': pid, 'properties': props}
    return None


def diagnostics(home):
    windows = subprocess.run(['xwininfo', '-root', '-tree'], capture_output=True, text=True).stdout
    properties = []
    import re
    for window in re.findall(r'^\s+(0x[0-9a-f]+)', windows, re.MULTILINE):
        query = subprocess.run(['xprop', '-id', window, '_NET_WM_WINDOW_TYPE',
                                'WM_NAME', 'WM_CLASS', '_NET_WM_PID'], capture_output=True, text=True)
        properties.append({'windowId': window, 'properties': query.stdout})
    logs = {str(p.relative_to(home)): p.read_text(errors='replace')[-12000:]
            for p in home.rglob('*.log') if p.is_file()}
    processes = subprocess.run(['ps', '-eo', 'pid,ppid,user,stat,args'], capture_output=True, text=True).stdout
    return dict(windowTree=windows, windowProperties=properties, editorLogs=logs, processes=processes)


def trial(editor, perf, extra_switches=(), verify_render_and_exit=False):
    with tempfile.TemporaryDirectory(prefix='startup-trial-') as directory:
        d = Path(directory)
        home = d / 'home'
        home.mkdir()
        env = {**os.environ, 'HOME': str(home), 'LC_ALL': 'C', 'LIBGL_ALWAYS_SOFTWARE': '1',
               'GALLIUM_DRIVER': 'llvmpipe', 'ZED_ALLOW_EMULATED_GPU': '1',
               'ELECTRON_OZONE_PLATFORM_HINT': 'x11'}
        for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
                          ('XDG_RUNTIME_DIR', 'runtime')]:
            env[key] = str(home / name)
            (home / name).mkdir()
        (home / 'runtime').chmod(0o700)
        if 'SUDO_UID' in env:
            uid, gid = int(env['SUDO_UID']), int(env['SUDO_GID'])
            for path in [d, home, *home.iterdir()]:
                os.chown(path, uid, gid)
        command = command_for(editor, home, extra_switches, verify_render_and_exit)
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
                            render_validation = None
                            if verify_render_and_exit:
                                child.wait(timeout=10)
                                stdout_text = (d / 'stdout').read_text(errors='replace')
                                marker = 'BENCHMARK_RENDER_VERIFIED=true'
                                if child.returncode != 0 or marker not in stdout_text:
                                    raise RuntimeError('Basic Electron did not render the expected page and exit cleanly')
                                exit_deadline = time.monotonic() + 5
                                while capture.pids():
                                    if time.monotonic() >= exit_deadline:
                                        raise RuntimeError('Basic Electron child processes remained after app quit')
                                    time.sleep(.01)
                                render_validation = {
                                    'expectedTitle': 'Basic Electron',
                                    'expectedHeading': 'Basic Electron',
                                    'verified': True,
                                    'exitCode': child.returncode,
                                    'processTreeExited': True,
                                    'evidence': marker,
                                }
                            result.update(valid=True, readiness=window, launchToWindowSeconds=observed-start,
                                          launchToCutoffSeconds=capture.disabled_at-start,
                                          pidsAtCutoff=pids, command=command,
                                          renderValidation=render_validation)
                            break
                        if time.monotonic() - start > PROTOCOL['timeoutSeconds']:
                            failure_diagnostics = diagnostics(home)
                            raise RuntimeError('main window readiness timeout')
                        time.sleep(PROTOCOL['pollSeconds'])
                
            child.wait(timeout=5)
            return result
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            return {'valid': False, 'error': str(error), 'command': command,
                    'diagnostics': failure_diagnostics if 'failure_diagnostics' in locals() else diagnostics(home),
                    **{name: (d / name).read_text(errors='replace')[-8000:]
                       for name in ['stdout', 'stderr', 'perf.log'] if (d / name).exists()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor', required=True)
    parser.add_argument('--perf', required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--switch-set', choices=ELECTRON_SWITCH_SETS, default='baseline')
    parser.add_argument('--verify-render-and-exit', action='store_true')
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three trials required')
    if args.verify_render_and_exit and args.editor != 'basic-electron':
        parser.error('--verify-render-and-exit only applies to Basic Electron')
    editor = next(e for e in json.loads((ROOT / 'config/editors.lock.json').read_text()) if e['id'] == args.editor)
    host = {'machine': platform.machine(), 'kernel': platform.release(), 'cpuinfo': Path('/proc/cpuinfo').read_text(),
            'perf': subprocess.check_output([args.perf, '--version'], text=True).strip(),
            'eventSources': sorted(p.name for p in Path('/sys/bus/event_source/devices').iterdir()),
            'paranoid': Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip(),
            'editorUid': int(os.environ.get('SUDO_UID', os.getuid())),
            'runUrl': os.environ.get('BENCHMARK_RUN_URL'), 'commit': os.environ.get('BENCHMARK_COMMIT')}
    if host['machine'] != 'aarch64':
        raise SystemExit('requires Linux ARM64')
    if editor.get('package'):
        host['packageVersion'] = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', editor['package']], text=True)
    extra_switches = ELECTRON_SWITCH_SETS[args.switch_set]
    protocol = {**PROTOCOL, 'electronSwitchSet': args.switch_set,
                'extraElectronSwitches': extra_switches,
                'renderValidationAfterCutoff': args.verify_render_and_exit}
    trials = [dict(trial(editor, args.perf, extra_switches, args.verify_render_and_exit), repeat=i+1)
              for i in range(args.repeats)]
    Path('results').mkdir(exist_ok=True)
    Path('results/results.json').write_text(json.dumps(dict(editor=editor, protocol=protocol, host=host, trials=trials), indent=2)+'\n')
    if not all(t['valid'] for t in trials):
        for item in trials:
            if not item['valid']:
                print(json.dumps({key: item.get(key) for key in ('error', 'stdout', 'stderr', 'perf.log')},
                                 indent=2), file=sys.stderr)
        raise SystemExit('invalid trials; cannot publish complete report')

if __name__ == '__main__':
    main()
