# Startup instructions benchmark

Compare retired hardware CPU instructions consumed during IDE startup on Linux
ARM64. The chart follows the [idle CPU benchmark](https://levivilet.github.io/lvce-idle-cpu-benchmark/)
and orders editors by median instructions, lowest first. Each editor runs three
trials; downloadable JSON contains every count, raw perf output, package identity,
host metadata, window evidence and measurement protocol.

## Protocol

Each trial starts with a fresh HOME and XDG configuration/data/cache/state profile.
There is no bootstrap launch. Startup ends at the **first visible normal main
window** owned by a process in the editor cgroup. Splash windows are excluded. Managed windows without a window-type hint and
without a transient parent use the standard EWMH normal-window default, as Zed does.
This measures window readiness, not interactivity, document loading or completion
of background startup work. Polling happens every 20 ms, plus the time needed to
inspect windows; polling and counter-disable latency are included in the measured
interval. The recorded window properties and elapsed times make the cutoff auditable.

`perf stat -a -e instructions -G <unique-cgroup>` counts user and kernel instructions
only while editor tasks run. Forks, threads, detached processes and tasks that exit
before readiness remain covered by cgroup membership. The launcher enters the group
before exec; its small cgroup-entry and exec overhead is included. The controller,
perf, Xvfb, window manager and readiness commands stay outside the cgroup. Counters
are enabled before launch and disabled with an acknowledged control command before
any shutdown or cleanup. Cleanup kills the entire cgroup, including detached tasks.
[perf's cgroup and control interface](https://www.man7.org/linux/man-pages/man1/perf-stat.1.html)
provides the hardware accounting and synchronized cutoff.

OS filesystem caches may be warm, including subsequent trials. The runner uses
software graphics and an X11 desktop. These are fresh-profile launches, not cold
machine boots. Results from different editor jobs use separate instances of the
same ARM image; compare counts with the included CPU/kernel metadata. Geany uses
the Ubuntu package with its exact installed version recorded; other packages have
checked-in versions and SHA-256 hashes verified before extraction.

## Initial ARM matrix

The checked-in matrix includes LVCE Editor, VS Code, Zed, Lapce, Geany, Basic
Electron (an empty-window baseline), IntelliJ IDEA Community, Eclipse IDE for Java
Developers, and Cursor. Atom and Theia are excluded because verified native Linux
ARM64 artifacts are unavailable: [Atom's final official release](https://github.com/atom/atom/releases/tag/v1.60.0)
publishes only AMD64 Linux packages, while [Theia's current Linux metadata](https://download.eclipse.org/theia/ide/latest/linux/latest-linux.yml)
does not identify an ARM64 build and its [Snap stable channel](https://api.snapcraft.io/v2/snaps/info/theia-ide)
lists only amd64. These exclusions are not zero-valued results. The full
nine-editor matrix must succeed for a report to be considered complete.

## Basic Electron switch experiment

The `Electron switch experiment` CI job measures Basic Electron v44.3.0 on the
same ARM host and X11 setup with thirty fresh-profile trials for each configuration:
the existing baseline, `--disable-background-networking`,
`--disable-http-cache`, `--disable-http2`, and the two documented HTTP switches
together. It uploads each complete result as `electron-switch-experiment`,
including the exact command, raw per-trial counter output, host metadata, window
evidence and fresh-profile protocol. Ten blocks of three trials run in seeded,
shuffled configuration order; the seed and full order are stored with each
result. Filesystem caches may warm across configurations, as in the main benchmark.

Electron v44.3.0 documents `--disable-http-cache` and `--disable-http2` as
supported switches. Its switch documentation says unsupported switches have no
effect, so `--disable-background-networking` is included only as an exploratory
Chromium flag and is not treated as an Electron recommendation. The Basic
Electron fixture renders a local `data:` URL and makes no network requests;
the network switches are not representative of apps that load remote content.
None of these settings is recommended as an application default without a
separate functional and security review. See Electron's [v44.3.0 switch
documentation](https://github.com/electron/electron/blob/v44.3.0/docs/api/command-line-switches.md).

## Validation and publication

The ARM feasibility probe first demonstrated a working PMU on `ubuntu-24.04-arm`.
The hardware accounting gate then uses the production capture implementation to
compare a fixed native loop with a detached double-fork child, 10 times as much work
after cutoff, and a busy external Python controller. Each must match the direct
loop within 10%; missing descendants or counted shutdown/controller work fail CI.

Tests cover counter parsing, invalid/multiplexed counters, cutoff evidence, missing
artifacts, pinned identity, medians and ascending chart ordering. Hardware counters,
readiness timeouts and failed launches fail explicitly; none become zero or a
complete report. All three trials per editor are required even for PRs. Pages
publication runs only on main after accounting, every editor and report tests pass.
No report is published from synthetic test data.

Run tests with `python3 -m unittest discover -s tests`. Hardware measurement needs
Linux ARM64, a writable cgroup v2 root, a usable PMU, perf and the desktop packages
listed in the workflow. The workflow provisions them and uses sudo for cgroup and
per-CPU counter access. The launcher drops to the normal runner UID before
exec; the isolated profile and X11 desktop belong to that user. Run it through GitHub Actions to reproduce the complete
matrix, or use `scripts/install.py`, `scripts/validate_accounting.py` and
`scripts/run.sh` in the same environment.
