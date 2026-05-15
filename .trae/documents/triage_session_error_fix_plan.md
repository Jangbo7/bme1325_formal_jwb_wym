# Triage Session 500 Error Fix Plan

## 问题分析

用户报告了一个 500 Internal Server Error 错误，发生在 POST /api/v1/triage-sessions 请求时。根据错误信息和代码分析，可能的原因包括：

1. **API 请求格式问题**：在 `TriageService.request_llm_json` 方法中，请求格式可能仍然存在问题
2. **会话 ID 冲突**：UUID 生成逻辑可能与系统其他部分存在冲突
3. **患者 ID 处理**：前端传递的患者 ID 格式可能与后端期望的格式不匹配
4. **GPT API 调用失败**：调用 GPT API 时可能出现错误，导致整个请求失败

## 实施步骤

### 1. 检查 API 路由和服务实现

**修改文件**：`backend/app/api/routes/triage.py`
**修改文件**：`backend/app/agents/triage/service.py`
**修改文件**：`backend/app/agents/triage/graph.py`

**修改内容**：
- 检查 `create_triage_session` 函数的实现
- 检查 `TriageService.create_session` 方法的实现
- 检查 `TriageGraph.invoke` 方法的实现
- 确保所有方法都能正确处理请求参数

### 2. 修复 GPT API 调用错误处理

**修改文件**：`backend/app/agents/triage/service.py`

**修改内容**：
- 在 `request_llm_json` 方法中添加错误处理
- 在 `request_triage_from_llm` 方法中添加错误处理
- 确保即使 GPT API 调用失败，也能返回合理的错误信息，而不是 500 错误

### 3. 验证会话 ID 和患者 ID 处理

**修改文件**：`backend/app/api/routes/triage.py`
**修改文件**：`backend/app/agents/triage/graph.py`

**修改内容**：
- 验证会话 ID 的生成和处理逻辑
- 验证患者 ID 的处理逻辑
- 确保前端传递的患者 ID 格式与后端期望的格式匹配

## 技术实现细节

### API 路由和服务实现修复

```python
# 确保 create_triage_session 函数能正确处理请求参数
def create_triage_session(body: CreateTriageSessionRequest, request: Request):
    service = request.app.state.container["triage_service"]
    payload = body.model_dump()
    # 确保 session_id 生成逻辑正确
    payload["session_id"] = payload.get("session_id") or f"session-{uuid.uuid4().hex[:8]}"
    try:
        return service.create_session(payload)
    except Exception as e:
        # 记录错误并返回合理的错误信息
        print(f"Error creating triage session: {e}")
        raise
```

### GPT API 调用错误处理

```python
# 在 request_llm_json 方法中添加错误处理
def request_llm_json(self, messages: list[dict]):
    if not self.llm_settings["api_key"]:
        return None
    try:
        req = urlrequest.Request(
            self.llm_settings["endpoint"],
            data=json.dumps(
                {
                    "model": self.llm_settings["model"],
                    "messages": messages,
                    "temperature": 0,
                    "n": 1,
                    "stream": False,
                    "presence_penalty": 0,
                    "frequency_penalty": 0,
                }
            ).encode("utf-8"),
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.llm_settings['api_key']}",
            },
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=18) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = self.extract_text_from_response(data)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return None
```

## 验收标准

1. **API 调用成功**：POST /api/v1/triage-sessions 请求不再返回 500 错误
2. **会话创建成功**：能够成功创建 triage 会话
3. **错误处理合理**：即使 GPT API 调用失败，也能返回合理的错误信息
4. **数据处理正确**：能够正确处理和存储患者数据

## 实施顺序

1. 先检查 API 路由和服务实现
2. 再修复 GPT API 调用错误处理
3. 最后验证会话 ID 和患者 ID 处理