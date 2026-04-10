#!/usr/bin/env python3
"""
Standalone script to run Internal Medicine Doctor Agent for testing.
This allows debugging the agent without starting the main application.

Usage:
    python run_internal_medicine_agent.py

Requirements:
    - Set API keys in environment or .env file:
        GPT52_API_KEY or LLM_API_KEY
        LLM_ENDPOINT (optional, defaults to internal API)
        LLM_MODEL (optional, defaults to GPT-5.2)
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone

# 注释掉不需要的导入
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 
# from services.private_api_config import get_backend_private_config
# from app.agents.internal_medicine import create_internal_medicine_service
# from app.agents.internal_medicine.service import InternalMedicineService
# from app.domain.patient.state_machine import PatientStateMachine
# from app.events.bus import EventBus


# 注释掉不需要的类
# class MockPatient:
#     def __init__(self, patient_id, name, lifecycle_state="untriaged", priority="M", location="internal"):
#         self.patient_id = patient_id
#         self.name = name
#         self.lifecycle_state = lifecycle_state
#         self.priority = priority
#         self.location = location
#         self.session_id = None
#         self.triage_level = None
#         self.triage_note = None
#         self.updated_at = datetime.now(timezone.utc).isoformat()


# class MockPatientRepository:
#     def __init__(self):
#         self.patients = {}

#     def upsert_basic(self, patient_id, name):
#         if patient_id not in self.patients:
#             self.patients[patient_id] = MockPatient(patient_id, name)
#         else:
#             self.patients[patient_id].name = name
#             self.patients[patient_id].updated_at = datetime.now(timezone.utc).isoformat()

#     def get(self, patient_id):
#         if patient_id in self.patients:
#             p = self.patients[patient_id]
#             return {
#                 "id": p.patient_id,
#                 "name": p.name,
#                 "lifecycle_state": p.lifecycle_state,
#                 "priority": p.priority,
#                 "location": p.location,
#                 "session_id": p.session_id,
#                 "triage_level": p.triage_level,
#                 "triage_note": p.triage_note,
#                 "updated_at": p.updated_at,
#             }
#         return None

#     def update_patient(self, patient_id, **kwargs):
#         if patient_id in self.patients:
#             for key, value in kwargs.items():
#                 setattr(self.patients[patient_id], key, value)
#             self.patients[patient_id].updated_at = datetime.now(timezone.utc).isoformat()

#     def list(self):
#         return list(self.patients.values())

#     def to_view(self, patient, **kwargs):
#         return patient


# class MockSession:
#     def __init__(self, session_id, patient_id, dialogue_state="idle"):
#         self.session_id = session_id
#         self.patient_id = patient_id
#         self.dialogue_state = dialogue_state
#         self.created_at = datetime.now(timezone.utc).isoformat()
#         self.updated_at = datetime.now(timezone.utc).isoformat()
#         self.turns = []


# class MockSessionRepository:
#     def __init__(self):
#         self.sessions = {}

#     def create_or_update(self, session_id, patient_id, dialogue_state):
#         if session_id not in self.sessions:
#             self.sessions[session_id] = MockSession(session_id, patient_id, dialogue_state)
#         else:
#             self.sessions[session_id].dialogue_state = dialogue_state
#             self.sessions[session_id].updated_at = datetime.now(timezone.utc).isoformat()

#     def get(self, session_id):
#         if session_id in self.sessions:
#             s = self.sessions[session_id]
#             return {
#                 "id": s.session_id,
#                 "patient_id": s.patient_id,
#                 "dialogue_state": s.dialogue_state,
#                 "created_at": s.created_at,
#                 "updated_at": s.updated_at,
#             }
#         return None

#     def update_state(self, session_id, dialogue_state):
#         if session_id in self.sessions:
#             self.sessions[session_id].dialogue_state = dialogue_state
#             self.sessions[session_id].updated_at = datetime.now(timezone.utc).isoformat()

#     def append_turn(self, session_id, patient_id, role, message, timestamp, metadata=None):
#         if session_id not in self.sessions:
#             self.sessions[session_id] = MockSession(session_id, patient_id)
#         self.sessions[session_id].turns.append({
#             "role": role,
#             "message": message,
#             "timestamp": timestamp,
#             "metadata": metadata or {},
#         })

#     def list_turns(self, session_id):
#         if session_id in self.sessions:
#             return self.sessions[session_id].turns
#         return []


# class MockMemoryRepository:
#     def __init__(self):
#         self.shared_memory = {}
#         self.agent_memory = {}

#     def get_shared_memory(self, patient_id, name=""):
#         if patient_id not in self.shared_memory:
#             self.shared_memory[patient_id] = {
#                 "patient_id": patient_id,
#                 "profile": {
#                     "name": name or patient_id,
#                     "age": None,
#                     "sex": None,
#                     "allergies": [],
#                     "allergy_status": "unknown",
#                     "chronic_conditions": [],
#                     "baseline_risk_flags": [],
#                 },
#                 "clinical_memory": {
#                     "chief_complaint": "",
#                     "symptoms": [],
#                     "onset_time": None,
#                     "vitals": {},
#                     "risk_flags": [],
#                     "last_department": None,
#                     "last_diagnosis_level": None,
#                 },
#             }
#         return self.shared_memory[patient_id]

#     def save_shared_memory(self, patient_id, payload):
#         self.shared_memory[patient_id] = payload

#     def get_agent_session_memory(self, session_id, patient_id, agent_type="internal_medicine"):
#         key = f"{session_id}_{patient_id}_{agent_type}"
#         if key not in self.agent_memory:
#             self.agent_memory[key] = {
#                 "session_id": session_id,
#                 "patient_id": patient_id,
#                 "agent_type": agent_type,
#                 "dialogue_state": "idle",
#                 "latest_summary": {},
#                 "missing_fields": [],
#                 "expected_field": None,
#                 "assistant_message": "",
#                 "evidence": [],
#             }
#         return self.agent_memory[key]

#     def save_agent_session_memory(self, session_id, patient_id, payload, agent_type="internal_medicine"):
#         key = f"{session_id}_{patient_id}_{agent_type}"
#         self.agent_memory[key] = payload

#     def append_internal_medicine_history(self, patient_id, session_id, payload, created_at):
#         pass


# class MockQueueRepository:
#     def get_active_ticket_for_patient(self, patient_id):
#         return None


# 简化的banner
# def print_banner():
#     print("=" * 60)
#     print("Internal Medicine Doctor Agent - Standalone Testing Mode")
#     print("=" * 60)
#     print()
#     print("You can test the Internal Medicine doctor consultation here.")
#     print("Type 'quit' or 'exit' to end the session.")
#     print("Type 'reset' to start a new session.")
#     print()


# 简化的response打印
# def print_response(response):
#     print("\n" + "-" * 40)
#     print("Doctor's Response:")
#     print("-" * 40)
#     if "dialogue" in response:
#         msg = response["dialogue"].get("assistant_message", "No message")
#         print(msg)
#     if "patient" in response and response["patient"]:
#         patient = response["patient"]
#         print(f"\n[Patient: {patient.get('name', 'Unknown')}]")
#         print(f"[State: {patient.get('lifecycle_state', 'unknown')}]")
#     print("-" * 40)


# 简单的LLM调用函数
from urllib import request as urlrequest

def call_llm(api_key, endpoint, model, messages):
    """直接调用LLM API"""
    req = urlrequest.Request(
        endpoint,
        data=json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": 0,
                "n": 1,
                "stop": [],
                "stream": False,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            }
        ).encode("utf-8"),
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))

    #print(f"[DEBUG] Full API response: {json.dumps(data, ensure_ascii=False, indent=2)}")

    # 尝试多种响应格式
    # 格式1: OpenAI兼容格式 - content可能是字符串或数组
    if "choices" in data and data["choices"]:
        msg_content = data["choices"][0]["message"]["content"]
        if isinstance(msg_content, list):
            return "".join([item.get("text", "") for item in msg_content if isinstance(item, dict)])
        return msg_content

    # 格式2: 直接content字段
    if "content" in data:
        content = data["content"]
        if isinstance(content, list):
            return "".join([item.get("text", "") for item in content if isinstance(item, dict)])
        return content

    # 格式3: output字段
    if "output" in data:
        return data["output"]

    # 格式4: result字段
    if "result" in data:
        return data["result"]

    # 格式5: text字段
    if "text" in data:
        return data["text"]

    return f"[No response extracted] Raw: {str(data)[:200]}"


# 从.env文件加载配置
def load_env_file():
    """直接从.env文件读取环境变量"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env_file()


