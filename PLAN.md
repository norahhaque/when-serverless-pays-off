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

## Milestones

- [x] Inference service, one image for both targets, verified locally
- [x] Load generator (steady/burst), probe, cold-start script
- [x] Analytical cost model + figures (assumed inputs)
- [x] Router prototype
- [ ] Lambda deployed at 1024/2048/3008 MB; concurrency limit checked
- [ ] Cold vs. warm latency per memory size (10 trials each)
- [ ] EC2 single-instance capacity curve; pick SLO and per-container cap
- [ ] Re-run cost model with measured inputs  **← midterm**
- [ ] Steady sweep, both backends, 3 reps
- [ ] Burst sweep, both backends, 3 reps
- [ ] Hybrid sweep over N; validate against the model
- [ ] Final report + presentation
