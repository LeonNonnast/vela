"""Workflow and run API endpoints for the dashboard."""

import json
import os
from typing import Optional

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from src.shared.config import VELA_MODULES_DIR, VELA_WORKFLOWS_DIR
from src.shared.db.database import async_session_factory
from src.shared.db.models import WorkflowRun, WorkflowRunStatus
from src.shared.repositories.workflow_repository import WorkflowRepository
from src.shared.services.workflow_loader import load_workflows

logger = structlog.get_logger()

router = APIRouter(tags=["workflows"])


def _load_all_workflows() -> list[dict]:
    """Load all workflow definitions with module metadata."""
    workflows = []

    modules_dir = os.path.abspath(VELA_MODULES_DIR)
    if os.path.isdir(modules_dir):
        for module_name in sorted(os.listdir(modules_dir)):
            wf_dir = os.path.join(modules_dir, module_name, "workflows")
            if os.path.isdir(wf_dir):
                loaded = load_workflows(wf_dir)
                for wf_id, wf_def in loaded.items():
                    workflows.append({
                        "id": wf_id,
                        "name": wf_def.name,
                        "version": wf_def.version,
                        "description": wf_def.description,
                        "step_count": len(wf_def.steps),
                        "module": module_name,
                        "_def": wf_def,
                    })

    if os.path.isdir(VELA_WORKFLOWS_DIR):
        loaded = load_workflows(VELA_WORKFLOWS_DIR)
        for wf_id, wf_def in loaded.items():
            workflows.append({
                "id": wf_id,
                "name": wf_def.name,
                "version": wf_def.version,
                "description": wf_def.description,
                "step_count": len(wf_def.steps),
                "module": "user",
                "_def": wf_def,
            })

    return workflows


def _serialize_run(run) -> dict:
    """Convert a WorkflowRun ORM object to a JSON-safe dict."""
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_version": run.workflow_version,
        "project_id": run.project_id,
        "current_step": run.current_step,
        "status": run.status.value if run.status else None,
        "params": json.loads(run.params) if run.params else None,
        "state_data": json.loads(run.state_data) if run.state_data else None,
        "parent_run_id": run.parent_run_id,
        "parent_step_id": run.parent_step_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/workflows")
async def api_list_workflows() -> JSONResponse:
    """List all loaded workflow definitions with active run counts."""
    try:
        all_wfs = _load_all_workflows()

        # Get active run counts per workflow_id
        active_counts: dict[str, int] = {}
        try:
            async with async_session_factory() as session:
                stmt = (
                    select(WorkflowRun.workflow_id, func.count())
                    .where(WorkflowRun.status.in_([WorkflowRunStatus.ACTIVE, WorkflowRunStatus.PAUSED]))
                    .group_by(WorkflowRun.workflow_id)
                )
                rows = (await session.execute(stmt)).all()
                for wf_id, count in rows:
                    active_counts[wf_id] = count
        except Exception as e:
            logger.warning("workflows.active_counts_failed", error=str(e))

        workflows = []
        for wf in all_wfs:
            wf_id = wf["id"]
            base_id = wf_id.split("@")[0]
            # Runs store workflow_id without @version, definitions have it with
            run_count = active_counts.get(wf_id, 0) or active_counts.get(base_id, 0)
            wf_def = wf["_def"]
            workflows.append({
                "id": wf_id,
                "name": wf["name"],
                "version": wf["version"],
                "description": wf["description"],
                "step_count": wf["step_count"],
                "module": wf["module"],
                "active_run_count": run_count,
                "tools": [t.model_dump(mode="json") for t in wf_def.tools] if wf_def.tools else [],
            })

        return JSONResponse({"workflows": workflows, "count": len(workflows)})
    except Exception as e:
        logger.error("api.workflows.error", error=str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/workflows/{workflow_id:path}")
async def api_get_workflow(workflow_id: str) -> JSONResponse:
    """Get full workflow definition including steps, dependencies, and resources."""
    try:
        all_wfs = _load_all_workflows()
        # Match by exact ID or by base ID (without @version suffix)
        match = next((wf for wf in all_wfs if wf["id"] == workflow_id), None)
        if not match:
            match = next(
                (wf for wf in all_wfs if wf["id"].split("@")[0] == workflow_id),
                None,
            )
        if not match:
            return JSONResponse({"error": "Workflow not found"}, status_code=404)

        wf_def = match["_def"]
        data = wf_def.model_dump(mode="json")
        data["module"] = match["module"]
        return JSONResponse({"workflow": data})
    except Exception as e:
        logger.error("api.workflows.get.error", error=str(e), workflow_id=workflow_id)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/runs")
async def api_list_runs(
    status: Optional[str] = Query(None, description="Filter by status: active, paused, completed, cancelled"),
    workflow_id: Optional[str] = Query(None, description="Filter by workflow ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    """List workflow runs with optional filters."""
    try:
        status_enum = None
        if status:
            try:
                status_enum = WorkflowRunStatus(status.lower())
            except ValueError:
                return JSONResponse(
                    {"error": f"Invalid status: {status}. Must be one of: active, paused, completed, cancelled"},
                    status_code=400,
                )

        async with async_session_factory() as session:
            repo = WorkflowRepository(session)
            runs = await repo.list_runs(
                workflow_id=workflow_id,
                project_id=project_id,
                status=status_enum,
                limit=limit,
                offset=offset,
            )
            return JSONResponse({
                "runs": [_serialize_run(r) for r in runs],
                "count": len(runs),
            })
    except Exception as e:
        logger.error("api.runs.list.error", error=str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/runs/{run_id}")
async def api_get_run(run_id: str) -> JSONResponse:
    """Get details of a specific workflow run including child runs."""
    try:
        async with async_session_factory() as session:
            repo = WorkflowRepository(session)
            run = await repo.get_by_id(run_id)
            if not run:
                return JSONResponse({"error": "Run not found"}, status_code=404)

            # Find child runs (sub-workflows spawned by this run)
            child_runs = []
            try:
                child_stmt = (
                    select(WorkflowRun)
                    .where(WorkflowRun.parent_run_id == run_id)
                    .order_by(WorkflowRun.started_at)
                )
                child_rows = (await session.execute(child_stmt)).scalars().all()
                child_runs = [_serialize_run(r) for r in child_rows]
            except Exception as e:
                logger.warning("workflows.child_runs_failed", error=str(e))

            return JSONResponse({
                "run": _serialize_run(run),
                "child_runs": child_runs,
            })
    except Exception as e:
        logger.error("api.runs.get.error", error=str(e), run_id=run_id)
        return JSONResponse({"error": str(e)}, status_code=500)
