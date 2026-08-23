FROM python:3.12-slim
WORKDIR /opt/beo-agents
COPY control/requirements-gmail.txt /tmp/requirements-gmail.txt
RUN pip install --no-cache-dir -r /tmp/requirements-gmail.txt
ENV PYTHONUNBUFFERED=1
CMD ["python", "control/server.py"]
