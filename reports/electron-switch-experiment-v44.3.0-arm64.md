# Basic Electron startup switch experiment — Linux ARM64

## Result

On this Linux ARM64 host, none of the tested switches reduced retired startup
instructions beyond the observed baseline variation. Disabling the HTTP cache
had a lower pooled median (5.27%), but its paired block bootstrap interval
includes zero. These measurements do not show a useful startup instruction
reduction for this workload.

Do not add any tested switch as a Basic Electron or application default based on
this result. The page makes no HTTP requests, so the HTTP switches do not remove
work exercised by this workload; disabling cache or HTTP/2 may change behavior
for applications that use the network. `--disable-background-networking` is
not listed among Electron's supported switches for v44.3.0 and is retained only
as an exploratory candidate, not as a recommendation.

## Method

- Electron: Basic Electron v44.3.0, pinned in `config/editors.lock.json` with
  SHA-256 `c11fde221c08e9bffdb3336579f09bd934a009862f509af5033616876741be24`.
- Host: GitHub Actions `ubuntu-24.04-arm`, Linux `aarch64`, kernel
  `6.17.0-1022-azure`, `perf version 6.8.12`. `/proc/cpuinfo` reports ARM
  implementer `0x41`, architecture `8`, CPU part `0xd49`. Full host and counter
  metadata are retained in every raw JSON file.
- Run: [Startup instructions benchmark, run 38635519823](https://github.com/levivilet/startup-instructions-benchmark/actions/runs/38635519823).
  It validated PR head `6de95f82e9df897e24884216280c4b3ca25915ed`. The workflow's
  checked-out merge commit was `a4329b0d028e10fb4df46db4daa64c08f42496a6`; its
  parents are `main` commit `c960c1dc55c60d8b5ab05b6b7479e8f28f8f3109` and the
  measured PR head.
- Workload: the checked-in Basic Electron app creates a 1000×700
  `BrowserWindow` and loads
  `data:text/html,<title>Basic Electron</title><h1>Basic Electron</h1>`.
- Endpoint: first visible normal main window. `perf stat` counts retired user
  and kernel instructions for the complete editor cgroup, including
  descendants, through an acknowledged counter cutoff. The controller, X11
  desktop and cleanup are outside the cgroup. Each result has valid raw counter
  evidence, an acknowledged cutoff, and EWMH properties showing a normal
  visible window. After cutoff, the app separately verifies the expected
  document title and heading. It waits for the benchmark's exit signal, then
  exits with code 0; the controller verifies the process tree is empty. This
  handshake keeps rendering and shutdown validation out of the measured count
  while ensuring each trial completed the same visible and rendered work.
- Profiles and order: every trial uses a fresh HOME and XDG directories, with no
  bootstrap launch. OS filesystem caches may be warm. Each configuration has 30
  trials in ten blocks of three; the five configurations are shuffled within
  each block using seed `4403`. Raw JSON includes the exact batch order, command,
  raw counter output, process IDs, window properties, render checks and timings.
- Analysis: pooled medians, sample standard deviations, coefficients of
  variation and min/max use all 30 instruction counts per configuration. For
  uncertainty, take each block's median for a candidate and subtract that
  block's baseline median. The table reports the median of ten paired
  differences and a 95% percentile bootstrap interval from 100,000 resamples of
  those ten differences with replacement. Python `random.Random` seeds are
  `20261015` through `20261018` in candidate table order. Percentile endpoints
  use the sorted bootstrap draws at `floor(p × (B−1))` for `p = 0.025` and
  `0.975`. Every interval includes zero, so these trials do not establish a
  switch effect beyond run-to-run variation.

Baseline command:

```text
/home/runner/work/startup-instructions-benchmark/startup-instructions-benchmark/.tmp/apps/basic-electron/electron --no-sandbox --disable-gpu --ozone-platform=x11 /home/runner/work/startup-instructions-benchmark/startup-instructions-benchmark/basic-electron --benchmark-verify-render
```

Each candidate added the listed switch before the app path. Every exact
per-trial argument array is recorded in its raw JSON.

## Measurements

Counts and intervals are millions of instructions. Median delta compares each
pooled median to the baseline pooled median of 1,734.8M.

| Configuration | Extra Electron switches | Median | Median delta | Sample SD (CV) | Min–max | Paired block median delta (95% interval) |
|---|---|---:|---:|---:|---:|---:|
| Baseline | — | 1,734.8M | — | 117.6M (6.97%) | 1,364.3–1,801.1M | — |
| Background networking | `--disable-background-networking` | 1,716.7M | −1.05% | 112.7M (6.80%) | 1,424.5–1,796.7M | −28.8M (−170.2 to +123.3M) |
| HTTP cache disabled | `--disable-http-cache` | 1,643.4M | −5.27% | 130.1M (8.00%) | 1,411.2–1,795.8M | −38.0M (−177.4 to +111.6M) |
| HTTP/2 disabled | `--disable-http2` | 1,709.3M | −1.47% | 130.3M (7.94%) | 1,420.2–1,800.4M | −14.2M (−194.7 to +24.3M) |
| Both HTTP switches | `--disable-http-cache --disable-http2` | 1,730.2M | −0.27% | 110.0M (6.58%) | 1,386.2–1,790.2M | −14.6M (−150.3 to +110.8M) |

All 150 trials passed counter, readiness, render, clean-exit and empty-process-
tree validation. Launch-to-visible-window times ranged from 0.188 to 0.353
seconds across configurations. The large spread in instruction counts and
overlapping paired intervals do not support a recommendation for any switch.

## Raw trial data

- [Baseline JSON](electron-switch-experiment-v44.3.0-arm64/raw/baseline.json)
- [Background networking JSON](electron-switch-experiment-v44.3.0-arm64/raw/disable-background-networking.json)
- [HTTP cache disabled JSON](electron-switch-experiment-v44.3.0-arm64/raw/disable-http-cache.json)
- [HTTP/2 disabled JSON](electron-switch-experiment-v44.3.0-arm64/raw/disable-http2.json)
- [Both HTTP switches JSON](electron-switch-experiment-v44.3.0-arm64/raw/disable-http-cache+disable-http2.json)

Version-matched documentation: [Electron v44.3.0 supported command-line
switches](https://github.com/electron/electron/blob/v44.3.0/docs/api/command-line-switches.md).
