# OpenEMR Phase1 集成结果总结

## 1. 目标与边界
- 主系统继续负责流程编排，OpenEMR 仅作为外部 EMR 写入目标。
- 不改前端、不改 OpenEMR 源码、不直连 OpenEMR 数据库。
- 保留“同步失败不阻断主流程”语义。

## 2. 已实现内容
- 新增 OpenEMR 适配层：`client / mapper / service / subscriber / debug routes`。
- 新增幂等写入状态：
  - `patients.openemr_patient_id`
  - `visits.openemr_encounter_id`
  - `visits.emr_sync_status / emr_synced_at / emr_sync_error`
  - `visits.data_json.openemr_sync.triage_note_id`
  - `visits.data_json.openemr_sync.internal_medicine_note_id`
  - `visits.data_json.openemr_sync.test_report_id`
- 新增调试接口：
  - `GET /api/v1/openemr/health`
  - `POST /api/v1/openemr/sync/patient/{patient_id}`
  - `POST /api/v1/openemr/sync/visit/{visit_id}`
  - `POST /api/v1/openemr/sync/visit/{visit_id}/notes?force=false`

## 3. OAuth（client_credentials）接入
### 3.1 鉴权策略
- 主链路：OAuth `client_credentials`（Bearer token）。
- 降级链路：OAuth 失败时可回退 Basic Auth（可配置开关）。
- 兼容策略：
  - `OPENEMR_ENABLED=false`：no-op
  - `OPENEMR_DRY_RUN=true`：返回 dry-run 结果，不发真实请求

### 3.2 配置项
- `OPENEMR_OAUTH_ENABLED`（默认 `true`）
- `OPENEMR_OAUTH_DISCOVERY_URL`（可选）
- `OPENEMR_OAUTH_TOKEN_URL`（可选，优先级高于 discovery）
- `OPENEMR_OAUTH_SCOPE`（默认：`api:fhir user/Patient.write user/DocumentReference.write`）
- `OPENEMR_OAUTH_AUDIENCE`（可选）
- `OPENEMR_OAUTH_USE_BASIC_FALLBACK`（默认 `true`）
- Basic fallback 凭据：`OPENEMR_USERNAME` / `OPENEMR_PASSWORD`

### 3.3 运行时行为
- 支持 SMART discovery 自动发现 token endpoint。
- token 使用内存缓存，并在过期前提前刷新。
- 所有 HTTP 请求固定 `trust_env=False`，避免系统代理干扰本地 OpenEMR。
- `GET /api/v1/openemr/health` 新增：
  - `auth_mode`：`oauth | basic_fallback | basic | disabled | dry_run`
  - `token_endpoint_source`：`discovery | override | n/a`
  - `token_endpoint`

## 4. 联调步骤（真实写入）
1. 启动 OpenEMR（例如 `openemr-demo/docker-compose.yml`）。
2. 在 OpenEMR 后台预先创建 confidential OAuth client（拿到 `client_id/client_secret`）。
3. 设置后端环境变量：
   - `OPENEMR_ENABLED=true`
   - `OPENEMR_DRY_RUN=false`
   - `OPENEMR_BASE_URL=http://localhost:8080`
   - `OPENEMR_API_BASE_PATH=/apis/default/fhir`
   - `OPENEMR_CLIENT_ID=...`
   - `OPENEMR_CLIENT_SECRET=...`
4. 启动后端后按顺序验证：
   - `/api/v1/openemr/health`
   - `/api/v1/openemr/sync/patient/{patient_id}`
   - `/api/v1/openemr/sync/visit/{visit_id}`
   - `/api/v1/openemr/sync/visit/{visit_id}/notes`

## 5. 常见问题定位
- `invalid_client`：OAuth client id/secret 错误，或 client 未启用 `client_credentials`。
- `401/403`：scope 不足或 token audience 不匹配。
- `token endpoint unreachable`：`OPENEMR_BASE_URL` / discovery URL 不可达。
- fallback 生效判断：`health.auth_mode == basic_fallback`。

## 6. 限制项
- Phase1 不覆盖 billing / insurance / pharmacy / HL7。
- Phase1 使用 `DocumentReference` 承载 note/test report，不展开 `DiagnosticReport/Observation`。
