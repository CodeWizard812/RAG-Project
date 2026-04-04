#!/bin/sh
# entrypoint.sh — lean version for Render free tier
set -e

echo "==> Waiting for database..."
python manage.py wait_for_db 2>/dev/null || python -c "
import os, time, psycopg2
url = os.getenv('DATABASE_URL', '')
for i in range(20):
    try:
        psycopg2.connect(url)
        print('Database ready.')
        break
    except Exception:
        print(f'Waiting... ({i+1}/20)')
        time.sleep(3)
"

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Creating superuser..."
python manage.py shell -c "
from django.contrib.auth.models import User
import os
u = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin')
p = os.getenv('DJANGO_SUPERUSER_PASSWORD', 'changeme123')
e = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@rag.com')
User.objects.filter(username=u).exists() or User.objects.create_superuser(u, e, p)
"

echo "==> Seeding SQL data..."
python manage.py shell -c "
from rag_app.models import Company
if Company.objects.count() == 0:
    from rag_app.ingestion.seed_sql import run
    run()
else:
    print(f'SQL: {Company.objects.count()} companies already present.')
"

echo "==> Seeding vector data..."
python manage.py shell -c "
import os, chromadb
from rag_app.utils.embeddings import GeminiEmbeddingFunction
path = os.getenv('CHROMA_PATH', './chroma_store')
client = chromadb.PersistentClient(path=path)
ef = GeminiEmbeddingFunction()
try:
    col = client.get_or_create_collection('financial_regulatory_kb', embedding_function=ef)
    if col.count() == 0:
        raise ValueError('empty')
    print(f'Vector: {col.count()} docs already present.')
except Exception:
    from rag_app.ingestion.seed_vector import run
    run()
"

echo "==> Starting gunicorn..."
exec gunicorn rag_project.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 1 \
    --timeout 120 \
    --log-level info