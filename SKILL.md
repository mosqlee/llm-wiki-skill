---
name: llm-wiki
description: >
  基于 Karpathy LLM Wiki 模式的个人知识库构建与维护系统。
  在 OpenClaw 上实现 Incremental Wiki：LLM 持续编译、复合增长的知识工件。
  触发词：wiki、知识库、摄入资料、查wiki、lint wiki、初始化wiki、wiki ingest、wiki query、wiki lint
---

# LLM Wiki - 增量式个人知识库

## 核心概念

不是 RAG（每次重新推导），而是 **Incremental Wiki**（持续编译、复合增长）。
Wiki 是一个持久的、复合的知识工件，每次摄入和查询都让它更丰富。

## 存储结构

```
$LLM_WIKI_ROOT/（默认 ~/llm-wiki）
├── raw/                 # 原始资料（不可变，LLM 只读）
│   ├── papers/
│   ├── articles/
│   ├── books/
│   └── assets/
├── wiki/
│   ├── pages/           # 所有 wiki 页面扁平存放
│   ├── qa/              # 查询回填的优质问答
│   └── slides/          # Marp 幻灯片导出
├── index.md             # 内容索引
├── log.md               # 变更日志（append-only）
├── log-archive/         # 历史日志归档
└── SCHEMA.md            # 结构规范
```

## 角色分工

- **人类**：策展（选资料）、提问、审核准确性
- **LLM**：阅读、提取、整合、维护（所有记账工作）

## 操作

### init - 初始化
```bash
python3 scripts/wiki.py init [--path ~/llm-wiki]
```
创建目录结构、SCHEMA.md、初始化 git。

### ingest - 摄入资料
```bash
python3 scripts/wiki.py ingest <file_or_url_or_text> [--interactive]
```
**分工**：脚本处理确定性部分（获取、保存、git），LLM agent 在上下文中完成智能部分（概念提取、页面生成、交叉引用）。

1. 脚本：获取资料 → 保存到 raw/ → git commit → 输出内容预览
2. LLM agent：提取概念 → 创建/更新 wiki 页面（含 frontmatter + 来源引用 + confidence）→ 更新 index.md → 追加 log.md → git commit

详见 [references/ingest-flow.md](references/ingest-flow.md)。

### update-raw - 回填 URL 正文
```bash
python3 scripts/wiki.py update-raw raw/articles/xxx.md --content <file_or_text>
```
用于 LLM agent 把 URL 抓取正文写回占位 raw 文件。
会保留 `source_url`、计算 `sha256`，并自动 git commit。

### compile - 编译资料
```bash
python3 scripts/wiki.py compile <file_or_url_or_text> [--level L0|L1|L2|L3]
```
保存 raw、生成 `source_id` 和 `compiled/source-notes/` 占位文件。
自动登记 `source-registry`、追加 changelog/log，并提交 git。

### promote - 提拔正式页面
```bash
python3 scripts/wiki.py promote <cpt_or_frm_id> [--type concept|framework]
```
从 concept/framework registry 读取条目并用 schema 模板渲染页面。
写入 `wiki/concepts/` 或 `wiki/frameworks/`，更新状态和 `page-registry`。

### rebuild-maps - 重建知识图谱
```bash
python3 scripts/wiki.py rebuild-maps
```
扫描 registry 和 wiki 页面 frontmatter/链接。
生成 `maps/domain-map.generated.md` 与 `maps/concept-map.generated.md`。

### query - 查询知识库
```bash
python3 scripts/wiki.py query "<question>"
```
**分工**：脚本提供页面列表和索引信息，LLM agent 完成检索、综合和回填。

1. 脚本：加载 index.md + 页面元数据列表
2. LLM agent：读取相关页面 → 综合回答（含引用 + confidence）→ 判断是否回填 wiki/qa/ → 更新 index.md + log.md → git commit

详见 [references/query-flow.md](references/query-flow.md)。

### lint - 健康检查
```bash
python3 scripts/wiki.py lint [--quick | --deep]
```
- `--quick`：孤儿页、过时页（>90天）、未回填查询
- `--deep`：矛盾检测、缺失引用、覆盖缺口、新资料建议
详见 [references/lint-flow.md](references/lint-flow.md)。

## 页面 Frontmatter 规范

```yaml
---
title: 页面标题
created: 2026-04-05
updated: 2026-04-05
tags: [标签1, 标签2]
type: concept          # entity / concept / source / summary / comparison / qa
sources:               # 来源引用
  - raw/articles/xxx.md
confidence: high       # high / medium / low
related:
  - [[关联页面]]
---
```

