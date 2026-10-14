import logging
from datetime import datetime, timezone

from django.db import OperationalError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import RoutePlan
from .serializers import RoutePlanRequestSerializer, RoutePlanSerializer
from .services.directions import DirectionsError
from .services.geocoding import GeocodingError, suggest
from .services.planner import PlanRequest, build_plan
from .services.risk import band_table
from .services.types import iso
from .services.weather import WeatherError

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def thresholds(request):
    return Response(band_table())


@api_view(["GET"])
def place_suggest(request):
    query = request.query_params.get("q", "")
    try:
        results = suggest(query)
    except GeocodingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"results": results})


@api_view(["POST"])
def create_route_plan(request):
    serializer = RoutePlanRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    plan_request = PlanRequest(
        origin=data["origin"],
        destination=data["destination"],
        depart_at=data["depart_at"],
        load_lbs=data["load_lbs"],
        sample_interval_miles=data["sample_interval_miles"],
        heatmap_hours=data["heatmap_hours"],
    )

    try:
        result = build_plan(plan_request)
    except GeocodingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except (DirectionsError, WeatherError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Unexpected failure while building a route plan")
        return Response(
            {"detail": "Something went wrong while planning this route."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        saved = RoutePlan.objects.create(
            origin=data["origin"],
            destination=data["destination"],
            depart_at=data["depart_at"],
            load_lbs=data["load_lbs"],
            sample_interval_miles=data["sample_interval_miles"],
            recommended_route=result["recommendation"]["label"] or "",
            result=result,
        )
        return Response(
            {"id": saved.id, "created_at": iso(saved.created_at), **result},
            status=status.HTTP_201_CREATED,
        )
    except OperationalError:
        # Vercel /tmp may be cold or unavailable; still return the computed plan.
        logger.exception("Could not persist route plan; returning ephemeral result")
        return Response(
            {
                "id": None,
                "created_at": iso(datetime.now(timezone.utc)),
                **result,
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(["GET"])
def route_plan_detail(request, pk: int):
    try:
        plan = RoutePlan.objects.get(pk=pk)
    except RoutePlan.DoesNotExist:
        return Response(
            {"detail": "Route plan not found."}, status=status.HTTP_404_NOT_FOUND
        )

    return Response(
        {
            "id": plan.id,
            "created_at": iso(plan.created_at),
            "inputs": RoutePlanSerializer(plan).data,
            **plan.result,
        }
    )
