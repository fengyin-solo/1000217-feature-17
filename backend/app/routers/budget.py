"""预算科目接口：维护预算科目，覆盖提交审批、确认批复、标记超支等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.budget import BudgetService

router = APIRouter(prefix="/api/budget", tags=["预算科目"])

service = BudgetService()

LIST_FIELDS = ["科目编号", "科目名称", "费用类别", "负责人", "预算金额", "已用金额", "剩余额度", "科目状态"]
STATUSES = ["待审批", "已批复", "执行中", "已超支"]


def _filters(
    keyword: str | None,
    status: str | None,
    name: str | None,
    category: str | None,
    owner: str | None,
    remaining_min: float | None,
    remaining_max: float | None,
) -> dict[str, Any]:
    """列表、合计、导出共用同一组筛选参数，保证切换条件后三者范围一致。"""
    return {
        "keyword": keyword,
        "status": status,
        "name": name,
        "category": category,
        "owner": owner,
        "remaining_min": remaining_min,
        "remaining_max": remaining_max,
    }


FILTER_QUERY = {
    "keyword": Query(default=None, description="按科目编号检索"),
    "status": Query(default=None, description="待审批、已批复、执行中、已超支"),
    "name": Query(default=None, description="按科目名称模糊检索"),
    "category": Query(default=None, description="按费用类别检索"),
    "owner": Query(default=None, description="按负责人检索"),
    "remaining_min": Query(default=None, description="剩余额度下限，含边界"),
    "remaining_max": Query(default=None, description="剩余额度上限，含边界"),
}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = FILTER_QUERY["keyword"],
    status: str | None = FILTER_QUERY["status"],
    name: str | None = FILTER_QUERY["name"],
    category: str | None = FILTER_QUERY["category"],
    owner: str | None = FILTER_QUERY["owner"],
    remaining_min: float | None = FILTER_QUERY["remaining_min"],
    remaining_max: float | None = FILTER_QUERY["remaining_max"],
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按科目名称、费用类别、负责人与剩余额度范围组合过滤；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if remaining_min is not None and remaining_max is not None and remaining_min > remaining_max:
        raise HTTPException(status_code=400, detail="剩余额度下限不能大于上限，请调整范围")
    filters = _filters(keyword, status, name, category, owner, remaining_min, remaining_max)
    items, total = service.list_entries(page=page, size=size, **filters)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summarize_entries(
    keyword: str | None = FILTER_QUERY["keyword"],
    status: str | None = FILTER_QUERY["status"],
    name: str | None = FILTER_QUERY["name"],
    category: str | None = FILTER_QUERY["category"],
    owner: str | None = FILTER_QUERY["owner"],
    remaining_min: float | None = FILTER_QUERY["remaining_min"],
    remaining_max: float | None = FILTER_QUERY["remaining_max"],
) -> dict[str, Any]:
    """按当前筛选条件汇总预算总额、已用金额、剩余额度与超支科目数，与列表口径一致。"""
    filters = _filters(keyword, status, name, category, owner, remaining_min, remaining_max)
    return service.summarize(**filters)


@router.get("/export")
def export_entries(
    keyword: str | None = FILTER_QUERY["keyword"],
    status: str | None = FILTER_QUERY["status"],
    name: str | None = FILTER_QUERY["name"],
    category: str | None = FILTER_QUERY["category"],
    owner: str | None = FILTER_QUERY["owner"],
    remaining_min: float | None = FILTER_QUERY["remaining_min"],
    remaining_max: float | None = FILTER_QUERY["remaining_max"],
) -> dict[str, Any]:
    """导出预算科目清单：返回当前过滤条件下的全量数据，范围与列表保持一致。"""
    filters = _filters(keyword, status, name, category, owner, remaining_min, remaining_max)
    items, total = service.list_entries(page=1, size=10000, **filters)
    return {"module": "budget", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条预算科目明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"预算科目 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条预算科目，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="预算科目已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条预算科目执行提交审批、确认批复、标记超支；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    reason = payload.values.get("超支原因")
    entry, message = service.run_action(
        entry_id, action, reason=None if reason is None else str(reason)
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
