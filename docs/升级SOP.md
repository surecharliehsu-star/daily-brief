# 每日简报 · 升级隔离 SOP

> 测试与正式版本隔离的强制流程。**只有测试完全通过，才允许升级正式版。**

## 环境结构

```
每日信息/            ← 正式版，master 分支，cron (com.daily-papers.push.plist) 7:00 自动推送正式群
每日信息-test/       ← 测试版，dev 分支，git worktree，推送测试群（卡片标题带【测试】）
```

- 两地代码通过 git worktree 关联同一仓库，独立工作目录、独立 `config.json`
- 正式 `config.json`：`push.feishu_webhook`（正式群）
- 测试 `config.json`：`push.feishu_webhook_test`（测试群），**不写** `feishu_webhook`
- `push_runner.py` 读取规则：`webhook = feishu_webhook_test or feishu_webhook`；用测试 webhook 时卡片标题加 `【测试】` 前缀，且日志开头打印 `version: <分支> <commit>`

## 开发与测试（dev / 每日信息-test）

1. 在 `~/Brain/projects/每日信息-test/` 修改代码（只影响 dev 分支）
2. 跑完整 pipeline 验证：
   ```bash
   cd ~/Brain/projects/每日信息-test
   PYTHONPATH=src python3 -m src.daily_papers.push_runner
   ```
3. 核对：
   - 日志开头 `version: dev xxx`
   - 14 个源 `[fetch]` 全部成功，无 `[WARN]`
   - HTML/PDF/Word 产物生成
   - 测试群收到「📬 货币政策日报【测试】」卡片，内容完整
4. 测试通过后，将 dev 改动提交并推送备份：
   ```bash
   cd ~/Brain/projects/每日信息-test
   git add -A && git commit -m "..." && git push origin dev && git push github dev
   ```

## 升级门禁（测试通过 → 版本升级）

```bash
# 1. 在正式目录合并已验证的 dev 改动
cd ~/Brain/projects/每日信息
git merge dev
git push origin master && git push github master

# 2. 正式目录已在 master（cron 工作目录就是这里），无需额外 pull
#    若在其他机器，则 git pull
```

合并前必须满足：dev 上该功能的完整验证全部通过；还未通过的功能**不得**进入 master。

## 升级后回归验证

1. `git log --oneline -3` 确认 master 已含 dev merge 的 commit
2. 手动跑一次（可选，先看日志）：
   ```bash
   cd ~/Brain/projects/每日信息
   PYTHONPATH=src python3 -m src.daily_papers.push_runner
   ```
   核对日志 `version: master xxx`、产物正常、正式群收到无【测试】前缀的卡片
3. 次日 07:00 cron 自动运行即新版本

## 原则

- **隔离**：dev 与 master 代码、配置、推送目标完全分离；cron 只指向正式目录，测试改动绝不被定时任务误触发
- **门禁**：升级 = 已通过的 merge，回滚 = `git revert` 或切回旧 commit
- **可追溯**：每次运行日志都带版本号，可定位"跑的是哪版"