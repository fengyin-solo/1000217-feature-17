"""预算科目接口：维护预算科目，覆盖提交审批、确认批复、标记超支等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.budget import to_number
from app.services.budget import BudgetService

router = APIRouter(prefix="/api/budget", tags=["预算科目"])

service = BudgetService()

LIST_FIELDS = ["科目编号", "科目名称", "费用类别", "预算金额", "已用金额", "剩余额度", "负责人", "审批人", "科目状态", "超支原因"]
STATUSES = ["待审批", "已批复", "执行中", "已超支"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按科目编号检索"),
    name: str | None = Query(default=None, description="按科目名称模糊检索"),
    category: str | None = Query(default=None, description="按费用类别精确筛选"),
    owner: str | None = Query(default=None, description="按负责人精确筛选"),
    remaining_min: str | None = Query(default=None, description="剩余额度下限"),
    remaining_max: str | None = Query(default=None, description="剩余额度上限"),
    status: str | None = Query(default=None, description="待审批、已批复、执行中、已超支"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按科目名称、费用类别、负责人、剩余额度区间组合过滤；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    minimum = to_number(remaining_min) if remaining_min is not None else None
    maximum = to_number(remaining_max) if remaining_max is not None else None
    if remaining_min is not None and minimum is None:
        raise HTTPException(status_code=400, detail="剩余额度下限需要是数字")
    if remaining_max is not None and maximum is None:
        raise HTTPException(status_code=400, detail="剩余额度上限需要是数字")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(status_code=400, detail="剩余额度下限不能大于上限")
    items, total = service.list_entries(
        keyword=keyword,
        name=name,
        category=category,
        owner=owner,
        remaining_min=minimum,
        remaining_max=maximum,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    """列表合计：始终统计全部科目，不随筛选条件变化；另返回费用类别、负责人筛选项。"""
    return {"summary": service.summary(), "options": service.filter_options()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出预算科目清单：导出范围固定为全部科目，不受列表筛选条件影响。"""
    items, total = service.list_entries(page=1, size=10000)
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
    """对单条预算科目执行提交审批、确认批复、标记超支；不允许的动作会被拦下并说明原因。

    标记超支时可携带超支原因；原因为空也允许，记录照常保留与查看。
    """
    action = str(payload.values.get("action") or "").strip()
    reason = payload.values.get("超支原因")
    reason = str(reason).strip() if reason is not None else ""
    entry, message = service.run_action(entry_id, action, reason)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
