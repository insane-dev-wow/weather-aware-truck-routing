from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("thresholds/", views.thresholds, name="thresholds"),
    path("places/", views.place_suggest, name="place-suggest"),
    path("route-plans/", views.create_route_plan, name="route-plan-create"),
    path("route-plans/<int:pk>/", views.route_plan_detail, name="route-plan-detail"),
]
