"""USTC academic report enrollment assistant (browser UI only).

Browser-based login and enrollment. Verification challenges are handled manually.
"""
import json
import logging
import re
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from .filters import validate_filters, matches_report
from .history import append_success, show_success_popup
from .config import load_credentials, load_settings
from .storage import storage_settings, cleanup_round
from .logging_setup import configure_logging
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

ROOT = Path(__file__).resolve().parent.parent
SHANGHAI = timezone(timedelta(hours=8))
CFG = {}
FILTERS = validate_filters({})
LOG = logging.getLogger('ustc')
STOP_EVENT = threading.Event()
REPORT_DETAILS = {}


def report_key(button, title, location):
    return button.get_attribute('data-bgbm') or (title, location)


def record_success(title, location, key=None):
    details = REPORT_DETAILS.get(key, REPORT_DETAILS.get((title, location), {}))
    record = append_success(ROOT / '选课日志.jsonl', title, location,
                            details.get('report_time', '未提供'),
                            details.get('selected_at', datetime.now(SHANGHAI).isoformat(timespec='seconds')))
    show_success_popup(record)


class StopRequested(KeyboardInterrupt):
    pass


def check_stop():
    if STOP_EVENT.is_set():
        raise StopRequested()


def listen_for_enter():
    try:
        input()
    except (EOFError, OSError):
        LOG.warning('终端输入不可用，可用 Ctrl+C 停止')
        return
    STOP_EVENT.set()
    LOG.info('收到 Enter，正在停止检测，不再提交新的选课', extra={'console': True})


def wait_for_report_page(context):
    LOG.info('正在进入报告页面；若菜单未自动展开，请在浏览器打开【学术报告选课 → 未选报告】，打开后自动开始。Enter 可停止。', extra={'console': True})
    while context.pages:
        check_stop()
        try:
            return open_report_page(context)
        except (RuntimeError, PWError):
            STOP_EVENT.wait(1)
    raise RuntimeError('浏览器已关闭')


def trusted_auth_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in
            {'id.ustc.edu.cn', 'passport.ustc.edu.cn'} and parsed.port in (None, 443))


def portal_ready(page):
    parsed = urlsplit(page.url)
    if parsed.scheme != 'https' or parsed.hostname != 'yjs1.ustc.edu.cn':
        return False
    for frame in page.frames:
        frame_url = urlsplit(frame.url)
        if frame_url.hostname != 'yjs1.ustc.edu.cn':
            continue
        for label in ('培养', '学术报告选课', '我的培养方案'):
            if visible_first(frame.get_by_text(re.compile(r'^\s*' + label + r'\s*$'))) is not None:
                return True
    return False


def has_manual_verification(page):
    if not trusted_auth_url(page.url):
        return False
    for frame in page.frames:
        if not trusted_auth_url(frame.url):
            continue
        for locator in (
                frame.get_by_placeholder(re.compile(r'验证码|校验码|动态码')),
                frame.locator('input[name*="captcha" i], input[id*="captcha" i], '
                              'input[name*="verifycode" i], input[id*="verifycode" i]'),
                frame.get_by_text(re.compile(r'请完成.*验证|拖动.*滑块|扫码确认'))):
            if visible_first(locator) is not None:
                return True
    return False


def visible_first(locator):
    for item in locator.all():
        if item.is_visible():
            return item
    return None


def login_fields(page):
    """Find visible fields even when a hidden alternative form comes first."""
    if not trusted_auth_url(page.url):
        return None
    for frame in page.frames:
        if not trusted_auth_url(frame.url):
            continue
        username = visible_first(frame.get_by_placeholder(re.compile(r'学工号|学号|GID|用户名', re.I)))
        if username is None:
            username = visible_first(frame.locator(
                'input[name="username"], input#username, input[autocomplete="username"], '
                'input[name="user"], input[name="userName"]'))
        password = visible_first(frame.locator('input[type="password"]'))
        if username is not None and password is not None:
            return frame, username, password
    return None


