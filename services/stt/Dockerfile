FROM python:3.12-slim
ARG GPU=0
WORKDIR /srv
COPY requirements.txt requirements-gpu.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$GPU" = "1" ]; then pip install --no-cache-dir -r requirements-gpu.txt; fi
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib
COPY main.py stream.py ./
RUN useradd -r -u 10001 app && mkdir -p /models /tmp/stt && chown app /models /tmp/stt
USER app
ENV HF_HOME=/models
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
