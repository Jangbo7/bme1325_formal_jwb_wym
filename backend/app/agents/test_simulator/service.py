from __future__ import annotations

from datetime import datetime, timezone

from app.reporting.test_report_card import REPORT_TEMPLATE_VERSION, TestReportCardService

PRIMARY_CATEGORY_LABELS = {
    "medical_imaging": "医学影像检查",
    "medical_laboratory": "医学实验室检查",
}

PRIMARY_WINDOW_LABELS = {
    "medical_imaging": "医学影像检查窗",
    "medical_laboratory": "医学实验室检查窗",
}

DEFAULT_ITEMS_BY_CATEGORY = {
    "medical_imaging": ["胸部X线", "必要时床旁超声"],
    "medical_laboratory": ["血常规", "C反应蛋白", "基础生化"],
}

IMAGING_HINTS = ("chest", "head", "neurological", "respiratory", "cardiac")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestSimulationAgent:
    """Generate a structured Chinese report for primary diagnostic testing zones."""

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
        reason = self._resolve_reason(consultation_result)
        priority = str(consultation_result.get("priority") or "M")
        symptoms = [str(item).strip() for item in (shared_memory.get("clinical_memory", {}).get("symptoms") or []) if str(item).strip()]
        report_items = (
            self._build_imaging_report_items(test_items, symptoms, rare_event_profile or {})
            if category_code == "medical_imaging"
            else self._build_laboratory_report_items(test_items, symptoms, rare_event_profile or {})
        )
        key_findings_cn = self._build_key_findings(category_code, report_items)
        preliminary_assessment = self._build_preliminary_assessment(category_code, report_items, key_findings_cn)

        report_summary = self._build_report_summary(
            consultation_result=consultation_result,
            shared_memory=shared_memory,
            rare_event_profile=rare_event_profile or {},
            current_department=current_department,
            category_code=category_code,
            category_label=category_label,
            priority=priority,
            reason=reason,
            key_findings_cn=key_findings_cn,
            preliminary_assessment=preliminary_assessment,
        )

        payload = {
            "simulation": True,
            "simulation_version": "v3",
            "template_version": REPORT_TEMPLATE_VERSION,
            "generated_at": now_iso(),
            "report_type": category_code,
            "category_code": category_code,
            "category_label": category_label,
            "window_code": f"{category_code}_window",
            "window_label": window_label,
            "report_title": "医学影像检查报告" if category_code == "medical_imaging" else "医学实验室检查报告",
            "test_items": test_items,
            "report_items": report_items,
            "key_findings_cn": key_findings_cn,
            "preliminary_assessment": preliminary_assessment,
            "report_summary": report_summary,
        }
        normalized_report = TestReportCardService.normalize_report(payload)
        normalized_report["report_summary"]["reason"] = reason
        normalized_report["report_summary"]["preliminary_assessment"] = preliminary_assessment
        return normalized_report

    @staticmethod
    def _resolve_reason(consultation_result: dict) -> str:
        preferred = str(
            consultation_result.get("test_reason")
            or consultation_result.get("note")
            or ""
        ).strip()
        if not preferred:
            return "建议在下一步门诊处置前完成基础检查。"
        lowered = preferred.lower()
        if lowered == "baseline testing is recommended before the next outpatient decision.":
            return "建议在下一步门诊处置前完成基础检查。"
        return preferred if any("\u4e00" <= char <= "\u9fff" for char in preferred) else "结合当前病情进行进一步评估。"

    def _build_laboratory_report_items(self, test_items: list[str], symptoms: list[str], rare_event_profile: dict) -> list[dict]:
        symptom_text = " ".join(item.lower() for item in symptoms)
        abnormal_wbc = any(token in symptom_text for token in ("fever", "发热", "咳", "cough", "感染"))
        abnormal_crp = abnormal_wbc
        bleeding_risk = bool(rare_event_profile.get("report_special_signal_enabled")) and str(
            rare_event_profile.get("report_special_signal_type") or rare_event_profile.get("event_type") or ""
        ).strip() in {"icu_escalation", "emergency_escalation"}

        report_items: list[dict] = []
        for item in test_items:
            lowered = item.lower()
            if "cbc" in lowered or "血常规" in item:
                report_items.extend(
                    [
                        self._lab_item("白细胞计数", "12.6" if abnormal_wbc else "7.2", "x10^9/L", "3.5-9.5", abnormal_wbc, "提示感染活动度时可升高" if abnormal_wbc else "结果在参考范围内"),
                        self._lab_item("血红蛋白", "91" if bleeding_risk else "128", "g/L", "115-150", bleeding_risk, "需警惕失血或慢性贫血" if bleeding_risk else "结果在参考范围内"),
                        self._lab_item("血小板", "356", "x10^9/L", "125-350", False, "临床结合复核"),
                    ]
                )
            elif "crp" in lowered or "c反应蛋白" in item.lower():
                report_items.append(
                    self._lab_item("C反应蛋白", "24.8" if abnormal_crp else "4.2", "mg/L", "0-8", abnormal_crp, "炎症指标轻度升高" if abnormal_crp else "未见明显炎症异常")
                )
            elif "chemistry" in lowered or "生化" in item or "basic chemistry" in lowered:
                report_items.extend(
                    [
                        self._lab_item("肌酐", "76", "umol/L", "45-84", False, "肾功能指标参考范围内"),
                        self._lab_item("钠", "139", "mmol/L", "137-147", False, "电解质未见明显异常"),
                        self._lab_item("钾", "4.1", "mmol/L", "3.5-5.3", False, "电解质未见明显异常"),
                    ]
                )
            else:
                report_items.append(
                    self._lab_item(item, "", "", "", False, "当前为模拟报告，需补充该项目具体指标。")
                )
        return report_items

    @staticmethod
    def _lab_item(item_name: str, result_value: str, unit: str, reference_range: str, is_abnormal: bool, comment: str) -> dict:
        return {
            "item_name": item_name,
            "result_value": result_value,
            "unit": unit,
            "reference_range": reference_range,
            "status": "异常" if is_abnormal else "正常",
            "is_abnormal": is_abnormal,
            "comment": comment,
        }

    def _build_imaging_report_items(self, test_items: list[str], symptoms: list[str], rare_event_profile: dict) -> list[dict]:
        symptom_text = " ".join(item.lower() for item in symptoms)
        emergency_signal = bool(rare_event_profile.get("report_special_signal_enabled")) and str(
            rare_event_profile.get("report_special_signal_type") or rare_event_profile.get("event_type") or ""
        ).strip() in {"icu_escalation", "emergency_escalation"}
        respiratory_signal = any(token in symptom_text for token in ("cough", "咳", "shortness of breath", "呼吸"))

        report_items: list[dict] = []
        for item in test_items:
            lowered = item.lower()
            if "x-ray" in lowered or "x线" in item or "chest" in lowered:
                report_items.append(
                    {
                        "exam_name": "胸部X线",
                        "body_part": "胸部",
                        "finding": "双肺纹理稍增多" if respiratory_signal else "胸廓对称，未见明显实变影",
                        "impression": "考虑轻度炎症改变" if respiratory_signal else ("未见明确急性异常" if not emergency_signal else "需警惕急性胸部异常改变"),
                        "status": "异常" if respiratory_signal or emergency_signal else "正常",
                        "comment": "建议结合临床症状与复诊评估",
                    }
                )
            elif "ultrasound" in lowered or "超声" in item:
                report_items.append(
                    {
                        "exam_name": "床旁超声",
                        "body_part": "目标部位待结合临床确定",
                        "finding": "未见明显液性暗区或占位性异常",
                        "impression": "当前超声所见未提示急性占位或明显积液",
                        "status": "正常",
                        "comment": "若症状持续，建议复查或结合其他影像",
                    }
                )
            else:
                report_items.append(
                    {
                        "exam_name": item,
                        "body_part": "待补充",
                        "finding": "当前为模拟报告，待补充正式影像所见。",
                        "impression": "需结合正式检查结果判断。",
                        "status": "待复核",
                        "comment": "需结合临床由二轮医生复核。",
                    }
                )
        return report_items

    @staticmethod
    def _build_key_findings(category_code: str, report_items: list[dict]) -> list[str]:
        findings: list[str] = []
        if category_code == "medical_imaging":
            for item in report_items:
                impression = str(item.get("impression") or "").strip()
                exam_name = str(item.get("exam_name") or "").strip()
                if impression:
                    findings.append(f"{exam_name}：{impression}" if exam_name else impression)
        else:
            for item in report_items:
                if not item.get("is_abnormal"):
                    continue
                item_name = str(item.get("item_name") or "").strip()
                result_value = str(item.get("result_value") or "").strip()
                unit = str(item.get("unit") or "").strip()
                findings.append(" ".join(part for part in [item_name, result_value, unit, "异常"] if part))
        return findings[:4]

    @staticmethod
    def _build_preliminary_assessment(category_code: str, report_items: list[dict], key_findings_cn: list[str]) -> dict:
        abnormal_items: list[str] = []
        normal_items: list[str] = []
        if category_code == "medical_imaging":
            for item in report_items:
                label = "：".join(part for part in [str(item.get("exam_name") or "").strip(), str(item.get("impression") or "").strip()] if part)
                if not label:
                    continue
                if str(item.get("status") or "").strip() == "异常":
                    abnormal_items.append(label)
                else:
                    normal_items.append(label)
        else:
            for item in report_items:
                label = "：".join(
                    part
                    for part in [
                        str(item.get("item_name") or "").strip(),
                        " ".join(part for part in [str(item.get("result_value") or "").strip(), str(item.get("unit") or "").strip()] if part),
                    ]
                    if part
                )
                if not label:
                    continue
                if bool(item.get("is_abnormal")):
                    abnormal_items.append(label)
                else:
                    normal_items.append(label)

        if abnormal_items:
            summary_cn = f"本次{PRIMARY_CATEGORY_LABELS[category_code]}提示{TestReportCardService._join_nonempty(abnormal_items[:2], separator='；')}，建议结合临床继续评估。"
        elif key_findings_cn:
            summary_cn = f"本次{PRIMARY_CATEGORY_LABELS[category_code]}重点提示：{TestReportCardService._join_nonempty(key_findings_cn[:2], separator='；')}。"
        else:
            summary_cn = f"本次{PRIMARY_CATEGORY_LABELS[category_code]}暂未见明确异常提示，建议结合临床复核。"

        return {
            "summary_cn": summary_cn,
            "abnormal_items": abnormal_items,
            "normal_items": normal_items,
            "review_required": True,
            "review_note": "以上为检验/检查初步结果，需结合临床由二轮医生复核。",
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
        key_findings_cn: list[str],
        preliminary_assessment: dict,
    ) -> dict:
        symptoms = [str(item).strip() for item in (shared_memory.get("clinical_memory", {}).get("symptoms") or []) if str(item).strip()]
        text = " ".join(symptoms).lower()
        event_type = str(rare_event_profile.get("report_special_signal_type") or rare_event_profile.get("event_type") or "").strip()
        report_signal_enabled = bool(rare_event_profile.get("report_special_signal_enabled"))
        current_department_text = str(current_department or consultation_result.get("department") or "").strip()

        key_findings = list(key_findings_cn)
        supports_current_department = True
        cross_specialty_clues: list[dict] = []
        escalation_clues = {
            "to_emergency": False,
            "to_icu": False,
            "reason": "",
        }
        suggested_next_context = "结合当前检查结果完成二轮复核"
        acuity_level = "routine"

        profile_escalation_target = self._profile_escalation_target(rare_event_profile)
        profile_escalation_reason = self._profile_escalation_reason(rare_event_profile)

        if report_signal_enabled and event_type == "icu_escalation" and (
            profile_escalation_target == "icu" or self._supports_icu_signal(text, current_department_text)
        ):
            key_findings = [
                "提示活动性出血或血流动力学不稳定风险",
                "存在超出常规门诊监测能力的危重异常信号",
            ]
            supports_current_department = False
            escalation_clues = {
                "to_emergency": True,
                "to_icu": True,
                "reason": profile_escalation_reason or "检查结果提示病情存在危重恶化风险，需要尽快升级评估。",
            }
            suggested_next_context = "尽快完成危重再评估并考虑 ICU 升级"
            acuity_level = "critical"
        elif report_signal_enabled and event_type == "emergency_escalation" and (
            profile_escalation_target == "emergency" or self._supports_emergency_signal(text)
        ):
            key_findings = [
                "提示急性恶化趋势",
                "当前检查信号已不适合常规门诊随访处理",
            ]
            supports_current_department = False
            escalation_clues = {
                "to_emergency": True,
                "to_icu": False,
                "reason": profile_escalation_reason or "检查结果提示需要尽快进行急诊时效性评估。",
            }
            suggested_next_context = "尽快完成急诊再评估"
            acuity_level = "urgent"
        elif report_signal_enabled and event_type == "specialty_referral":
            referral_target = self._referral_target_from_profile(rare_event_profile)
            if referral_target is None:
                referral_target = self._referral_target_from_context(text, current_department_text)
            if referral_target is not None:
                key_findings = [
                    "当前检查结果整体稳定，现科室可完成本轮门诊闭环",
                    f"剩余问题更适合由{referral_target['department']}继续随访",
                ]
                supports_current_department = False
                cross_specialty_clues = [referral_target]
                suggested_next_context = f"结束当前流程后，转由{referral_target['department']}重新挂号接诊"
                acuity_level = "urgent" if referral_target["priority"] == "urgent" else "routine"

        if priority == "H" and acuity_level == "routine":
            acuity_level = "urgent"

        return {
            "impression": preliminary_assessment["summary_cn"],
            "reason": reason,
            "priority": priority,
            "confidence": 0.72,
            "next_step": "return_consultation",
            "key_findings": key_findings,
            "key_findings_cn": key_findings,
            "acuity_level": acuity_level,
            "supports_current_department": supports_current_department,
            "cross_specialty_clues": cross_specialty_clues,
            "escalation_clues": escalation_clues,
            "suggested_next_context": suggested_next_context,
            "preliminary_assessment": preliminary_assessment,
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
                "reason": "当前残余问题更偏向创伤或伤口评估，较适合外科继续随访。",
                "priority": "routine",
            }
        if "surgery" in department_text and any(
            token in text
            for token in ("dizziness", "fatigue", "cough", "fever", "palpitation", "headache")
        ):
            return {
                "target_department": "Internal Medicine",
                "department": "Internal Medicine",
                "reason": "当前残余问题更偏向系统性内科评估，较适合内科继续随访。",
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
            "reason": target_reason or f"当前剩余问题更适合由{target_department}继续评估。",
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
