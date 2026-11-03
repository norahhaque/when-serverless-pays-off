# Findings log

Dated observations, newest last. Raw data is in `results/raw/`; figures in `results/figures/`.

## 2026-11-03: local (Docker on an M-series Mac)

- Model load (torch import + weights): ~2.5 s.
- Sequential requests: p50 30 ms. At 10 req/s: p50 200 ms, p99 250 ms.
  Concurrent requests contend for CPU (PyTorch intra-op threads × server threadpool).
  Not payload size: shrinking the image 275 KB → 20 KB barely changed it. Re-check on EC2.

## 2026-11-03: Lambda, us-east-2, x86_64, container image (~2 GB uncompressed)

- Deploy gotchas:
  - Public Function URLs need **both** `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`
    (with `--invoked-via-function-url`) since Oct 2025; otherwise 403.
  - Account concurrency limit was 10 (new account). Increase to 1000 requested.
- First invoke after deploy: init hit the **10 s init limit**, Lambda retried init inside the
  invoke, and the request ran past the 60 s timeout. Timeout raised to 120 s.
  3008 MB: 10 s failed init + 58 s in-invoke = ~68 s for the very first request.
- Warm billed duration (CloudWatch REPORT):

  | Memory | Billed ms | GB-s per request |
  |---|---|---|
  | 1024 MB | ~190 | ~0.19 |
  | 2048 MB | ~90 | ~0.18 |
  | 3008 MB | ~58 | ~0.17 |

  CPU scales with memory, so cost per request is roughly flat while latency drops ~3.3×.
- Early cold starts while the image cache was still warming: 1024 MB ~18.3 s, 2048 MB ~6.2 s.
  Steady-state cold starts are ~4.5–5 s (next section). Cache warm-up is its own effect worth reporting.
- Client latency from a laptop in Minnesota adds ~60 ms of network; real runs use an in-region load generator.

## 2026-11-03: Lambda cold vs. warm (10 forced cold starts per size, 5 warm after each; client on laptop)

| Memory | Cold median (p90) | Warm median (p90) | Billed init (median of 10) |
|---|---|---|---|
| 1024 MB | 5,063 ms (5,922) | 255 ms (422) | ~4.2 s |
| 2048 MB | 4,583 ms (5,150) | 157 ms (231) | ~3.9 s |
| 3008 MB | 4,455 ms (5,053) | 123 ms (398) | ~3.9 s |

- Cold start is **~4.5–5 s regardless of memory**: init (~4 s, mostly import torch + load weights,
  in-function model load ~3.6–3.9 s) doesn't speed up much with more CPU. Warm latency does.
- Cold ≈ 30–40× warm. Any request that lands on a new environment blows a sub-second SLO.
- Init is billed for container images: ~4 s × GB per cold start ≈ 20–70 warm requests' worth.
- Only the very first invoke after deploy (image not yet cached) exceeded the 10 s init limit.
- Warm numbers include ~60–100 ms laptop→us-east-2 network; in-region numbers come from the load generator.

## 2026-11-03: EC2 capacity sweep #1, c7i-flex.large (discarded for latency, kept as a methodology finding)

- Free-plan account: c6i.large not allowed; using c7i-flex.large (2 vCPU, 4 GB, $0.08479/hr,
  full CPU guaranteed ~95% of the time).
- Load-generator artifact: p50 = **exactly 45 ms × rate** (2→90, 4→180, ..., 12→540 ms).
  Cause: Locust users spawned together with `constant_throughput(1)` fire in lock-step, so each
  second is one burst of N simultaneous requests and the last waits for N−1 others.
  Fix: Poisson request start times (exponential gaps per user). Local sanity check at 6 req/s
  (Mac, not EC2): p50 54 ms, vs. 270 ms lock-step on EC2. Data kept as `ec2cap-lockstep_*`.
- Still valid from this run: **max throughput ~16–18 req/s** per instance (achieved rate
  plateaued at 15–18 req/s for targets 20–30); ~45 ms of full-machine CPU per request.

