"""Shared inference core: loads ResNet-18 once per process and classifies one image."""
import io
import time

_t0 = time.perf_counter()

import torch
from PIL import Image
from torchvision.models import ResNet18_Weights, resnet18

_weights = ResNet18_Weights.DEFAULT
_model = resnet18(weights=_weights).eval()
_preprocess = _weights.transforms()
_labels = _weights.meta["categories"]

# Time spent importing torch + loading weights; reported on cold starts.
LOAD_MS = (time.perf_counter() - _t0) * 1000


def predict(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    x = _preprocess(img).unsqueeze(0)
    with torch.inference_mode():
        logits = _model(x)
    return _labels[int(logits.argmax())]
