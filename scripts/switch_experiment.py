"""Run a shuffled, repeated ARM64 startup switch experiment."""
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
ROUNDS = 10
TRIALS_PER_BLOCK = 3
ORDER_SEED = 4403
SWITCH_SETS = [
    'baseline',
    'disable-background-networking',
    'disable-http-cache',
    'disable-http2',
    'disable-http-cache+disable-http2',
]


def execution_order():
    randomizer = random.Random(ORDER_SEED)
    rounds = []
    for _ in range(ROUNDS):
        switch_sets = SWITCH_SETS.copy()
        randomizer.shuffle(switch_sets)
        rounds.append(switch_sets)
    return rounds


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: switch_experiment.py PERF')
    perf = sys.argv[1]
    results = {}
    batches = []
    results_dir = ROOT / 'results'
    results_dir.mkdir(exist_ok=True)
    (results_dir / 'electron-switches').mkdir(exist_ok=True)

    for round_index, switch_sets in enumerate(execution_order(), 1):
        for switch_set in switch_sets:
            command = [
                'sudo',
                '--preserve-env=DISPLAY,XAUTHORITY,BENCHMARK_RUN_URL,BENCHMARK_COMMIT',
                'python3', 'scripts/benchmark.py', '--editor', 'basic-electron',
                '--perf', perf, '--repeats', str(TRIALS_PER_BLOCK),
                '--switch-set', switch_set, '--verify-render-and-exit',
            ]
            subprocess.run(command, cwd=ROOT, check=True)
            path = results_dir / 'results.json'
            data = json.loads(path.read_text())
            path.unlink()
            if len(data.get('trials', [])) != TRIALS_PER_BLOCK or not all(
                    trial.get('valid') is True for trial in data['trials']):
                raise ValueError(f'{switch_set}: invalid result block')
            if not all(trial.get('renderValidation', {}).get('verified') is True and
                       trial['renderValidation'].get('exitCode') == 0 and
                       trial['renderValidation'].get('processTreeExited') is True
                       for trial in data['trials']):
                raise ValueError(f'{switch_set}: render or clean-exit verification failed')

            if switch_set not in results:
                results[switch_set] = data
            else:
                combined = results[switch_set]
                if any(data[key] != combined[key] for key in ('editor', 'protocol', 'host')):
                    raise ValueError(f'{switch_set}: metadata changed between blocks')
                data_trials = data['trials']
                start = len(combined['trials']) + 1
                combined['trials'].extend(dict(trial, repeat=start + index)
                                          for index, trial in enumerate(data_trials))
            batches.append({'round': round_index, 'switchSet': switch_set,
                            'trialsPerBlock': TRIALS_PER_BLOCK})

    if set(results) != set(SWITCH_SETS):
        raise ValueError('incomplete switch matrix')
    for switch_set, data in results.items():
        if len(data['trials']) != ROUNDS * TRIALS_PER_BLOCK:
            raise ValueError(f'{switch_set}: expected 30 trials')
        data['experiment'] = {
            'rounds': ROUNDS,
            'trialsPerBlock': TRIALS_PER_BLOCK,
            'orderSeed': ORDER_SEED,
            'batches': batches,
        }
        output = results_dir / 'electron-switches' / f'{switch_set}.json'
        output.write_text(json.dumps(data, indent=2) + '\n')


if __name__ == '__main__':
    main()
