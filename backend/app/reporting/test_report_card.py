from __future__ import annotations

from datetime import datetime, timezone

REPORT_TEMPLATE_VERSION = "cn_structured_v1"

REPORT_TYPE_LABELS = {
    "medical_laboratory": "医学实验室检查",
    "medical_imaging": "医学影像检查",
}

REPORT_TITLE_LABELS = {
    "medical_laboratory": "医学实验室检查报告",
    "medical_imaging": "医学影像检查报告",
}

DEFAULT_CATEGORY_LABELS = {
    "medical_laboratory": "医学实验室检查",
    "medical_imaging": "医学影像检查",
}

DEFAULT_WINDOW_LABELS = {
    "medical_laboratory": "医学实验室检查窗",
    "medical_imaging": "医学影像检查窗",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestReportCardService:
    def __init__(self, *, visit_repo=None):
        self.visit_repo = visit_repo

    @staticmethod
    def _normalize_text(value, *, default: str = "") -> str:
        text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        return " ".join(text.split()) or default

    @classmethod
    def _join_nonempty(cls, parts: list[str], *, separator: str = "；", default: str = "") -> str:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in parts:
            text = cls._normalize_text(item)
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(text)
        return separator.join(cleaned) if cleaned else default

    @classmethod
    def _resolve_report_type(cls, payload: dict) -> str:
        report_type = cls._normalize_text(payload.get("report_type"))
        category_code = cls._normalize_text(payload.get("category_code"))
        if report_type in REPORT_TYPE_LABELS:
            return report_type
        if category_code in REPORT_TYPE_LABELS:
            return category_code
        return "medical_laboratory"

    @classmethod
    def _normalize_lab_item(cls, item: dict) -> dict:
        status = cls._normalize_text(item.get("status"))
        is_abnormal = bool(item.get("is_abnormal"))
        if not status:
            status = "异常" if is_abnormal else "正常"
        if status == "异常":
            is_abnormal = True
        return {
            "item_name": cls._normalize_text(item.get("item_name")),
            "result_value": cls._normalize_text(item.get("result_value")),
            "unit": cls._normalize_text(item.get("unit")),
            "reference_range": cls._normalize_text(item.get("reference_range")),
            "status": status or "待复核",
            "is_abnormal": is_abnormal,
            "comment": cls._normalize_text(item.get("comment")),
        }

    @classmethod
    def _normalize_imaging_item(cls, item: dict) -> dict:
        status = cls._normalize_text(item.get("status"), default="待复核")
        return {
            "exam_name": cls._normalize_text(item.get("exam_name")),
            "body_part": cls._normalize_text(item.get("body_part")),
            "finding": cls._normalize_text(item.get("finding")),
            "impression": cls._normalize_text(item.get("impression")),
            "status": status,
            "comment": cls._normalize_text(item.get("comment")),
        }

    @classmethod
    def _fallback_items_from_test_items(cls, report_type: str, test_items: list[str]) -> list[dict]:
        if report_type == "medical_imaging":
            return [
                cls._normalize_imaging_item(
                    {
                        "exam_name": item,
                        "body_part": "待结合临床确定",
                        "finding": "当前记录仅保留检查申请项目。",
                        "impression": "待补充正式影像所见。",
                        "status": "待复核",
                        "comment": "需结合临床由二轮医生复核。",
                    }
                )
                for item in test_items
            ]
        return [
            cls._normalize_lab_item(
                {
                    "item_name": item,
                    "status": "待复核",
                    "is_abnormal": False,
                    "comment": "当前记录仅保留检查申请项目，待补充具体指标。",
                }
            )
            for item in test_items
        ]

    @classmethod
    def _normalize_report_items(cls, payload: dict, report_type: str, test_items: list[str]) -> list[dict]:
        raw_items = payload.get("report_items")
        normalized: list[dict] = []
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                if report_type == "medical_imaging":
                    normalized_item = cls._normalize_imaging_item(item)
                    if normalized_item["exam_name"] or normalized_item["finding"] or normalized_item["impression"]:
                        normalized.append(normalized_item)
                else:
                    normalized_item = cls._normalize_lab_item(item)
                    if normalized_item["item_name"] or normalized_item["result_value"] or normalized_item["comment"]:
                        normalized.append(normalized_item)
        if normalized:
            return normalized
        return cls._fallback_items_from_test_items(report_type, test_items)

    @classmethod
    def _derive_key_findings(cls, report_type: str, report_items: list[dict], report_summary: dict) -> list[str]:
        raw_key_findings = report_summary.get("key_findings_cn") or report_summary.get("key_findings") or []
        key_findings = [cls._normalize_text(item) for item in raw_key_findings if cls._normalize_text(item)]
        if key_findings:
            return key_findings

        findings: list[str] = []
        if report_type == "medical_imaging":
            for item in report_items:
                exam_name = cls._normalize_text(item.get("exam_name"))
                impression = cls._normalize_text(item.get("impression"))
                finding = cls._normalize_text(item.get("finding"))
                if impression:
                    findings.append(cls._join_nonempty([exam_name, impression], separator="："))
                elif finding:
                    findings.append(cls._join_nonempty([exam_name, finding], separator="："))
        else:
            for item in report_items:
                if not item.get("is_abnormal"):
                    continue
                findings.append(
                    cls._join_nonempty(
                        [
                            cls._normalize_text(item.get("item_name")),
                            cls._normalize_text(item.get("result_value")),
                            cls._normalize_text(item.get("unit")),
                            "异常",
                        ],
                        separator=" ",
                    )
                )
        return findings[:4]

    @classmethod
    def _build_preliminary_assessment(cls, report_type: str, report_items: list[dict], key_findings: list[str], report_summary: dict) -> dict:
        raw = dict(report_summary.get("preliminary_assessment") or {})
        abnormal_items: list[str] = []
        normal_items: list[str] = []

        if report_type == "medical_imaging":
            for item in report_items:
                exam_name = cls._normalize_text(item.get("exam_name"))
                impression = cls._normalize_text(item.get("impression"))
                status = cls._normalize_text(item.get("status"))
                content = cls._join_nonempty([exam_name, impression or status], separator="：")
                if not content:
                    continue
                if status == "异常" or ("异常" in impression):
                    abnormal_items.append(content)
                else:
                    normal_items.append(content)
        else:
            for item in report_items:
                item_name = cls._normalize_text(item.get("item_name"))
                result_value = cls._join_nonempty(
                    [cls._normalize_text(item.get("result_value")), cls._normalize_text(item.get("unit"))],
                    separator=" ",
                )
                status = cls._normalize_text(item.get("status"))
                content = cls._join_nonempty([item_name, result_value or status], separator="：")
                if not content:
                    continue
                if bool(item.get("is_abnormal")) or status == "异常":
                    abnormal_items.append(content)
                else:
                    normal_items.append(content)

        summary_cn = cls._normalize_text(raw.get("summary_cn"))
        if not summary_cn:
            if abnormal_items:
                summary_cn = f"本次{REPORT_TYPE_LABELS.get(report_type, '检查')}提示{cls._join_nonempty(abnormal_items[:2], separator='；')}，建议结合临床继续评估。"
            elif key_findings:
                summary_cn = f"本次{REPORT_TYPE_LABELS.get(report_type, '检查')}重点提示：{cls._join_nonempty(key_findings[:2], separator='；')}。"
            else:
                summary_cn = f"本次{REPORT_TYPE_LABELS.get(report_type, '检查')}暂未见明确异常提示，建议结合临床复核。"

        return {
            "summary_cn": summary_cn,
            "abnormal_items": abnormal_items,
            "normal_items": normal_items,
            "review_required": True,
            "review_note": cls._normalize_text(
                raw.get("review_note"),
                default="以上为检验/检查初步结果，需结合临床由二轮医生复核。",
            ),
        }

    @classmethod
    def _format_item_lines(cls, report_type: str, report_items: list[dict]) -> list[str]:
        lines: list[str] = []
        if report_type == "medical_imaging":
            for item in report_items:
                exam_name = cls._normalize_text(item.get("exam_name"))
                body_part = cls._normalize_text(item.get("body_part"))
                finding = cls._normalize_text(item.get("finding"))
                impression = cls._normalize_text(item.get("impression"))
                status = cls._normalize_text(item.get("status"))
                comment = cls._normalize_text(item.get("comment"))
                line = cls._join_nonempty(
                    [
                        cls._join_nonempty([exam_name, body_part], separator=" / "),
                        f"所见：{finding}" if finding else "",
                        f"印象：{impression}" if impression else "",
                        f"状态：{status}" if status else "",
                        f"备注：{comment}" if comment else "",
                    ]
                )
                if line:
                    lines.append(line)
            return lines

        for item in report_items:
            item_name = cls._normalize_text(item.get("item_name"))
            result_value = cls._join_nonempty(
                [cls._normalize_text(item.get("result_value")), cls._normalize_text(item.get("unit"))],
                separator=" ",
            )
            reference_range = cls._normalize_text(item.get("reference_range"))
            status = cls._normalize_text(item.get("status"))
            comment = cls._normalize_text(item.get("comment"))
            line = cls._join_nonempty(
                [
                    item_name,
                    f"结果：{result_value}" if result_value else "",
                    f"参考范围：{reference_range}" if reference_range else "",
                    f"状态：{status}" if status else "",
                    f"备注：{comment}" if comment else "",
                ]
            )
            if line:
                lines.append(line)
        return lines

    @classmethod
    def _build_display_text(cls, normalized: dict) -> str:
        sections = cls._build_sections(normalized)
        return "\n".join(
            [f"{section['title']}：{section['content'] or '无'}" for section in sections]
        )

    @classmethod
    def _build_sections(cls, normalized: dict) -> list[dict]:
        report_type_label = REPORT_TYPE_LABELS.get(normalized["report_type"], normalized["category_label"])
        item_lines = cls._format_item_lines(normalized["report_type"], normalized["report_items"])
        preliminary = dict(normalized.get("preliminary_assessment") or {})
        return [
            {"title": "检查类型", "content": cls._join_nonempty([report_type_label, normalized.get("category_label")], separator=" / ", default="无")},
            {"title": "项目结果", "content": cls._join_nonempty(item_lines, separator="\n", default="无")},
            {"title": "关键发现", "content": cls._join_nonempty(normalized.get("key_findings_cn") or [], separator="；", default="无")},
            {
                "title": "初步判断",
                "content": cls._join_nonempty(
                    [
                        cls._normalize_text(preliminary.get("summary_cn")),
                        cls._normalize_text(preliminary.get("review_note")),
                    ],
                    separator="\n",
                    default="无",
                ),
            },
        ]

    @classmethod
    def normalize_report(cls, report: dict | None) -> dict:
        if not isinstance(report, dict):
            return {}
        payload = dict(report)
        report_summary = dict(payload.get("report_summary") or {})
        report_type = cls._resolve_report_type(payload)
        category_code = cls._normalize_text(payload.get("category_code"), default=report_type)
        category_label = cls._normalize_text(payload.get("category_label"), default=DEFAULT_CATEGORY_LABELS.get(report_type, "辅助检查"))
        window_code = cls._normalize_text(payload.get("window_code"), default=f"{report_type}_window")
        window_label = cls._normalize_text(payload.get("window_label"), default=DEFAULT_WINDOW_LABELS.get(report_type, "辅助检查窗"))
        test_items = [cls._normalize_text(item) for item in (payload.get("test_items") or []) if cls._normalize_text(item)]
        report_items = cls._normalize_report_items(payload, report_type, test_items)
        if not test_items:
            if report_type == "medical_imaging":
                test_items = [item["exam_name"] for item in report_items if item.get("exam_name")]
            else:
                test_items = [item["item_name"] for item in report_items if item.get("item_name")]
        key_findings = cls._derive_key_findings(report_type, report_items, report_summary)
        preliminary_assessment = cls._build_preliminary_assessment(report_type, report_items, key_findings, report_summary)
        normalized = {
            "simulation": bool(payload.get("simulation", True)),
            "simulation_version": payload.get("simulation_version") or "v3",
            "template_version": payload.get("template_version") or REPORT_TEMPLATE_VERSION,
            "generated_at": payload.get("generated_at") or now_iso(),
            "report_type": report_type,
            "category_code": category_code,
            "category_label": category_label,
            "window_code": window_code,
            "window_label": window_label,
            "report_title": cls._normalize_text(payload.get("report_title"), default=REPORT_TITLE_LABELS.get(report_type, "辅助检查报告")),
            "test_items": test_items,
            "report_items": report_items,
            "key_findings_cn": key_findings,
            "preliminary_assessment": preliminary_assessment,
            "source": cls._normalize_text(payload.get("source"), default="simulated_report"),
        }
        normalized["display_text_cn"] = cls._normalize_text(
            payload.get("display_text_cn"),
            default=cls._build_display_text(normalized),
        )
        normalized["report_text"] = cls._normalize_text(payload.get("report_text"), default=normalized["display_text_cn"])
        normalized_summary = dict(report_summary)
        normalized_summary["impression"] = cls._normalize_text(
            normalized_summary.get("impression"),
            default=preliminary_assessment["summary_cn"],
        )
        normalized_summary["reason"] = cls._normalize_text(normalized_summary.get("reason"))
        normalized_summary["priority"] = cls._normalize_text(normalized_summary.get("priority"), default="M")
        normalized_summary["confidence"] = normalized_summary.get("confidence", 0.72)
        normalized_summary["next_step"] = cls._normalize_text(normalized_summary.get("next_step"), default="return_consultation")
        normalized_summary["key_findings"] = key_findings
        normalized_summary["key_findings_cn"] = key_findings
        normalized_summary["acuity_level"] = cls._normalize_text(normalized_summary.get("acuity_level"), default="routine")
        normalized_summary["supports_current_department"] = bool(normalized_summary.get("supports_current_department", True))
        normalized_summary["cross_specialty_clues"] = list(normalized_summary.get("cross_specialty_clues") or [])
        normalized_summary["escalation_clues"] = dict(normalized_summary.get("escalation_clues") or {"to_emergency": False, "to_icu": False, "reason": ""})
        normalized_summary["suggested_next_context"] = cls._normalize_text(
            normalized_summary.get("suggested_next_context"),
            default="结合当前检查结果完成二轮复核",
        )
        normalized_summary["summary"] = normalized["display_text_cn"]
        normalized_summary["preliminary_assessment"] = preliminary_assessment
        normalized["report_summary"] = normalized_summary
        return normalized

    @classmethod
    def build_summary_text(cls, report: dict | None) -> str:
        normalized = cls.normalize_report(report)
        if not normalized:
            return "无"
        category_label = cls._normalize_text(normalized.get("category_label"), default="辅助检查")
        preliminary = dict(normalized.get("preliminary_assessment") or {})
        abnormal_items = [cls._normalize_text(item) for item in (preliminary.get("abnormal_items") or []) if cls._normalize_text(item)]
        key_findings = [cls._normalize_text(item) for item in (normalized.get("key_findings_cn") or []) if cls._normalize_text(item)]
        if abnormal_items:
            return cls._join_nonempty([category_label, "异常项", cls._join_nonempty(abnormal_items[:2], separator="；")], separator="：", default="无")
        if key_findings:
            return cls._join_nonempty([category_label, cls._join_nonempty(key_findings[:2], separator="；")], separator="：", default="无")
        return cls._join_nonempty(
            [category_label, cls._normalize_text(preliminary.get("summary_cn"), default="结果待结合临床复核")],
            separator="：",
            default="无",
        )

    @classmethod
    def build_card_from_report(cls, report: dict | None, *, source: str = "simulated_report") -> dict:
        normalized = cls.normalize_report(report)
        if not normalized:
            return cls.build_pending_view(source=source)
        sections = cls._build_sections(normalized)
        return {
            "status": "ready",
            "title": normalized["report_title"],
            "display_text": normalized["display_text_cn"],
            "sections": sections,
            "generated_at": normalized.get("generated_at"),
            "source": source,
            "report_type": normalized["report_type"],
        }

    @classmethod
    def build_pending_view(cls, *, source: str = "simulated_report") -> dict:
        sections = [
            {"title": "检查类型", "content": "无"},
            {"title": "项目结果", "content": "无"},
            {"title": "关键发现", "content": "无"},
            {"title": "初步判断", "content": "无"},
        ]
        return {
            "status": "pending",
            "title": "检查报告卡",
            "display_text": "\n".join(f"{section['title']}：{section['content']}" for section in sections),
            "sections": sections,
            "generated_at": None,
            "source": source,
            "report_type": None,
        }

    def get_card_for_visit(self, visit_id: str) -> dict:
        if self.visit_repo is None:
            return self.build_pending_view()
        visit_data = self.visit_repo.get_visit_data(visit_id)
        return self.build_card_from_report(visit_data.get("simulated_report"))
