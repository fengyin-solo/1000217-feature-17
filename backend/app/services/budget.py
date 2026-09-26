"""预算科目业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "budget"
REQUIRED_FIELDS = ["科目编号", "科目名称", "费用类别"]
STATUS_ORDER = ["待审批", "已批复", "执行中", "已超支"]
ACTION_RULES = {"提交审批": "已批复", "确认批复": "执行中", "标记超支": "已超支"}
NEGATIVE_ACTIONS = ["标记超支"]
MONEY_FIELDS = ["预算金额", "已用金额", "剩余额度"]


def _to_number(value: Any) -> float | None:
    """把接口里的金额字段解析成数字；空值或脏数据返回 None，由调用方决定口径。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class BudgetService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        name: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        remaining_min: float | None = None,
        remaining_max: float | None = None,
    ) -> list[dict[str, Any]]:
        """组合筛选的唯一入口：列表、合计、导出都走这里，保证三者口径一致。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("科目编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if name:
            rows = [row for row in rows if name in str(row.get("科目名称", ""))]
        if category:
            rows = [row for row in rows if category in str(row.get("费用类别", ""))]
        if owner:
            rows = [row for row in rows if owner in str(row.get("负责人", ""))]
        if remaining_min is not None or remaining_max is not None:
            rows = [
                row for row in rows
                if self._remaining_in_range(row, remaining_min, remaining_max)
            ]
        return rows

    @staticmethod
    def _remaining_in_range(
        row: dict[str, Any],
        remaining_min: float | None,
        remaining_max: float | None,
    ) -> bool:
        remaining = _to_number(row.get("剩余额度"))
        if remaining is None:
            return False
        if remaining_min is not None and remaining < remaining_min:
            return False
        if remaining_max is not None and remaining > remaining_max:
            return False
        return True

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        name: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        remaining_min: float | None = None,
        remaining_max: float | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(
            keyword=keyword,
            status=status,
            name=name,
            category=category,
            owner=owner,
            remaining_min=remaining_min,
            remaining_max=remaining_max,
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summarize(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        name: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        remaining_min: float | None = None,
        remaining_max: float | None = None,
    ) -> dict[str, Any]:
        """按当前筛选条件汇总金额合计；与列表、导出共用同一套过滤口径。"""
        rows = self._filter_rows(
            keyword=keyword,
            status=status,
            name=name,
            category=category,
            owner=owner,
            remaining_min=remaining_min,
            remaining_max=remaining_max,
        )

        def total_of(field: str) -> float:
            return round(sum(num for row in rows if (num := _to_number(row.get(field))) is not None), 2)

        return {
            "total": len(rows),
            "预算总额": total_of("预算金额"),
            "已用金额": total_of("已用金额"),
            "剩余额度": total_of("剩余额度"),
            "超支科目": sum(1 for row in rows if row.get("status") == "已超支"),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["负责人"] = str(values.get("负责人") or "").strip()
        entry["预算金额"] = _to_number(values.get("预算金额")) or 0
        entry["已用金额"] = _to_number(values.get("已用金额")) or 0
        entry["剩余额度"] = round(entry["预算金额"] - entry["已用金额"], 2)
        entry["超支原因"] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["科目状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        reason: str | None = None,
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
        entry["科目状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "标记超支":
            # 超支原因允许留空：留空的记录之后仍能正常查看，只是原因显示为占位符
            entry["超支原因"] = (reason or "").strip()
        return entry, f"预算科目已{action}"
