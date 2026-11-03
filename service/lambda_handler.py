"""AWS Lambda entry point. Works for Function URL requests and direct invokes."""
import base64
import json
import time

from model import LOAD_MS, predict

_cold = True


def handler(event, context):
    global _cold
    if "body" in event:  # Function URL / API Gateway event
        body = event["body"] or "{}"
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        payload = json.loads(body)
    else:  # direct invoke: event is the payload
        payload = event

    t = time.perf_counter()
    label = predict(base64.b64decode(payload["image"]))
    inference_ms = (time.perf_counter() - t) * 1000

    cold, _cold = _cold, False
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({
            "label": label,
            "inference_ms": inference_ms,
            "cold": cold,
            "model_load_ms": LOAD_MS if cold else 0.0,
            "backend": "lambda",
        }),
    }
