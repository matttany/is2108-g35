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
  cycle_sessions = {"washing": [], "drying": []}
  for session in sessions:
    stage = {"washer": "washing", "dryer": "drying"}.get(session.machine.machine_type)
    if stage is not None:
      cycle_sessions[stage].append(session)

  completed_cycles = set()
  for stage, stage_sessions in cycle_sessions.items():
    if stage_sessions:
      # Starting a cycle does not mean it has been completed.
      if all(session.ended_at is not None for session in stage_sessions):
        completed_cycles.add(stage)
        timestamps[stage] = max(session.ended_at for session in stage_sessions)
      else:
        timestamps[stage] = min(session.started_at for session in stage_sessions)

  stage_codes = [code for code, label in ORDER_STAGES]
  current_index = stage_codes.index(order.status) if order.status in stage_codes else None
  stopped = order.status in ["cancelled", "rejected"]
  timeline = []
  for index, (code, label) in enumerate(ORDER_STAGES):
    timestamp = timestamps.get(code)
    if code in completed_cycles:
      state = "Completed"
    elif code == order.status:
      state = "Current"
    elif code in cycle_sessions:
      state = "Not complete"
    elif timestamp is not None:
      state = "Completed"
    elif current_index is not None and index < current_index:
      state = "Completed"
    else:
      state = "Not complete"
    timeline.append({"label": label, "state": state, "timestamp": timestamp})

  if stopped:
    # Older cancellations and rejected orders may have no recorded timestamp.
    label = "Cancelled" if order.status == "cancelled" else "Rejected"
    timestamp = order.cancelled_at if order.status == "cancelled" else None
    timeline.append({"label": label, "state": "Current", "timestamp": timestamp})
  return timeline
