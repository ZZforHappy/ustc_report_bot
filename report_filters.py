"""Report selection rules, independent of browser and account configuration."""
import json
from pathlib import Path

FIELDS = ('地点', '报告题目', '院系', '报告人')


def load_filters(path):
    rules = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return validate_filters(rules)


def validate_filters(rules):
    if isinstance(rules, dict):
        rules = dict(rules)
    if not isinstance(rules, dict) or set(rules) - set(FIELDS) - {'排除题目关键词', '排除院系关键词', '最多遍历页数'}:
        raise ValueError('筛选配置包含不支持的字段')
    page_limit = rules.get('最多遍历页数', 3)
    if type(page_limit) is not int or page_limit < 1:
        raise ValueError('最多遍历页数必须是大于等于 1 的整数')
    rules['最多遍历页数'] = page_limit
    for field in FIELDS:
        value = rules.get(field, '任意')
        terms = [value] if isinstance(value, str) else value
        if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or not t.strip() for t in terms):
            raise ValueError(f'{field} 必须填写关键词、关键词数组或“任意”')
        terms = [t.strip() for t in terms]
        if '任意' in terms and len(terms) != 1:
            raise ValueError(f'{field} 的“任意”不能与其他关键词混用')
        rules[field] = terms
    excluded = rules.get('排除题目关键词', ['作业', '提交'])
    if not isinstance(excluded, list) or any(not isinstance(t, str) or not t.strip() for t in excluded):
        raise ValueError('排除题目关键词必须是字符串数组；不排除请填 []')
    rules['排除题目关键词'] = [t.strip() for t in excluded]
    excluded_departments = rules.get('排除院系关键词', [])
    if not isinstance(excluded_departments, list) or any(not isinstance(t, str) or not t.strip() for t in excluded_departments):
        raise ValueError('排除院系关键词必须是字符串数组；不排除请填 []')
    rules['排除院系关键词'] = [t.strip() for t in excluded_departments]
    return rules


def matches_report(report, rules):
    excluded_departments = rules.get('排除院系关键词', [])
    if excluded_departments:
        if '院系' not in report:
            raise ValueError('网页未识别到排除条件所需的字段：院系')
        if any(term.casefold() in report['院系'].casefold() for term in excluded_departments):
            return False
    for field in FIELDS:
        terms = rules[field]
        if terms == ['任意']:
            continue
        if field not in report:
            raise ValueError(f'网页未识别到筛选所需的字段：{field}')
        if not any(term.casefold() in report[field].casefold() for term in terms):
            return False
    return not any(term.casefold() in report.get('报告题目', '').casefold()
                   for term in rules['排除题目关键词'])
