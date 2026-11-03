# One image for both deployments.
#   Lambda: uses the default CMD (lambda_handler.handler).
#   EC2:    docker run -p 8080:8080 --entrypoint python IMAGE -m uvicorn server:app --host 0.0.0.0 --port 8080
FROM public.ecr.aws/lambda/python:3.11

# CPU-only PyTorch keeps the image small (no CUDA libraries).
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.3.1 torchvision==0.18.1 "numpy<2" fastapi==0.115.0 uvicorn==0.30.6 pillow==10.4.0

# Bake the weights into the image so cold starts never download them.
ENV TORCH_HOME=/opt/torch
RUN python -c "from torchvision.models import resnet18, ResNet18_Weights; resnet18(weights=ResNet18_Weights.DEFAULT)"

COPY service/ ${LAMBDA_TASK_ROOT}/
CMD ["lambda_handler.handler"]
