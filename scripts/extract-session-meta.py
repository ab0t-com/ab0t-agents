#!/usr/bin/env python3
"""
Extract all available metadata from Claude session files.
Shows what data is available for summaries.
"""

import os
import sys
import json
from pathlib import Path

def extract_session_metadata(jsonl_path):
    """Extract all useful metadata from a session file."""
    meta = {
        'file': os.path.basename(jsonl_path)[:8],
        'slug': None,
        'gitBranch': None,
        'summaries': [],
        'first_user_msg': None,
        'user_count': 0,
        'assistant_count': 0,
        'snapshot_count': 0,
        'cwd': None,
    }

    try:
        with open(jsonl_path, 'r') as f:
            for line in f:
                try:
                    d = json.loads(line)
                    record_type = d.get('type')

                    # Extract slug
                    if 'slug' in d and not meta['slug']:
                        meta['slug'] = d['slug']

                    # Extract git branch
                    if 'gitBranch' in d and d['gitBranch'] and not meta['gitBranch']:
                        meta['gitBranch'] = d['gitBranch']

                    # Extract cwd
                    if 'cwd' in d and not meta['cwd']:
                        meta['cwd'] = d['cwd']

                    # Count types
                    if record_type == 'user':
                        meta['user_count'] += 1
                        if not meta['first_user_msg']:
                            content = d.get('message', {}).get('content', '')
                            if isinstance(content, str):
                                meta['first_user_msg'] = content[:80]
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        meta['first_user_msg'] = item.get('text', '')[:80]
                                        break
                    elif record_type == 'assistant':
                        meta['assistant_count'] += 1
                    elif record_type == 'file-history-snapshot':
                        meta['snapshot_count'] += 1
                    elif record_type == 'summary':
                        summary = d.get('summary', '').strip()
                        if summary:
                            meta['summaries'].append(summary)

                except json.JSONDecodeError:
                    pass
    except Exception as e:
        meta['error'] = str(e)

    return meta


def main():
    if len(sys.argv) < 2:
        projects_dir = os.path.expanduser('~/.claude/projects')
    else:
        projects_dir = sys.argv[1]

    # Process each project
    for project_dir in sorted(Path(projects_dir).iterdir()):
        if not project_dir.is_dir():
            continue

        print(f"\n{'='*60}")
        print(f"Project: {project_dir.name}")
        print('='*60)

        for jsonl_file in sorted(project_dir.glob('*.jsonl')):
            meta = extract_session_metadata(jsonl_file)

            # Determine best summary
            best_summary = None
            if meta['summaries']:
                best_summary = meta['summaries'][-1][:60]
            elif meta['first_user_msg']:
                best_summary = meta['first_user_msg'][:60]

            # Status indicator
            if meta['user_count'] > 0:
                status = '✓'
            elif meta['snapshot_count'] > 0:
                status = '⚠'
            else:
                status = '✗'

            print(f"\n{status} {meta['file']}")
            print(f"  users={meta['user_count']}, assist={meta['assistant_count']}, snap={meta['snapshot_count']}")
            if meta['slug']:
                print(f"  slug: {meta['slug']}")
            if meta['gitBranch']:
                print(f"  branch: {meta['gitBranch']}")
            if best_summary:
                print(f"  summary: \"{best_summary}...\"")
            elif not meta['user_count'] and not meta['summaries']:
                print(f"  summary: [no conversation data]")


if __name__ == '__main__':
    main()
