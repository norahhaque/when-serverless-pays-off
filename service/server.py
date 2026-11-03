"""FastAPI entry point for the always-on container (EC2)."""
import base64
import time

from fastapi import FastAPI
from pydantic import BaseModel

from model import LOAD_MS, predict

app = FastAPI()


class PredictRequest(BaseModel):
    image: str  # base64-encoded JPEG/PNG


@app.get("/health")
def health():
    return {"ok": True, "model_load_ms": LOAD_MS}


@app.post("/predict")
def predict_route(req: PredictRequest):
    t = time.perf_counter()
    label = predict(base64.b64decode(req.image))
    return {
        "label": label,
        "inference_ms": (time.perf_counter() - t) * 1000,
        "cold": False,
        "backend": "ec2",
    }
