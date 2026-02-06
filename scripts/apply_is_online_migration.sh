#!/bin/bash
# Apply migration 0009_user_is_online (adds core_user.is_online column).
# Run this on the server after deploying, e.g.:
#   cd /home/luna/projects/MyCafe/My-Cafe-Server
#   source env/bin/activate
#   bash scripts/apply_is_online_migration.sh

set -e
cd "$(dirname "$0")/.."
source env/bin/activate 2>/dev/null || true
echo "Applying core migrations..."
python manage.py migrate core
echo "Done. Restart gunicorn (e.g. sudo systemctl restart gunicorn) if running on server."
