#!/bin/sh

set -e   # exit immediately on any error

echo "==> Waiting for database to be ready..."
# Double-check connectivity before running migrate
python -c "
import os, time, psycopg2
for i in range(30):
    try:
        psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
        )
        print('Database connection established.')
        break
    except psycopg2.OperationalError:
        print(f'Attempt {i+1}/30 — waiting...')
        time.sleep(2)
else:
    print('ERROR: Could not connect to database after 30 attempts.')
    exit(1)
"

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Seeding SQL data (skips if data already exists)..."
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rag_project.settings')
django.setup()
from rag_app.models import Company
if Company.objects.count() == 0:
    print('No data found — running SQL seeder...')
    from rag_app.ingestion.seed_sql import run
    run()
else:
    print(f'SQL data already present ({Company.objects.count()} companies) — skipping.')
"

echo "==> Seeding vector data (skips if data already exists)..."
python -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_store')
try:
    col = client.get_collection('financial_regulatory_kb')
    count = col.count()
    if count == 0:
        raise ValueError('empty')
    print(f'Vector data already present ({count} documents) — skipping.')
except Exception:
    print('No vector data found — running vector seeder...')
    import django, os, sys
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rag_project.settings')
    django.setup()
    from rag_app.ingestion.seed_vector import run
    run()
"

echo "==> Starting Django development server..."
exec python manage.py runserver 0.0.0.0:8000