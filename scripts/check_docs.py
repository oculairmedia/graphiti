#!/usr/bin/env python3
"""
Check documentation health: broken links, stale files, coverage.

Usage:
    python3 scripts/check_docs.py              # Full check
    python3 scripts/check_docs.py --links      # Check links only
    python3 scripts/check_docs.py --stale      # Check stale docs only
    python3 scripts/check_docs.py --coverage   # Check code coverage
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple


class DocIssue(NamedTuple):
    file: str
    line: int
    issue: str
    severity: str  # "error" or "warning"


def find_docs(base_path: Path) -> list[Path]:
    """Find all markdown files in docs/."""
    docs = []
    docs_dir = base_path / 'docs'
    if docs_dir.exists():
        for md_file in docs_dir.rglob('*.md'):
            # Skip bookstack mirror
            if 'bookstack' not in str(md_file):
                docs.append(md_file)
    return docs


def check_broken_links(base_path: Path, docs: list[Path]) -> list[DocIssue]:
    """Check for broken internal links in documentation."""
    issues = []
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+\.md)\)')

    for doc in docs:
        content = doc.read_text()
        doc_dir = doc.parent

        for line_num, line in enumerate(content.split('\n'), 1):
            for match in link_pattern.finditer(line):
                link_text, link_target = match.groups()

                # Resolve relative path
                if link_target.startswith('http'):
                    continue  # Skip external links

                # Skip regex patterns (like .*\.md in grep commands)
                if '.*' in link_target or '.+' in link_target:
                    continue

                target_path = (doc_dir / link_target).resolve()

                if not target_path.exists():
                    issues.append(
                        DocIssue(
                            file=str(doc.relative_to(base_path)),
                            line=line_num,
                            issue=f"Broken link to '{link_target}'",
                            severity='error',
                        )
                    )

    return issues


def check_stale_docs(base_path: Path, docs: list[Path], days: int = 90) -> list[DocIssue]:
    """Find docs not updated in specified days."""
    issues = []
    cutoff = datetime.now() - timedelta(days=days)

    for doc in docs:
        # Check git last modified if available
        import subprocess

        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%ct', str(doc)],
                capture_output=True,
                text=True,
                cwd=base_path,
            )
            if result.returncode == 0 and result.stdout.strip():
                mtime = datetime.fromtimestamp(int(result.stdout.strip()))
            else:
                # Fall back to file mtime
                mtime = datetime.fromtimestamp(doc.stat().st_mtime)
        except:
            mtime = datetime.fromtimestamp(doc.stat().st_mtime)

        if mtime < cutoff:
            days_old = (datetime.now() - mtime).days
            issues.append(
                DocIssue(
                    file=str(doc.relative_to(base_path)),
                    line=0,
                    issue=f'Not updated in {days_old} days (since {mtime.date()})',
                    severity='warning',
                )
            )

    return issues


def check_doc_coverage(base_path: Path, docs: list[Path]) -> list[DocIssue]:
    """Check if key code areas have corresponding docs."""
    issues = []

    # Map of code patterns to expected docs
    coverage_map = {
        'graphiti_core/prompts/extract_nodes.py': 'docs/how-to/add-episode.md',
        'graphiti_core/prompts/extract_edges.py': 'docs/how-to/add-episode.md',
        'graphiti_core/search/search.py': 'docs/how-to/search-graph.md',
        'server/': 'docs/reference/api-reference.md',
        'mcp_server/': 'docs/how-to/mcp-tools.md',
    }

    # Check if expected docs exist
    for code_pattern, expected_doc in coverage_map.items():
        doc_path = base_path / expected_doc
        if not doc_path.exists():
            issues.append(
                DocIssue(
                    file=expected_doc,
                    line=0,
                    issue=f'Expected doc for {code_pattern} not found',
                    severity='warning',
                )
            )

    return issues


def check_index_coverage(base_path: Path, docs: list[Path]) -> list[DocIssue]:
    issues = []

    official_dirs = {
        str(base_path / 'docs' / 'how-to'),
        str(base_path / 'docs' / 'reference'),
        str(base_path / 'docs' / 'explanation'),
        str(base_path / 'docs' / 'tutorials'),
    }
    official_root_docs = {
        'INDEX.md',
        'gotchas.md',
        'MAINTENANCE.md',
    }

    index_files = [
        base_path / 'docs' / 'INDEX.md',
        base_path / 'docs' / 'how-to' / 'INDEX.md',
        base_path / 'docs' / 'reference' / 'INDEX.md',
        base_path / 'docs' / 'explanation' / 'INDEX.md',
        base_path / 'docs' / 'tutorials' / 'INDEX.md',
    ]

    for index_file in index_files:
        if not index_file.exists():
            continue

        index_content = index_file.read_text()
        index_dir = index_file.parent

        # Check docs in this directory are mentioned in index
        for doc in docs:
            if doc.parent == index_dir and doc.name != 'INDEX.md':
                is_official = False
                doc_parent = str(doc.parent)
                if doc_parent in official_dirs:
                    is_official = True
                elif doc_parent == str(base_path / 'docs') and doc.name in official_root_docs:
                    is_official = True

                if not is_official:
                    continue

                if doc.stem not in index_content:
                    issues.append(
                        DocIssue(
                            file=str(doc.relative_to(base_path)),
                            line=0,
                            issue=f'Not referenced in {index_file.relative_to(base_path)}',
                            severity='warning',
                        )
                    )

    return issues


def check_known_stale_patterns(base_path: Path) -> list[DocIssue]:
    issues = []

    monitored_dirs = [
        base_path / 'docs' / 'how-to',
        base_path / 'docs' / 'reference',
        base_path / 'docs' / 'explanation',
        base_path / 'docs' / 'tutorials',
    ]
    monitored_files = [
        base_path / 'docs' / 'INDEX.md',
        base_path / 'docs' / 'MAINTENANCE.md',
    ]

    stale_patterns = [
        (r'\bGET /health\b', "Use 'GET /healthcheck' for Graph API health endpoint"),
        (r'\bserver/main\.py\b', "Use 'server/graph_service/main.py'"),
        (r'\bserver/routes/\b', "Use 'server/graph_service/routers/'"),
        (
            r'\bgraphiti_core/extract_nodes\.py\b',
            "Use 'graphiti_core/prompts/extract_nodes.py'",
        ),
        (
            r'\bgraphiti_core/extract_edges\.py\b',
            "Use 'graphiti_core/prompts/extract_edges.py'",
        ),
        (
            r'\bgraphiti_core/node_operations\.py\b',
            "Use 'graphiti_core/utils/maintenance/node_operations.py'",
        ),
        (r'\bgraphiti_core/search\.py\b', "Use 'graphiti_core/search/search.py'"),
        (r'\bSearchRecipy\b', 'Typo: use SearchConfig recipes from search_config_recipes.py'),
        (r'\bPort 8001\b', 'MCP stack default is port 3010 (MCP_PORT)'),
        (r'\b6389\b', 'FalkorDB stack default port is 6379'),
    ]

    files_to_check = []
    for directory in monitored_dirs:
        if directory.exists():
            files_to_check.extend(directory.rglob('*.md'))

    for file_path in monitored_files:
        if file_path.exists():
            files_to_check.append(file_path)

    for file_path in files_to_check:
        rel_file = str(file_path.relative_to(base_path))
        content = file_path.read_text()
        for line_num, line in enumerate(content.split('\n'), 1):
            for pattern, guidance in stale_patterns:
                if re.search(pattern, line):
                    issues.append(
                        DocIssue(
                            file=rel_file,
                            line=line_num,
                            issue=f'Known stale reference: {guidance}',
                            severity='warning',
                        )
                    )

    return issues


def main():
    parser = argparse.ArgumentParser(description='Check documentation health')
    parser.add_argument('--links', action='store_true', help='Check broken links only')
    parser.add_argument('--stale', action='store_true', help='Check stale docs only')
    parser.add_argument('--coverage', action='store_true', help='Check doc coverage only')
    parser.add_argument(
        '--consistency',
        action='store_true',
        help='Check known stale path/port/endpoint references',
    )
    parser.add_argument('--days', type=int, default=90, help='Days threshold for stale docs')
    args = parser.parse_args()

    base_path = Path(__file__).parent.parent
    docs = find_docs(base_path)

    all_issues = []

    if not any([args.links, args.stale, args.coverage, args.consistency]):
        # Run all checks
        all_issues.extend(check_broken_links(base_path, docs))
        all_issues.extend(check_stale_docs(base_path, docs, args.days))
        all_issues.extend(check_doc_coverage(base_path, docs))
        all_issues.extend(check_index_coverage(base_path, docs))
        all_issues.extend(check_known_stale_patterns(base_path))
    else:
        if args.links:
            all_issues.extend(check_broken_links(base_path, docs))
        if args.stale:
            all_issues.extend(check_stale_docs(base_path, docs, args.days))
        if args.coverage:
            all_issues.extend(check_doc_coverage(base_path, docs))
            all_issues.extend(check_index_coverage(base_path, docs))
        if args.consistency:
            all_issues.extend(check_known_stale_patterns(base_path))

    # Report
    errors = [i for i in all_issues if i.severity == 'error']
    warnings = [i for i in all_issues if i.severity == 'warning']

    if errors:
        print(f'\n❌ Errors ({len(errors)}):')
        for issue in errors:
            if issue.line:
                print(f'   {issue.file}:{issue.line}: {issue.issue}')
            else:
                print(f'   {issue.file}: {issue.issue}')

    if warnings:
        print(f'\n⚠️  Warnings ({len(warnings)}):')
        for issue in warnings:
            if issue.line:
                print(f'   {issue.file}:{issue.line}: {issue.issue}')
            else:
                print(f'   {issue.file}: {issue.issue}')

    if not all_issues:
        print('✅ Documentation health check passed!')
        return 0

    print(f'\n📊 Summary: {len(errors)} errors, {len(warnings)} warnings')
    print(f'   Total docs checked: {len(docs)}')

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
