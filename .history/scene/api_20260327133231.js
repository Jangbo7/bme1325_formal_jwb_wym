const API_CONFIG = {
  model: "qwen2.5-vl-instruct",
  apiKey: "7cbf678f86e24121864883fd950e3449",
  baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1",
};

export async function callQwenAPI(messages, systemPrompt = "") {
  const fullMessages = [];
  if (systemPrompt) {
    fullMessages.push({ role: "system", content: systemPrompt });
  }
  fullMessages.push(...messages);

  try {
    const response = await fetch(`${API_CONFIG.baseURL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${API_CONFIG.apiKey}`,
      },
      body: JSON.stringify({
        model: API_CONFIG.model,
        messages: fullMessages,
        max_tokens: 500,
        temperature: 0.7,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error?.message || `API Error: ${response.status}`);
    }

    const data = await response.json();
    return data.choices[0]?.message?.content || "抱歉，我没有收到回复。";
  } catch (error) {
    console.error("[API] Qwen API call failed:", error);
    return `网络错误: ${error.message}`;
  }
}

export const MEDICAL_SYSTEM_PROMPT = `你是一位医院分诊台的智能护士，名叫"小医"。你需要：
1. 礼貌地问候患者，询问他们的症状
2. 根据症状建议合适的科室（内科、外科、儿科、眼科等）
3. 如果是紧急情况，提醒患者去急诊
4. 保持专业、耐心、友善的态度
5. 回答简明扼要，一般不超过3句话
6. 可以提供一些基本的健康建议

当前医院科室：
- 内科：常见疾病、感冒发烧、慢性病
- 外科：需要手术的疾病、创伤
- 儿科：14岁以下儿童
- 眼科：眼睛相关疾病
- 骨科：骨骼、关节疾病
- 急诊：紧急情况、危重病人`;

export const DOCTOR_SYSTEM_PROMPT = `你是一位专业的医生，名叫"Dr.张"。你需要：
1. 仔细询问患者的症状和病史
2. 提供专业的医疗建议
3. 如需进一步检查，建议患者去做相应检查
4. 开具处方或建议住院治疗
5. 保持专业、温和的态度
6. 回答要专业但易懂`;

export function createUserMessage(content) {
  return { role: "user", content };
}

export function createAssistantMessage(content) {
  return { role: "assistant", content };
}
