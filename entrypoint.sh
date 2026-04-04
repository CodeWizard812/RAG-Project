#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Creating superuser if not exists..."
python -c "
import django, os
django.setup()
from django.contrib.auth.models import User
username = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin')
password = os.getenv('DJANGO_SUPERUSER_PASSWORD', 'changeme123')
email    = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f'Superuser created: {username}')
else:
    print(f'Superuser already exists: {username}')
"

echo "==> Seeding SQL data..."
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rag_project.settings')
django.setup()
from rag_app.models import Company
if Company.objects.count() == 0:
    from rag_app.ingestion.seed_sql import run
    run()
else:
    print(f'SQL data present ({Company.objects.count()} companies) — skipping.')
"

echo "==> Seeding vector data..."
python -c "
import chromadb, os
path = os.getenv('CHROMA_PATH', './chroma_store')
client = chromadb.PersistentClient(path=path)
try:
    col = client.get_collection('financial_regulatory_kb')
    count = col.count()
    if count == 0:
        raise ValueError('empty')
    print(f'Vector data present ({count} docs) — skipping.')
except Exception:
    print('Seeding vector data...')
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rag_project.settings')
    django.setup()
    from rag_app.ingestion.seed_vector import run
    run()
"

echo "==> Starting server..."
exec gunicorn rag_project.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --log-level info