def ensure_login(context):
    """Submit credentials once, only to USTC authentication origins.

    Do not log credentials, page contents or raw Playwright errors during login.
    A retained session can succeed without credentials configured.
    """
    auth = CFG.get('login', {})
    deadline = time.monotonic() + max(15, int(auth.get('timeout_seconds', 120)))
    submitted = False
    clicked = False
    stage = '等待认证入口或已有登录状态'
    announced = None
    manual_wait_started = False
    last_wait_notice = 0
    try:
        while time.monotonic() < deadline:
            check_stop()
            if stage != announced:
                LOG.info('登录进度：%s', stage)
                announced = stage
            for page in list(context.pages):
                if page.is_closed():
                    continue
                try:
                    ready = portal_ready(page)
                except PWError:
                    # Redirects can destroy the old document during any lookup.
                    continue
                if ready:
                    LOG.info('已确认进入研究生综合服务系统')
                    return page
                if submitted:
                    try:
                        manual_required = has_manual_verification(page)
                    except PWError:
                        continue
                    if manual_required and not manual_wait_started:
                        manual_wait_started = True
                        deadline = max(deadline, time.monotonic() + max(30, int(auth.get('manual_timeout_seconds', 300))))
                        stage = '等待手动验证并提交登录'
                        LOG.info('检测到验证步骤：请在浏览器填写验证码，并点击“立即登录/确认”；仅填写验证码可能不会提交。程序不会替你完成验证。', extra={'console': True})
                    now = time.monotonic()
                    if now - last_wait_notice >= 15:
                        last_wait_notice = now
                        current = urlsplit(page.url)
                        LOG.info('仍在等待登录跳转（当前站点：%s）；若验证码已填，请检查是否还需点击登录或确认', current.hostname)
                    continue
                parsed = urlsplit(page.url)
                if parsed.scheme == 'https' and parsed.hostname == 'yjs1.ustc.edu.cn' and not clicked:
                    try:
                        entry = page.get_by_text(re.compile(r'^\s*统一身份认证\s*$'))
                        candidate = visible_first(entry)
                        if candidate is not None:
                            candidate.click(timeout=5000)
                            clicked = True
                            stage = '等待统一认证页面加载'
                            LOG.info('已点击统一身份认证，等待登录页')
                    except PWError:
                        continue
                if not trusted_auth_url(page.url):
                    continue
                stage = '等待可见的账号密码输入框'
                try:
                    fields = login_fields(page)
                except PWError:
                    continue
                if fields is None:
                    continue
                frame, username, password = fields
                credentials = load_credentials(ROOT / 'credentials.json')
                student_id = credentials['student_id']
                secret = credentials['password']
                if not trusted_auth_url(page.url) or not trusted_auth_url(frame.url):
                    raise RuntimeError('认证页面地址异常，已停止填写')
                stage = '填写账号'
                username.fill(student_id, timeout=5000)
                if not trusted_auth_url(page.url) or not trusted_auth_url(frame.url):
                    raise RuntimeError('认证页面地址异常，已停止填写')
                stage = '填写密码'
                password.fill(secret, timeout=5000)
                if not trusted_auth_url(page.url) or not trusted_auth_url(frame.url):
                    raise RuntimeError('认证页面地址异常，已停止提交')
                stage = '点击登录按钮'
                submit = visible_first(frame.get_by_role('button', name=re.compile(r'^\s*(立即登录|登\s*录|Login)\s*$', re.I)))
                if submit is None:
                    submit = visible_first(frame.locator('input[type="submit"]'))
                if submit is None:
                    submit = visible_first(frame.get_by_text('立即登录', exact=True))
                if submit is None:
                    raise RuntimeError('未找到可见的登录按钮')
                # A successful navigation can make click() time out after the
                # request was sent. Do not abandon the login or submit again.
                submitted = True
                try:
                    submit.click(timeout=5000)
                except PWError:
                    LOG.info('登录按钮点击后页面状态发生变化，继续检查登录结果；如未提交请在浏览器手动点击登录')
                stage = '等待登录完成（如有验证码请手动处理）'
                LOG.info('已提交登录一次；若出现验证码，请手动填写，并点击页面登录/确认按钮完成提交')
            time.sleep(0.5)
    except ValueError:
        raise
    except Exception:
        raise RuntimeError('自动登录未完成，停在：' + stage + '；请检查浏览器，未自动重试密码') from None
    raise RuntimeError('等待登录超时，停在：' + stage + '；请检查浏览器或账号配置，未自动重试密码')


