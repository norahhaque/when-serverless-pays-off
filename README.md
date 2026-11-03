# When Does Serverless Pay Off?

Cost–latency tradeoffs and a hybrid design for ML inference serving (CSCI 5144).
Norah Haque, Aymah Sohaib.

We serve one ResNet-18 image classifier on **AWS Lambda** and on **always-on EC2 containers**,
then measure cost per 1,000 requests, p50/p99 latency, and cold-start rate under steady and bursty
load. From that we find the request rate where containers become cheaper (the crossover) and evaluate a
**hybrid router** that fills N containers and sends overflow to Lambda.

## Layout

| Path | What it is |
|---|---|
| `service/model.py` | Shared inference core (loads ResNet-18 once, classifies one image) |
| `service/lambda_handler.py` | Lambda entry point (Function URL or direct invoke) |
| `service/server.py` | FastAPI entry point for EC2 |
| `Dockerfile` | **One image for both** (Lambda base image; EC2 overrides the entrypoint) |
| `infra/` | Deploy Lambda (ECR + 3 memory sizes + Function URLs), set up EC2, tear down |
| `loadgen/locustfile.py` | Steady / bursty load shapes (`MODE`, `RATE`, `BURST_MULT`, ...) |
| `scripts/probe.py` | Sequential latency probe for calibration |
| `scripts/cold_start.py` | Forces Lambda cold starts and records cold vs. warm latency |
| `router/router.py` | Hybrid router: least-loaded container under in-flight cap, else Lambda |
| `analysis/cost_model.py` | Analytical cost model and figures (`analysis/params.json` holds inputs) |
| `results/raw/` | Measurement CSVs (committed) |
| `results/figures/` | Generated figures |

## Quick start (local, no AWS)

```bash
# Python 3.9–3.12. On macOS use /usr/bin/python3 (Homebrew's 3.15 breaks pip/locust).
/usr/bin/python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
docker build -t resnet-serving:local .

# EC2-style server on :8080
docker run -d --name rs-ec2 -p 8080:8080 --entrypoint python resnet-serving:local \
  -m uvicorn server:app --host 0.0.0.0 --port 8080
.venv/bin/python scripts/probe.py --url http://localhost:8080/predict -n 30 --out results/raw/local_probe.csv

# Lambda-style (runtime interface emulator) on :9000
docker run -d --name rs-lambda -p 9000:8080 resnet-serving:local
curl -X POST localhost:9000/2015-03-31/functions/function/invocations -d "{\"image\":\"$(base64 -i data/sample.jpg)\"}"

# Cost model figures
.venv/bin/python analysis/cost_model.py
```

## On AWS

```bash
./infra/deploy_lambda.sh                       # prints one Function URL per memory size
.venv/bin/python scripts/cold_start.py --functions resnet18-1024 resnet18-2048 resnet18-3008 \
    --trials 10 --out results/raw/cold_start.csv
# EC2: launch c6i.large (AL2023) with an ECR-read role, copy infra/ec2_setup.sh, run it.
MODE=steady RATE=10 DURATION=300 .venv/bin/locust -f loadgen/locustfile.py --headless \
    --host http://EC2_IP:8080 --csv results/raw/ec2_steady_r10
./infra/teardown.sh                            # when done
```

Run the load generator from an EC2 instance in the same region, not a laptop, for the real experiments.

## Status

See [PLAN.md](PLAN.md).
