FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir flask flask-sock

COPY . .

EXPOSE 8888

CMD ["python3", "dashboard/live_server.py"]
