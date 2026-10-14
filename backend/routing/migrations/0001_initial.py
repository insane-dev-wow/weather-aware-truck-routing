from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RoutePlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin", models.CharField(max_length=255)),
                ("destination", models.CharField(max_length=255)),
                ("depart_at", models.DateTimeField()),
                ("load_lbs", models.FloatField()),
                ("sample_interval_miles", models.PositiveSmallIntegerField(default=25)),
                ("recommended_route", models.CharField(blank=True, max_length=32)),
                ("result", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
