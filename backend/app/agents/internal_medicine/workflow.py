from enum import Enum


class ConsultationStep(str, Enum):
    CHIEF_COMPLAINT = "chief_complaint"
    ONSET_TIME = "onset_time"
    SYMPTOMS = "symptoms"
    SEVERITY = "severity"
    MEDICAL_HISTORY = "medical_history"
    ALLERGIES = "allergies"
    CURRENT_MEDICATIONS = "current_medications"
    VITAL_SIGNS = "vital_signs"

    DIAGNOSIS_MILD = "diagnosis_mild"
    TREATMENT_PLAN_MILD = "treatment_plan_mild"
    MEDICATION_FEEDBACK = "medication_feedback"
    ADJUST_MEDICATION = "adjust_medication"
    TREATMENT_CONFIRMED = "treatment_confirmed"
    FOLLOW_UP_MILD = "follow_up_mild"

    ORDER_TESTS = "order_tests"
    TESTS_PENDING = "tests_pending"
    TEST_RESULTS = "test_results"
    DIAGNOSIS_MODERATE = "diagnosis_moderate"
    TREATMENT_PLAN_MODERATE = "treatment_plan_moderate"
    FOLLOW_UP_MODERATE = "follow_up_moderate"

    COMPLETE = "complete"


CONSULTATION_STEPS = [
    {
        "step": ConsultationStep.CHIEF_COMPLAINT,
        "question": "您今天主要哪里不舒服？有什么症状？",
        "keywords": ["主诉", "concern", "complaint", "problem", "不舒服", "症状", "尿急", "发烧", "咳嗽"],
        "required_field": "chief_complaint",
        "level": "all",
    },
    {
        "step": ConsultationStep.ONSET_TIME,
        "question": "这些症状什么时候开始的？持续多久了？",
        "keywords": ["时间", "什么时候", "when", "duration", "多久", "onset", "开始", "天", "小时"],
        "required_field": "onset_time",
        "level": "all",
    },
    {
        "step": ConsultationStep.SYMPTOMS,
        "question": "请详细描述一下您的症状（位置、类型、程度）",
        "keywords": ["症状", "symptom", "感觉", "感觉如何", "描述", "describe", "疼", "痛", "难受"],
        "required_field": "symptoms",
        "level": "all",
    },
    {
        "step": ConsultationStep.SEVERITY,
        "question": "如果从1到10评分，您的难受程度是多少？有什么加重或缓解的因素吗？",
        "keywords": ["严重", "pain", "痛", "难受", "severity", "评分", "1-10", "几分"],
        "required_field": "severity",
        "level": "all",
    },
    {
        "step": ConsultationStep.MEDICAL_HISTORY,
        "question": "您有什么既往病史或慢性病吗？",
        "keywords": ["病史", "history", "慢性病", "chronic", "之前", "以往", "medical history", "糖尿病", "高血压"],
        "required_field": "medical_history",
        "level": "all",
    },
    {
        "step": ConsultationStep.ALLERGIES,
        "question": "您有什么药物或食物过敏吗？",
        "keywords": ["过敏", "allergy", "过敏史", "药物过敏", "food allergy", "青霉素", "海鲜"],
        "required_field": "allergies",
        "level": "all",
    },
    {
        "step": ConsultationStep.CURRENT_MEDICATIONS,
        "question": "您目前有在服用什么药物吗？",
        "keywords": ["药物", "medication", "吃药", "用药", "medicine", "taking", "服用", "吃药"],
        "required_field": "current_medications",
        "level": "all",
    },
    {
        "step": ConsultationStep.VITAL_SIGNS,
        "question": "让我为您检查一下生命体征（体温、血压、心率）",
        "keywords": ["体温", "血压", "心率", "vital", "temperature", "bp", "hr", "检查"],
        "required_field": "vital_signs",
        "level": "all",
    },
    {
        "step": ConsultationStep.DIAGNOSIS_MILD,
        "question": "根据您的症状，我初步判断您可能患有：",
        "keywords": ["诊断", "diagnosis", "可能", "likely", "probably", "判断"],
        "required_field": "diagnosis",
        "level": "1",
    },
    {
        "step": ConsultationStep.TREATMENT_PLAN_MILD,
        "question": "这是我的治疗建议：",
        "keywords": ["治疗", "treatment", "建议", "recommend", "处方", "prescription", "开药"],
        "required_field": "treatment_plan",
        "level": "1",
    },
    {
        "step": ConsultationStep.MEDICATION_FEEDBACK,
        "question": "您觉得这个药怎么样？药量是太强、太弱还是正好？",
        "keywords": ["反馈", "感觉", "太强", "太弱", "正好", "ok", "good", "fine", "反馈", "feedback", "合适"],
        "required_field": "medication_feedback",
        "level": "1",
    },
    {
        "step": ConsultationStep.ADJUST_MEDICATION,
        "question": "好的，我来根据您的反馈调整一下处方：",
        "keywords": ["调整", "modify", "改变", "change"],
        "required_field": "adjusted_treatment",
        "level": "1",
    },
    {
        "step": ConsultationStep.TREATMENT_CONFIRMED,
        "question": "好的！您的处方已确认。如果症状持续请复诊。",
        "keywords": ["满意", "confirmed", "ok", "good", "好的", "可以", "谢谢"],
        "required_field": "confirmation",
        "level": "1",
    },
    {
        "step": ConsultationStep.FOLLOW_UP_MILD,
        "question": "如果症状持续请安排复诊。您还有什么问题吗？",
        "keywords": ["复诊", "follow up", "后续", "问题", "question", "没有了", "好的"],
        "required_field": "follow_up",
        "level": "1",
    },
    {
        "step": ConsultationStep.ORDER_TESTS,
        "question": "我建议您做一些检查：X光片、血检和/或尿检。这次问诊结束后请去检验科。",
        "keywords": ["检查", "检验", "test", "xray", "x-ray", "血检", "尿检", "lab", "拍片"],
        "required_field": "ordered_tests",
        "level": "2+",
    },
    {
        "step": ConsultationStep.TESTS_PENDING,
        "question": "请完成检查后带着结果回来。您检查完成了吗？",
        "keywords": ["完成", "done", "回来了", "completed", "results", "做完了", "检查完了"],
        "required_field": "tests_completed",
        "level": "2+",
    },
    {
        "step": ConsultationStep.TEST_RESULTS,
        "question": "请把您的检查结果告诉我。",
        "keywords": ["结果", "results", "报告", "report", "拿到了"],
        "required_field": "test_results",
        "level": "2+",
    },
    {
        "step": ConsultationStep.DIAGNOSIS_MODERATE,
        "question": "根据您的检查结果，我现在可以给您更准确的诊断了：",
        "keywords": ["诊断", "diagnosis", "结果", "based on"],
        "required_field": "diagnosis",
        "level": "2+",
    },
    {
        "step": ConsultationStep.TREATMENT_PLAN_MODERATE,
        "question": "这是根据您的诊断和检查结果制定的治疗方案：",
        "keywords": ["治疗", "treatment", "建议", "recommend", "处方", "prescription", "方案"],
        "required_field": "treatment_plan",
        "level": "2+",
    },
    {
        "step": ConsultationStep.FOLLOW_UP_MODERATE,
        "question": "请安排复诊预约。您对治疗方案有什么问题吗？",
        "keywords": ["复诊", "follow up", "后续", "问题", "question", "没有了"],
        "required_field": "follow_up",
        "level": "2+",
    },
]


