# LLM Wiki Skill

基于 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 模式的增量式个人知识库系统。

不是 RAG（每次重新推导），而是 **Incremental Wiki**（持续编译、复合增长）。知识被编译一次，交叉引用已经建好，矛盾已经标记，合成反映所有已摄入内容。

## 安装

```bash
# 作为 Hermes skill 使用（推荐）
cp -r llm-wiki-skill ~/.hermes/skills/research/llm-wiki/

# 或直接克隆
git clone https://github.com/mosqlee/llm-wiki-skill.git
```

## 快速开始

```bash
WIKI_PY=scripts/wiki.py

# 初始化
python3 $WIKI_PY init

# 摄入资料（文件/URL/文本）
python3 $WIKI_PY compile my-article.md --level L2

# URL 摄入（占位 + agent 回填）
python3 $WIKI_PY ingest https://example.com/article
# → 输出 NEEDS_AGENT_FETCH，由 LLM agent 抓取后调用：
python3 $WIKI_PY update-raw raw/articles/article.md --content fetched.md

# 提拔为正式页面
python3 $WIKI_PY promote cpt_20260531_001

# 查询
python3 $WIKI_PY query "什么是增量知识库？"

# 维护
python3 $WIKI_PY maintain all --fix
```

## 全部命令（20 个）

| 命令 | 说明 |
|------|------|
| `init` | 初始化 Wiki 目录结构 + git |
| `ingest` | 摄入资料（文件/URL/文本） |
| `update-raw` | LLM agent 回填 URL 抓取内容 |
| `compile` | 编译资料：source-note + registry 自动登记 |
| `promote` | registry 条目 → 正式 wiki 页面 |
| `rebuild-maps` | 生成 domain-map + concept-map |
| `maintain` | 周期维护（broken-links/orphan-pages/concept-dedupe/stale-claims/map-drift） |
| `query` | 查询知识库 |
| `lint` | 健康检查（--quick / --deep） |
| `status` | 查看统计 |
| `new-id` | 生成稳定 ID（src/cpt/frm/clm） |
| `registry` | 读取/追加注册表 |
| `changelog` | 追加变更记录 |
| `create-page` | 创建 wiki 页面 |
| `update-page` | 更新 wiki 页面 |
| `create-qa` | 创建 QA 回填页面 |
| `backfill` | 回填优质答案 |
| `diff` | Git 变更历史 |
| `history` | log.md 操作历史 |
| `observe` | Obsidian 集成（symlink） |

## 知识分级

| 级别 | 适用场景 | 动作 |
|------|----------|------|
| L0 | 低价值碎片 | 仅归档 raw/ + registry |
| L1 | 普通文章 | 轻量 source-note |
| L2 | 有明确问题链 | 完整 source-note + mutation 判断 |
| L3 | 核心框架 | 完整管道 + promote + changelog |

## 目录结构

```
wiki-root/
├── raw/                    # 原始资料（不可变）
├── wiki/
│   ├── pages/              # 通用页面
│   ├── concepts/           # 概念页面
│   ├── frameworks/         # 框架页面
│   └── qa/                 # QA 回填
├── compiled/source-notes/  # source-note 文件
├── registry/               # 5 个注册表
├── changelog/              # 变更记录
├── maps/                   # 生成的知识图谱
├── maintenance/            # 维护报告
├── index.md                # 内容索引
├── log.md                  # 操作日志
└── SCHEMA.md               # 结构规范
```

## 页面 Frontmatter

```yaml
---
title: 页面标题
created: 2026-05-31
updated: 2026-05-31
type: concept
tags: [wiki, knowledge-base]
sources: [raw/articles/source.md]
confidence: high
related:
  - [[关联页面]]
---
```

## 测试

```bash
pytest tests/ -v
```

## License

MIT