## 2026-11-03: EC2 capacity, default server (1 uvicorn worker, PyTorch default 2 threads), Poisson load, 3 reps

| Target | Achieved | p50 (mean) | p99 mean (min–max) |
|---|---|---|---|
| 2 | 1.9 | 62 | 126 (88–150) |
| 4 | 4.1 | 64 | 143 (110–170) |
| 6 | 5.7 | 67 | 213 (160–260) |
| 8 | 7.8 | 74 | 260 (190–370) |
| 10 | 9.4 | 88 | 503 (300–880) |
| 12 | 11.9 | 97 | 627 (390–840) |
| 14 | 13.5 | 157 | 737 (380–1000) |
| 16 | 15.2 | 203 | 950 (350–2000) |
| 18 | 17.2 | 253 | 877 (360–1700) |
| 20 | 18.3 | 280 | 1167 (900–1700) |
| 25 | 21.0 | 633 | 1233 (1100–1300) |

- Max throughput ~21 req/s, but **p99 ≤ 500 ms only up to ~7.8 req/s** (<40% of max).
- Large run-to-run spread in p99 at 10–20 req/s (e.g. 350 vs 2000 ms at 16): flex instance + tail sensitivity.
- Cost at SLO capacity: $0.08479 / (7.8 × 3600) × 1000 = **$0.00302 per 1k** ≈ Lambda 3008 MB ($0.00304).
  With this server config, EC2 can't meaningfully beat Lambda under a 500 ms p99 SLO.
- Hypothesis: CPU oversubscription (concurrent requests × 2 intra-op threads on 2 vCPUs).
  Testing OMP_NUM_THREADS=1 with 2 uvicorn workers next (`ec2tuned-*`).

## 2026-11-03: Lambda steady sweep, in-region (load generator in us-east-2), Poisson load, 1 rep

| Memory | p50 | p99 at 5–25 req/s | p99 at 2 req/s |
|---|---|---|---|
| 3008 MB | ~71 ms | 120–160 ms | 4,600 ms |
| 2048 MB | ~91 ms | 110–120 ms | 4,200 ms |
| 1024 MB | ~190 ms | 220–240 ms | 4,500 ms |

- **Latency is flat with load** (each request gets its own environment). EC2 p99 grows 126 → 1,233 ms over the same range.
- The 2 req/s run came first after the functions sat idle, so it started with cold environments;
  ~180 requests total, so a handful of ~4.5 s cold starts own the p99.
- **Throttling**: 1024 MB at 20 and 25 req/s had 1 and 13 HTTP 429s. Avg concurrency ≈ 25 × 0.19 s ≈ 5,
  but Poisson peaks exceed the account limit of 10. Bigger memory = shorter requests = fewer
  concurrent environments = less throttling at the same rate.

## 2026-11-03: EC2 capacity, tuned server (OMP_NUM_THREADS=1, 2 uvicorn workers), 3 reps

| Target | Achieved | p50 | p99 mean (min–max) |
|---|---|---|---|
| 2 | 1.9 | 63 | 140 (120–170) |
| 6 | 6.0 | 68 | 203 (180–220) |
| 10 | 9.9 | 74 | 223 (190–250) |
| 14 | 14.2 | 87 | 300 (260–350) |
| 16 | 15.3 | 97 | 360 (340–390) |
| 18 | 17.9 | 127 | 520 (460–560) |
| 20 | 19.8 | 200 | 730 (670–790) |
| 25 | 21.8 | 537 | 1003 (930–1100) |

- **SLO capacity 7.8 → 15.3 req/s** (≈2×) with no code change, and run-to-run spread shrinks a lot.
  Oversubscription confirmed: 2 intra-op threads per request × concurrent requests on 2 vCPUs.
- Cost at SLO capacity: $0.08479 / (15.3 × 3600) × 1000 = **$0.00154 per 1k**, about half of Lambda 3008 MB.
- Takeaway: **server tuning decides the winner.** Untuned, EC2 ≈ Lambda at best; tuned, EC2 is ~2× cheaper when busy.