STEP_INDEX = {s["step"]: idx for idx, s in enumerate(CONSULTATION_STEPS)}

MILD_STEPS = [
    ConsultationStep.DIAGNOSIS_MILD,
    ConsultationStep.TREATMENT_PLAN_MILD,
    ConsultationStep.MEDICATION_FEEDBACK,
    ConsultationStep.ADJUST_MEDICATION,
    ConsultationStep.TREATMENT_CONFIRMED,
    ConsultationStep.FOLLOW_UP_MILD,
]

MODERATE_STEPS = [
    ConsultationStep.ORDER_TESTS,
    ConsultationStep.TESTS_PENDING,
    ConsultationStep.TEST_RESULTS,
    ConsultationStep.DIAGNOSIS_MODERATE,
    ConsultationStep.TREATMENT_PLAN_MODERATE,
    ConsultationStep.FOLLOW_UP_MODERATE,
]


class ConsultationProgress:
    def __init__(
        self,
        current_step: ConsultationStep = ConsultationStep.CHIEF_COMPLAINT,
        severity_level: int = 1,
    ):
        self.current_step = current_step
        self.severity_level = severity_level
        self.collected_info: dict[str, str] = {}
        self.step_history: list[str] = []
        self.medication_adjustments: list[dict] = []
        self.ordered_tests: list[str] = []

    def get_workflow_path(self) -> list[ConsultationStep]:
        if self.severity_level == 1:
            return [ConsultationStep.CHIEF_COMPLAINT] + MILD_STEPS + [ConsultationStep.COMPLETE]
        else:
            return [ConsultationStep.CHIEF_COMPLAINT] + MODERATE_STEPS + [ConsultationStep.COMPLETE]

    def advance(self, field_name: str, value: str):
        self.collected_info[field_name] = value
        if self.current_step.value not in self.step_history:
            self.step_history.append(self.current_step.value)

    def get_next_step(self) -> ConsultationStep | None:
        workflow = self.get_workflow_path()
        try:
            current_idx = workflow.index(self.current_step)
            if current_idx + 1 < len(workflow):
                return workflow[current_idx + 1]
            return ConsultationStep.COMPLETE
        except ValueError:
            return ConsultationStep.COMPLETE

    def get_current_question(self) -> str:
        for s in CONSULTATION_STEPS:
            if s["step"] == self.current_step:
                return s["question"]
        return "How can I help you today?"

    def is_complete(self) -> bool:
        return self.current_step == ConsultationStep.COMPLETE

    def to_dict(self) -> dict:
        return {
            "current_step": self.current_step.value,
            "severity_level": self.severity_level,
            "collected_info": self.collected_info,
            "step_history": self.step_history,
            "medication_adjustments": self.medication_adjustments,
            "ordered_tests": self.ordered_tests,
            "progress_percent": self._calc_progress(),
        }

    def _calc_progress(self) -> int:
        if self.current_step == ConsultationStep.COMPLETE:
            return 100
        workflow = self.get_workflow_path()
        try:
            idx = workflow.index(self.current_step)
            return min(95, int((idx / len(workflow)) * 100))
        except ValueError:
            return 0

    @classmethod
    def from_dict(cls, data: dict) -> "ConsultationProgress":
        progress = cls(
            current_step=ConsultationStep(data.get("current_step", "chief_complaint")),
            severity_level=data.get("severity_level", 1),
        )
        progress.collected_info = data.get("collected_info", {})
        progress.step_history = data.get("step_history", [])
        progress.medication_adjustments = data.get("medication_adjustments", [])
        progress.ordered_tests = data.get("ordered_tests", [])
        return progress


