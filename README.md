# Startup instructions benchmark

This repository is being developed to compare retired hardware CPU instructions
from IDE launch to startup readiness on Linux ARM. The intended chart orders
editors by median instruction count, lowest first, like the
[LVCE idle CPU benchmark](https://levivilet.github.io/lvce-idle-cpu-benchmark/).

The first prerequisite is a working hardware instruction counter on the GitHub
Actions runner. The ARM counter feasibility workflow records raw `perf stat`
output, CPU/kernel metadata and available event sources. It fails if the
counter is unavailable or returns no positive count. It does not substitute CPU
time, sampled activity or estimated instructions, and does not publish a chart.

Implementation of editor measurements and report publication follows successful
counter and process-inheritance validation. No measured editor results are
available yet.