## 2026-11-03: Cost model with measured inputs (Lambda billed ms, init, EC2 tuned capacity)

- Lambda $/1k: 1024 → $0.00337, 2048 → $0.00320, **3008 → $0.00304** (biggest is cheapest: linear
  speedup + fixed request fee amortized).
- Steady crossover vs. one c7i-flex.large: ~7.0–7.8 req/s. Break-even EC2 utilization vs. 3008 MB: **51%**.
- Bursts (5× for 2 of every 10 min), peak-sized EC2: crossover stays 7.8 req/s avg up to 2.5×; **never** at ≥3×.
- Hybrid (Lambda 3008 overflow), cost vs. Lambda-only:
  base 5 → Lambda-only wins (N=1 is 106%); base 10 → N=1 at 82%; base 20 → N=1 at 79%, N=2 at 82%.
  Optimal N is small: only keep containers you can run above ~51% utilization; let Lambda absorb the rest.

## 2026-11-03: Burst test #1, 5 → 25 req/s (5× for 120 s every 600 s), 20 min, tuned EC2 vs. Lambda 3008 MB

| Backend | Requests | p50 | p99 | Failures |
|---|---|---|---|---|
| Lambda 3008 MB | 10,881 | 67 ms | **88 ms** | 0 |
| EC2 tuned, 1 instance | 10,102 | 140 ms | **1,100 ms** | 0 |

- Lambda cold starts (CloudWatch Init Duration): 5 at test start (functions idle), **2 at burst 1, 3 at burst 2**,
  3.5–4.3 s each. 10 / 10,881 = 0.09% of requests, so overall p99 stays at 88 ms.
- One EC2 instance (SLO capacity 15.3) can't hold the 25 req/s peak: p99 1.1 s. This is the hybrid's case.
- Locust's stats_history percentiles are cumulative over the run, not windowed, so they can't show
  per-burst behavior. Added per-request logging (`REQUEST_LOG`) + `scripts/window_stats.py`; rerunning as `burst2-*`.

## 2026-11-03: Burst test #2 (same shape), per-request logging → p99 per 10 s window

| Backend | Requests | p50 | p99 | Failures |
|---|---|---|---|---|
| Lambda 3008 MB | 10,751 | 68 ms | 93 ms | 0 |
| EC2 tuned, 1 instance | 10,030 | 140 ms | 1,100 ms | 0 |

- Reproduces run #1 closely (Lambda p99 88 → 93 ms; EC2 1,100 both times).
- EC2 timeline: ~150 ms between bursts → **0.9–1.35 s during each burst** → recovers within ~20 s after.
- Lambda: flat ~90 ms. Cold starts this run: 4 at burst 1 (t = 487–528 s), 1 at burst 2 (t = 1115 s);
  none at start (functions were still warm from run #1). 1–3 slow requests among ~250 per 10 s window
  sit above the window's p99, so they don't show in the windowed p99 line.
- Figure: `results/figures/burst_timeline.png`.

## 2026-11-03: Lambda steady sweep, reps 2 and 3 (now 3 runs per point)

| Memory | p50 (3-run mean) | p99 mean at 5–25 req/s | p99 range across runs | HTTP 429s |
|---|---|---|---|---|
| 3008 MB | ~69 ms | 98–110 ms | 84–160 ms | 0 |
| 2048 MB | ~90 ms | 113–120 ms | 110–120 ms | 0 |
| 1024 MB | ~190 ms | 227–247 ms | 220–250 ms | 2 at 20 req/s, 30 at 25 req/s |

- Flat with load in every run. Throttling at 1024 MB / 25 req/s repeats every run (13, 10, 7).
- 2 req/s runs that start after idle include cold starts (p99 up to 4.6 s); one 3008 MB run started warm (p99 96 ms).
- EC2 instances terminated after this run. Lambda functions left deployed (no cost while idle).
