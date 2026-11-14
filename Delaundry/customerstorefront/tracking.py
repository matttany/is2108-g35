ORDER_STAGES = [
  ("requested", "Requested"),
  ("confirmed", "Confirmed"),
  ("picked_up", "Picked up"),
  ("washing", "Washing"),
  ("drying", "Drying"),
  ("out_for_return", "Out for return"),
  ("delivered", "Delivered"),
]


def get_order_timeline(order, assignment, sessions):
  # Use recorded events, never the scheduled pickup time, as progress timestamps.
  timestamps = {"requested": order.created_at}
  if assignment is not None:
    timestamps["confirmed"] = assignment.accepted_at
    if assignment.picked_up_at is not None:
      timestamps["picked_up"] = assignment.picked_up_at
    if assignment.out_for_return_at is not None:
      timestamps["out_for_return"] = assignment.out_for_return_at
    if assignment.completed_at is not None:
      timestamps["delivered"] = assignment.completed_at
  for session in sessions:
    stage = {"washer": "washing", "dryer": "drying"}.get(session.machine.machine_type)
    if stage is not None:
      timestamps[stage] = min(timestamps.get(stage, session.started_at), session.started_at)

  stage_codes = [code for code, label in ORDER_STAGES]
  current_index = stage_codes.index(order.status) if order.status in stage_codes else None
  stopped = order.status in ["cancelled", "rejected"]
  timeline = []
  for index, (code, label) in enumerate(ORDER_STAGES):
    timestamp = timestamps.get(code)
    if code == order.status:
      state = "Current"
    elif timestamp is not None:
      state = "Recorded"
    elif current_index is not None and index < current_index:
      state = "Reached"
    else:
      # A missing update does not prove that the stage has not happened.
      state = "Not recorded"
    timeline.append({"label": label, "state": state, "timestamp": timestamp})

  if stopped:
    # No cancellation/rejection timestamp exists yet; do not invent one.
    label = "Cancelled" if order.status == "cancelled" else "Rejected"
    timeline.append({"label": label, "state": "Current", "timestamp": None})
  return timeline
