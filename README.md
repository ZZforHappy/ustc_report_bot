# 中科大学术报告选课助手

## 配置

只需编辑一个文件：`config.json`。账号和已有筛选条件已从旧配置保留并合并。
`report_filters.py` 是筛选逻辑代码，不是配置文件。保存配置后重启程序生效。

配置结构示例（请保留你本机已填好的账号密码）：

```json
{
  "portal_url": "https://yjs1.ustc.edu.cn/gsapp/sys/yjsemaphome/portal/index.do",
  "login": {
    "student_id": "你的学号",
    "password": "你的密码",
    "timeout_seconds": 120
  },
  "login_only": false,
  "scheduled_monitor": true,
  "batch_enroll_all": true,
  "test_enroll_one": false,
  "interval_seconds": 600,
  "dry_run": false,
  "max_pages": 200,
  "filters": {
    "最多遍历页数": 3,
    "地点": "高新",
    "报告题目": "任意",
    "院系": "任意",
    "报告人": "任意",
    "排除题目关键词": ["作业", "提交"],
    "排除院系关键词": []
  }
}
```

### 登录与运行

- `login`：学号、统一身份认证密码和登录等待秒数。字母学号按学校要求大写。
- `login_only: true`：仅测试登录，优先于其他模式。
- `scheduled_monitor: true`：定时运行，优先于批量和单场模式。
- `batch_enroll_all: true`：单轮批量选课，也遵守 `filters`，并非不限制地点。
- `test_enroll_one: true`：单轮最多提交一场。
- `interval_seconds: 600`：每轮结束等待 10 分钟再查询；最小 30 秒。
- `dry_run: true`：仅记录匹配，不提交；正式选课设为 `false`。
- `max_pages`：已选报告结果核验最多遍历页数。未选报告扫描上限由 `filters.最多遍历页数` 控制。

### 筛选条件（filters）

- `最多遍历页数`：只处理未选报告前几页，填写正整数。
- 地点、题目、院系、报告人均可填关键词或 `"任意"`。“任意”表示对应字段不限制。
- `"地点": "高新"` 表示地点包含高新；`"地点": ["高新", "西区"]` 表示包含其中一个即可。
- 不同字段需要同时满足。英文不区分大小写。
- `排除题目关键词`：题目包含任一个关键词就跳过。
- `排除院系关键词`：院系包含任一个关键词就跳过。即使院系选“任意”，排除仍生效。
- 排除项填 `[]` 表示不排除；包含条件与排除条件同时设置时排除优先。
- 所有模式仍要求有选课入口且已选人数小于容量。

配置为 JSON，字段之间用逗号分隔，末项不要加逗号。密码中的双引号写为 `\"`，反斜杠写为 `\\`。
账号密码为本地明文，不要分享 `config.json` 或 `browser_profile`。它们已加入 `.gitignore`。

## 安装与运行

需要 Python、Microsoft Edge。Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

自动登录成功后尝试进入选课页；若菜单未自动打开，首次按终端提示进入“培养 → 学术报告管理 → 学术报告选课 → 未选报告”。
程序逐页处理，同页提交后重新读取列表，全部处理完才进入一次已选报告统一核验。
定时模式每轮重新查询数据，无成功报名时记日志，有成功报名时通过桌面通知和提示音提醒。
登录失效、页面异常或有未确认报名时停止，待人工检查后重新运行。
电脑需保持唤醒、网络连接、程序与浏览器运行。窗口可以最小化，按 Ctrl+C 停止。
验证码或二次认证由你在浏览器中完成。程序不会自动退选。
如果出现验证码，填写后请点击页面的“立即登录/确认”按钮完成提交。程序检测到验证步骤后默认额外提供至少 300 秒处理时间；可通过 `login.manual_timeout_seconds` 修改。等待期间每 15 秒输出一次状态，不记录验证码或密码。

## 日志与测试

`bot.log` 记录运行过程，`enrollment_results.json` 保存最近一轮结果。
桌面通知依赖 `plyer` 和 Windows 通知设置，终端与日志会保留结果。
页面结构变化、原生确认框或分页组件变化仍可能需要适配。

筛选测试无需浏览器：`python -m unittest discover -s tests -p test_filters.py -v`。
全部测试：`python -m unittest discover -s tests -v`。DOM 测试需要先执行 `python -m playwright install chromium`。
