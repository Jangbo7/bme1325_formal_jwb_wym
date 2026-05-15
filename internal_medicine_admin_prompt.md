# Internal Medicine Agent 修改 Pipeline

## 背景与目标
- 当前 `internal_medicine` 存在以下主要问题：重复追问、final plan 输出不稳定、final 后对话行为不一致、信息不足判定偏严、重症升级策略不够严格。
- 本文档目标是将需求整理为可直接执行的分阶段实现 Pipeline，避免协作过程中的二次理解偏差。
- 产出导向：每阶段都有明确输入、输出、验收标准和边界约束。

## 本期范围与非范围
- 本期范围：
- 仅定义并推进内科 agent 的追问策略、final 输出结构、final 后会话行为、ICU 升级规则。
- 明确与 triage/ICU 的接口边界和协作方式，但不重构它们的内部实现。
- 强化 fallback 与校验器，保证 LLM 异常时仍可稳定输出。
- 非范围：
- 不改 visit 主状态机总体业务流转。
- 不引入支付、检查中心等新业务模块实现。
- 不修改前端交互协议，只要求现有消费端可识别新增 `message_type`。

## 三阶段实现计划（P0/P1/P2）
- P0 稳定性与基线阶段（先做）
- 修复文档与提示词相关文本编码，统一为 UTF-8。
- 清理现有乱码文案，确保追问与 final 文案可读、可回归。
- 固定最小可运行流程基线：`create_session -> followup -> complete`，并保留可复现样例。
- 交付产物：编码修复报告 + 基线回归结果。
- P1 追问策略阶段
- 在 `consultation_progress` 扩展追问护栏字段，纳入持续会话记忆。
- 增加 `prioritize_missing_fields()`，实现字段优先级、刚问过降权、重复追问换问法。
- 强化 `extract_structured_updates()`，提升中文自由文本信息抽取质量，减少误判“信息不足”。
- 交付产物：追问策略变更说明 + 重复追问回归结果。
- P2 Final 与重症升级阶段
- 强制 final 输出为固定结构中文方案（LLM 与 fallback 同结构）。
- 实现 final 后行为约束：不主动追问，仅重评估并输出“更新版 final”或“建议不变”。
- 建立 ICU 升级硬规则优先机制（deterministic red flags），LLM 仅补充解释。
- 交付产物：final schema 示例 + ICU 命中案例回归结果。

## 接口与数据契约（仅内科 agent）
- `consultation_progress` 新增字段：
- `asked_fields_history`
- `last_question_focus`
- `last_question_text`
- `last_extracted_fields`
- final 结构要求至少包含以下字段：
- `assistant_message`
- `complete`
- `department`
- `priority`
- `diagnosis_level`
- `note`
- `patient_plan`
- `tests_suggested`
- `medication_or_action`
- `red_flags`
- `message_type` 扩展建议：
- `followup | final | final_update | final_no_change`
- 约束：
- LLM 输出不满足 final schema 时，必须回退到 fallback，同样输出完整结构。
- 所有 final 输出字段名保持稳定，不允许阶段内随意变更。

## 状态与会话行为约束（含 final 后行为）
- 状态推进原则：
- P0 不调整主业务状态机，仅在内科 agent 内保证会话逻辑一致。
- P1 只增强追问策略，不放宽到“无条件完成”。
- P2 再引入 final 后重评估逻辑。
- final 后行为（强约束）：
- agent 不再主动发起信息采集式追问。
- 患者追加信息时允许重评估。
- 若影响结论：输出 `final_update`。
- 若不影响结论：输出 `final_no_change`，明确“当前建议不变”。
- 禁止行为：
- final 后回退到常规 follow-up 循环。
- final 后丢失历史结论并重新从头问诊。

## ICU 升级规则（硬规则优先）
- 升级策略分层：
- 第一层：deterministic red flags 命中即触发升级建议（优先级与诊室建议直接提升）。
- 第二层：LLM 仅生成解释与面向患者的补充说明，不得覆盖第一层结论。
- 规则要求：
- red flags 可审计、可复现、可回归测试。
- 升级动作至少影响 `priority` 与 `department`（或等价诊室建议字段）。
- 回退要求：
- 即使 LLM 不可用，也必须输出带 red flags 解释的结构化 final。

## 测试与验收清单
- 重复追问：同一字段不可连续使用同问法追问。
- 信息不足判定：患者多轮有效补充后可进入完成，不得无限追问。
- final 一致性：LLM 成功与失败路径均输出同结构 final。
- final 后会话：不回退主动追问；仅允许 `final_update` 或 `final_no_change`。
- ICU 升级：命中 red flags 时必须触发优先级/诊室升级建议。
- 兼容性：旧 session memory 无新增字段时可自动补默认值并继续运行。

## 风险与回退方案
- 风险：
- 一次性改动过多导致行为漂移，影响现网会话稳定性。
- LLM 返回不稳定导致 final 字段缺失。
- 与 triage/ICU 的边界不清导致协作冲突。
- 回退方案：
- 按 P0/P1/P2 分阶段开关控制，未通过验收不进入下一阶段。
- 保留 fallback 同结构输出能力作为最终兜底。
- 若 P2 不稳定，可回退至 P1（追问稳定版）继续运行。

## 唯一修改文件声明
- 本次改造说明文档仅修改 `internal_medicine_admin_prompt.md`。
- 不触碰任何代码文件和其他 Markdown 文件。
