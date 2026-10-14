from rest_framework import serializers

from .constants import DEFAULT_SAMPLE_INTERVAL_MILES, HEATMAP_HOURS, LOAD_LIMIT_LBS, SAMPLE_INTERVALS
from .models import RoutePlan


class RoutePlanRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=255, trim_whitespace=True)
    destination = serializers.CharField(max_length=255, trim_whitespace=True)
    depart_at = serializers.DateTimeField()
    load_lbs = serializers.FloatField(min_value=0, max_value=LOAD_LIMIT_LBS)
    sample_interval_miles = serializers.ChoiceField(
        choices=list(SAMPLE_INTERVALS), default=DEFAULT_SAMPLE_INTERVAL_MILES
    )
    heatmap_hours = serializers.IntegerField(min_value=6, max_value=HEATMAP_HOURS, default=HEATMAP_HOURS)

    def validate(self, attrs: dict) -> dict:
        origin = attrs["origin"].strip()
        destination = attrs["destination"].strip()
        if origin.lower() == destination.lower():
            raise serializers.ValidationError(
                {"destination": "Origin and destination must be different."}
            )
        attrs["origin"] = origin
        attrs["destination"] = destination
        return attrs


class RoutePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoutePlan
        fields = [
            "id",
            "origin",
            "destination",
            "depart_at",
            "load_lbs",
            "sample_interval_miles",
            "recommended_route",
            "created_at",
        ]
        read_only_fields = fields
