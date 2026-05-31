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
        "compiled/source-notes", "registry", "changelog",
        "wiki/concepts", "wiki/frameworks", "schema",
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

    # Copy bundled markdown templates into matching wiki subdirectories.
    SKILL_DIR = Path(__file__).parent.parent
    templates_dir = SKILL_DIR / 'templates'
    if templates_dir.exists():
        for template_path in templates_dir.rglob('*.md'):
            relative_path = template_path.relative_to(templates_dir)
            dest_path = Path(root) / relative_path
            if dest_path.exists():
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(template_path, dest_path)

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


def save_source_to_raw(root, source):
    """按 ingest 规则保存来源资料到 raw/，返回元数据。"""
    root_path = Path(root)
    content = ""
    filename = ""
    category = "articles"
    title = ""
    source_type = "article"

    if source.startswith('http://') or source.startswith('https://'):
        title = source.split('/')[-1].split('?')[0][:50] or f"article-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        title = title.replace('/', '-').replace('\\', '-').replace(':', '-')
        filename = f"{title}.md"
        category = 'articles'
        source_type = 'article'
        # URL 只落占位文件，由 LLM agent 抓取正文后调用 update-raw 回填。
        content = f"---\nsource_url: {source}\ningested: {datetime.now().strftime('%Y-%m-%d')}\n---\n\n<!-- NEEDS_AGENT_FETCH -->\n"
        raw_path = root_path / "raw" / category / filename
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        lock = acquire_lock(str(root_path))
        try:
            raw_path.write_text(content, encoding='utf-8')
        finally:
            release_lock(lock)
        print(f"NEEDS_AGENT_FETCH: {source} -> {raw_path.relative_to(root_path).as_posix()}")
        return {
            "content": "",
            "title": title,
            "category": category,
            "filename": filename,
            "raw_path": raw_path,
            "raw_rel_path": raw_path.relative_to(root_path).as_posix(),
            "source_type": source_type,
            "needs_agent_fetch": True,
        }
    elif os.path.isfile(source):
        source_path = Path(source)
        content = source_path.read_text(encoding='utf-8')
        filename = source_path.name
        # 根据路径粗略判断 raw 分类，与 ingest 保持一致。
        source_lower = source.lower()
        if 'paper' in source_lower:
            category = 'papers'
            source_type = "paper"
        elif 'book' in source_lower:
            category = 'books'
            source_type = "book"
    else:
        # 直接文本保存为 note。
        content = source
        title = f"note-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        filename = f"{title}.md"
        source_type = "text"

    if not title:
        title = filename.replace('.md', '').replace('.txt', '')

    raw_path = root_path / "raw" / category / filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(str(root_path))
    try:
        raw_path.write_text(content, encoding='utf-8')
    finally:
        release_lock(lock)

    return {
        "content": content,
        "title": title,
        "category": category,
        "filename": filename,
        "raw_path": raw_path,
        "raw_rel_path": raw_path.relative_to(root_path).as_posix(),
        "source_type": source_type,
    }


def cmd_update_raw(args):
    """LLM agent 调用：回填 URL 抓取内容到 raw 文件。"""
    root = Path(get_root(args)).resolve()
    raw_path = (root / args.raw_path).resolve()
    if not raw_path.is_relative_to(root):
        print(f"❌ Invalid raw path outside wiki root: {args.raw_path}")
        sys.exit(1)
    if not raw_path.exists():
        print(f"❌ Raw file not found: {raw_path}")
        sys.exit(1)

    content_arg = args.content
    if content_arg and os.path.isfile(content_arg):
        new_content = Path(content_arg).read_text(encoding='utf-8')
    else:
        new_content = content_arg

    existing = raw_path.read_text(encoding='utf-8')
    source_url = ''
    if existing.startswith('---'):
        end = existing.find('---', 3)
        if end != -1:
            for line in existing[3:end].strip().split('\n'):
                if line.startswith('source_url:'):
                    source_url = line.split(':', 1)[1].strip().strip('"').strip("'")
                    break

    import hashlib
    sha256 = hashlib.sha256(new_content.encode('utf-8')).hexdigest()

    today = datetime.now().strftime('%Y-%m-%d')
    header = f"---\nsource_url: {source_url}\ningested: {today}\nsha256: {sha256}\n---\n\n"
    lock = acquire_lock(str(root))
    try:
        raw_path.write_text(header + new_content, encoding='utf-8')
    finally:
        release_lock(lock)

    git_commit(str(root), f"update-raw: {raw_path.name}")
    print(f"✅ Raw updated: {raw_path.relative_to(root)} ({len(new_content)} chars)")
    print(f"  sha256: {sha256[:16]}...")

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
        saved = save_source_to_raw(root, source)
        if saved.get("needs_agent_fetch"):
            git_commit(root, f"ingest placeholder: {saved['filename']}")
            return saved
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

