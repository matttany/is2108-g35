from math import ceil


CYCLE_WARNING_MINUTES = 5
RETURN_WARNING_MINUTES = 15


def cycle_reminder(session, now):
  if session.ended_at is not None:
    return None

  seconds = (session.expected_end - now).total_seconds()
  if seconds < 0:
    minutes = ceil(-seconds / 60)
    return {
      "style": "danger",
      "message": f"Cycle overdue by {minutes} min. Unload the machine and record completion as soon as possible.",
    }
  if seconds == 0:
    return {
      "style": "warning",
      "message": "Cycle is now completed. Unload the machine and record completion after.",
    }

  minutes = ceil(seconds / 60)
  return {
    "style": "warning" if seconds <= CYCLE_WARNING_MINUTES * 60 else "info",
    "message": f"About {minutes} min until the cycle is due.",
  }


def return_reminder(deadline, now):
  seconds = (deadline - now).total_seconds()
  if seconds < 0:
    return {
      "style": "danger",
      "message": f"Return deadline passed {ceil(-seconds / 60)} min ago. Complete the return and record delivery evidence.",
    }
  if seconds == 0:
    return {"style": "warning", "message": "Return is due now."}
  if seconds <= RETURN_WARNING_MINUTES * 60:
    return {
      "style": "warning",
      "message": f"Return is due in about {ceil(seconds / 60)} min. Please ensure laundry is collected and returned on time.",
    }
  return None