## Log 格式规范

```markdown
## [2026-04-05] ingest | 文章标题
- 新建: wiki/pages/xxx.md
- 更新: wiki/pages/yyy.md（新增引用）
- 更新: index.md（+2 条目）
- 来源: raw/articles/xxx.md
```

可解析：`grep "^## \[" log.md | cut -d'|' -f2`

## 一致性保障

- 所有写入操作为**增量模式**，覆盖需显式 `--force`
- 每次 ingest/query 后**自动 git commit**
- log.md 使用**原子 append**
- 大规模更新**串行执行**，不并发写同一文件
- 文件锁机制（fcntl.flock）保障并发安全

## Phase 3: OpenClaw 原生增强

### Heartbeat 主动巡检 ⭐
已集成到 HEARTBEAT.md：
- **每次心跳**：`wiki.py lint --quick`（孤儿页/过时页/元数据缺失），发现问题→飞书通知
- **每天早上9点**：`wiki.py lint --deep`（矛盾检测/覆盖缺口），生成详细报告

### Git Diff + History
```bash
python3 scripts/wiki.py diff -n 10 -v    # 查看 git 变更历史+统计
python3 scripts/wiki.py history -n 20 --filter ingest  # 过滤操作历史
```

### Session 记忆驱动查询
LLM agent 在 query 时自动检查对话历史中的相关查询，提供上下文关联建议。

## 知识分级机制

### L0: 仅归档
适合：低价值碎片、暂时看不出问题意识的资料
动作：保存到 raw/，登记到 source-registry，不生成 source-note

### L1: 轻量卡片
适合：普通文章、普通播客、观点不复杂但有参考价值的资料
动作：生成简版 source-note（知识定位 + 一句话摘要 + 可能关联概念），不触发 mutation

### L2: 标准编译
适合：有明确问题链、能补充现有知识、未来可能复用
动作：生成完整 source-note，查 concept-registry，查 claim-registry，做 mutation 判断

### L3: 体系级知识
适合：强方法论、核心框架、可工程化、可复用于课程/Agent/投资框架
动作：完整 source-note + 更新 registry + 提拔 concept/framework + 写 changelog + 进入 pending-review

## Mutation 类型

| 类型 | 说明 | 风险等级 |
|------|------|----------|
| archive_only | 仅归档，不生成知识页面 | 低 |
| new_knowledge | 新增知识 | 低 |
| supplement | 补充旧知识 | 低 |
| correction | 修正旧知识 | 中 |
| falsification | 证伪旧知识 | 高 |
| split | 拆分旧概念 | 高 |
| merge | 合并旧概念 | 高 |
| pending_review | 待人工判断 | - |

Mutation 判断应用于 claim 级别，不是整篇资料。

## Registry 系统

四个注册表维护知识索引：
- **concept-registry**：概念注册表，防止概念重复，统一命名
- **claim-registry**：判断/主张注册表，支持 mutation-check 和证伪记录
- **source-registry**：资料注册表，记录所有 raw 来源
- **page-registry**：页面注册表，维护 wiki 页面清单

模板位于 `templates/registry/`，初始化时复制到 `registry/` 目录。

## 三条管道

### 知识进入管道（高频、轻量、逐源执行）
raw → 资料分级 → source-note → registry match → mutation judge → changelog / pending-review

### 知识维护管道（周期性、批量、防腐烂）
registry → dedupe → stale review → broken links → generated maps

### 内容输出管道（按需触发）
wiki / registry / source-note → 小红书 / 课程 / PPT / Agent 方案

## 稳定 ID 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| Source Note | src_YYYYMMDD_NNN | src_20260530_001 |
| Concept | cpt_YYYYMMDD_NNN | cpt_20260530_001 |
| Framework | frm_YYYYMMDD_NNN | frm_20260530_001 |
| Claim | clm_YYYYMMDD_NNN | clm_20260530_001 |

不要用中文标题做文件名。标题存在 frontmatter 和 H1 里。

## Human Gate 规则

只有高风险操作需要人工审核：
- 修正高置信度 claim
- 证伪已有 claim
- 合并/拆分概念
- 重命名页面
- 修改核心框架
- 重构 generated map

低风险操作默认自动完成。高风险项写入 `changelog/pending-review.md`。

## Changelog 规则

每次修正或证伪必须保留：旧 claim、新证据、来源、原因、受影响页面、处理决策、日期。

绝不静默覆盖旧知识。
