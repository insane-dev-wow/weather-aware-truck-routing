import os

from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Vercel cold starts need a schema in /tmp before the first write.
if os.environ.get("VERCEL") or os.environ.get("VERCEL_URL"):
    try:
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
    except Exception:
        # Planning can still succeed without persistence.
        pass
