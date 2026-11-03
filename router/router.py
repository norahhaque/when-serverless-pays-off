"""Hybrid router: fill a fixed pool of N containers first, overflow to Lambda.

A container is "full" when it has CAP requests in flight. Pick CAP from the
calibration run with Little's law: CAP ~= (max RPS under SLO) x (service time in s).

  CONTAINERS=http://10.0.0.5:8080,http://10.0.0.6:8080 CAP=2 \
  LAMBDA_URL=https://XXXX.lambda-url.us-east-1.on.aws/ \
  uvicorn router.router:app --host 0.0.0.0 --port 8000
"""
import os

import httpx
from fastapi import FastAPI, Request, Response

CONTAINERS = [c for c in os.environ.get("CONTAINERS", "").split(",") if c]
CAP = int(os.environ.get("CAP", 2))
LAMBDA_URL = os.environ["LAMBDA_URL"]

app = FastAPI()
client = httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=1000))
# Single event loop, so plain counters are safe without locks.
inflight = {c: 0 for c in CONTAINERS}
routed = {"ec2": 0, "lambda": 0}


@app.post("/predict")
async def route(request: Request):
    body = await request.body()
    headers = {"content-type": "application/json"}
    target = min(CONTAINERS, key=inflight.get) if CONTAINERS else None

    if target is not None and inflight[target] < CAP:
        backend = "ec2"
        inflight[target] += 1
        try:
            r = await client.post(f"{target}/predict", content=body, headers=headers)
        finally:
            inflight[target] -= 1
    else:
        backend = "lambda"
        r = await client.post(LAMBDA_URL, content=body, headers=headers)

    routed[backend] += 1
    return Response(r.content, status_code=r.status_code,
                    media_type="application/json", headers={"x-backend": backend})


@app.get("/stats")
def stats():
    return {"inflight": inflight, "routed": routed, "cap": CAP}
