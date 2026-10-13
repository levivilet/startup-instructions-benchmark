# Startup instructions benchmark

Compare retired hardware CPU instructions consumed during IDE startup on Linux
ARM64. The chart follows the [idle CPU benchmark](https://levivilet.github.io/lvce-idle-cpu-benchmark/)
and orders editors by median instructions, lowest first. Each editor runs three
trials; downloadable JSON contains every count, raw perf output, package identity,
host metadata, window evidence and measurement protocol.

## Protocol

Each trial starts with a fresh HOME and XDG configuration/data/cache/state profile.
There is no bootstrap launch. Startup ends at the **first visible normal main
window** owned by a process in the editor cgroup. Splash windows are excluded.
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

The checked-in matrix includes LVCE Editor, VS Code, Zed, Lapce, Geany, and Basic
Electron (an empty-window baseline). It is a subset of the reference idle CPU chart.
Cursor, Eclipse, IntelliJ IDEA, Atom and Theia are outside this initial artifact
matrix, not zero-valued results. This does not claim those editors lack ARM support.
The full six-editor matrix must succeed for a report to be considered complete.

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
