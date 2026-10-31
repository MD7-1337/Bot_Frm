# Measured performance and limits

`tools/benchmark_workers.py --output report.json` runs one, two and four actual
spawned workers on independent stateful simulated devices. Each run creates real
PNG templates, starts isolated Python, performs OpenCV matching, clicks the target,
verifies changed simulator state and cleans up owned workers. It records platform,
Python, logical CPUs and elapsed seconds. This is a short startup/workflow probe;
it does not measure sustained throughput or Android latency.

The current Linux observations are in
[alpha-workers-performance.json](validation/alpha-workers-performance.json).
The real workbench/Monaco plus spawned-worker release-smoke source run is in
[alpha-source-release-smoke.json](validation/alpha-source-release-smoke.json).
That report explicitly has `frozen: false`; it is not Windows packaging evidence.
The separate recognition benchmark remains available as
`tools/benchmark_recognition.py`.

Streaming FPS, frame drops, real screenshot latency, physical-phone recognition,
Windows GUI responsiveness, idle/active RSS and sustained CPU use remain
**NOT VERIFIED** by these probes. No support for 20+ devices is claimed.
Use the existing worker limit and conservative preview/encoder settings on weak
hosts. Region-limited matching and smaller preview encoder size reduce work;
recognition coordinates still refer to original Android pixels.

Before Beta, collect repeated cold/warm startup, idle/active host and worker RSS,
long-running execution/cleanup, responsiveness during OCR/recognition, scheduling
overhead and physical one-/two-phone video measurements on the target Windows
machine. Record run duration, CPU/RAM/GPU, OS build and device models with those
results. Do not extrapolate short simulator timings into real-phone capacity.
