FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir httpx==0.28.1 matplotlib==3.10.1 nvidia-ml-py==12.570.86
COPY bench /app/bench
COPY eval /app/eval
CMD ["python", "/app/bench/run.py"]