import os

from hypothesis import HealthCheck, settings

settings.register_profile(
    "ci", derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile("dev", deadline=None)
settings.load_profile("ci" if os.environ.get("CI") else "dev")
