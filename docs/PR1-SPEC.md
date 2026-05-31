# PR 1: V1 核心功能

## 目标
给 wiki.py 添加 4 个新命令：compile、promote、rebuild-maps、update-raw。
添加 2 个缺失的 registry 模板。更新 SKILL.md。

## 参考文件
- `/tmp/local-wiki.py` — 本地已实现的完整版 wiki.py（2170行），从中提取需要的函数
- `scripts/wiki.py` — 仓库当前版本（913行），在此基础上添加

## 需要添加的命令

### 1. update-raw（URL 回填）
让 LLM agent 回填 URL 抓取内容到 raw 文件。

函数签名：`cmd_update_raw(args)`
- 参数：`raw_path`（raw 文件相对路径）、`--content`（内容文件路径或直接文本）
- 行为：读取现有 frontmatter 获取 source_url → 计算 sha256 → 重写文件（header + content）→ git commit

在 `save_source_to_raw` 的 URL 分支中，将 zhipu_api 调用替换为占位文件模式：
- 保存占位文件到 raw/articles/{slug}.md（只含 source_url + ingested frontmatter）
- stdout 输出 `NEEDS_AGENT_FETCH: {url} -> {raw_path}`
- 返回 dict 中加 `"needs_agent_fetch": True`

### 2. compile（V1 编译）
将资料编译为 source-note + 自动登记 source-registry + changelog。

函数签名：`cmd_compile(args)`
- 参数：`source`（文件/URL/文本）、`--level`（L0/L1/L2/L3，默认 L2）
- 行为：
  1. 调用 `save_source_to_raw` 保存到 raw/
  2. 生成 source_id（调用 `generate_new_id`）
  3. 创建 source-note 文件 `compiled/source-notes/{source_id}.md`
  4. 自动登记 source-registry（调用 `auto_register_source`）
  5. 追加 changelog（调用 `append_changelog_change`）
  6. 追加 log.md + git commit

新增辅助函数：
- `create_source_note(root, source_id, title, source_type, raw_path, level)` — 创建 source-note 占位
- `auto_register_source(root, source_id, title, source_type, raw_path, level)` — 追加 source-registry

L0 级别跳过内容长度检查（`len(content) < 20` 只对 L1-L3 生效）。

### 3. promote（提拔 registry 条目）
将 concept-registry 或 framework-registry 中的条目提拔为正式 wiki 页面。

函数签名：`cmd_promote(args)`
- 参数：`id`（concept/framework ID）、`--type`（concept/framework，可自动推断）
- 行为：
  1. 从 registry 找到条目
  2. 用 schema 模板渲染页面内容
  3. 写入 `wiki/concepts/{id}.md` 或 `wiki/frameworks/{id}.md`
  4. 更新 registry 状态为 active
  5. 登记 page-registry
  6. 追加 changelog + log + git commit

新增辅助函数：
- `render_promoted_page(root, page_type, object_id, entry)` — 用模板渲染
- `auto_page_register(root, page_id, title, page_type, path)` — 追加 page-registry

需要添加 `REGISTRY_FILES` 字典中缺少的 `"framework"` 和 `"page"` 条目。

### 4. rebuild-maps（重建知识图谱）
从 registry 和 wiki 页面 frontmatter 扫描知识结构，生成 domain-map 和 concept-map。

函数签名：`cmd_rebuild_maps(args)`
- 无额外参数
- 行为：
  1. 扫描 concept-registry + claim-registry + wiki 页面
  2. 生成 `maps/domain-map.generated.md`（按领域分组）
  3. 生成 `maps/concept-map.generated.md`（概念详情+来源+关联）

新增辅助函数：
- `_scan_registry_rows(root, registry_name)` — 读取 registry 表格行
- `_scan_content_pages(root)` — 扫描 wiki 页面 frontmatter 和链接
- `_source_label(source_id, source_rows)` — 可读来源标签

## 需要添加的模板文件

在 `templates/registry/` 下添加：
- `framework-registry.md` — 框架注册表模板
- `page-registry.md` — 页面注册表模板

内容从 `/tmp/local-wiki.py` 同级的 templates 目录中复制：
```
~/.hermes/skills/research/llm-wiki/templates/registry/framework-registry.md
~/.hermes/skills/research/llm-wiki/templates/registry/page-registry.md
```

## SKILL.md 更新

在 SKILL.md 的"操作"部分添加 compile、promote、rebuild-maps、update-raw 的说明。
保持简洁风格，每个命令 3-5 行说明。

## 注意事项

1. 从 `/tmp/local-wiki.py` 中提取代码时，只取需要的函数，不要全量替换
2. 保持现有函数（init, ingest, query, lint 等）不变
3. 在 `main()` 的 argparse 和 elif 链中注册新命令
4. `REGISTRY_FILES` 字典需要加 `"framework"` 和 `"page"` 条目
5. `ID_PREFIXES` 和 `ID_DIRS` 需要检查是否完整
6. 使用中文注释
7. 不要修改 tests/ 目录
