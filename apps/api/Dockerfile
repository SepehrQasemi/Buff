FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        fastapi>=0.110.0 \
        uvicorn>=0.27.0 \
        pandas>=1.5.0 \
        pyarrow==14.0.2 \
        pydantic>=2.5.0 \
        PyYAML>=6.0

COPY apps /app/apps

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
