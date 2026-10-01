import time
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.workflows.engine import (
    load_workflows_from_disk,
    save_workflows_to_disk,
    get_builtin_workflow_templates,
    WorkflowExecutionEngine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["可视化节点编排工作流"])


class WorkflowPayload(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    cron: Optional[str] = "0 18 * * 5"
    is_scheduled: Optional[bool] = False
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("")
async def list_workflows():
    """获取所有已保存的可视化工作流与模版清单"""
    workflows = load_workflows_from_disk()
    return {"workflows": workflows}


@router.post("")
async def save_workflow(payload: WorkflowPayload):
    """保存或更新工作流配置"""
    workflows = load_workflows_from_disk()
    existing_idx = next((i for i, w in enumerate(workflows) if w["id"] == payload.id), -1)

    wf_dict = payload.model_dump()
    wf_dict["updated_at"] = int(time.time())

    if existing_idx >= 0:
        workflows[existing_idx] = wf_dict
    else:
        wf_dict["created_at"] = int(time.time())
        workflows.append(wf_dict)

    success = save_workflows_to_disk(workflows)
    if not success:
        raise HTTPException(status_code=500, detail="保存工作流配置失败")

    return {"success": True, "workflow": wf_dict}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """删除指定工作流"""
    workflows = load_workflows_from_disk()
    filtered = [w for w in workflows if w["id"] != workflow_id]
    if len(filtered) == len(workflows):
        raise HTTPException(status_code=404, detail="未找到该工作流")

    save_workflows_to_disk(filtered)
    return {"success": True, "message": f"已成功删除工作流 {workflow_id}"}


@router.post("/run")
async def run_workflow(payload: WorkflowPayload):
    """
    单次在线触发执行可视化工作流 DAG 拓扑管道。
    按顺序执行各个节点，并返回每个节点的耗时、输入输出与执行日志。
    """
    try:
        result = await WorkflowExecutionEngine.execute_workflow(payload.model_dump())
        return result
    except Exception as e:
        logger.error(f"工作流执行异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"工作流执行中断: {str(e)}")


@router.post("/{workflow_id}/schedule")
async def toggle_workflow_schedule(workflow_id: str, enable: bool):
    """开启或关闭工作流的周期性自动调度"""
    workflows = load_workflows_from_disk()
    found = False
    for w in workflows:
        if w["id"] == workflow_id:
            w["is_scheduled"] = enable
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="未找到指定工作流")

    save_workflows_to_disk(workflows)
    return {
        "success": True,
        "workflow_id": workflow_id,
        "is_scheduled": enable,
        "message": "已开启周期性定时调度" if enable else "已关闭周期性定时调度",
    }