def detect_info_collected(user_message: str, current_step: ConsultationStep) -> tuple[bool, str | None]:
    msg_lower = user_message.lower()
    step_info = None
    for s in CONSULTATION_STEPS:
        if s["step"] == current_step:
            step_info = s
            break
    if not step_info:
        return False, None

    for keyword in step_info.get("keywords", []):
        if keyword.lower() in msg_lower:
            return True, step_info["required_field"]

    if len(user_message.strip()) > 10:
        return True, step_info["required_field"]

    return False, None


def detect_medication_feedback(user_message: str) -> str | None:
    msg_lower = user_message.lower()
    if any(term in msg_lower for term in ["太强", "too strong", "strong", "太重"]):
        return "too_strong"
    if any(term in msg_lower for term in ["太弱", "too weak", "weak", "太轻"]):
        return "too_weak"
    if any(term in msg_lower for term in ["正好", "ok", "good", "fine", "可以", "好"]):
        return "ok"
    return None


def detect_test_completion(user_message: str) -> bool:
    msg_lower = user_message.lower()
    return any(
        term in msg_lower
        for term in ["done", "completed", "完成", "回来了", "here", "results", "结果", "报告"]
    )


def should_advance_step(progress: ConsultationProgress, user_message: str) -> bool:
    if progress.current_step == ConsultationStep.MEDICATION_FEEDBACK:
        return detect_medication_feedback(user_message) is not None
    if progress.current_step == ConsultationStep.TESTS_PENDING:
        return detect_test_completion(user_message)
    if progress.current_step == ConsultationStep.TREATMENT_CONFIRMED:
        msg_lower = user_message.lower()
        return any(term in msg_lower for term in ["满意", "confirmed", "ok", "good", "好的", "可以", "谢谢"])
    return detect_info_collected(user_message, progress.current_step)[0]
