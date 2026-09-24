# anta-bi 工具升级指令（存量实例一次性升级）

> **给项目所有者**：把本文件原样发给**早期配置过**的 agent（特征：其 `.magic/skills/anta-bi/`
> 下没有 `scripts/update_agent.py` 或没有 `VERSION` 标记），并说明「**按本文件完成升级**」。
> 升级完成后该 agent 获得自助更新能力（update_agent.py 随本次一并安装），**此后无需再发本文件**——
> 使用者说「检查更新」即可。全新接入仍走 `INIT_PROMPT.md`，不要用本文件。

---

你的任务：把本项目内安装的 anta-bi 工具（五个 skill + AGENTS.md/USAGE.md）升级到上游最新版，
并建立版本标记。只动这七类位置 + 版本标记，项目里其它一切（workspace/、out/、你的自加内容）不动。

## 升级前自查（先做，结果随汇报一起给出）

1. 列出 `<PROJECT>/.magic/skills/anta-bi/references/` 下所有 md：凡含「报表连接 spec」小节、
   且**不属于**上游自带清单（`retail_daily_*`、`channel_monthly_*`、`r03_sales_stock_*`、
   `metrics-glossary`、`sell_through_rate_descente`、`ecom_daily_kolon`、`new_store_tracking_kolon`）
   的，是**本项目自行接入的报表指引**。升级是合并覆盖（只新增/覆盖同名文件），这些文件会
   **原样保留**——新版路由有「自加报表通用发现规则」，按文件名即可继续查询，无需任何迁移。
2. 若你或使用者**修改过** `SKILL.md` / `AGENTS.md` / `USAGE.md`（如早期在路由表手工加过行）：
   先把这三个文件副本存到 `<PROJECT>/workspace/upgrade-backup-<今日日期>/`。
   （本次是无基线的整文件覆盖，不会自动备份；自 v1.2.0 起之后的更新才有自动备份。）

## 三步执行

```bash
# 1) 浅克隆上游（若报 "Empty reply" / "Failed to connect"，在 git 后加
#    -c http.version=HTTP/1.1 重试）
git clone --depth 1 https://github.com/ZhangS0/Anta_Scrap.git /tmp/anta/Anta_Scrap

# 2) 覆盖式拷贝（<PROJECT>=当前项目根目录；cp -r 对已存在目录是合并覆盖，
#    目标独有的文件会保留）
mkdir -p <PROJECT>/.magic/skills
cp -r /tmp/anta/Anta_Scrap/.claude/skills/anta-bi           <PROJECT>/.magic/skills/
cp -r /tmp/anta/Anta_Scrap/.claude/skills/hamilton-report   <PROJECT>/.magic/skills/
cp -r /tmp/anta/Anta_Scrap/.claude/skills/bi-report-build   <PROJECT>/.magic/skills/
cp -r /tmp/anta/Anta_Scrap/.claude/skills/bi-report-rerun   <PROJECT>/.magic/skills/
cp -r /tmp/anta/Anta_Scrap/.claude/skills/anta-bi-onboard   <PROJECT>/.magic/skills/
cp    /tmp/anta/Anta_Scrap/agent_setup/AGENTS.md            <PROJECT>/
cp    /tmp/anta/Anta_Scrap/agent_setup/USAGE.md             <PROJECT>/
cp    /tmp/anta/Anta_Scrap/VERSION                          <PROJECT>/.magic/skills/anta-bi/VERSION

# 3) 清理临时克隆
rm -rf /tmp/anta
```

## 升级后验证

- `python <PROJECT>/.magic/skills/anta-bi/scripts/update_agent.py check` → 应显示「已是最新」；
- 重新加载 skills（新版 anta-bi 含 MCP 直连逃生通道与自加报表发现规则）；
- 向项目所有者汇报：版本标记内容、自加报表指引清单（应与升级前一致）、
  自查第 2 步是否发现过被改过的分发文件及备份位置。

## 之后（写给使用者，可转述）

- 说「检查更新」→ agent 跑 check 并展示影响范围；确认后说「更新到最新版」→ apply
  （本地改过的分发文件会自动备份到 `.magic/update-backup/`，自加报表永不被覆盖删除）；
- 需要定时检查可让 agent 配置每日定时任务跑 `check --json`。
