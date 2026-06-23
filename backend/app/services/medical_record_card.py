from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone

from app.agents.department_runtime.replies import normalize_prescription_plan
from app.services.disposition import is_outpatient_flow_finished


STRUCTURED_FIELD_KEYS = (
    "主诉",
    "症状",
    "生命体征摘要",
    "检查结果摘要",
    "诊断结果摘要",
    "药方",
    "处置摘要",
)

CARD_WRITING_RULES = {
    "主诉": "仅保留一句核心就诊诉求，不拼接问答过程。",
    "症状": "仅保留 2 到 4 个关键症状短语，不展开成长段复述。",
    "生命体征摘要": "只写已有生命体征，统一为中文临床短句。",
    "检查结果摘要": "只写检查类别和关键发现，不照抄英文模拟报告。",
    "诊断结果摘要": "只写最终诊断或临床判断，不重复处置去向。",
    "药方": "有药才写；每条必须明确药物名称和使用频次，缺失则写无。",
    "处置摘要": "只写去向、复诊、转诊、住院或注意事项，不重复药名。",
}

DISPOSITION_CATEGORY_LABELS = {
    "outpatient_treatment": "门诊处理",
    "followup_booking": "门诊复诊",
    "specialty_referral": "专科转诊",
    "inpatient_admission": "建议住院",
    "emergency_escalation": "建议急诊处理",
    "icu_rescue": "建议 ICU 抢救转入",
}

DEPARTMENT_NAME_LABELS = {
    "Internal Medicine": "内科",
    "Surgery": "外科",
    "Emergency": "急诊科",
    "ICU": "ICU",
    "Consultation": "门诊",
    "Disposition": "处置区",
    "Payment": "收费处",
    "Auxiliary Diagnostic Center": "辅助检查中心",
    "internal": "内科",
    "surgery": "外科",
    "emergency": "急诊科",
    "icu": "ICU",
}

COMMON_MEDICAL_TRANSLATIONS = [
    ("left groin", "左侧腹股沟"),
    ("right groin", "右侧腹股沟"),
    ("groin area", "腹股沟区"),
    ("visible bulge", "可见包块"),
    ("swelling", "肿胀"),
    ("pain", "疼痛"),
    ("cough", "咳嗽"),
    ("fever", "发热"),
    ("low fever", "低热"),
    ("sore throat", "咽痛"),
    ("runny nose", "流涕"),
    ("nausea", "恶心"),
    ("vomiting", "呕吐"),
    ("wound", "伤口"),
    ("postoperative", "术后"),
    ("after surgery", "术后"),
    ("toothache", "牙痛"),
    ("red eye", "眼红"),
    ("anxiety", "焦虑"),
    ("insomnia", "失眠"),
]

