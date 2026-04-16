FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT_DASHBOARD_HOST=0.0.0.0 \
    PORT_DASHBOARD_PORT=5001

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY port_project_dashboard.py ./

EXPOSE 5001

CMD ["python", "port_project_dashboard.py"]