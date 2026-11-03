"""Steady and bursty load for any backend (EC2, Lambda Function URL, or the router).

Each simulated user sends ~1 request/s, so user count == target request rate.
Request start times are Poisson (exponential gaps), so the merged stream is Poisson too.
Without that, users spawned together fire in lock-step and every second becomes one
burst of N simultaneous requests (we measured this: p50 grew as exactly 45 ms x rate).
This is closed-loop: if responses take longer than the gap, the real rate drops below
the target. Always report the *achieved* rate from Locust's CSV, not the target.

Examples:
  MODE=steady RATE=10 DURATION=300 locust -f loadgen/locustfile.py --headless \
      --host http://EC2_IP:8080 --csv results/raw/ec2_steady_r10
  MODE=burst RATE=5 BURST_MULT=5 PERIOD=600 BURST_LEN=120 DURATION=1800 TARGET_PATH=/ \
      locust -f loadgen/locustfile.py --headless --host https://XXXX.lambda-url.us-east-1.on.aws \
      --csv results/raw/lambda_burst_r5
"""
import base64
import os
import random
import time

from locust import HttpUser, LoadTestShape, task

MODE = os.environ.get("MODE", "steady")           # steady | burst
RATE = float(os.environ.get("RATE", 5))            # base requests/s
BURST_MULT = float(os.environ.get("BURST_MULT", 5))
PERIOD = float(os.environ.get("PERIOD", 600))      # seconds between burst starts
BURST_LEN = float(os.environ.get("BURST_LEN", 120))
DURATION = float(os.environ.get("DURATION", 300))
TARGET_PATH = os.environ.get("TARGET_PATH", "/predict")  # "/" for Lambda Function URLs

_here = os.path.dirname(__file__)
IMAGE_B64 = base64.b64encode(
    open(os.environ.get("IMAGE", os.path.join(_here, "..", "data", "sample.jpg")), "rb").read()
).decode()


class InferenceUser(HttpUser):
    def on_start(self):
        self._next = time.monotonic() + random.expovariate(1.0)
        time.sleep(max(0.0, self._next - time.monotonic()))  # gevent-patched: yields

    def wait_time(self):
        # Exponential gap between request *starts* (not after the response): ~1 req/s per user.
        self._next = max(self._next + random.expovariate(1.0), time.monotonic())
        return self._next - time.monotonic()

    @task
    def predict(self):
        with self.client.post(TARGET_PATH, json={"image": IMAGE_B64},
                              name="predict", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"HTTP {r.status_code}")


class Shape(LoadTestShape):
    def tick(self):
        t = self.get_run_time()
        if t > DURATION:
            return None
        rate = RATE
        if MODE == "burst" and (t % PERIOD) >= PERIOD - BURST_LEN:
            rate = RATE * BURST_MULT
        users = max(1, round(rate))
        return users, max(users, 50)  # spawn fast so bursts are sharp
