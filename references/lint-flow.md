# Lint Flow - 健康检查流程

## 快速 Lint（--quick）
适用于 Heartbeat 定时巡检。

检查项：
1. **孤儿页检测**：wiki/pages/ 中存在但未被 index.md 引用、且未被其他 wiki 页面 `[[链接]]` 的页面
2. **过时页面**：frontmatter 中 `updated` 距今 > 90 天的页面
3. **未回填查询**：log.md 中有 query 记录但未产生 qa/ 回填的条目
4. **空目录**：raw/ 或 wiki/ 中的空子目录

输出：简要报告，如发现问题则通知用户。

## 深度 Lint（--deep）
适用于手动触发或 Cron 定时执行。

在快速 Lint 基础上增加：
5. **矛盾内容检测**：LLM 对比相关页面，发现逻辑矛盾或数据冲突
6. **缺失交叉引用**：两页面讨论同一主题但未互相链接
7. **覆盖缺口分析**：用户常问的主题在 wiki 中缺少专门页面
8. **新资料建议**：基于 wiki 中的引用缺口，建议补充的资料

输出：详细报告 + 建议操作列表。

## 实现方式
```bash
python3 scripts/wiki.py lint --quick
python3 scripts/wiki.py lint --deep
```

脚本会：
1. 扫描 wiki/pages/ 所有 .md 文件，解析 frontmatter
2. 扫描 index.md 解析条目
3. 扫描 log.md 解析操作记录
4. 对比生成报告
```

## Registry 一致性检查（新增）

- concept-registry 中的 page 列是否指向存在的 wiki 页面
- claim-registry 中的 source 列是否指向存在的 raw 文件
- source-registry 中的 source_note 列是否指向存在的 compiled/source-note
- 检查 registry 中 status 字段是否合法

## Changelog 完整性检查（新增）

- pending-review 中的条目是否有对应的 changelog 记录
- changes.md 中引用的对象是否存在
- 超过 30 天未处理的 pending-review 条目

## 稳定 ID 格式检查（新增）

- compiled/source-notes/ 下的文件名是否符合 src_YYYYMMDD_NNN 格式
- wiki/concepts/ 下的文件名是否符合 cpt_YYYYMMDD_NNN 格式
- wiki/frameworks/ 下的文件名是否符合 frm_YYYYMMDD_NNN 格式
