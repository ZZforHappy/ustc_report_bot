"""Read only the separate login credentials; never echo secret file contents."""
import json
from pathlib import Path


def load_settings(path):
    try:
        settings = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        raise ValueError('config.json 缺失、不可读或 JSON 格式有误，请按 README 检查') from None
    if not isinstance(settings, dict) or not isinstance(settings.get('filters'), dict):
        raise ValueError('config.json 必须包含 filters 筛选对象')
    login = settings.setdefault('login', {})
    if not isinstance(login, dict):
        raise ValueError('config.json 的 login 必须是等待时间配置对象')
    if 'student_id' in login or 'password' in login:
        raise ValueError('请将学号密码放入 credentials.json，不要放在 config.json 的 login 中')
    settings.setdefault('portal_url', 'https://yjs1.ustc.edu.cn/gsapp/sys/yjsemaphome/portal/index.do')
    settings.setdefault('dry_run', False)
    settings.setdefault('interval_seconds', 600)
    for key in ('login_only', 'scheduled_monitor', 'batch_enroll_all', 'test_enroll_one', 'dry_run'):
        if key in settings and type(settings[key]) is not bool:
            raise ValueError(f'config.json 的 {key} 必须是 true 或 false')
    if type(settings['interval_seconds']) is not int or settings['interval_seconds'] < 30:
        raise ValueError('interval_seconds 必须是大于等于 30 的整数')
    for key in ('timeout_seconds', 'manual_timeout_seconds'):
        if key in login and (type(login[key]) is not int or login[key] < 1):
            raise ValueError(f'login.{key} 必须是正整数')
    return settings


def load_credentials(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        raise ValueError('缺少 credentials.json，请按 README 创建并填写学号和密码') from None
    except (ValueError, OSError):
        raise ValueError('credentials.json 无法读取或 JSON 格式有误，请在本机检查') from None
    if not isinstance(data, dict):
        raise ValueError('credentials.json 必须是包含 student_id 和 password 的 JSON 对象')
    student_id, password = data.get('student_id'), data.get('password')
    if not isinstance(student_id, str) or not student_id.strip() or not isinstance(password, str) or not password:
        raise ValueError('请填写 credentials.json 中的 student_id 和 password，且均使用字符串')
    return {'student_id': student_id.strip(), 'password': password}
