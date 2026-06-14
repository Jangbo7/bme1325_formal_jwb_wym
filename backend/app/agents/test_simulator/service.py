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
    "medical_imaging": ["Chest X-ray", "Focused ultrasound if needed"],
    "medical_laboratory": ["CBC", "CRP", "Basic chemistry"],
}

IMAGING_HINTS = ("chest", "head", "neurological", "respiratory", "cardiac")


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

    def generate_report(
        self,
        consultation_result: dict,
        shared_memory: dict,
        *,
        rare_event_profile: dict | None = None,
        current_department: str | None = None,
    ) -> dict:
        category_code = self.assign_primary_category(consultation_result, shared_memory)
        category_label = PRIMARY_CATEGORY_LABELS[category_code]
        window_label = PRIMARY_WINDOW_LABELS[category_code]
        test_items = self.build_test_items(category_code, consultation_result)
        reason = str(
            consultation_result.get("test_reason")
            or consultation_result.get("note")
            or "Baseline testing is recommended before the next outpatient decision."
        ).strip()
        diagnosis_level = int(consultation_result.get("diagnosis_level") or 1)
        priority = str(consultation_result.get("priority") or "M")
        report_summary = self._build_report_summary(
            consultation_result=consultation_result,
            shared_memory=shared_memory,
            rare_event_profile=rare_event_profile or {},
            current_department=current_department,
            category_code=category_code,
            category_label=category_label,
            priority=priority,
            reason=reason,
        )

        report_text = (
            "Simulated auxiliary report\n"
            f"Category: {category_label}\n"
            f"Window: {window_label}\n"
            f"Suggested items: {', '.join(test_items)}\n"
            f"Clinical reason: {reason}\n"
            f"Priority: level {diagnosis_level}, queue {priority}\n"
            f"Key findings: {', '.join(report_summary['key_findings']) if report_summary['key_findings'] else 'none'}\n"
            f"Acuity: {report_summary['acuity_level']}\n"
            "This is a simulated report for workflow testing only."
        )

        return {
            "simulation": True,
            "simulation_version": "v2",
            "generated_at": now_iso(),
            "category_code": category_code,
            "category_label": category_label,
            "window_code": f"{category_code}_window",
            "window_label": window_label,
            "test_items": test_items,
            "report_text": report_text,
            "report_summary": report_summary,
        }

    def _build_report_summary(
        self,
        *,
        consultation_result: dict,
        shared_memory: dict,
        rare_event_profile: dict,
        current_department: str | None,
        category_code: str,
        category_label: str,
        priority: str,
        reason: str,
    ) -> dict:
        symptoms = [str(item).strip() for item in (shared_memory.get("clinical_memory", {}).get("symptoms") or []) if str(item).strip()]
        text = " ".join(symptoms).lower()
        event_type = str(rare_event_profile.get("report_special_signal_type") or rare_event_profile.get("event_type") or "").strip()
        report_signal_enabled = bool(rare_event_profile.get("report_special_signal_enabled"))
        current_department_text = str(current_department or consultation_result.get("department") or "").strip()

        key_findings = [f"{category_label} baseline pattern for current outpatient reassessment"]
        supports_current_department = True
        cross_specialty_clues: list[dict] = []
        escalation_clues = {
            "to_emergency": False,
            "to_icu": False,
            "reason": "",
        }
        suggested_next_context = "routine second-round outpatient review"
        acuity_level = "routine"

        profile_escalation_target = self._profile_escalation_target(rare_event_profile)
        profile_escalation_reason = self._profile_escalation_reason(rare_event_profile)

        if report_signal_enabled and event_type == "icu_escalation" and (
            profile_escalation_target == "icu" or self._supports_icu_signal(text, current_department_text)
        ):
            key_findings = [
                "active bleeding or hemodynamic instability concern",
                "critical abnormal pattern that may exceed routine outpatient monitoring",
            ]
            supports_current_department = False
            escalation_clues = {
                "to_emergency": True,
                "to_icu": True,
                "reason": profile_escalation_reason or "Report-level findings suggest unstable bleeding or another ICU-grade deterioration risk.",
            }
            suggested_next_context = "critical reassessment with ICU escalation consideration"
            acuity_level = "critical"
        elif report_signal_enabled and event_type == "emergency_escalation" and (
            profile_escalation_target == "emergency" or self._supports_emergency_signal(text)
        ):
            key_findings = [
                "acute worsening pattern",
                "report concern that no longer fits routine outpatient follow-up",
            ]
            supports_current_department = False
            escalation_clues = {
                "to_emergency": True,
                "to_icu": False,
                "reason": profile_escalation_reason or "Report-level findings suggest a time-sensitive emergency reassessment need.",
            }
            suggested_next_context = "urgent emergency reassessment"
            acuity_level = "urgent"
        elif report_signal_enabled and event_type == "specialty_referral":
            referral_target = self._referral_target_from_profile(rare_event_profile)
            if referral_target is None:
                referral_target = self._referral_target_from_context(text, current_department_text)
            if referral_target is not None:
                key_findings = [
                    "findings are stable enough for outpatient closure in the current department",
                    f"remaining issue fits {referral_target['department']} follow-up better",
                ]
                supports_current_department = False
                cross_specialty_clues = [referral_target]
                suggested_next_context = f"close current loop, then re-register with {referral_target['department']}"
                acuity_level = "urgent" if referral_target["priority"] == "urgent" else "routine"

        if priority == "H" and acuity_level == "routine":
            acuity_level = "urgent"

        return {
            "impression": f"Complete {category_label.lower()} review before the next disposition decision.",
            "reason": reason,
            "priority": priority,
            "confidence": 0.72,
            "next_step": "return_consultation",
            "key_findings": key_findings,
            "acuity_level": acuity_level,
            "supports_current_department": supports_current_department,
            "cross_specialty_clues": cross_specialty_clues,
            "escalation_clues": escalation_clues,
            "suggested_next_context": suggested_next_context,
        }

    @staticmethod
    def _supports_emergency_signal(text: str) -> bool:
        return any(
            token in text
            for token in (
                "chest pain",
                "shortness of breath",
                "black stool",
                "bloody stool",
                "confusion",
                "worsening fever",
                "drainage",
                "bleeding",
                "vomiting",
            )
        )

    @staticmethod
    def _supports_icu_signal(text: str, current_department: str) -> bool:
        department_text = current_department.lower()
        if "surgery" in department_text and any(
            token in text
            for token in (
                "heavy bleeding",
                "bleeding",
                "blood loss",
                "fainting",
                "confusion",
                "shock",
                "severe wound",
            )
        ):
            return True
        return any(token in text for token in ("shock", "fainting", "confusion", "collapse"))

    @staticmethod
    def _referral_target_from_context(text: str, current_department: str) -> dict | None:
        department_text = current_department.lower()
        if "internal" in department_text and any(
            token in text
            for token in ("trauma", "wound", "cut", "bleeding", "injury", "laceration")
        ):
            return {
                "target_department": "Surgery",
                "department": "Surgery",
                "reason": "The remaining issue looks more trauma- or wound-focused than internal-medicine-focused.",
                "priority": "routine",
            }
        if "surgery" in department_text and any(
            token in text
            for token in ("dizziness", "fatigue", "cough", "fever", "palpitation", "headache")
        ):
            return {
                "target_department": "Internal Medicine",
                "department": "Internal Medicine",
                "reason": "The residual issue now fits systemic medical follow-up better than continued routine surgery review.",
                "priority": "routine",
            }
        return None

    @staticmethod
    def _referral_target_from_profile(rare_event_profile: dict) -> dict | None:
        target_department = str(
            rare_event_profile.get("target_department")
            or rare_event_profile.get("recommended_department")
            or ""
        ).strip()
        target_department_id = str(
            rare_event_profile.get("target_department_id")
            or rare_event_profile.get("recommended_department_id")
            or ""
        ).strip()
        target_reason = str(
            rare_event_profile.get("target_department_reason")
            or rare_event_profile.get("recommended_department_reason")
            or ""
        ).strip()
        if not target_department:
            return None
        return {
            "target_department": target_department,
            "department": target_department,
            "department_id": target_department_id or None,
            "reason": target_reason or f"The remaining issue is better suited for {target_department}.",
            "priority": "routine",
        }

    @staticmethod
    def _profile_escalation_target(rare_event_profile: dict) -> str:
        return str(
            rare_event_profile.get("report_escalation_target")
            or ""
        ).strip().lower()

    @staticmethod
    def _profile_escalation_reason(rare_event_profile: dict) -> str:
        return str(
            rare_event_profile.get("report_escalation_reason")
            or ""
        ).strip()