def wait_for_manual_login(context):
    """Keep detecting portal readiness after an automatic-login failure."""
    timeout = max(30, int(CFG.get('login', {}).get('manual_timeout_seconds', 300)))
    deadline = time.monotonic() + timeout
    LOG.info('请在浏览器完成登录；接下来 %s 秒内进入系统后将自动继续选课，无需回终端按 Enter', timeout, extra={'console': True})
    while time.monotonic() < deadline:
        check_stop()
        if not context.pages:
            return None
        for page in list(context.pages):
            try:
                if not page.is_closed() and portal_ready(page):
                    LOG.info('已检测到手动登录成功，继续执行选课流程')
                    return page
            except PWError:
                continue
        time.sleep(0.5)
    return None


def notify(message):
    LOG.info('通知: %s', message, extra={'console': True})
    try:
        from plyer import notification
        notification.notify(title='中科大学术报告助手', message=message[:220], timeout=10)
    except Exception:
        LOG.warning('桌面通知不可用，请查看终端和 bot.log')
    try:
        import winsound
        winsound.MessageBeep()
    except ImportError:
        pass


def find_table(page):
    # The platform may render a jqx div grid, not an HTML table.
    for selector in ('[role="grid"]', '.jqx-grid', '.bh-table', 'table'):
        for grid in page.locator(selector).all():
            if not grid.is_visible():
                continue
            headers = grid_headers(grid)
            if any('报告题目' in h for h in headers) and '地点' in headers and '操作' in headers:
                return grid
    return None


def grid_headers(grid):
    for selector in ('[role="columnheader"]', '.jqx-grid-column-header', 'thead th', 'thead td'):
        headers = [re.sub(r'\s+', '', value) for value in grid.locator(selector).all_inner_texts()]
        if any('报告题目' in h for h in headers) and '操作' in headers:
            return headers
    # A table can have a sizing row before its actual header.
    for row in grid.locator('tr').all():
        headers = [re.sub(r'\s+', '', value) for value in row.locator('th,td').all_inner_texts()]
        if any('报告题目' in h for h in headers) and '操作' in headers:
            return headers
    return []


def grid_rows(grid):
    for row_selector, cell_selector in (
            ('[role="row"]', '[role="gridcell"]'),
            ('[id^="row"]', '.jqx-grid-cell'),
            ('tr', 'td')):
        rows = [(row, row.locator(cell_selector)) for row in grid.locator(row_selector).all()]
        rows = [(row, cells) for row, cells in rows if cells.count() and row.is_visible()]
        if rows:
            return rows
    return []


def enrollment_button(grid, original):
    """jqx duplicates frozen columns; click the top, pinned copy of the same report."""
    report_id = original.get_attribute('data-bgbm')
    if report_id and re.fullmatch(r'[A-Za-z0-9_-]+', report_id):
        pinned = grid.locator(f'table[id^="pinnedtable"] a[data-bgbm="{report_id}"]')
        button = visible_first(pinned)
        if button is not None:
            return button
    return original


def parse_rows(page):
    table = find_table(page)
    if table is None:
        raise RuntimeError('未识别报告表格，无法判断是否存在可选报告')
    headers = grid_headers(table)
    location_idx = next((i for i, x in enumerate(headers) if '地点' in x), None)
    title_idx = next((i for i, x in enumerate(headers) if '报告题目' in x), None)
    action_idx = next((i for i, x in enumerate(headers) if '操作' in x), None)
    capacity_idx = next((i for i, x in enumerate(headers) if '容量/已选' in x), None)
    department_idx = next((i for i, x in enumerate(headers) if '院系' in x), None)
    speaker_idx = next((i for i, x in enumerate(headers) if x == '报告人'), None)
    time_idx = next((i for i, x in enumerate(headers) if x == '报告时间'), None)
    if None in (location_idx, title_idx, action_idx, capacity_idx):
        raise RuntimeError('已识别报告网格，但缺少必要表头：' + repr(headers))
    found = []
    rows = grid_rows(table)
    LOG.debug('识别报告网格：表头 %s，数据行 %s', headers, len(rows))
    if not rows and pagination_state(page) and pagination_state(page)[2] > 0:
        raise RuntimeError('网格有记录但未识别数据行，请检查网格结构')
    unique_reports = set()
    for row, cells in rows:
        if cells.count() <= max(location_idx, title_idx, action_idx, capacity_idx):
            continue
        title = cells.nth(title_idx).inner_text().strip()
        location = cells.nth(location_idx).inner_text().strip()
        action = cells.nth(action_idx)
        enroll = action.get_by_text('选课', exact=True)
        capacity = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', cells.nth(capacity_idx).inner_text())
        available = capacity and int(capacity[2]) < int(capacity[1])
        report = {'地点': location, '报告题目': title}
        for field, index in (('院系', department_idx), ('报告人', speaker_idx)):
            if index is not None and index < cells.count():
                report[field] = cells.nth(index).inner_text().strip()
        if title and available and enroll.count() and enroll.first.is_visible() and matches_report(report, FILTERS):
            button = enrollment_button(table, enroll.first)
            report_time = '未提供'
            if time_idx is not None and time_idx < cells.count():
                cell = cells.nth(time_idx)
                report_time = (cell.get_attribute('title') or cell.text_content() or '').strip() or '未提供'
            key = report_key(button, title, location)
            if key in unique_reports:
                continue
            unique_reports.add(key)
            details = REPORT_DETAILS.setdefault(key, {})
            details['report_time'] = report_time
            REPORT_DETAILS[(title, location)] = details
            found.append((title, location, button))
    return found


