#!/usr/bin/env python3
"""LLM Wiki - 核心操作脚本"""

import argparse
import os
import sys
import json
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

DEFAULT_ROOT = os.path.expanduser("~/llm-wiki")

def get_root(args):
    return getattr(args, 'path', None) or os.environ.get("LLM_WIKI_ROOT", DEFAULT_ROOT)

# ─── init ───────────────────────────────────────────────

def cmd_init(args):
    root = get_root(args)
    dirs = [
        "raw/papers", "raw/articles", "raw/books", "raw/assets",
        "wiki/pages", "wiki/qa", "wiki/slides",
        "log-archive",
    ]
    for d in dirs:
        os.makedirs(os.path.join(root, d), exist_ok=True)

    # SCHEMA.md
    schema = """# LLM Wiki Schema

## 角色分工
- **人类**：策展（选资料）、提问、审核准确性
- **LLM**：阅读、提取、整合、维护

## 页面规范
- 所有 wiki 页面放在 wiki/pages/（扁平）
- QA 回填放在 wiki/qa/
- Frontmatter 包含：title, created, updated, tags, type, sources, confidence, related

## 一致性规则
- 所有写入操作为增量模式
- 每次 ingest/query 后自动 git commit
- log.md 原子 append
- 大规模更新串行执行
"""
    schema_path = os.path.join(root, "SCHEMA.md")
    if not os.path.exists(schema_path):
        with open(schema_path, 'w') as f:
            f.write(schema)

    # index.md
    index_path = os.path.join(root, "index.md")
    if not os.path.exists(index_path):
        with open(index_path, 'w') as f:
            f.write("# LLM Wiki Index\n\n")
            f.write("## Sources\n\n")
            f.write("## Concepts\n\n")
            f.write("## Entities\n\n")
            f.write("## Summaries\n\n")
            f.write("## Comparisons\n\n")
            f.write("## Q&A\n\n")

    # log.md
    log_path = os.path.join(root, "log.md")
    if not os.path.exists(log_path):
        with open(log_path, 'w') as f:
            f.write("# LLM Wiki Log\n\n")

    # git init
    if not os.path.exists(os.path.join(root, ".git")):
        subprocess.run(["git", "init"], cwd=root, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init: LLM Wiki initialized"], cwd=root, capture_output=True)
        print(f"✅ Wiki initialized at {root} (with git)")
    else:
        print(f"✅ Wiki already exists at {root}")

# ─── helpers ────────────────────────────────────────────

def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a markdown file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if not content.startswith('---'):
        return {}, content
    end = content.find('---', 3)
    if end == -1:
        return {}, content
    fm_str = content[3:end].strip()
    body = content[end+3:].strip()
    # Simple YAML parser (key: value or key: [a, b])
    fm = {}
    for line in fm_str.split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            val = val.strip().strip('"').strip("'")
            if val.startswith('[') and val.endswith(']'):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',')]
            fm[key.strip()] = val
    return fm, body

def append_log(root, operation, title, details=None):
    """Atomically append to log.md."""
    log_path = os.path.join(root, "log.md")
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n## [{today}] {operation} | {title}\n"
    if details:
        for d in details:
            entry += f"- {d}\n"
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(entry)

