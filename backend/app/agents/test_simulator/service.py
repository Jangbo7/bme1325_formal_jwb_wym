from __future__ import annotations

from datetime import datetime, timezone


PRIMARY_CATEGORY_LABELS = {
    "medical_imaging": "医学影像检查",
    "medical_laboratory": "医学实验室检验",
}

PRIMARY_WINDOW_LABELS = {
    "medical_imaging": "医学影像检查窗",
    "medical_laboratory": "医学实验室检验窗",
}

DEFAULT_ITEMS_BY_CATEGORY = {
    "medical_imaging": ["胸部X线", "超声检查"],
    "medical_laboratory": ["血常规", "C反应蛋白", "基础生化"],
}

IMAGING_HINTS = ("chest", "head", "neurological", "respiratory", "cardiac", "胸", "头", "呼吸")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestSimulationAgent:
    """Generate a simulated report for primary diagnostic testing zones."""

    def assign_primary_category(self, consultation_result: dict, shared_memory: dict) -> str:
        declared = str(consultation_result.get("test_category") or "").strip()
        if declared in PRIMARY_CATEGORY_LABELS:
            return declared

        diagnosis_level = int(consultation_result.get("diagnosis_level") or 1)
        symptoms = [str(item).lower() for item in (shared_memory.get("clinical_memory", {}).get("symptoms") or [])]
        risk_flags = [str(item).lower() for item in (shared_memory.get("clinical_memory", {}).get("risk_flags") or [])]
        merged_text = " ".join(symptoms + risk_flags)

        if diagnosis_level >= 3 or any(keyword in merged_text for keyword in IMAGING_HINTS):
            return "medical_imaging"
        return "medical_laboratory"

    def build_test_items(self, category_code: str, consultation_result: dict) -> list[str]:
        declared_items = consultation_result.get("test_items")
        if isinstance(declared_items, list):
            cleaned = [str(item).strip() for item in declared_items if str(item).strip()]
            if cleaned:
                return cleaned
        return list(DEFAULT_ITEMS_BY_CATEGORY.get(category_code, DEFAULT_ITEMS_BY_CATEGORY["medical_laboratory"]))

    def generate_report(self, consultation_result: dict, shared_memory: dict) -> dict:
        category_code = self.assign_primary_category(consultation_result, shared_memory)
        category_label = PRIMARY_CATEGORY_LABELS[category_code]
        window_label = PRIMARY_WINDOW_LABELS[category_code]
        test_items = self.build_test_items(category_code, consultation_result)
        reason = str(
            consultation_result.get("test_reason")
            or consultation_result.get("note")
            or "根据当前临床表现，建议先完成基础检查。"
        )
        diagnosis_level = int(consultation_result.get("diagnosis_level") or 1)
        priority = str(consultation_result.get("priority") or "M")

        report_text = (
            "辅助检查模拟报告\n"
            f"检查类别：{category_label}\n"
            f"窗口名称：{window_label}\n"
            f"建议项目：{', '.join(test_items)}\n"
            f"临床理由：{reason}\n"
            f"风险等级：诊断级别 {diagnosis_level}，优先级 {priority}\n"
            "说明：该报告为模拟结果，仅用于流程演示，最终结论以医生面诊与正式检查结果为准。"
        )

        return {
            "simulation": True,
            "simulation_version": "v1",
            "generated_at": now_iso(),
            "category_code": category_code,
            "category_label": category_label,
            "window_code": f"{category_code}_window",
            "window_label": window_label,
            "test_items": test_items,
            "report_text": report_text,
            "report_summary": {
                "impression": f"建议先前往{category_label}完成初步检查。",
                "reason": reason,
                "priority": priority,
                "confidence": 0.72,
                "next_step": "return_consultation",
            },
        }
