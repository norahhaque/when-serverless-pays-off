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
