# 前端 Subtree 维护说明

本仓库已经把上游前端仓库 [XanderZhou2022/BME_1325_Full_Vis](https://github.com/XanderZhou2022/BME_1325_Full_Vis.git) 以 `git subtree + --squash` 的方式导入到 `frontend/fullview/`。

这份说明只讲后续维护方式，不再重复历史背景。

## 当前约定

- 主仓 remote：`bme_1325_formal_jwb_wym`
- 上游前端 remote：`frontend-upstream`
- subtree 路径：`frontend/fullview`
- 上游分支：`main`
- 同步策略：`--squash`

## 目录边界

- `scene/`：当前仓库里原有的旧前端，继续保留并独立维护
- `frontend/fullview/`：上游前端 subtree，按上游仓库节奏同步
- `backend/`：后端与 API 适配层

原则上，主仓特有的适配不要直接写进 `frontend/fullview/`，否则后续和上游同步时更容易冲突。

## 日常命令

### 主仓正常同步

```bash
git pull
git push
```

这两条命令只会同步当前仓库配置的 remote 和 branch，不会自动去上游前端仓库抓取代码。

### 同步上游前端

```bash
git fetch frontend-upstream
git subtree pull --prefix=frontend/fullview frontend-upstream main --squash
```

### 回推 subtree 改动到上游

```bash
git subtree push --prefix=frontend/fullview frontend-upstream main
```

## 重要规则

1. `git subtree add/pull/push` 最好在干净工作区执行。
2. 如果当前有未提交的后端改动，先 `commit` 或 `stash`，再做 subtree 操作。
3. `git pull` 不会主动同步上游前端 remote，但如果你拉下来的主仓提交里已经包含了 subtree 变更，`frontend/fullview/` 也会随之变化。
4. host 特有的接口适配、私有配置、启动说明放在 subtree 外部，保持 `frontend/fullview/` 尽量贴近上游。

## 推荐流程

1. 上游前端作者在自己的仓库里正常维护 `main`。
2. 你这边在当前仓库里定期执行 `git subtree pull --prefix=frontend/fullview frontend-upstream main --squash`。
3. 如果你在 subtree 内修了必须回流的内容，确认稳定后用 `git subtree push` 回到上游。
4. 如果只是当前仓库需要的适配，放到 subtree 外部，避免和上游代码纠缠。

## 目录索引

- [README](../README.md)
- [AGENT 开发说明](./AGENT_DEVELOPMENT_README.md)
- [当前架构总览](./CURRENT_ARCHITECTURE_VISUALIZATION.md)
