"""预算科目业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "budget"
REQUIRED_FIELDS = ["科目编号", "科目名称", "费用类别"]
# 金额类字段统一转数值，便于做区间筛选与合计；读不出来时按 None 处理而不是报错。
NUMERIC_FIELDS = ["预算金额", "已用金额", "剩余额度"]
STATUS_ORDER = ["待审批", "已批复", "执行中", "已超支"]
ACTION_RULES = {"提交审批": "已批复", "确认批复": "执行中", "标记超支": "已超支"}
NEGATIVE_ACTIONS = ["标记超支"]


def to_number(value: Any) -> float | None:
    """把字符串/数字金额转成 float；空值或无法解析的内容返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BudgetService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        name: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        remaining_min: float | None = None,
        remaining_max: float | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """按科目名称、费用类别、负责人、剩余额度区间组合筛选；各条件之间为“且”关系。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("科目编号", ""))]
        if name:
            rows = [row for row in rows if name in str(row.get("科目名称", ""))]
        if category:
            rows = [row for row in rows if str(row.get("费用类别", "")) == category]
        if owner:
            rows = [row for row in rows if str(row.get("负责人", "")) == owner]
        if remaining_min is not None:
            rows = [
                row for row in rows
                if (amount := to_number(row.get("剩余额度"))) is not None and amount >= remaining_min
            ]
        if remaining_max is not None:
            rows = [
                row for row in rows
                if (amount := to_number(row.get("剩余额度"))) is not None and amount <= remaining_max
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> dict[str, float | int]:
        """列表合计：始终基于全部科目统计，不随筛选条件变化。"""
        rows = store.rows(MODULE)
        budget_total = sum(amount for row in rows if (amount := to_number(row.get("预算金额"))) is not None)
        used_total = sum(amount for row in rows if (amount := to_number(row.get("已用金额"))) is not None)
        over_count = sum(1 for row in rows if row.get("status") == STATUS_ORDER[-1])
        return {"预算总额": budget_total, "已用金额": used_total, "超支科目": over_count, "科目总数": len(rows)}

    def filter_options(self) -> dict[str, list[str]]:
        """费用类别与负责人的可选项，供前端做精确筛选下拉。"""
        rows = store.rows(MODULE)
        categories = sorted({str(row.get("费用类别", "")).strip() for row in rows if row.get("费用类别")})
        owners = sorted({str(row.get("负责人", "")).strip() for row in rows if row.get("负责人")})
        return {"费用类别": categories, "负责人": owners}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        if values.get("负责人"):
            entry["负责人"] = values.get("负责人")
        for field in NUMERIC_FIELDS:
            amount = to_number(values.get(field))
            if amount is not None:
                entry[field] = amount
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, reason: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"预算科目 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于预算科目可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "标记超支":
            # 超支原因允许为空：空原因的超支记录依旧保留并可查看。
            entry["超支原因"] = (reason or "").strip()
        return entry, f"预算科目已{action}"