# ─── mvp helpers ───────────────────────────────────────

ID_PREFIXES = {
    "source": "src",
    "concept": "cpt",
    "framework": "frm",
    "claim": "clm",
}

ID_DIRS = {
    "source": "compiled/source-notes",
    "concept": "wiki/concepts",
    "framework": "wiki/frameworks",
    "claim": "registry",
}

REGISTRY_FILES = {
    "concept": "concept-registry.md",
    "framework": "framework-registry.md",
    "claim": "claim-registry.md",
    "source": "source-registry.md",
    "page": "page-registry.md",
}


def generate_new_id(root, object_type):
    """按现有目录中最大序号生成下一个对象 ID。"""
    root = Path(root)
    prefix = ID_PREFIXES[object_type]
    today = datetime.now().strftime("%Y%m%d")
    target_dir = root / ID_DIRS[object_type]
    target_dir.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(rf"^{re.escape(prefix)}_{today}_(\d{{3}})")
    max_seq = 0
    for path in target_dir.iterdir():
        match = pattern.match(path.name)
        if match:
            max_seq = max(max_seq, int(match.group(1)))

    return f"{prefix}_{today}_{max_seq + 1:03d}"


def cmd_new_id(args):
    root = Path(get_root(args))
    print(generate_new_id(root, args.type))


def cmd_registry(args):
    root = Path(get_root(args))
    registry_path = root / "registry" / REGISTRY_FILES[args.name]

    if args.action == "list":
        if not registry_path.exists():
            print(f"❌ Registry not found: {registry_path}")
            sys.exit(1)
        print(registry_path.read_text(encoding="utf-8"), end="")
        return

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    entry = args.entry.rstrip()
    with registry_path.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")
    print(f"✅ Registry updated: {registry_path}")


def _table_cell(value):
    """清理 Markdown 表格单元格，避免换行或竖线破坏表格。"""
    return str(value).replace("\n", " ").replace("|", "\\|").strip()


def _split_md_table_row(line):
    """按未转义竖线拆分 Markdown 表格行。"""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    stripped = stripped[1:]

    cells = []
    current = []
    escaped = False
    for ch in stripped:
        if ch == "\\" and not escaped:
            escaped = True
            current.append(ch)
            continue
        if ch == "|" and not escaped:
            cells.append("".join(current).replace("\\|", "|").strip())
            current = []
        else:
            current.append(ch)
        escaped = False
    cells.append("".join(current).replace("\\|", "|").strip())
    return cells


def _is_table_separator(cells):
    """判断是否为 Markdown 表格分隔行。"""
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def read_markdown_table(path):
    """读取首个 Markdown 表格，返回 lines、headers、rows。"""
    path = Path(path)
    if not path.exists():
        return [], [], []

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    headers = []
    rows = []
    for idx, line in enumerate(lines):
        cells = _split_md_table_row(line)
        if not cells:
            continue
        if _is_table_separator(cells):
            continue
        if not headers:
            headers = cells
            continue
        padded = cells + [""] * max(0, len(headers) - len(cells))
        rows.append({
            "__line_index": idx,
            "__cells": padded[:len(headers)],
            **{headers[i]: padded[i] if i < len(padded) else "" for i in range(len(headers))},
        })
    return lines, headers, rows


