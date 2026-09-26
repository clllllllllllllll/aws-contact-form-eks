"""Bounded status and diagnostic filters for the database setup Job."""

POD_PHASES = {"Pending", "Running", "Succeeded", "Failed", "Unknown"}
CONTAINER_REASONS = {
    "Completed",
    "ContainerCannotRun",
    "CrashLoopBackOff",
    "CreateContainerError",
    "ErrImagePull",
    "Error",
    "ImagePullBackOff",
    "OOMKilled",
}


def database_job_state(job):
    """Classify a named Job using terminal conditions, not failure counts."""
    if not job:
        return "absent"
    conditions = (job.get("status") or {}).get("conditions") or []
    for condition in conditions:
        if condition.get("type") == "Failed" and condition.get("status") in (True, "True"):
            return "failed"
    for condition in conditions:
        if condition.get("type") == "Complete" and condition.get("status") in (True, "True"):
            return "complete"
    return "running"


def _count(value):
    return value if type(value) is int and value >= 0 else 0


def database_job_diagnostics(job, pods):
    """Return only status fields that cannot contain logs or secret values."""
    status = (job or {}).get("status") or {}
    result = {
        "active": _count(status.get("active")),
        "failed": _count(status.get("failed")),
        "succeeded": _count(status.get("succeeded")),
        "pod_count": len(pods or []),
        "pods": [],
    }
    for pod in (pods or [])[:5]:
        pod_status = pod.get("status") or {}
        phase = pod_status.get("phase")
        container = next(
            (item for item in (pod_status.get("containerStatuses") or [])
             if item.get("name") == "setup"),
            {},
        )
        container_state = container.get("state") or {}
        terminated = container_state.get("terminated") or {}
        waiting = container_state.get("waiting") or {}
        reason = terminated.get("reason") or waiting.get("reason")
        exit_code = terminated.get("exitCode")
        result["pods"].append({
            "phase": phase if phase in POD_PHASES else "Unknown",
            "setup_reason": reason if reason in CONTAINER_REASONS else "unavailable",
            "setup_exit_code": _count(exit_code) if exit_code is not None else None,
        })
    return result


class FilterModule:
    def filters(self):
        return {
            "database_job_state": database_job_state,
            "database_job_diagnostics": database_job_diagnostics,
        }
