from django.db import models


class RoutePlan(models.Model):
    """A persisted weather-aware route plan (inputs + full computed result)."""

    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    depart_at = models.DateTimeField()
    load_lbs = models.FloatField()
    sample_interval_miles = models.PositiveSmallIntegerField(default=25)
    recommended_route = models.CharField(max_length=32, blank=True)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.origin} -> {self.destination}"
