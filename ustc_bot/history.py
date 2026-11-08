"""Append verified enrollment history and display non-blocking Windows popups."""
import json
import logging
import queue
import sys
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG = logging.getLogger('ustc')
POPUPS = queue.Queue(maxsize=20)
_worker = None


def append_success(path, title, location, report_time, selected_at):
    record = {'报告名称': title, '报告时间': report_time, '地点': location,
              '选课时间': selected_at,
              '核验时间': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    LOG.info('选课成功，已追加选课日志：%s | 报告时间：%s | 地点：%s | 选课时间：%s',
             title, report_time, location, selected_at, extra={'console': True})
    return record


def _popup_worker():
    import ctypes
    while True:
        record = POPUPS.get()
        try:
            message = '\n'.join(f'{key}：{record[key]}' for key in ('报告名称', '报告时间', '地点', '选课时间'))
            ctypes.windll.user32.MessageBoxW(None, message, '学术报告选课成功', 0x00040000 | 0x00010000 | 0x40)
        except Exception:
            LOG.exception('成功提示弹窗不可用，请查看选课日志')
        finally:
            POPUPS.task_done()


def show_success_popup(record):
    global _worker
    if sys.platform != 'win32':
        LOG.info('屏幕弹窗仅在 Windows 支持，选课日志已保存')
        return
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_popup_worker, daemon=True)
        _worker.start()
    try:
        POPUPS.put_nowait(record)
    except queue.Full:
        # The durable history was written before this call. Do not block the
        # scanner or accumulate notifications when a popup is left unattended.
        LOG.warning('成功提示队列已满，本条仅保留选课日志；关闭已有弹窗可继续显示后续提示')
