from django.conf import settings

from . import clock


def demo_clock(request):
  if not getattr(settings, "DEMO_MODE", False):
    return {}
  return {"demo_time": clock.localtime(), "demo_session": settings.DEMO_SESSION}