# 从环境变量获取配置
def get_backend_private_config():
    """获取配置"""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GPT52_API_KEY") or os.environ.get("OPENAI_API_KEY")
    print(f"[DEBUG] API Key loaded: {api_key[:20] if api_key else 'None'}...")
    return {
        "llm_endpoint": os.environ.get("LLM_ENDPOINT", "https://genaiapi.shanghaitech.edu.cn/api/v1/start"),
        "llm_model": os.environ.get("LLM_MODEL", "GPT-5.2"),
        "llm_api_key": api_key,
    }


def main():
    """主函数"""
    print("=" * 60)
    print("原始AI对话窗口 - 无限制模式")
    print("=" * 60)
    print()
    print("你可以和AI进行任何对话，不受任何规则限制。")
    print("输入 'quit' 或 'exit' 结束对话。")
    print()

    # 获取配置
    config = get_backend_private_config()
    llm_settings = {
        "endpoint": config["llm_endpoint"],
        "model": config["llm_model"],
        "api_key": config["llm_api_key"],
    }

    if not llm_settings["api_key"]:
        print("ERROR: No API key found!")
        print("Please set GPT52_API_KEY, LLM_API_KEY, or OPENAI_API_KEY environment variable.")
        print("Or create a .env file with your API key.")
        sys.exit(1)

    print(f"Using LLM endpoint: {llm_settings['endpoint']}")
    print(f"Using LLM model: {llm_settings['model']}")
    print()

    # 选择分诊等级
    print("=" * 60)
    print("分诊等级选择：")
    print("  1 - 1级（轻症：感冒、轻微不适等）")
    print("  2 - 2级（中症：需要检查后确诊）")
    print("  3 - 3级（重症：需要多项检查）")
    print("=" * 60)

    while True:
        level_input = input("请输入分诊等级 (1/2/3): ").strip()
        if level_input in ["1", "2", "3"]:
            break
        print("请输入 1、2 或 3")

    triage_level = level_input

    # 根据分诊等级设置不同的system prompt
    if triage_level == "1":
        system_prompt = """你是一位经验丰富的内科医生。请用中文与患者进行问诊。

【1级轻症工作流程】
第一步：询问患者的主要症状和不适情况，如果信息不够充分可以多问几轮（但一轮也可以）。
第二步：根据症状开药，并询问患者是否满意（如药是否太重、是否不想打吊瓶等）。
第三步：如果患者满意，主动结束对话，并提醒患者去药房拿药。
第四步：如果患者不满意（药太重/太轻/不想用某种治疗方式），根据反馈调整用药或治疗方案，直到患者满意后结束对话。

请严格按照上述流程进行问诊。始终用中文回答。"""
    elif triage_level == "2":
        system_prompt = """你是一位经验丰富的内科医生。请用中文与患者进行问诊。

【2级中等症工作流程】
第一步：仔细询问患者的主要症状、发病时间、伴随症状等信息，收集充分的临床信息。
第二步：根据收集的信息，向患者反馈三种可能的情况：
  情况A：您的问题不严重，按照轻症处理即可。
  情况B：建议您去拍个片子（如X光、B超等），然后带着片子回来复诊。
  情况C：建议您做个尿检/血检，然后带着检查结果回来复诊。
第三步：
- 如果选择情况A：直接进入1级流程（问症状→开药→询问满意度→结束）
- 如果选择情况B或C：等待患者带检查结果回来，根据结果开药，询问满意度，直到患者满意后结束

请严格按照上述流程进行问诊。始终用中文回答。"""
    else:  # triage_level == "3"
        system_prompt = """你是一位经验丰富的内科医生。请用中文与患者进行问诊。

【3级重症工作流程】
第一步：仔细询问患者的主要症状、发病时间、伴随症状、既往病史等信息，收集充分的临床信息。
第二步：根据收集的信息，向患者反馈三种可能的情况：
  情况A：您的问题不严重，按照轻症处理即可。
  情况B：建议您去拍个片子（如X光、CT、B超等），然后带着片子回来复诊。
  情况C：建议您做尿检+血检等多项检查，然后带着检查结果回来复诊。
第三步：
- 如果选择情况A：直接进入1级流程（问症状→开药→询问满意度→结束）
- 如果选择情况B或C：等待患者带检查结果回来，根据结果开药，询问满意度，直到患者满意后结束

请严格按照上述流程进行问诊。始终用中文回答。"""

    print(f"\n已选择 {triage_level} 级分诊流程")
    print("=" * 60)
    print()

    # 对话历史
    conversation_history = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": system_prompt
                }
            ]
        }
    ]

    # 对话循环
    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                print("\n对话结束。再见！")
                break

            if not user_input:
                continue

            # 添加用户消息到历史
            conversation_history.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_input
                    }
                ]
            })

            # 调用LLM
            print("\nAI is thinking...")
            response = call_llm(
                llm_settings["api_key"],
                llm_settings["endpoint"],
                llm_settings["model"],
                conversation_history
            )

            # 打印回复
            print("\n" + "-" * 40)
            print("AI:")
            print("-" * 40)
            print(response)
            print("-" * 40)

            # 添加AI回复到历史
            conversation_history.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": response
                    }
                ]
            })

            # 限制历史长度，避免API调用过长
            if len(conversation_history) > 10:
                conversation_history = conversation_history[:1] + conversation_history[-9:]

        except KeyboardInterrupt:
            print("\n\n对话被中断。再见！")
            break
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()