# Plan

## Re-scoped after losing a team member

| Change | Why |
|---|---|
| Autoscaled-container baseline: **dropped** | Was already "if time permits" |
| Azure trace replay: **stretch only** | Synthetic steady + periodic bursts answer RQ1–RQ3 |
| Repetitions: **3** (not 3–5) | Time and AWS budget |
| Single instance type (c6i.large), single region (us-east-1) | Keeps the sweep tractable |
| Analytical cost model validated by measurement | Lets the sweep be sparse: measure a few points, check the model fits |

## Work split

| Member | Owns |
|---|---|
| Norah | Inference service + image, Lambda deploy, cold starts, EC2 deploy, cost model |
| Aymah | Locust workloads, capacity tests, hybrid router, analysis + charts |

## Progress to midterm

| # | Step | Status |
|---|---|---|
| 1 | GitHub repo (public) | Done |
| 2a | AWS CLI installed, logged in (us-east-2) | Done |
| 2b | Budget: $25/mo, alerts at 50%, 100%, forecast 100% (credits excluded) | Done |
| 2c | Lambda concurrency increase 10 → 1000 requested | In progress (waiting on AWS) |
| 3 | Deploy Lambda (1024/2048/3008 MB) | Done |
| 4 | Cold vs. warm latency per memory size | Done |
| 5 | EC2 capacity curve; choose SLO (p99 ≤ 500 ms) | Done: default 7.8, tuned 15.3 req/s (3 reps each) |
| 6 | Cost model with measured inputs | Done |
| 7 | Steady sweep on both backends (in-region) + 2 burst tests | Done (3 reps each; EC2 terminated) |
| 8 | Slides | Done: Slot12_WhenServerlessPaysOff.pptx/.pdf (outside repo) |

## Milestones

- [x] Inference service, one image for both targets, verified locally
- [x] Load generator (steady/burst), probe, cold-start script
- [x] Analytical cost model + figures (assumed inputs)
- [x] Router prototype
- [x] Lambda deployed at 1024/2048/3008 MB; concurrency limit checked
- [x] Cold vs. warm latency per memory size (10 trials each)
- [x] EC2 single-instance capacity curve; pick SLO and per-container cap
- [x] Re-run cost model with measured inputs  **← midterm**
- [ ] Steady sweep, both backends, 3 reps
- [ ] Burst sweep, both backends, 3 reps
- [ ] Hybrid sweep over N; validate against the model
- [ ] Final report + presentation
