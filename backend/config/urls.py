from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def root(_request):
    return JsonResponse(
        {
            "service": "wayline-api",
            "status": "ok",
            "endpoints": {
                "health": "/api/health/",
                "places": "/api/places/?q=",
                "route_plans": "/api/route-plans/",
                "thresholds": "/api/thresholds/",
            },
        }
    )


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", root),
    path("health", health),
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
]

