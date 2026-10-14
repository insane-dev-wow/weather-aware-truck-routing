#!/usr/bin/env bash
# Render/Heroku-style build step.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