def find_registry_entry(root, registry_name, object_id):
    """按 ID 查找 registry 表格条目。"""
    root = Path(root)
    registry_path = root / "registry" / REGISTRY_FILES[registry_name]
    _, headers, rows = read_markdown_table(registry_path)
    if not headers:
        return registry_path, None

    id_candidates = [f"{registry_name}_id", "id", headers[0]]
    for row in rows:
        for key in id_candidates:
            if row.get(key) == object_id:
                return registry_path, row
    return registry_path, None


def update_registry_row(root, registry_name, object_id, values):
    """更新 registry 指定行的部分字段。"""
    root = Path(root)
    registry_path = root / "registry" / REGISTRY_FILES[registry_name]
    lines, headers, rows = read_markdown_table(registry_path)
    if not headers:
        return False

    id_candidates = [f"{registry_name}_id", "id", headers[0]]
    for row in rows:
        if not any(row.get(key) == object_id for key in id_candidates):
            continue
        cells = row["__cells"] + [""] * max(0, len(headers) - len(row["__cells"]))
        for key, value in values.items():
            if key in headers:
                cells[headers.index(key)] = _table_cell(value)
        lines[row["__line_index"]] = "| " + " | ".join(cells[:len(headers)]) + " |\n"
        lock = acquire_lock(str(root))
        try:
            registry_path.write_text("".join(lines), encoding="utf-8")
        finally:
            release_lock(lock)
        return True
    return False


def auto_register_source(root, source_id, title, source_type, raw_path, level):
    """自动追加 source registry 条目。"""
    root = Path(root)
    registry_path = root / "registry" / "source-registry.md"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    source_note = f"compiled/source-notes/{source_id}.md"
    entry = (
        f"| {_table_cell(source_id)} | {_table_cell(title)} | {_table_cell(source_type)} | "
        f"{_table_cell(raw_path)} | {_table_cell(source_note)} | {_table_cell(level)} | pending | {today} |\n"
    )

    lock = acquire_lock(str(root))
    try:
        with registry_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    finally:
        release_lock(lock)
    return registry_path


def auto_page_register(root, page_id, title, page_type, path):
    """自动追加 page registry 条目。"""
    root = Path(root)
    registry_path = root / "registry" / "page-registry.md"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if not registry_path.exists():
        registry_path.write_text(
            "# Page Registry\n\n"
            "| page_id | title | type | path | created |\n"
            "|---|---|---|---|---|\n",
            encoding="utf-8",
        )

    today = datetime.now().strftime("%Y-%m-%d")
    page_path = Path(path)
    if page_path.is_absolute():
        try:
            page_path = page_path.relative_to(root)
        except ValueError:
            pass
    entry = (
        f"| {_table_cell(page_id)} | {_table_cell(title)} | {_table_cell(page_type)} | "
        f"{_table_cell(page_path.as_posix())} | {today} |\n"
    )

    lock = acquire_lock(str(root))
    try:
        with registry_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    finally:
        release_lock(lock)
    return registry_path


def append_changelog_change(root, change_type, object_id, summary, source=""):
    """按 changelog add 格式追加 changes.md。"""
    root = Path(root)
    changelog_dir = root / "changelog"
    changelog_dir.mkdir(parents=True, exist_ok=True)
    changelog_path = changelog_dir / "changes.md"
    today = datetime.now().strftime("%Y-%m-%d")
    entry = (
        f"| {today} | {_table_cell(change_type)} | {_table_cell(object_id)} | "
        f"{_table_cell(source)} | {_table_cell(summary)} | pending |\n"
    )

    lock = acquire_lock(str(root))
    try:
        with changelog_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    finally:
        release_lock(lock)
    return changelog_path