def verify_selected(page, title):
    tab = page.get_by_text('已选报告', exact=True)
    if tab.count() == 0:
        LOG.warning('找不到已选报告标签，无法核验')
        return False
    tab.first.click()
    page.wait_for_timeout(1200)
    next_page(page, first=True)
    # Search visible selected-report list, potentially paginated.
    for page_index in range(FILTERS['最多遍历页数']):
        table = find_table(page)
        if table is not None and table.get_by_text(title, exact=True).count():
            return True
        if page_index + 1 >= FILTERS['最多遍历页数'] or not next_page(page):
            break
    return False


def pagination_state(page):
    text = page.locator('body').inner_text(timeout=5000)
    match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*总记录数\s*(\d+)', text)
    return tuple(map(int, match.groups())) if match else None


def next_page(page, first=False):
    check_stop()
    """Prefer the numbered jump input; verify both range and table update."""
    before_state = pagination_state(page)
    if before_state:
        start, end, total = before_state
        if (first and start == 1) or (not first and end >= total):
            return False
    before = find_table(page)
    if before is None:
        raise RuntimeError('翻页前未识别到报告表格，不能确认扫描范围')
    signature = before.inner_text()
    jump = visible_first(page.locator(
        '.jqx-grid-pager input, input.jqx-grid-pager-input, [class*="pager"] input[type="text"], '
        '[class*="pager"] input[type="number"]'))
    if jump is None:
        jump = visible_first(page.locator(
            'xpath=//*[text()[contains(., "跳转")]]/ancestor::*[.//input][1]//input'))
    if jump is not None and before_state:
        target = 1 if first else int(jump.input_value()) + 1
        LOG.info('翻页：跳转至第 %s 页（当前记录 %s-%s）', target, start, end)
        jump.fill(str(target))
        jump.press('Enter')
    else:
        label = r'^(首页|第一页|First|«|\|<)$' if first else r'^(下一页|下页|Next|›|>)$'
        el = visible_first(page.get_by_role('button', name=re.compile(label)))
        if el is None:
            selector = ('[title="首页"], [title="第一页"], [aria-label="首页"], '
                        '.jqx-icon-arrow-first, .jqx-icon-arrow-first-small') if first else (
                        '[title="下一页"], [aria-label="下一页"], '
                        '.jqx-icon-arrow-right, .jqx-icon-arrow-right-small')
            el = visible_first(page.locator(selector))
        if el is None:
            raise RuntimeError('未识别到翻页控件，扫描未完成；请提供分页栏的网页元素信息')
        if not el.is_enabled() or el.get_attribute('aria-disabled') == 'true':
            return False
        el.click(timeout=5000)
    for _ in range(40):
        page.wait_for_timeout(250)
        after_state = pagination_state(page)
        after = find_table(page)
        changed = after is not None and after.inner_text() != signature
        range_changed = before_state is None or (after_state is not None and after_state != before_state)
        if changed and range_changed:
            LOG.info('翻页成功：当前记录 %s', after_state)
            return True
    raise RuntimeError('点击翻页后，页码或列表内容没有更新；已停止，避免漏扫')


def monitor(page, attempted=None, results=None):
    REPORT_DETAILS.clear()
    try:
        return _monitor(page, attempted, results)
    finally:
        REPORT_DETAILS.clear()
        cleanup_round(ROOT, CFG)


