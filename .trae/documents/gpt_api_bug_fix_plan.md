# GPT API 调用问题修复计划

## 问题分析

用户报告在分诊连接 GPT API 时出现了 bug，错误信息显示在 starlette 中间件中。根据错误堆栈，问题可能出在后端的 API 调用上，特别是在调用 GPT API 时。

## 可能的原因

1. **API 请求格式问题**：在 `TriageService.request_llm_json` 方法中，请求格式可能不符合 API 的要求
2. **UUID 生成问题**：修改后的 session_id 生成逻辑可能与 API 期望的格式不匹配
3. **环境变量配置**：新添加的环境变量可能影响了 API 调用

## 实施步骤

### 1. 检查 API 请求格式

**修改文件**：`backend/app/agents/triage/service.py`

**修改内容**：
- 检查 `request_llm_json` 方法中的请求格式，特别是 `content` 字段的格式
- 确保请求格式符合 GPT API 的要求

### 2. 验证 UUID 生成

**修改文件**：`backend/app/agents/triage/graph.py`

**修改内容**：
- 验证 UUID 生成是否正确
- 确保生成的 session_id 格式符合系统要求

### 3. 检查环境变量配置

**修改文件**：`backend/.env`

**修改内容**：
- 验证环境变量配置是否正确
- 确保 LLM API 相关的环境变量设置正确

## 技术实现细节

### API 请求格式修复

```python
# 修复 request_llm_json 方法中的请求格式
def request_llm_json(self, messages: list[dict]):
    if not self.llm_settings["api_key"]:
        return None
    # 确保 messages 格式正确
    # 检查 content 字段的格式
    # 确保符合 GPT API 的要求
```

### UUID 生成验证

```python
# 验证 UUID 生成
import uuid
session_id = work.get("session_id") or payload.get("session_id") or str(uuid.uuid4())
# 确保生成的 session_id 格式正确
```

## 验收标准

1. **API 调用成功**：分诊连接 GPT API 时不再出现 bug
2. **会话创建成功**：能够成功创建 triage 会话
3. **数据处理正确**：能够正确处理和存储患者数据

## 实施顺序

1. 先检查 API 请求格式
2. 再验证 UUID 生成
3. 最后检查环境变量配置