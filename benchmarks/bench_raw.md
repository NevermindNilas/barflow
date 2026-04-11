# BarFlow benchmark results

Iterations per run: **20,000,000**  (5 runs, best wall time reported)
Platform: Windows + Python 3.13

## Import startup (median, baseline-subtracted)

| Library | Cold import (ms) |
|---|---:|
| barflow | **1.21** |
| tqdm | **72.27** |
| rich | **74.96** |
| alive | **30.12** |

Baseline bare for-loop: **145.75 M it/s**  (6.9 ns/iter)

## Counter hot path (each lib in its disabled mode)

> **Caveat:** `rich` and `alive-progress` don't truly short-circuit
> when `disable=True`. They skip rendering but still run the full
> `advance()` accounting path (dict + RLock + deque for rich; similar
> bookkeeping for alive). Their numbers here reflect that, not a zero-work
> path. `barflow-tick` and `barflow-track` short-circuit at the C level.

| Variant | M it/s | ns/iter over baseline |
|---|---:|---:|
| barflow-tick | **65.39** | 8.4 |
| barflow-track | **101.13** | 3.0 |
| barflow-iter | **160.76** | 0.0 |
| tqdm | **70.23** | 7.4 |
| rich | **2.09** | 471.9 |
| alive-progress | **2.55** | 384.9 |

## Display on (writing to in-memory sink)

| Library | M it/s |
|---|---:|
| barflow | **101.76** |
| tqdm | **19.57** |
| rich | **2.11** |
| alive-progress | **2.09** |

## CPU cost (process_time, sums all threads)

Baseline bare for-loop CPU: **140.6 ms** for 20,000,000 iters.

| Library | Mode | CPU ms | extra ns/iter | CPU/wall |
|---|---|---:|---:|---:|
| barflow | nodisplay | **187.5** | 2.3 | 0.96 |
| barflow | display | **187.5** | 2.3 | 0.96 |
| tqdm | nodisplay | **265.6** | 6.2 | 0.93 |
| tqdm | display | **953.1** | 40.6 | 0.95 |
| rich | nodisplay | **9437.5** | 464.8 | 0.96 |
| rich | display | **9296.9** | 457.8 | 0.98 |
| alive-progress | nodisplay | **7671.9** | 376.6 | 0.98 |
| alive-progress | display | **9390.6** | 462.5 | 0.98 |