def _monitor(page, attempted=None, results=None):
    attempted = attempted if attempted is not None else set()
    results = results if results is not None else []
    # Must start on 未选报告 tab, navigated by the user on first launch.
    tab = page.get_by_text('未选报告', exact=True)
    if tab.count() == 0:
        notify('请先登录并打开 培养 → 学术报告选课 页面')
        return
    tab.first.click()
    page.wait_for_timeout(1000)
    # Fetch fresh rows rather than repeatedly inspecting a stale list.
    search = page.get_by_text('搜索', exact=True)
    if search.count() and search.first.is_visible():
        search.first.click()
        page.wait_for_timeout(1000)
    next_page(page, first=True)
    seen = set()
    scan_limit = FILTERS['最多遍历页数']
    for n in range(scan_limit):
        table = find_table(page)
        if table is None:
            structure = page.locator('body').evaluate('''body => ({
                tables: body.querySelectorAll('table').length,
                grids: Array.from(body.querySelectorAll('[role="grid"], .jqx-grid, .bh-table')).map(e => ({
                    tag: e.tagName, role: e.getAttribute('role'), classes: e.className,
                    columnHeaders: e.querySelectorAll('[role="columnheader"]').length,
                    gridCells: e.querySelectorAll('[role="gridcell"]').length,
                    jqxCells: e.querySelectorAll('.jqx-grid-cell').length
                }))
            })''')
            (ROOT / 'grid_structure.json').write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding='utf-8')
            raise RuntimeError('未识别到报告网格，扫描未完成，请提供网页元素结构')
        candidates = parse_rows(page)
        LOG.info('扫描第 %s 页，记录范围 %s，有余量且符合筛选条件 %s 条', n + 1, pagination_state(page), len(candidates))
        for title, location, button in candidates:
            report_key = button.get_attribute('data-bgbm') or (title, location)
            if report_key in attempted or report_key in seen:
                continue
            seen.add(report_key)
            LOG.info('匹配: %s | %s', title, location)
            if CFG['dry_run']:
                continue
            try:
                check_stop()
                attempted.add(report_key)
                REPORT_DETAILS.setdefault(report_key, {})['selected_at'] = datetime.now(SHANGHAI).isoformat(timespec='seconds')
                status = submit_batch_report(page, button)
                if status == 'rejected':
                    results.append(('rejected', title, location))
                    continue
                dialog_text = page.locator('body').inner_text(timeout=5000)
                success_hint = '选课成功' in dialog_text
                confirmed = verify_selected(page, title)
                if confirmed:
                    results.append(('success', title, location))
                    notify('报名成功: ' + title + ' | ' + location)
                    record_success(title, location, report_key)
                    if CFG.get('test_enroll_one', False):
                        return True
                else:
                    notify(('检测到成功提示但未核验' if success_hint else '报名结果未确认') + ': ' + title)
                    raise RuntimeError('无法核验报名结果，请人工检查已选报告后继续')
                tab = page.get_by_text('未选报告', exact=True)
                if tab.count():
                    tab.first.click()
                    page.wait_for_timeout(1000)
                # After a mutation, pagination may change. Rescan from start.
                return True
            except Exception as exc:
                LOG.exception('报名尝试异常: %s', exc)
                notify('报名尝试异常，请检查浏览器: ' + title)
                raise RuntimeError('报名异常，已停止，避免重复提交') from exc
        LOG.info('扫描第 %s 页, 匹配 %s 条', n + 1, len(seen))
        if n + 1 >= scan_limit or not next_page(page):
            break
    LOG.info('本轮完成，符合条件 %d 条（测试模式=%s）', len(seen), CFG['dry_run'])
    return False


