# Internal Medicine Agent 修改 Prompt

请修改主分支里的 `internal_medicine` 医生 agent，目标是一次性解决以下 4 个问题：

1. 医生经常重复追问患者类似问题。
2. 医生最后不能稳定输出固定格式的 final plan。
3. 医生已经给出 final plan 后，患者再发消息时，agent 仍会重新进入“主动追问”模式。
4. 当前“信息不足”的判定过严，已经有多轮有效对话后，系统仍然认为信息不够。
5. 需要保留原有“根据后续交流自动升降分诊/风险等级”的能力，同时新增一个更严格的“严重症状直接建议转 ICU/更换诊室”能力。

请先阅读并理解当前实现，再修改。重点查看：
- `backend/app/agents/internal_medicine/`
- `backend/app/api/routes/internal_medicine.py`
- `backend/rag/internal_medicine_rules.json`
- 参考 `backend/app/agents/triage/` 中较成熟的 follow-up 设计

## 一、追问逻辑改造

1. 为 internal_medicine 增加和 triage 类似的追问护栏：
   - `asked_fields_history`
   - `last_question_focus`
   - `last_question_text`
   - 本轮提取成功字段
   - 仍未解决字段
2. 不要直接按 `build_missing_fields()` 原顺序追问；新增 `prioritize_missing_fields()`：
   - 优先问更关键字段
   - 刚问过的字段降级
   - 同一字段再次追问时必须换一种问法
3. 强化 `extract_structured_updates()`：
   - 能从自然中文中提取 onset / allergies / symptoms / 关键补充信息
   - 不要把整段回复粗暴当 chief complaint
   - 能识别“部分回答”“模糊回答”“只补一个点”的情况
4. follow-up 生成改成两层：
   - LLM 追问
   - fallback 追问模板
5. 对 LLM follow-up 增加校验：
   - `question_focus` 必须属于 `missing_fields`
   - 不能和 `last_question_text` 完全一致
   - 若 recommendation 未变化，不要反复重复同样的建议
6. fallback 追问模板请提供多个中文变体，避免复读。

## 二、final plan 输出改造

1. final 阶段不要再输出自由短句，必须输出固定格式、面向患者的中文 final plan。
2. final plan 至少包含：
   - 本次初步判断
   - 建议就诊科室
   - 优先级
   - 下一步流程
   - 检查/化验建议
   - 用药/处理建议
   - 何时需要尽快复诊或急诊
3. `下一步流程` 请固定为编号步骤，并明确包含以下候选内容（按病情选择其一部分或组合，不要每次全塞）：
   1. 到化验科进行血检和尿检
   2. 去影像科拍摄腹部CT或其他影像
   3. 直接根据病情开药并取药
   4. 医生评估后决定住院进一步检查
4. 即使 LLM 不可用，也必须由 fallback 生成同样结构的 final plan。
5. 调整 prompt / validator，让 LLM 返回严格 JSON，至少包含：
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

## 三、final plan 之后的会话行为

1. 一旦 agent 已输出 final plan，后续患者再发消息时：
   - agent 不应再主动追问病人
   - 不应重新回到“收集信息式追问”流程
2. 如果患者主动补充了新信息：
   - agent 应读取新增信息
   - 判断是否影响原 final plan
   - 如有影响，则输出“更新后的 final plan”
   - 如无明显影响，则输出“基于你补充的信息，当前建议暂不变”
3. 也就是说：
   - final 之后允许“更新建议”
   - 但不允许“重新主动追问”

## 四、放宽“信息不足”判定

1. 不要再用过于死板的缺字段策略。
2. 当满足以下任一条件时，应允许进入 final：
   - 关键字段已基本齐全
   - 患者已进行多轮有效补充，已足够支持门诊级建议
   - 虽仍有少量缺失，但不影响给出初步处理流程
3. 不要因为少数非关键字段缺失，就在多轮有效对话后持续追问。
4. “是否还能继续问”要更保守；“是否已经足够给出初步 plan”要更宽松。

## 五、RAG 约束

1. 检查 `internal_medicine_rules.json` 是否导致重复追问或泛化建议。
2. RAG 主要作为：
   - 证据支持
   - final plan 素材来源
   - 检查/化验/处理路径建议来源
3. 不要让 RAG 直接主导对话节奏。
4. 如有需要，可补充规则 schema，使其更适合生成稳定的 final plan。

## 六、风险升级与 ICU 跳转逻辑

1. 保留已有能力：如果患者在后续对话中补充了和当前分诊等级不匹配的新症状，agent 仍然可以自动升高或降低当前风险判断/建议等级。
2. 在此基础上，新增一个更严格的 ICU 跳转能力：
   - 不管当前原始分诊等级是什么
   - 只要能较高置信度确认患者正在描述严重危险症状
   - agent 应直接给出“建议立即更换到 ICU / 紧急诊室 / 重症处理通道”的结果
3. 这个 ICU 跳转判定必须严格，不能仅凭关键词命中：
   - 需要尽量基于“患者当前真实症状”判断
   - 要区分“真实症状陈述”与“情绪表达/担忧/假设/否定表达”
4. 以下这类表达默认不能直接触发 ICU 跳转，除非还有其他强阳性症状证据：
   - “我真害怕我别再病死了”
   - “我现在特别怕休克晕厥”
   - “我暂时还没有窒息的感觉”
   - 其他仅提到严重词汇，但并非患者真实正在发生的症状的表达
5. 请为严重症状识别增加更严谨的规则或解析逻辑，至少考虑：
   - 否定表达
   - 假设表达
   - 担忧/恐惧表达
   - 引述型表达
   - 真实正在发生的急危重症状表达
6. 一旦满足 ICU 跳转条件：
   - 不要继续普通追问
   - 不要继续维持普通 final plan
   - 直接输出高优先级紧急建议
   - 明确提示需要转 ICU / 重症监护 / 紧急处理
7. 如当前系统里已有升级/降级逻辑，请尽量复用，不要并行再造一套互相冲突的机制；新增的 ICU 跳转应该是更高优先级的 override。

## 七、测试要求

请补充/修改测试，至少覆盖：
1. 已回答某字段后，下一轮不会原样重复追问该字段。
2. 模糊回答时，会换一种问法，而不是复读。
3. 多轮有效补充后，即使还缺少次要字段，也能进入 final。
4. 已输出 final plan 后，患者再次发消息时，agent 不会重新主动追问。
5. 已输出 final plan 后，若患者补充新信息，agent 会更新 final plan，而不是回退到追问模式。
6. fallback final message 与 LLM final message 都有固定结构和“下一步流程”。
7. 患者补充的真实严重症状会触发升级，必要时直接建议转 ICU。
8. “害怕休克”“担心病死了”“暂时没有窒息”这类情绪/否定/假设表达，不会被误判成 ICU 跳转。

## 输出要求

1. 先简要说明你判断的根因。
2. 再实施修改。
3. 最后总结：
   - 修改了哪些文件
   - 如何解决了以上问题
   - 新增了哪些测试
   - 还剩什么风险
