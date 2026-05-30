# Query Flow - 查询知识库流程

## 输入
- 用户问题（自然语言）

## 流程

### Step 1: 检索
1. 读取 `index.md`，根据关键词定位候选页面
2. 使用 `memory_search` 语义补充，找到关联页面
3. 检查 Session 历史中是否有相关查询（记忆驱动）

### Step 2: 读取与综合
1. 读取候选页面（控制在上下文窗口内，优先高置信度页面）
2. 综合生成答案
3. 答案中包含页面引用：`参考：[[页面标题]]`
4. 标注来源置信度

### Step 3: 回填判断
答案是否优质？判断标准：
- 回答了非平凡的综合性问题
- 信息有长期参考价值
- 非简单事实查询

若优质：
1. 创建 `wiki/qa/<question-hash>.md`
   - frontmatter: type: qa, tags, related, sources
   - 内容：问题 + 答案 + 引用来源
2. 更新 `index.md`（在 QA 分类下添加条目）
3. 追加 `log.md`
4. git commit

若不优质：仅返回答案，不做额外操作。

## Registry 检查（新增）

查询时自动检查：
- 相关概念是否在 concept-registry 中
- 相关 claim 的 confidence 和 evidence_strength
- 是否有 pending-review 中的相关条目

## 回填时更新 Registry（新增）

优质答案回填时，如果包含新 claim：
- 自动追加到 claim-registry 草稿
- 更新相关 concept 的 last_reviewed