def acquire_lock(root):
    """Acquire file lock for wiki operations."""
    try:
        import fcntl
        lock_path = os.path.join(root, ".wiki.lock")
        lock_file = open(lock_path, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return lock_file
    except Exception:
        return None

def release_lock(lock_file):
    """Release file lock."""
    if lock_file:
        try:
            lock_file.close()
        except Exception:
            pass

def git_commit(root, message):
    """Auto git commit."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", message, "--allow-empty"], cwd=root, capture_output=True)
    except Exception:
        pass  # git not available or no changes

def update_index(root, title, summary, category="Concepts"):
    """Incrementally add entry to index.md."""
    index_path = os.path.join(root, "index.md")
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if already exists
    if f"- [[{title}]]" in content:
        return

    # Find the category section and append
    section_header = f"## {category}\n"
    if section_header in content:
        # Find next section or end of file
        idx = content.index(section_header) + len(section_header)
        # Skip existing content in section
        next_section = content.find("\n## ", idx)
        if next_section == -1:
            insert_pos = len(content)
        else:
            insert_pos = next_section
        new_entry = f"- [[{title}]] — {summary}\n"
        content = content[:insert_pos] + new_entry + content[insert_pos:]
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(content)

def extract_related_from_body(body):
    """Extract [[links]] from '## 相关页面' section in body."""
    links = []
    match = re.search(r'## 相关页面\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
    if match:
        links = re.findall(r'\[\[([^\]|#\]]+)', match.group(1))
    return [l.strip() for l in links if l.strip()]

def get_all_wiki_pages(root):
    """Get all wiki pages with their metadata."""
    pages = []
    pages_dir = os.path.join(root, "wiki", "pages")
    if not os.path.exists(pages_dir):
        return pages
    for fname in os.listdir(pages_dir):
        if fname.endswith('.md'):
            fpath = os.path.join(pages_dir, fname)
            fm, body = parse_frontmatter(fpath)
            pages.append({
                'path': fpath,
                'filename': fname,
                'title': fm.get('title', fname[:-3]),
                'type': fm.get('type', ''),
                'tags': fm.get('tags', []) if isinstance(fm.get('tags'), list) else [],
                'updated': fm.get('updated', ''),
                'sources': fm.get('sources', []) if isinstance(fm.get('sources'), list) else [],
                'confidence': fm.get('confidence', ''),
                'related': extract_related_from_body(body),
            })
    return pages

# ─── ingest ─────────────────────────────────────────────

def create_wiki_page(root, title, content, page_type="concept", tags=None, sources=None, confidence="medium", related=None):
    """Create a wiki page with proper frontmatter. Returns the file path."""
    pages_dir = os.path.join(root, "wiki", "pages")
    os.makedirs(pages_dir, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    safe_title = title.replace('/', '-').replace('\\', '-').replace(':', '-')
    filepath = os.path.join(pages_dir, f"{safe_title}.md")
    
    tags = tags or []
    sources = sources or []
    related = related or []
    
    fm = f"""---
title: {title}
created: {today}
updated: {today}
tags: [{', '.join(tags)}]
type: {page_type}
sources:
"""
    for s in sources:
        fm += f"  - {s}\n"
    fm += f"""confidence: {confidence}
---\n\n"""
    
    # Append related links to body (Obsidian-compatible)
    related_section = ""
    if related:
        related_section = "---\n## 相关页面\n"
        for r in related:
            related_section += f"- [[{r}]]\n"
    
    full_content = fm + content.rstrip() + related_section
    
    lock = acquire_lock(root)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
    finally:
        release_lock(lock)
    
    return filepath

def update_wiki_page(root, title, new_content=None, append_content=None, new_sources=None, new_related=None):
    """Update an existing wiki page. Incremental update."""
    pages_dir = os.path.join(root, "wiki", "pages")
    safe_title = title.replace('/', '-').replace('\\', '-').replace(':', '-')
    filepath = os.path.join(pages_dir, f"{safe_title}.md")
    
    if not os.path.exists(filepath):
        return None
    
    fm, body = parse_frontmatter(filepath)
    today = datetime.now().strftime('%Y-%m-%d')
    
    changed = False
    if new_content is not None:
        body = new_content
        changed = True
    if append_content:
        body = body + "\n\n" + append_content
        changed = True
    if new_sources:
        existing = fm.get('sources', []) if isinstance(fm.get('sources'), list) else []
        fm['sources'] = list(set(existing + new_sources))
        changed = True
    if new_related:
        # Add related links to body's ## 相关页面 section
        existing = extract_related_from_body(body)
        all_related = list(set(existing + new_related))
        # Remove old section if exists
        body = re.sub(r'\n---\n## 相关页面\n.*$', '', body, flags=re.DOTALL).rstrip()
        related_section = "\n---\n## 相关页面\n"
        for r in all_related:
            related_section += f"- [[{r}]]\n"
        body = body + related_section
        changed = True
    if changed:
        fm['updated'] = today
    
    # Reconstruct file
    new_fm = "---\n"
    for k, v in fm.items():
        if isinstance(v, list):
            new_fm += f"{k}:\n"
            for item in v:
                new_fm += f"  - {item}\n"
        else:
            new_fm += f"{k}: {v}\n"
    new_fm += "---\n\n"
    
    lock = acquire_lock(root)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_fm + body)
    finally:
        release_lock(lock)
    
    return filepath

def create_qa_page(root, question, answer, sources=None, tags=None):
    """Create a QA backfill page."""
    qa_dir = os.path.join(root, "wiki", "qa")
    os.makedirs(qa_dir, exist_ok=True)
    import hashlib
    qhash = hashlib.md5(question.encode()).hexdigest()[:8]
    today = datetime.now().strftime('%Y-%m-%d')
    filepath = os.path.join(qa_dir, f"qa-{qhash}.md")
    
    tags = tags or ["qa"]
    sources = sources or []
    
    fm = f"""---
title: Q&A - {question[:60]}
created: {today}
updated: {today}
tags: [{', '.join(tags)}]
type: qa
sources:
"""
    for s in sources:
        fm += f"  - {s}\n"
    fm += """confidence: high
---
"""
    content = f"## 问题\n\n{question}\n\n## 答案\n\n{answer}\n"
    
    lock = acquire_lock(root)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(fm + content)
    finally:
        release_lock(lock)
    
    return filepath

def cmd_ingest(args):
    root = get_root(args)
    source = args.source
    interactive = args.interactive

    # Check wiki exists
    if not os.path.exists(os.path.join(root, "index.md")):
        print("❌ Wiki not initialized. Run: wiki.py init")
        sys.exit(1)

    print(f"📥 Ingesting: {source}")

    # Step 1: Get content
    content = ""
    filename = ""
    category = "articles"
    title = ""

    if source.startswith('http://') or source.startswith('https://'):
        # Fetch via zhipu web reader
        reader = os.path.expanduser("~/.openclaw/workspace/skills/base/zhipu-toolkit/scripts/zhipu_api.py")
        if os.path.exists(reader):
            result = subprocess.run(
                ["python3", reader, "read", source, "--format", "markdown"],
                capture_output=True, text=True, timeout=60
            )
            content = result.stdout
            if not content or len(content) < 100:
                print("⚠️ Web fetch returned too little content, falling back to web_fetch")
                content = ""
        if not content:
            print("❌ Failed to fetch URL. Try saving locally first.")
            sys.exit(1)
        title = source.split('/')[-1][:50] or f"article-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        filename = f"{title}.md"
    elif os.path.isfile(source):
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
        filename = os.path.basename(source)
        # Determine category from path
        if 'paper' in source.lower():
            category = 'papers'
        elif 'book' in source.lower():
            category = 'books'
    else:
        # Treat as direct text
        content = source
        title = f"note-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        filename = f"{title}.md"

    if not title:
        title = filename.replace('.md', '').replace('.txt', '')

    if not content or len(content) < 20:
        print("❌ Content too short to ingest.")
        sys.exit(1)

    # Save to raw/
    raw_path = os.path.join(root, "raw", category, filename)
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  ✅ Saved to raw/{category}/{filename} ({len(content)} chars)")

    # Note: Steps 2-5 (concept extraction, page generation, index/log update)
    # are handled by the LLM agent, not this script.
    # The script only does the deterministic parts: fetch, save, git.
    print(f"\n📋 Raw content saved. LLM will now:")
    print(f"  1. Extract key concepts")
    print(f"  2. Create/update wiki pages")
    print(f"  3. Update index.md and log.md")
    print(f"\n📄 Content preview (first 500 chars):")
    print(content[:500])

    git_commit(root, f"ingest: save raw/{category}/{filename}")

# ─── query ─────────────────────────────────────────────

def cmd_query(args):
    root = get_root(args)
    question = args.question

    # Read index.md for context
    index_path = os.path.join(root, "index.md")
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            index_content = f.read()
        print(f"📖 Index loaded ({len(index_content)} chars)")
    else:
        print("❌ Wiki not initialized.")
        sys.exit(1)

    # Get all pages metadata for context
    pages = get_all_wiki_pages(root)
    print(f"📚 Found {len(pages)} wiki pages")

    # Output structured info for LLM to process
    print(f"\n🔍 Query: {question}")
    print(f"\n📋 Available pages:")
    for p in pages:
        print(f"  - {p['title']} (type={p['type']}, confidence={p['confidence']})")

# ─── lint ──────────────────────────────────────────────

def cmd_lint(args):
    root = get_root(args)
    quick = args.quick
    deep = args.deep

    if not quick and not deep:
        quick = True  # default to quick

    issues = []
    pages = get_all_wiki_pages(root)

    # Read index to find referenced pages
    index_path = os.path.join(root, "index.md")
    index_content = ""
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            index_content = f.read()

    # Read log for query records
    log_path = os.path.join(root, "log.md")
    log_content = ""
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            log_content = f.read()

    # 1. Orphan pages
    indexed_titles = set()
    for line in index_content.split('\n'):
        if line.startswith('- [['):
            t = line.split('[[')[1].split(']]')[0]
            indexed_titles.add(t.lower())

    for p in pages:
        title_lower = p['title'].lower()
        # Check if referenced in index
        if title_lower not in indexed_titles:
            # Check if referenced by other wiki pages
            referenced = False
            for other in pages:
                if other['path'] != p['path']:
                    with open(other['path'], 'r', encoding='utf-8') as f:
                        if f"[[{p['title']}]]" in f.read():
                            referenced = True
                            break
            if not referenced:
                issues.append(('orphan', f"孤儿页面: {p['title']}"))

    # 2. Outdated pages
    cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    for p in pages:
        if p['updated'] and p['updated'] < cutoff:
            days = (datetime.now() - datetime.strptime(p['updated'], '%Y-%m-%d')).days
            issues.append(('outdated', f"过时页面: {p['title']} ({days}天未更新)"))

    # 3. Pages without confidence or sources
    for p in pages:
        if not p.get('confidence'):
            issues.append(('metadata', f"缺少置信度: {p['title']}"))
        if not p.get('sources') and p.get('type') == 'source':
            issues.append(('metadata', f"来源页缺少sources: {p['title']}"))

    # 4. Deprecated: related in frontmatter (should be in body)
    for p in pages:
        fm, body = parse_frontmatter(p['path'])
        if 'related' in fm:
            issues.append(('deprecated', f"frontmatter 包含废弃的 related 字段: {p['title']}"))

    # 5. Broken [[links]] in body (deduplicated per page)
    existing_titles = set()
    for p in pages:
        existing_titles.add(p['title'].lower())
        existing_titles.add(p['filename'].lower().replace('.md', ''))
    for p in pages:
        _, body = parse_frontmatter(p['path'])
        body_links = set(re.findall(r'\[\[([^\]|#\]]+)', body))
        for link in body_links:
            link = link.strip()
            if link and link.lower() not in existing_titles:
                issues.append(('broken-link', f"断链: [[{link}]] 在 {p['title']}"))

    # 4. Unbackfilled queries
    query_lines = [l for l in log_content.split('\n') if 'query' in l.lower()]
    qa_count = len([f for f in os.listdir(os.path.join(root, "wiki", "qa")) if f.endswith('.md')]) \
        if os.path.exists(os.path.join(root, "wiki", "qa")) else 0

    # Report
    if not issues:
        print("✅ Wiki 健康，未发现问题。")
    else:
        print(f"🔍 发现 {len(issues)} 个问题：\n")
        orphans = [i for i in issues if i[0] == 'orphan']
        outdated = [i for i in issues if i[0] == 'outdated']
        metadata = [i for i in issues if i[0] == 'metadata']

        if orphans:
            print(f"  🔴 孤儿页面 ({len(orphans)}):")
            for _, desc in orphans:
                print(f"    - {desc}")
        if outdated:
            print(f"  🟡 过时页面 ({len(outdated)}):")
            for _, desc in outdated:
                print(f"    - {desc}")
        if metadata:
            print(f"  🟢 元数据缺失 ({len(metadata)}):")
            for _, desc in metadata:
                print(f"    - {desc}")
        deprecated = [i for i in issues if i[0] == 'deprecated']
        if deprecated:
            print(f"  🟠 废弃字段 ({len(deprecated)}):")
            for _, desc in deprecated:
                print(f"    - {desc}")
        broken = [i for i in issues if i[0] == 'broken-link']
        if broken:
            print(f"  🔴 断链 ({len(broken)}):")
            for _, desc in broken:
                print(f"    - {desc}")

    print(f"\n📊 统计: {len(pages)} 个页面, {len(query_lines)} 次查询, {qa_count} 个回填")

    if deep:
        print("\n🔄 深度 Lint 需要调用 LLM 分析，建议在 agent 上下文中执行。")

# ─── status ────────────────────────────────────────────

def cmd_status(args):
    root = get_root(args)
    pages = get_all_wiki_pages(root)
    types = {}
    for p in pages:
        t = p.get('type', 'unknown')
        types[t] = types.get(t, 0) + 1

    log_path = os.path.join(root, "log.md")
    log_lines = 0
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            log_lines = len([l for l in f if l.startswith('## [')])

    print(f"📚 LLM Wiki Status")
    print(f"  路径: {root}")
    print(f"  页面: {len(pages)}")
    print(f"  类型: {types}")
    print(f"  操作记录: {log_lines}")

# ─── main ──────────────────────────────────────────────

def cmd_observe(args):
    root = get_root(args)
    target = args.target
    action = args.action

    if action == 'link':
        # Create symlink from Obsidian vault to wiki
        wiki_pages = os.path.join(root, "wiki", "pages")
        qa_dir = os.path.join(root, "wiki", "qa")
        target_pages = os.path.join(target, "wiki-pages")
        target_qa = os.path.join(target, "wiki-qa")

        os.makedirs(target, exist_ok=True)
        if os.path.islink(target_pages):
            os.unlink(target_pages)
        if os.path.islink(target_qa):
            os.unlink(target_qa)
        os.symlink(wiki_pages, target_pages)
        os.symlink(qa_dir, target_qa)
        print(f"✅ Symlinks created:")
        print(f"  {target_pages} → {wiki_pages}")
        print(f"  {target_qa} → {qa_dir}")
        print(f"  Open Obsidian at {target} to browse wiki")
    else:
        print(f"Supported actions: link")

def cmd_diff(args):
    """Show git diff summary for recent changes."""
    root = get_root(args)
    n = args.n
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--oneline", "--name-status"],
            cwd=root, capture_output=True, text=True
        )
        print(result.stdout)
        if args.verbose:
            result2 = subprocess.run(
                ["git", "diff", f"HEAD~{min(n,5)}..HEAD", "--stat"],
                cwd=root, capture_output=True, text=True
            )
            print(f"\n📊 变更统计:\n{result2.stdout}")
    except Exception as e:
        print(f"❌ Git error: {e}")

def cmd_history(args):
    """Parse and display log.md entries."""
    root = get_root(args)
    log_path = os.path.join(root, "log.md")
    if not os.path.exists(log_path):
        print("❌ No log.md found")
        return
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    entries = [l.strip() for l in lines if l.startswith('## [')]
    if args.filter:
        entries = [e for e in entries if f"{args.filter}" in e]
    n = args.n
    for e in entries[-n:]:
        print(e)
    print(f"\n共 {len(entries)} 条记录")

# ─── main ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM Wiki - 增量式个人知识库")
    sub = parser.add_subparsers(dest='command')

    # init
    p_init = sub.add_parser('init', help='初始化 Wiki')
    p_init.add_argument('--path', default=DEFAULT_ROOT)

    # ingest
    p_ingest = sub.add_parser('ingest', help='摄入资料')
    p_ingest.add_argument('source', help='文件路径、URL 或直接文本')
    p_ingest.add_argument('--interactive', '-i', action='store_true')
    p_ingest.add_argument('--path', default=None)

    # query
    p_query = sub.add_parser('query', help='查询知识库')
    p_query.add_argument('question', help='查询问题')
    p_query.add_argument('--path', default=None)

    # lint
    p_lint = sub.add_parser('lint', help='健康检查')
    p_lint.add_argument('--quick', action='store_true', help='快速检查')
    p_lint.add_argument('--deep', action='store_true', help='深度检查')
    p_lint.add_argument('--path', default=None)

    # status
    p_status = sub.add_parser('status', help='查看状态')
    p_status.add_argument('--path', default=None)

    # observe (Obsidian integration)
    p_obs = sub.add_parser('observe', help='Obsidian 集成')
    p_obs.add_argument('action', choices=['link'], help='操作类型')
    p_obs.add_argument('--target', required=True, help='Obsidian vault 路径')
    p_obs.add_argument('--path', default=None)

    # diff
    p_diff = sub.add_parser('diff', help='查看 Git 变更历史')
    p_diff.add_argument('-n', type=int, default=10, help='显示最近 N 条')
    p_diff.add_argument('--verbose', '-v', action='store_true')
    p_diff.add_argument('--path', default=None)

    # history
    p_hist = sub.add_parser('history', help='查看 log.md 操作历史')
    p_hist.add_argument('-n', type=int, default=10, help='显示最近 N 条')
    p_hist.add_argument('--filter', default=None, help='过滤操作类型')
    p_hist.add_argument('--path', default=None)

    # create-page
    p_create = sub.add_parser('create-page', help='创建 wiki 页面')
    p_create.add_argument('title', help='页面标题')
    p_create.add_argument('--type', default='concept', help='页面类型')
    p_create.add_argument('--tags', default='', help='标签（逗号分隔）')
    p_create.add_argument('--sources', default='', help='来源（逗号分隔）')
    p_create.add_argument('--confidence', default='medium')
    p_create.add_argument('--related', default='', help='关联页面（逗号分隔）')
    p_create.add_argument('--path', default=None)

    # update-page
    p_update = sub.add_parser('update-page', help='更新 wiki 页面')
    p_update.add_argument('title', help='页面标题')
    p_update.add_argument('--append', default=None, help='追加内容')
    p_update.add_argument('--sources', default='', help='新增来源（逗号分隔）')
    p_update.add_argument('--related', default='', help='新增关联（逗号分隔）')
    p_update.add_argument('--path', default=None)

    # create-qa
    p_qa = sub.add_parser('create-qa', help='创建 QA 回填页面')
    p_qa.add_argument('--question', required=True)
    p_qa.add_argument('--answer', required=True)
    p_qa.add_argument('--sources', default='')
    p_qa.add_argument('--tags', default='')
    p_qa.add_argument('--path', default=None)

    # backfill
    p_bf = sub.add_parser('backfill', help='回填优质答案到 wiki/qa')
    p_bf.add_argument('title', help='QA 页面标题')
    p_bf.add_argument('--question', required=True)
    p_bf.add_argument('--answer', required=True)
    p_bf.add_argument('--sources', default='')
    p_bf.add_argument('--path', default=None)

    args = parser.parse_args()

    if args.command == 'init':
        cmd_init(args)
    elif args.command == 'ingest':
        cmd_ingest(args)
    elif args.command == 'query':
        cmd_query(args)
    elif args.command == 'lint':
        cmd_lint(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'observe':
        cmd_observe(args)
    elif args.command == 'diff':
        cmd_diff(args)
    elif args.command == 'history':
        cmd_history(args)
    elif args.command == 'create-page':
        title = args.title
        tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else []
        sources = [s.strip() for s in args.sources.split(',') if s.strip()] if args.sources else []
        related = [r.strip() for r in args.related.split(',') if r.strip()] if args.related else []
        path = create_wiki_page(get_root(args), title, '', page_type=args.type, tags=tags, sources=sources, confidence=args.confidence, related=related)
        print(f"✅ Page created: {path}")
        update_index(get_root(args), title, f"(type={args.type})", args.type.capitalize())
        append_log(get_root(args), 'create', title, [f"新建: {path}"])
        git_commit(get_root(args), f"create: {title}")
    elif args.command == 'update-page':
        title = args.title
        new_sources = [s.strip() for s in args.sources.split(',') if s.strip()] if args.sources else []
        new_related = [r.strip() for r in args.related.split(',') if r.strip()] if args.related else []
        path = update_wiki_page(get_root(args), title, append_content=args.append, new_sources=new_sources or None, new_related=new_related or None)
        if path:
            print(f"✅ Page updated: {path}")
            append_log(get_root(args), 'update', title, [f"更新: {path}"])
            git_commit(get_root(args), f"update: {title}")
        else:
            print(f"❌ Page not found: {title}")
    elif args.command == 'create-qa':
        sources = [s.strip() for s in args.sources.split(',') if s.strip()] if args.sources else []
        tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else ['qa']
        path = create_qa_page(get_root(args), args.question, args.answer, sources=sources, tags=tags)
        print(f"✅ QA page created: {path}")
        title = args.question[:40]
        update_index(get_root(args), title, args.question[:80], 'Q&A')
        append_log(get_root(args), 'query', title, [f"回填: {path}"])
        git_commit(get_root(args), f"qa-backfill: {title}")
    elif args.command == 'backfill':
        sources = [s.strip() for s in args.sources.split(',') if s.strip()] if args.sources else []
        tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else ['qa']
        path = create_qa_page(get_root(args), args.question, args.answer, sources=sources, tags=tags)
        print(f"✅ QA page created: {path}")
        update_index(get_root(args), args.title, args.question[:80], 'Q&A')
        append_log(get_root(args), 'query', args.title, [f"回填: {path}"])
        git_commit(get_root(args), f"qa-backfill: {args.title}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