def handle_enrollment_dialogs(frame):
    """Handle the platform's actual bh-bhdialog overlay, scoped to its buttons."""
    scopes = [frame]
    owner = getattr(frame, 'page', None)
    if owner is not None and owner is not frame:
        scopes.append(owner)
        scopes.extend(child for child in owner.frames if child is not frame)
    handled = False
    for scope in scopes:
        # bh's outer container can have a zero-sized box while its fixed
        # descendants (modal and buttons) are visibly covering the page.
        for dialog in scope.locator('.bh-bhdialog-container, [role="dialog"], .bh-dialog').all():
            visible_content = visible_first(dialog.locator('button:visible, a:visible, [role="button"]:visible, .bh-modal:visible, .bh-dialog-content:visible'))
            if not dialog.is_visible() and visible_content is None:
                continue
            text = re.sub(r'\s+', '', dialog.inner_text())
            rejected = bool(re.search(
                r'不在可选学生范围|不在可选范围|选课失败|人数已满|名额已满|已满员|不在选课范围|'
                r'不符合选课|不允许选课|选课时间已过|选课已截止', text))
            safe = rejected or ('选课' in text and not any(word in text for word in ('退选', '删除', '验证码')))
            if not safe:
                raise RuntimeError('出现未识别的提示弹窗，停止操作以便人工检查')
            confirm = visible_first(dialog.get_by_role('button', name=re.compile(r'^\s*(确定|确认|关闭)\s*$')))
            if confirm is None:
                confirm = visible_first(dialog.get_by_text(re.compile(r'^\s*(确定|确认|关闭)\s*$')))
            if confirm is None:
                confirm = visible_first(dialog.locator(
                    '[aria-label="关闭"], [aria-label="Close"], [title="关闭"], '
                    '.bh-dialog-close, .bh-bhdialog-close, .bh-close, [class*="close"], [data-dismiss="modal"]'))
            if confirm is None:
                raise RuntimeError('已识别选课提示，但找不到确定或关闭按钮')
            check_stop()
            LOG.info('已识别%s弹窗，正在点击确定/关闭', '不可选报告' if rejected else '选课')
            confirm.click(timeout=5000)
            confirm.wait_for(state='hidden', timeout=5000)
            if rejected:
                LOG.info('已关闭不可选报告提示，继续处理下一场')
                return 'rejected'
            handled = True
    return 'handled' if handled else 'none'


def submit_batch_report(frame, button):
    check_stop()
    button.click(timeout=5000)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        check_stop()
        status = handle_enrollment_dialogs(frame)
        if status == 'rejected':
            return status
        frame.wait_for_timeout(250)
    return 'pending'


def verify_batch(frame, pending):
    """Switch tabs once and check all submitted reports in a single traversal."""
    LOG.info('开始统一核验已选报告，最多 %s 页', FILTERS['最多遍历页数'])
    handle_enrollment_dialogs(frame)
    frame.get_by_text('已选报告', exact=True).first.click(timeout=5000)
    frame.wait_for_timeout(1200)
    next_page(frame, first=True)
    remaining = list(pending)
    confirmed = []
    for page_index in range(FILTERS['最多遍历页数']):
        check_stop()
        grid = find_table(frame)
        if grid is None:
            raise RuntimeError('无法识别已选报告列表')
        for item in list(remaining):
            title, location = item
            if grid.get_by_text(title, exact=True).count():
                confirmed.append(('success', title, location))
                remaining.remove(item)
        if not remaining or page_index + 1 >= FILTERS['最多遍历页数'] or not next_page(frame):
            break
    return confirmed


def batch_enrollment(context, interactive=True):
    REPORT_DETAILS.clear()
    summary = None
    try:
        summary = _batch_enrollment(context, interactive)
        return summary
    finally:
        # Includes rejected reports, errors and Enter/Ctrl+C interruption.
        REPORT_DETAILS.clear()
        cleanup_round(ROOT, CFG, context, completed=bool(summary and summary.get('scan_completed') and not summary.get('unconfirmed_count', 0)))