GENERIC_ENGLISH_REPORT_PATTERNS = (
    "baseline pattern",
    "outpatient reassessment",
    "complete",
    "review before the next disposition decision",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_empty_structured_record() -> dict:
    return {
        "主诉": "无",
        "症状": "无",
        "生命体征摘要": "无",
        "检查结果摘要": "无",
        "诊断结果摘要": "无",
        "药方": [],
        "处置摘要": "无",
    }


class MedicalRecordCardService:
    def __init__(self, *, visit_repo, patient_repo, agent_memory_repo=None, medical_record_repo=None):
        self.visit_repo = visit_repo
        self.patient_repo = patient_repo
        self.agent_memory_repo = agent_memory_repo
        self.medical_record_repo = medical_record_repo

    @staticmethod
    def _coerce_dict(value) -> dict:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
        value = re.sub(r"\s+", " ", value)
        return value.strip(" ;,，；。")

    @staticmethod
    def _translate_common_medical_text(text: str) -> str:
        value = str(text or "")
        for source, target in COMMON_MEDICAL_TRANSLATIONS:
            value = re.sub(source, target, value, flags=re.IGNORECASE)
        value = re.sub(r"\bleft\b", "左侧", value, flags=re.IGNORECASE)
        value = re.sub(r"\bright\b", "右侧", value, flags=re.IGNORECASE)
        value = re.sub(r"\bfor (\d+) days?\b", r"持续\1天", value, flags=re.IGNORECASE)
        value = re.sub(r"\bfor (\d+) weeks?\b", r"持续\1周", value, flags=re.IGNORECASE)
        value = re.sub(r"\band\b", "、", value, flags=re.IGNORECASE)
        value = re.sub(r"\bwith\b", "伴", value, flags=re.IGNORECASE)
        value = re.sub(r"\bafter\b", "后", value, flags=re.IGNORECASE)
        value = re.sub(r"\barea\b", "部位", value, flags=re.IGNORECASE)
        value = re.sub(r"\bvisible\b", "可见", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value)
        return value.strip(" ,;")

    @classmethod
    def _normalize_text(cls, value, *, default: str = "无", max_chars: int | None = None) -> str:
        text = cls._normalize_whitespace(str(value or ""))
        if not text:
            return default
        if not cls._contains_cjk(text):
            text = cls._translate_common_medical_text(text)
            text = cls._normalize_whitespace(text)
        if max_chars is not None and len(text) > max_chars:
            text = text[: max_chars - 1].rstrip(" ,;，；。") + "…"
        return text or default

    @classmethod
    def _join_nonempty(cls, parts: list[str], *, default: str = "无", separator: str = "；") -> str:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in parts:
            text = cls._normalize_text(item, default="")
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(text)
        return separator.join(cleaned) if cleaned else default

    @staticmethod
    def _split_segments(text: str) -> list[str]:
        value = str(text or "")
        raw_parts = re.split(r"[;；,，。！？!?\n\r]+", value)
        return [part.strip() for part in raw_parts if part and part.strip()]

    @classmethod
    def _normalize_department_name(cls, value) -> str:
        text = cls._normalize_whitespace(str(value or ""))
        if not text:
            return ""
        return DEPARTMENT_NAME_LABELS.get(text, text)

    @staticmethod
    def _looks_like_dialogue(segment: str) -> bool:
        return any(
            token in segment
            for token in ("医生", "请问", "怎么办", "严重吗", "需要手术", "这个情况", "是不是", "吗")
        )

    @staticmethod
    def _looks_like_symptom(segment: str) -> bool:
        keywords = (
            "痛",
            "胀",
            "肿",
            "包块",
            "发热",
            "咳",
            "呕",
            "吐",
            "恶心",
            "腹",
            "胸",
            "红",
            "痒",
            "bulge",
            "pain",
            "swelling",
            "fever",
            "cough",
            "nausea",
            "vomit",
            "wound",
        )
        lowered = segment.lower()
        return any(keyword in segment or keyword in lowered for keyword in keywords)

    @classmethod
    def _summarize_short_text(cls, value, *, default: str = "无", max_chars: int = 48) -> str:
        text = cls._normalize_text(value, default="", max_chars=None)
        if not text:
            return default
        segments = cls._split_segments(text)
        candidate = segments[0] if segments else text
        return cls._normalize_text(candidate, default=default, max_chars=max_chars)

    @classmethod
    def _summarize_symptoms(cls, value) -> str:
        items = value if isinstance(value, list) else cls._split_segments(str(value or ""))
        candidates: list[str] = []
        for item in items:
            normalized = cls._normalize_text(item, default="", max_chars=None)
            if not normalized:
                continue
            if cls._looks_like_dialogue(normalized):
                continue
            if len(normalized) > 28 and not cls._looks_like_symptom(normalized):
                continue
            candidates.append(normalized)
        if not candidates:
            return "无"
        picked: list[str] = []
        for item in candidates:
            if item not in picked:
                picked.append(item)
            if len(picked) >= 4:
                break
        return cls._join_nonempty(picked, default="无", separator="；")

    @classmethod
    def _normalize_card_payload(cls, card: dict | None) -> dict:
        payload = dict(card or {})
        structured = cls._normalize_structured(payload.get("structured"))
        display_text = str(payload.get("display_text") or "").strip()
        if not display_text:
            display_text = cls._build_display_text(structured)
        status = str(payload.get("status") or "pending").strip() or "pending"
        if status not in {"pending", "ready"}:
            status = "pending"
        source = str(payload.get("source") or "fallback_projection").strip() or "fallback_projection"
        return {
            "status": status,
            "structured": structured,
            "display_text": display_text,
            "generated_at": payload.get("generated_at"),
            "source": source,
        }

    @classmethod
    def _normalize_structured(cls, structured: dict | None) -> dict:
        payload = build_empty_structured_record()
        if isinstance(structured, dict):
            for key in STRUCTURED_FIELD_KEYS:
                if key == "药方":
                    payload[key] = deepcopy(structured.get(key) or [])
                else:
                    payload[key] = cls._normalize_text(structured.get(key))
        return payload

    @classmethod
    def _build_pending_card(cls, *, source: str = "fallback_projection", generated_at: str | None = None) -> dict:
        structured = build_empty_structured_record()
        return {
            "status": "pending",
            "structured": structured,
            "display_text": cls._build_display_text(structured),
            "generated_at": generated_at,
            "source": source,
        }

    @classmethod
    def _mask_as_pending(cls, card: dict | None) -> dict:
        normalized = cls._normalize_card_payload(card)
        return cls._build_pending_card(
            source=normalized.get("source") or "fallback_projection",
            generated_at=normalized.get("generated_at"),
        )

    @classmethod
    def _format_vitals(cls, vitals: dict | None) -> str:
        payload = dict(vitals or {})
        parts: list[str] = []
        if payload.get("temp_c") not in (None, ""):
            parts.append(f"体温 {payload['temp_c']}℃")
        if payload.get("heart_rate") not in (None, ""):
            parts.append(f"心率 {payload['heart_rate']}次/分")
        systolic = payload.get("systolic_bp")
        diastolic = payload.get("diastolic_bp")
        if systolic not in (None, "") or diastolic not in (None, ""):
            left = "" if systolic in (None, "") else str(systolic)
            right = "" if diastolic in (None, "") else str(diastolic)
            if left or right:
                parts.append(f"血压 {left}/{right} mmHg".replace(" /", "/").replace("/ ", "/"))
        if payload.get("spo2") not in (None, ""):
            parts.append(f"血氧 {payload['spo2']}%")
        if payload.get("pain_score") not in (None, ""):
            parts.append(f"疼痛评分 {payload['pain_score']}/10")
        return cls._join_nonempty(parts)

    @classmethod
    def _summarize_report(cls, report: dict | None) -> str:
        payload = dict(report or {})
        report_summary = dict(payload.get("report_summary") or {})
        category_label = cls._normalize_department_name(payload.get("category_label"))
        findings = [
            cls._normalize_text(item, default="", max_chars=28)
            for item in (report_summary.get("key_findings") or [])
        ]
        findings = [
            item
            for item in findings
            if item and not any(pattern in item.lower() for pattern in GENERIC_ENGLISH_REPORT_PATTERNS)
        ]
        impression = cls._normalize_text(report_summary.get("impression"), default="", max_chars=32)
        if any(pattern in impression.lower() for pattern in GENERIC_ENGLISH_REPORT_PATTERNS):
            impression = ""
        acuity_level = cls._normalize_text(report_summary.get("acuity_level"), default="", max_chars=12)

        parts: list[str] = []
        if category_label:
            parts.append(category_label)
        if findings:
            parts.append("关键发现：" + "、".join(findings[:2]))
        elif impression:
            parts.append(impression)
        elif acuity_level == "routine":
            parts.append("未见需紧急处理的异常提示")
        elif acuity_level in {"urgent", "critical"}:
            parts.append("提示需尽快进一步评估")
        return cls._join_nonempty(parts)

    @classmethod
    def _build_diagnosis_summary(cls, visit_data: dict, consultation_result: dict) -> str:
        preferred_values = (
            consultation_result.get("final_assessment_summary"),
            consultation_result.get("final_diagnosis"),
            consultation_result.get("diagnosis_summary"),
            consultation_result.get("clinical_impression"),
            visit_data.get("final_assessment_summary"),
            visit_data.get("final_diagnosis"),
            visit_data.get("diagnosis_summary"),
            visit_data.get("clinical_impression"),
        )
        for value in preferred_values:
            text = cls._summarize_short_text(value, default="", max_chars=72)
            if text:
                return text
        return "无"

    @classmethod
    def _build_prescription_items(cls, visit_data: dict, consultation_result: dict) -> list[dict]:
        raw_plan = consultation_result.get("prescription_plan")
        if not isinstance(raw_plan, list):
            raw_plan = visit_data.get("prescription_plan")
        normalized = normalize_prescription_plan(raw_plan)
        items: list[dict] = []
        for item in normalized:
            items.append(
                {
                    "药物名称": cls._normalize_text(item.get("drug_name")),
                    "剂量说明": cls._normalize_text(item.get("dose_text")),
                    "使用频次": cls._normalize_text(item.get("frequency_text")),
                    "疗程": cls._normalize_text(item.get("duration_text")),
                    "附加说明": cls._normalize_text(item.get("instructions")),
                }
            )
        return items

    @classmethod
    def _build_disposition_summary(cls, visit_data: dict, consultation_result: dict) -> str:
        disposition = cls._coerce_dict(visit_data.get("disposition"))
        category = str(disposition.get("category") or "").strip()
        category_label = DISPOSITION_CATEGORY_LABELS.get(category, "")
        target_department = cls._normalize_department_name(
            disposition.get("target_department")
            or visit_data.get("recommended_department")
            or consultation_result.get("recommended_department")
        )
        followup = cls._coerce_dict(
            consultation_result.get("followup_recommendation")
            or visit_data.get("followup_recommendation")
        )
        admission = cls._coerce_dict(
            consultation_result.get("admission_recommendation")
            or visit_data.get("admission_recommendation")
        )
        procedure = cls._coerce_dict(
            consultation_result.get("procedure_recommendation")
            or visit_data.get("procedure_recommendation")
        )
        carry_forward = cls._coerce_dict(
            visit_data.get("carry_forward_summary")
            or consultation_result.get("carry_forward_summary")
        )
        precautions = [
            cls._normalize_text(item, default="", max_chars=18)
            for item in (
                consultation_result.get("return_precautions")
                or visit_data.get("return_precautions")
                or []
            )
        ]
        precautions = [item for item in precautions if item]

        parts: list[str] = []
        if category_label:
            parts.append(category_label)
        if category == "specialty_referral" and target_department:
            parts.append(f"建议转{target_department}继续诊治")
        elif category == "followup_booking":
            timing = cls._summarize_short_text(
                followup.get("timing") or followup.get("timeframe"),
                default="",
                max_chars=20,
            )
            if timing:
                parts.append(f"建议{timing}复诊")
        elif category == "inpatient_admission":
            parts.append("建议尽快住院进一步评估")
        elif category in {"emergency_escalation", "icu_rescue"}:
            parts.append("建议立即升级处理")

        if admission.get("recommended") or admission.get("needs_admission"):
            parts.append("需进一步评估住院指征")
        if procedure.get("recommended") or procedure.get("surgery_evaluation_recommended"):
            parts.append("建议进一步外科/操作评估")

        carry_forward_reason = cls._summarize_short_text(
            carry_forward.get("reason") or carry_forward.get("summary"),
            default="",
            max_chars=40,
        )
        if category == "specialty_referral" and carry_forward_reason:
            parts.append(carry_forward_reason)

        if precautions:
            parts.append("注意事项：" + "、".join(precautions[:4]))
        return cls._join_nonempty(parts)

    @classmethod
    def _build_display_text(cls, structured: dict) -> str:
        medications = structured.get("药方") or []
        if medications:
            medication_text = "；".join(
                [
                    "，".join(
                        [
                            item.get("药物名称", "无"),
                            item.get("剂量说明", "无"),
                            item.get("使用频次", "无"),
                            item.get("疗程", "无"),
                        ]
                    )
                    for item in medications
                ]
            )
        else:
            medication_text = "无"

        return "\n".join(
            [
                f"主诉：{structured['主诉']}",
                f"症状：{structured['症状']}",
                f"生命体征：{structured['生命体征摘要']}",
                f"检查结果：{structured['检查结果摘要']}",
                f"诊断结果：{structured['诊断结果摘要']}",
                f"药方：{medication_text}",
                f"处置摘要：{structured['处置摘要']}",
            ]
        )

    def _load_clinical_memory(self, patient_id: str | None, patient_name: str | None = None) -> dict:
        if not self.agent_memory_repo or not patient_id:
            return {}
        payload = self.agent_memory_repo.get_shared_memory(patient_id, name=str(patient_name or ""))
        return self._coerce_dict(payload.get("clinical_memory"))

    def build_card_from_context(
        self,
        *,
        patient_id: str | None,
        visit_row: dict,
        consultation_result: dict | None = None,
        source: str = "fallback_projection",
    ) -> dict:
        consultation_payload = self._coerce_dict(consultation_result)
        visit_data = self._coerce_dict(self.visit_repo.get_visit_data(visit_row["id"]))
        patient_row = self.patient_repo.get(patient_id) if patient_id else None
        clinical_memory = self._load_clinical_memory(patient_id, (patient_row or {}).get("name"))

        structured = build_empty_structured_record()
        structured["主诉"] = self._summarize_short_text(
            clinical_memory.get("chief_complaint") or visit_data.get("chief_complaint"),
            max_chars=40,
        )
        structured["症状"] = self._summarize_symptoms(
            clinical_memory.get("symptoms") or visit_data.get("symptoms")
        )
        structured["生命体征摘要"] = self._format_vitals(
            clinical_memory.get("vitals") or visit_data.get("vitals")
        )
        structured["检查结果摘要"] = self._summarize_report(visit_data.get("simulated_report"))
        structured["诊断结果摘要"] = self._build_diagnosis_summary(visit_data, consultation_payload)
        structured["药方"] = self._build_prescription_items(visit_data, consultation_payload)
        structured["处置摘要"] = self._build_disposition_summary(visit_data, consultation_payload)
        structured = self._normalize_structured(structured)
        return {
            "status": "ready",
            "structured": structured,
            "display_text": self._build_display_text(structured),
            "generated_at": now_iso(),
            "source": source,
        }

    def generate_and_store_for_visit(
        self,
        *,
        visit_id: str,
        patient_id: str | None = None,
        consultation_result: dict | None = None,
        source: str = "fallback_projection",
    ) -> dict:
        visit_row = self.visit_repo.get(visit_id)
        if visit_row is None:
            raise KeyError(visit_id)
        resolved_patient_id = patient_id or visit_row.get("patient_id")
        card = self.build_card_from_context(
            patient_id=resolved_patient_id,
            visit_row=visit_row,
            consultation_result=consultation_result,
            source=source,
        )
        visit_data = self.visit_repo.get_visit_data(visit_id)
        visit_data["medical_record_card"] = card
        self.visit_repo.update_visit(visit_id, data=visit_data)
        return card

    def get_card_for_visit(self, visit_id: str, *, hide_until_finished: bool = False) -> dict:
        visit_row = self.visit_repo.get(visit_id)
        if visit_row is None:
            raise KeyError(visit_id)
        visit_data = self.visit_repo.get_visit_data(visit_id)
        stored = self._normalize_card_payload(visit_data.get("medical_record_card"))
        if visit_data.get("medical_record_card") is None:
            stored = self._build_pending_card()
        if hide_until_finished and not is_outpatient_flow_finished(visit_row.get("state"), visit_data):
            return self._mask_as_pending(stored)
        return stored

    def build_pending_view(self) -> dict:
        return self._build_pending_card()