def cmd_changelog(args):
    root = Path(get_root(args))
    changelog_dir = root / "changelog"
    changelog_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    if args.action == "add":
        changelog_path = append_changelog_change(
            root,
            args.change_type,
            args.object,
            args.summary,
        )
    else:
        changelog_path = changelog_dir / "pending-review.md"
        entry = (
            f"\n## {today}\n\n"
            f"- 类型：{args.change_type}\n"
            f"- 影响对象：{args.object}\n"
            f"- 摘要：{args.summary}\n"
        )
        with changelog_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    print(f"✅ Changelog updated: {changelog_path}")


def create_source_note(root, source_id, title, source_type, raw_path, level):
    """创建 V1 source-note 占位文件。"""
    root = Path(root)
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = root / "compiled" / "source-notes" / f"{source_id}.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""---
source_id: {source_id}
title: {title}
source_type: {source_type}
raw_path: {raw_path}
level: {level}
created: {today}
---

# {title}

## 核心观点

## 关键概念

## 待验证声明

## 关联
"""

    lock = acquire_lock(str(root))
    try:
        note_path.write_text(content, encoding="utf-8")
    finally:
        release_lock(lock)
    return note_path


def cmd_compile(args):
    root = Path(get_root(args))
    source = args.source
    level = args.level

    if not (root / "index.md").exists():
        print("❌ Wiki not initialized. Run: wiki.py init")
        sys.exit(1)

    print(f"📚 Compiling: {source}")
    saved = save_source_to_raw(root, source)

    if saved.get("needs_agent_fetch"):
        print("✅ Raw placeholder saved; agent fetch required before compile.")
        print(f"  raw: {saved['raw_rel_path']}")
        print("  needs_agent_fetch: true")
        return

    content = saved["content"]
    # L0 是碎片归档，不做正文长度检查；L1-L3 需要有可编译正文。
    if level != 'L0' and (not content or len(content) < 20):
        print("❌ Content too short to compile.")
        sys.exit(1)

    source_id = generate_new_id(root, "source")
    title = saved["title"]
    source_type = saved["source_type"]
    raw_rel_path = saved["raw_rel_path"]

    # 脚本只做确定性步骤；概念/声明/Mutation 由 LLM agent 后续完成。
    note_path = create_source_note(root, source_id, title, source_type, raw_rel_path, level)
    registry_path = auto_register_source(root, source_id, title, source_type, raw_rel_path, level)
    changelog_path = append_changelog_change(
        root,
        "compile",
        source_id,
        f"编译资料：{title}",
        source_id,
    )
    append_log(root, "compile", title, [
        f"source_id: {source_id}",
        f"raw: {raw_rel_path}",
        f"source-note: {note_path.relative_to(root).as_posix()}",
        f"level: {level}",
    ])
    git_commit(root, f"compile: {source_id} {title}")

    print("✅ Compile completed")
    print(f"  source_id: {source_id}")
    print(f"  raw: {raw_rel_path} ({len(content)} chars)")
    print(f"  source-note: {note_path.relative_to(root).as_posix()}")
    print(f"  registry: {registry_path.relative_to(root).as_posix()}")
    print(f"  changelog: {changelog_path.relative_to(root).as_posix()}")
    if saved.get("needs_agent_fetch"):
        print("  needs_agent_fetch: true")


def _row_value(row, *keys, default=""):
    """从 registry 行中按多个候选字段取值。"""
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return default


def _as_list(value):
    """把 frontmatter/registry 字段统一为列表。"""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in re.split(r"[,，;；]", str(value)) if v.strip()]


def _is_placeholder_link(value):
    """过滤模板中的示例链接，避免 generated maps 收录占位符。"""
    placeholders = {
        "cpt_上位概念", "cpt_下位概念", "cpt_相关概念1", "cpt_相关概念2",
        "cpt_对立概念", "cpt_xxx", "cpt_yyy", "clm_xxx", "clm_yyy", "frm_xxx",
    }
    return value in placeholders


def _template_path(root, page_type):
    """优先读取 wiki root 下 init 复制的模板，缺失时回退到内置模板。"""
    root = Path(root)
    filename = f"TEMPLATE.{page_type}.md"
    copied = root / "schema" / filename
    if copied.exists():
        return copied
    return Path(__file__).parent.parent / "templates" / "schema" / filename


def render_promoted_page(root, page_type, object_id, entry):
    """用 schema 模板渲染 promoted 页面。"""
    template_path = _template_path(root, page_type)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    today = datetime.now().strftime("%Y-%m-%d")
    title = _row_value(entry, "canonical_name", "title", "name", default=object_id)
    domain = _row_value(entry, "domain", default="未分类")
    description = _row_value(entry, "one_line_def", "definition", "description", "summary")
    confidence = _row_value(entry, "confidence", default="medium")

    content = template_path.read_text(encoding="utf-8")
    if page_type == "concept":
        replacements = {
            "cpt_概念名称": object_id,
            "概念中文名称": title,
            "concept_english_name": title,
            "领域标签": domain,
            "active / draft / archived / contested": "active",
            "high / medium / low / speculative": confidence,
            "YYYY-MM-DD": today,
        }
        for old, new in replacements.items():
            content = content.replace(old, str(new))
        if description:
            content = content.replace(f"[{title}] 是 [定义]。", f"{title} 是 {description}。")
            content = content.replace("[概念名称] 是 [定义]。", f"{title} 是 {description}。")
    else:
        replacements = {
            "frm_框架名称": object_id,
            "框架中文名称": title,
            "领域标签": domain,
            "active / draft / archived / contested": "active",
            "high / medium / low / speculative": confidence,
            "YYYY-MM-DD": today,
        }
        for old, new in replacements.items():
            content = content.replace(old, str(new))

    return content, title, domain, description


def cmd_promote(args):
    root = Path(get_root(args))
    object_id = args.id
    page_type = args.type
    if not page_type:
        if object_id.startswith("cpt_"):
            page_type = "concept"
        elif object_id.startswith("frm_"):
            page_type = "framework"
        else:
            print("❌ Cannot infer type. Use --type concept|framework.")
            sys.exit(1)

    if not (root / "index.md").exists():
        print("❌ Wiki not initialized. Run: wiki.py init")
        sys.exit(1)

    registry_path, entry = find_registry_entry(root, page_type, object_id)
    if not entry:
        print(f"❌ Registry entry not found: {object_id} in {registry_path}")
        sys.exit(1)

    try:
        content, title, _, description = render_promoted_page(root, page_type, object_id, entry)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # 按对象类型写入正式页面目录。
    subdir = "concepts" if page_type == "concept" else "frameworks"
    page_path = root / "wiki" / subdir / f"{object_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(str(root))
    try:
        page_path.write_text(content, encoding="utf-8")
    finally:
        release_lock(lock)

    rel_page = page_path.relative_to(root).as_posix()
    update_values = {"status": "active", "page": rel_page}
    update_registry_row(root, page_type, object_id, update_values)
    page_registry = auto_page_register(root, object_id, title, page_type, rel_page)
    changelog_path = append_changelog_change(
        root,
        "promote",
        object_id,
        f"提拔为 {page_type} 页面：{title}",
        object_id,
    )
    append_log(root, "promote", title, [
        f"id: {object_id}",
        f"type: {page_type}",
        f"page: {rel_page}",
    ])
    git_commit(root, f"promote: {object_id} {title}")

    print("✅ Promote completed")
    print(f"  id: {object_id}")
    print(f"  type: {page_type}")
    print(f"  page: {rel_page}")
    print(f"  registry: {registry_path.relative_to(root).as_posix()} status=active")
    print(f"  page-registry: {page_registry.relative_to(root).as_posix()}")
    print(f"  changelog: {changelog_path.relative_to(root).as_posix()}")
    if description:
        print(f"  description: {description}")


def _scan_registry_rows(root, registry_name):
    """读取 registry 行，缺失时返回空列表。"""
    registry_path = Path(root) / "registry" / REGISTRY_FILES[registry_name]
    _, _, rows = read_markdown_table(registry_path)
    return rows


def _scan_content_pages(root):
    """扫描 wiki 页面 frontmatter 和正文链接。"""
    root = Path(root)
    pages = []
    for rel_dir in ["wiki/concepts", "wiki/frameworks", "wiki/pages"]:
        target_dir = root / rel_dir
        if not target_dir.exists():
            continue
        for path in sorted(target_dir.glob("*.md")):
            fm, body = parse_frontmatter(path)
            pages.append({
                "id": fm.get("id") or path.stem,
                "title": fm.get("title") or path.stem,
                "type": fm.get("type") or rel_dir.split("/")[-1].rstrip("s"),
                "domain": str(fm.get("domain") or "未分类") if not isinstance(fm.get("domain"), list) else ", ".join(fm.get("domain", [])) or "未分类",
                "sources": _as_list(fm.get("sources")),
                "related": [link for link in dict.fromkeys(
                    _as_list(fm.get("related")) +
                    _as_list(fm.get("related_concepts")) +
                    extract_related_from_body(body) +
                    re.findall(r"\[\[([^\]|#\]]+)", body)
                ) if not _is_placeholder_link(link)],
                "path": path,
            })
    return pages


def _source_label(source_id, source_rows):
    """把 source_id 显示为可读标签。"""
    for row in source_rows:
        if row.get("source_id") == source_id:
            title = row.get("title") or source_id
            return f"{source_id} ({title})"
    return source_id


def cmd_rebuild_maps(args):
    root = Path(get_root(args))
    if not (root / "index.md").exists():
        print("❌ Wiki not initialized. Run: wiki.py init")
        sys.exit(1)

    maps_dir = root / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    concept_rows = _scan_registry_rows(root, "concept")
    source_rows = _scan_registry_rows(root, "source")
    claim_rows = _scan_registry_rows(root, "claim")
    pages = _scan_content_pages(root)

    # 先以 registry 为主，再用页面 frontmatter 补充/覆盖可展示字段。
    concepts = {}
    for row in concept_rows:
        concept_id = _row_value(row, "concept_id", "id")
        if not concept_id:
            continue
        concepts[concept_id] = {
            "id": concept_id,
            "title": _row_value(row, "canonical_name", "title", "name", default=concept_id),
            "domain": _row_value(row, "domain", default="未分类"),
            "description": _row_value(row, "one_line_def", "definition", "description"),
            "sources": [],
            "related": [],
        }

    for page in pages:
        if page["type"] != "concept":
            continue
        concept = concepts.setdefault(page["id"], {
            "id": page["id"],
            "title": page["title"],
            "domain": page["domain"],
            "description": "",
            "sources": [],
            "related": [],
        })
        concept["title"] = page["title"] or concept["title"]
        concept["domain"] = page["domain"] or concept["domain"]
        concept["sources"].extend(page["sources"])
        concept["related"].extend(page["related"])

    # 从 claim registry 反推概念来源和相关项。
    for row in claim_rows:
        related_field = " ".join([
            _row_value(row, "related_concepts"),
            _row_value(row, "target_page"),
            _row_value(row, "claim"),
        ])
        source_id = _row_value(row, "source")
        for concept in concepts.values():
            if concept["id"] in related_field or concept["title"] in related_field:
                if source_id:
                    concept["sources"].append(source_id)
                for related in _as_list(_row_value(row, "related_concepts")):
                    if related and related not in (concept["id"], concept["title"]):
                        concept["related"].append(related)

    domain_groups = {}
    for concept in concepts.values():
        domain_groups.setdefault(concept["domain"] or "未分类", []).append(concept)

    domain_lines = ["# Domain Map (Generated)\n\n"]
    for domain in sorted(domain_groups):
        domain_lines.append(f"## {domain}\n")
        for concept in sorted(domain_groups[domain], key=lambda c: c["title"]):
            desc = concept["description"] or "暂无描述"
            domain_lines.append(f"- [[{concept['title']}]] — {desc}\n")
        domain_lines.append("\n")

    concept_lines = ["# Concept Map (Generated)\n\n"]
    for concept in sorted(concepts.values(), key=lambda c: c["title"]):
        sources = list(dict.fromkeys([s for s in concept["sources"] if s]))
        related = list(dict.fromkeys([r for r in concept["related"] if r and r != concept["title"]]))
        source_text = ", ".join(_source_label(s, source_rows) for s in sources) if sources else "none"
        related_text = ", ".join(f"[[{r}]]" for r in related) if related else "none"
        concept_lines.append(f"## {concept['title']}\n")
        concept_lines.append(f"- sources: {source_text}\n")
        concept_lines.append(f"- related: {related_text}\n\n")

    domain_map = maps_dir / "domain-map.generated.md"
    concept_map = maps_dir / "concept-map.generated.md"
    domain_map.write_text("".join(domain_lines), encoding="utf-8")
    concept_map.write_text("".join(concept_lines), encoding="utf-8")

    print("✅ Maps rebuilt")
    print(f"  domain-map: {domain_map.relative_to(root).as_posix()} ({len(domain_groups)} domains)")
    print(f"  concept-map: {concept_map.relative_to(root).as_posix()} ({len(concepts)} concepts)")
    print(f"  scanned registries: concepts={len(concept_rows)}, sources={len(source_rows)}, claims={len(claim_rows)}")
    print(f"  scanned pages: {len(pages)}")

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

    # update-raw
    p_update_raw = sub.add_parser('update-raw', help='回填 URL 抓取内容')
    p_update_raw.add_argument('raw_path', help='raw 文件相对路径')
    p_update_raw.add_argument('--content', required=True, help='内容文件路径或直接文本')
    p_update_raw.add_argument('--path', default=None)

    # compile
    p_compile = sub.add_parser('compile', help='编译资料并登记 source-note')
    p_compile.add_argument('source', help='文件路径、URL 或直接文本')
    p_compile.add_argument('--level', choices=['L0', 'L1', 'L2', 'L3'], default='L2')
    p_compile.add_argument('--path', default=None)

    # promote
    p_promote = sub.add_parser('promote', help='将 registry 条目提拔为正式页面')
    p_promote.add_argument('id', help='concept/framework ID')
    p_promote.add_argument('--type', choices=['concept', 'framework'], default=None)
    p_promote.add_argument('--path', default=None)

    # rebuild-maps
    p_maps = sub.add_parser('rebuild-maps', help='重建 generated maps')
    p_maps.add_argument('--path', default=None)

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

    # new-id
    p_new_id = sub.add_parser('new-id', help='生成 MVP 对象 ID')
    p_new_id.add_argument('type', choices=['source', 'concept', 'framework', 'claim'])
    p_new_id.add_argument('--path', default=None)

    # registry
    p_registry = sub.add_parser('registry', help='读取或追加 registry')
    p_registry.add_argument('action', choices=['list', 'add'])
    p_registry.add_argument('name', choices=['concept', 'framework', 'claim', 'source', 'page'])
    p_registry.add_argument('--entry', default='')
    p_registry.add_argument('--path', default=None)

    # changelog
    p_changelog = sub.add_parser('changelog', help='追加 changelog 条目')
    p_changelog.add_argument('action', choices=['add', 'pending'])
    p_changelog.add_argument('--change-type', required=True)
    p_changelog.add_argument('--object', required=True)
    p_changelog.add_argument('--summary', required=True)
    p_changelog.add_argument('--path', default=None)

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
    elif args.command == 'update-raw':
        cmd_update_raw(args)
    elif args.command == 'compile':
        cmd_compile(args)
    elif args.command == 'promote':
        cmd_promote(args)
    elif args.command == 'rebuild-maps':
        cmd_rebuild_maps(args)
    elif args.command == 'query':
        cmd_query(args)
    elif args.command == 'lint':
        cmd_lint(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'new-id':
        cmd_new_id(args)
    elif args.command == 'registry':
        cmd_registry(args)
    elif args.command == 'changelog':
        cmd_changelog(args)
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
