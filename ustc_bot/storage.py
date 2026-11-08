"""Bound local runtime data without deleting credentials or browser sessions."""
import json
import logging
import os
import tempfile
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG = logging.getLogger('ustc')
DEFAULTS = {'log_max_mb': 2, 'log_backups': 2, 'history_max_records': 1000,
            'history_keep_days': 180, 'clear_browser_cache': True}


def storage_settings(config):
    settings = config.get('storage', {})
    if not isinstance(settings, dict) or set(settings) - set(DEFAULTS):
        raise ValueError('storage 包含不支持的设置或不是 JSON 对象')
    result = {**DEFAULTS, **settings}
    for key in ('log_max_mb', 'log_backups', 'history_max_records', 'history_keep_days'):
        if type(result[key]) is not int or result[key] < 1:
            raise ValueError(f'storage.{key} 必须是正整数')
    if type(result['clear_browser_cache']) is not bool:
        raise ValueError('storage.clear_browser_cache 必须是 true 或 false')
    return result


def trim_history(path, max_records, keep_days):
    path = Path(path)
    if not path.exists() or path.is_symlink():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    kept = deque(maxlen=max_records)
    original_count = 0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            original_count += 1
            try:
                record = json.loads(line)
                stamp = datetime.fromisoformat(record.get('核验时间') or record['选课时间'])
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone(timedelta(hours=8)))
                if stamp < cutoff:
                    continue
            except (ValueError, KeyError, TypeError, AttributeError):
                pass  # Preserve unrecognized records within the count limit.
            kept.append(line if line.endswith('\n') else line + '\n')
    if original_count == len(kept):
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.history-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.writelines(kept)
        os.replace(temporary, path)
        LOG.info('选课日志清理：保留 %s 条，移除 %s 条过期或超限记录', len(kept), original_count - len(kept))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def cleanup_round(root, config, context=None, completed=False):
    settings = storage_settings(config)
    try:
        trim_history(Path(root) / '选课日志.jsonl', settings['history_max_records'], settings['history_keep_days'])
        diagnostic = Path(root) / 'grid_structure.json'
        if completed and diagnostic.exists() and not diagnostic.is_symlink():
            diagnostic.unlink()
    except OSError:
        LOG.warning('本轮本地文件清理未完成，下轮重试')
    if context is not None and settings['clear_browser_cache'] and context.pages:
        session = None
        try:
            session = context.new_cdp_session(context.pages[0])
            session.send('Network.clearBrowserCache')
        except Exception:
            LOG.debug('浏览器缓存清理不可用，本轮跳过', exc_info=True)
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass
