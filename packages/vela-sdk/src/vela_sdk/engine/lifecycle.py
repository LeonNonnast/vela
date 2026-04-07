"""Lifecycle checking for workflow runs."""

import re
from typing import Optional

from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus
from vela_sdk.schemas.workflow import LifecycleDefinition


class LifecycleChecker:
    """Checks lifecycle rules and determines if a run's status should change."""

    @staticmethod
    def check_lifecycle(
        run: WorkflowRunState,
        lifecycle: Optional[LifecycleDefinition],
    ) -> Optional[WorkflowRunStatus]:
        """Check if lifecycle rules require a status change.

        Returns new status or None.
        """
        if not lifecycle:
            return None

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        updated = run.updated_at

        if not updated:
            return None

        # Ensure updated is timezone-aware
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)

        hours_since_update = (now - updated).total_seconds() / 3600

        if lifecycle.auto_cancel_after:
            cancel_hours = _parse_duration_hours(lifecycle.auto_cancel_after)
            if (
                cancel_hours is not None
                and hours_since_update > cancel_hours
                and run.status == WorkflowRunStatus.ACTIVE
            ):
                return WorkflowRunStatus.CANCELLED

        return None


def _parse_duration_hours(duration_str: str) -> Optional[float]:
    """Parse a duration string like '48h', '30d', '90d' into hours."""
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(h|d)$", duration_str.strip())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return value * 24
    return value