def _batch_enrollment(context, interactive=True):
    attempted, results, pending = set(), [], []
    frame = None
    completed = False
    try:
        try:
            frame = open_report_page(context)
        except (RuntimeError, PWError):
            frame = wait_for_report_page(context)
        LOG.info('批量选课：按 config.json 的 filters 筛选，逐页提交，最后统一核验')
        frame.get_by_text('未选报告', exact=True).first.click()
        frame.wait_for_timeout(1000)
        search = visible_first(frame.get_by_text('搜索', exact=True))
        if search is not None:
            search.click(timeout=5000)
            frame.wait_for_timeout(1000)
        next_page(frame, first=True)
        scan_limit = FILTERS['最多遍历页数']
        LOG.info('本次最多扫描未选报告前 %s 页', scan_limit)
        for page_number in range(1, scan_limit + 1):
            check_stop()
            LOG.info('批量处理第 %s 页，记录范围 %s', page_number, pagination_state(frame))
            while True:
                check_stop()
                # Reacquire rows after every submission, staying on this page.
                candidates = parse_rows(frame)
                candidate = None
                for title, location, button in candidates:
                    key = button.get_attribute('data-bgbm') or (title, location)
                    if key not in attempted:
                        candidate = (key, title, location, button)
                        break
                if candidate is None:
                    break
                key, title, location, button = candidate
                attempted.add(key)
                if CFG.get('dry_run', False):
                    LOG.info('仅监测，不提交：%s | %s', title, location)
                    continue
                pending.append((title, location))
                REPORT_DETAILS.setdefault(key, {})['selected_at'] = datetime.now(SHANGHAI).isoformat(timespec='seconds')
                LOG.info('提交选课，待最终核验：%s | %s', title, location)
                status = submit_batch_report(frame, button)
                if status == 'rejected':
                    pending.remove((title, location))
                    results.append(('rejected', title, location))
                    LOG.info('明确拒绝，跳过：%s', title)
                frame.wait_for_timeout(1000)
            if page_number == scan_limit:
                LOG.info('已处理配置指定的前 %s 页，停止翻页', scan_limit)
                break
            if not next_page(frame):
                break
        LOG.info('未选报告逐页处理结束，准备统一核验')
        completed = True
    except Exception:
        LOG.exception('批量选课暂停：结果或页面状态无法确认，不自动重试')
        notify('批量选课暂停，请检查浏览器与日志')
    finally:
        if frame is not None and pending and not STOP_EVENT.is_set():
            try:
                results.extend(verify_batch(frame, pending))
            except Exception:
                completed = False
                LOG.exception('统一核验未完成，请在已选报告中人工检查')
        successful = [item for item in results if item[0] == 'success']
        rejected = [item for item in results if item[0] == 'rejected']
        summary = {'success': successful, 'rejected': rejected,
                   'attempted_count': len(attempted),
                   'unconfirmed_count': len(pending) - len(successful),
                   'scan_completed': completed,
                   'finished_at': datetime.now(SHANGHAI).isoformat()}
        (ROOT / 'enrollment_results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        for _, title, location in successful:
            record_success(title, location)
        message = '本次批量选课：成功 %s 场，明确拒绝 %s 场，未确认 %s 场' % (
            len(successful), len(rejected), summary['unconfirmed_count'])
        if interactive or successful or summary['unconfirmed_count']:
            notify(message)
        else:
            LOG.info(message, extra={'console': True})
    return summary


def scheduled_monitor(context):
    interval = CFG.get('interval_seconds', 600)
    if type(interval) is not int or interval < 30:
        raise ValueError('config.json 的 interval_seconds 必须是大于等于 30 的整数')
    LOG.info('定时监测启动：立即扫描，此后每轮结束等待 %s 秒；按 Enter 停止', interval)
    while True:
        check_stop()
        summary = batch_enrollment(context, interactive=False)
        if not summary['scan_completed'] or summary['unconfirmed_count']:
            notify('定时监测已停止：本轮未完整完成或有未确认报名，请人工检查后重新启动')
            return
        del summary
        next_run = datetime.now(SHANGHAI) + timedelta(seconds=interval)
        LOG.info('本轮结束，下次扫描时间：%s', next_run.strftime('%Y-%m-%d %H:%M:%S %z'), extra={'console': True})
        deadline = time.monotonic() + interval
        while time.monotonic() < deadline:
            check_stop()
            if not context.pages:
                LOG.info('浏览器已关闭，停止定时监测')
                return
            STOP_EVENT.wait(min(1, max(0, deadline - time.monotonic())))


def report_frame(context):
    for page in context.pages:
        for frame in page.frames:
            tab = frame.get_by_text('未选报告', exact=True)
            if tab.count() and tab.first.is_visible():
                return frame
    raise RuntimeError('未找到学术报告选课页面，请检查登录状态和已打开的标签页')


def open_report_page(context):
    """Try the menu path; retain a manual fallback for an unknown menu DOM."""
    for label in ('培养', '学术报告管理', '学术报告选课'):
        check_stop()
        try:
            return report_frame(context)
        except RuntimeError:
            pass
        clicked = False
        for page in context.pages:
            for frame in page.frames:
                candidate = visible_first(frame.get_by_text(label, exact=True))
                if candidate is not None:
                    candidate.click(timeout=5000)
                    page.wait_for_timeout(1000)
                    clicked = True
                    break
            if clicked:
                break
    return report_frame(context)


def test_enrollment(context):
    """One scan, at most one submission, and no automatic retries."""
    try:
        try:
            frame = open_report_page(context)
        except (RuntimeError, PWError):
            frame = wait_for_report_page(context)
        LOG.info('单场试选：按 config.json 的 filters 筛选，最多提交一场')
        if not monitor(frame):
            notify('本次扫描没有选课成功，请查看日志中的匹配及分页情况')
    except Exception:
        LOG.exception('单场试选未完成，已停止，不会自动重试')
        notify('试选已停止，请检查浏览器和 bot.log，确认是否已选上')


def route_lightweight_resources(route):
    request = route.request
    try:
        frame_url = urlsplit(request.frame.url)
        # Never filter authentication/captcha pages. Keep CSS, scripts and fonts.
        portal = (frame_url.hostname == 'yjs1.ustc.edu.cn' and
                  '/dbLogin/' not in frame_url.path and
                  '/login' not in frame_url.path.lower())
        if portal and request.resource_type in ('image', 'media'):
            route.abort()
        else:
            route.continue_()
    except PWError:
        route.continue_()


def run_main():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(ROOT / 'browser_profile'),
            headless=False, channel='msedge', accept_downloads=False,
            chromium_sandbox=True,
            args=['--disk-cache-size=33554432', '--media-cache-size=16777216'],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(CFG['portal_url'], wait_until='domcontentloaded', timeout=45000)
            page = ensure_login(context)
        except (RuntimeError, ValueError, PWTimeout) as exc:
            # Raw browser exceptions may contain filled values. Never print them.
            message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else '打开登录入口超时，请检查网络'
            LOG.error('%s', message)
            page = wait_for_manual_login(context)
            if page is None:
                LOG.error('仍未检测到登录成功，本次未执行选课')
                context.close()
                return
        LOG.info('登录流程完成，准备进入选课页面（仅登录模式=%s，定时监测=%s）',
                 CFG.get('login_only', True), CFG.get('scheduled_monitor', False))
        if CFG.get('block_report_media', False):
            context.route('**/*', route_lightweight_resources)
            LOG.info('已启用报告页面图片/媒体过滤，认证页面保持加载')
        if CFG.get('login_only', True):
            print('登录成功，当前为仅登录模式，不执行选课。')
            try:
                LOG.info('仅登录模式，按 Enter 关闭程序', extra={'console': True})
                while not STOP_EVENT.wait(0.5):
                    pass
            finally:
                context.close()
            return
        if CFG.get('scheduled_monitor', False):
            try:
                # Initial navigation can be assisted once; rounds need no input.
                try:
                    open_report_page(context)
                except (RuntimeError, PWError):
                    wait_for_report_page(context)
                scheduled_monitor(context)
            except KeyboardInterrupt:
                LOG.info('用户停止定时监测')
            finally:
                context.close()
            return
        if CFG.get('batch_enroll_all', False):
            try:
                batch_enrollment(context)
            finally:
                context.close()
            return
        if CFG.get('test_enroll_one', False):
            try:
                test_enrollment(context)
            finally:
                context.close()
            return
        print('\n请进入【培养 → 学术报告管理 → 学术报告选课】。')
        wait_for_report_page(context)
        notify('学术报告助手已启动（测试模式=%s）' % CFG['dry_run'])
        try:
            while True:
                check_stop()
                try:
                    changed = monitor(report_frame(context))
                    if changed:
                        time.sleep(2)
                        continue
                except Exception as exc:
                    LOG.exception('监测异常: %s', exc)
                    notify('监测已暂停，请检查浏览器和终端')
                    break
                STOP_EVENT.wait(max(30, int(CFG['interval_seconds'])))
        except KeyboardInterrupt:
            LOG.info('用户停止')
        finally:
            context.close()


def main():
    global CFG, FILTERS
    try:
        CFG = load_settings(ROOT / 'config.json')
        FILTERS = validate_filters(CFG['filters'])
        storage = storage_settings(CFG)
    except ValueError as exc:
        print(str(exc))
        return
    configure_logging(ROOT, storage, CFG.get('console_log_mode', 'summary'))
    STOP_EVENT.clear()
    LOG.info('程序启动后自动登录并开始检测；在运行终端按 Enter 停止（Ctrl+C 也可）', extra={'console': True})
    threading.Thread(target=listen_for_enter, daemon=True).start()
    try:
        run_main()
    except (StopRequested, KeyboardInterrupt):
        LOG.info('检测已停止', extra={'console': True})


if __name__ == '__main__':
    main()
