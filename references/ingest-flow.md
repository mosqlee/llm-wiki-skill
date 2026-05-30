# Ingest Flow - 资料摄入流程

## 输入
- 文件路径（.md/.pdf/.txt）
- URL（通过 zhipu-web-reader 抓取）
- 直接文本

## 流程

### Step 1: 资料获取
- URL → `python3 ~/.openclaw/workspace/skills/base/zhipu-toolkit/scripts/zhipu_api.py read <url>` → Markdown
- 文件 → 直接读取
- 文本 → 直接使用
- 保存到 `raw/<category>/<filename>.md`（category 由内容类型决定）

### Step 2: 概念提取
LLM 读取原始资料，提取：
- 关键实体（人名、公司、项目名）
- 核心概念（术语、理论、方法）
- 重要论点和数据点
- 与已有 wiki 页面的潜在关联

### Step 3: 页面生成（串行，保障一致性）
1. 创建 `wiki/pages/<title>.md` 摘要页
   - 含 frontmatter（title, created, updated, tags, type: source, sources, confidence, related）
   - 关键要点摘要（3-5 段）
   - 与已有 wiki 页面的 `[[双向链接]]`
2. 逐个更新相关已有页面
   - 在相关页面中新增引用和交叉链接
   - 更新 `updated` 时间戳
   - 每个页面更新后立即 git commit
3. 如果资料引入新实体/概念，创建对应页面

### Step 4: 元数据更新
1. 更新 `index.md`（增量追加，非全量重建）
   - 在对应分类下添加新条目
   - 格式：`- [[页面标题]] — 一行摘要`
2. 追加 `log.md`（原子 append）
   - 格式：`## [YYYY-MM-DD] ingest | 原始资料标题`
   - 子项：新建/更新/来源
3. 最终 git commit

### Step 5: 用户确认
展示摘要：
- 新建了哪些页面
- 更新了哪些页面
- 提取的关键概念列表
用户可要求调整强调重点或补充内容

## 与已有页面的关联查找
```bash
# 先查 index.md 找已有页面
grep -i "关键词" $LLM_WIKI_ROOT/index.md

# 再用 memory_search 语义补充
# 在 LLM 上下文中判断关联性
```

## 资料分级（新增）

在 Step 1 之后、Step 2 之前，增加分级判断：

- **L0（仅归档）**：低价值碎片 → 只保存 raw/ + 登记 source-registry，不生成 source-note
- **L1（轻量卡片）**：普通文章 → 生成简版 source-note，不触发 mutation
- **L2（标准编译）**：有明确问题链 → 生成完整 source-note + registry matching + mutation judgment
- **L3（体系级知识）**：核心框架/方法论 → 完整流程 + 提拔 concept/framework + changelog + pending-review

## Registry Matching（新增）

在 Step 3（页面生成）之前，增加注册表查询：

1. 从资料中提取 candidate concepts
2. 查 `registry/concept-registry.md`：
   - 已存在 → 关联到已有概念
   - 别名 → 更新 aliases
   - 相似 → 标记待合并
   - 新概念 → 建议新增
3. 从资料中提取 candidate claims
4. 查 `registry/claim-registry.md`：
   - 已存在 → 检查是否补充/修正/冲突
   - 新 claim → 建议新增

## Mutation Judgment（新增）

对每个 claim 级别的新知识判断 mutation 类型：

- `archive_only`：仅归档
- `new_knowledge`：新增知识
- `supplement`：补充旧 claim
- `correction`：修正旧 claim（中风险）
- `falsification`：证伪旧 claim（高风险 → pending-review）
- `split`：拆分旧概念（高风险 → pending-review）
- `merge`：合并旧概念（高风险 → pending-review）
- `pending_review`：待人工判断

## 入库动作建议（新增）

根据 mutation 判断，输出建议动作清单：
- [ ] 仅保存 source-note
- [ ] 更新 source-registry
- [ ] 更新 concept-registry
- [ ] 更新 claim-registry
- [ ] 提拔 concept 页面
- [ ] 提拔 framework 页面
- [ ] 更新 wiki 页面
- [ ] 写入 changelog
- [ ] 加入 pending-review

高风险项（falsification/split/merge/correction of high-confidence）必须写入 `changelog/pending-review.md`。
