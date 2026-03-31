FROM python:3.13-slim

# Prevents Python from writing .pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed by pdfplumber and psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libglib2.0-0 \
    libgl1\
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project source
COPY . .

# Create directory for ChromaDB persistent store inside the container
RUN mkdir -p /app/chroma_store

# Collect static files for Django admin
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["python", "-m", "gunicorn", "rag_project.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "120", \
     "--log-level", "info"]