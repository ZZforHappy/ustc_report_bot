# 中科大学术报告选课助手

本项目帮助中国科学技术大学（USTC）的研究生自动选择和预约学术报告。一些热门报告名额紧张、经常满员，手动查看容易错过报名机会；程序可以定时检查符合条件的报告，在发现剩余名额时自动尝试选课，减少反复刷新页面的操作。

## 主要功能

- 自动登录研究生综合服务系统，支持复用登录状态；偶尔出现的验证码由用户手动完成。
- 按地点、报告题目、院系、报告人筛选，支持“任意”选项及关键词排除。
- 在配置的页数范围内逐页扫描，检查选课入口和剩余容量，并尝试预约符合条件的报告。
- 支持定时检测，可用于检查新开放名额或他人退选后释放的名额；运行后自动开始，终端按 Enter 停止。
- 自动关闭“不在可选学生范围内”等明确拒绝提示，继续处理其他报告。
- 批量提交后统一核验已选报告，成功时弹窗提醒，并追加记录报告名称、时间、地点和选课时间。

程序只能在系统允许报名且仍有名额时尝试选课，不保证一定抢到热门报告，最终结果以系统中的“已选报告”为准。

## 项目结构

```text
main.py                     启动入口
ustc_bot/
  app.py                    浏览器操作、登录、分页、选课与定时检测
  config.py                 普通配置和私密凭据的读取与校验
  filters.py                报告筛选条件与匹配规则
  history.py                成功历史追加及 Windows 屏幕弹窗
tests/                      本地逻辑测试和网页结构测试
requirements.txt            Python 依赖
config.json                 非敏感运行设置与筛选条件
credentials.example.json    可上传的空凭据模板
credentials.json            学号和密码，仅保存在本机
```

运行产生的文件和目录：

| 路径 | 用途 |
| --- | --- |
| `browser_profile/` | Edge 独立浏览器会话，可复用登录状态 |
| `bot.log` | 登录、翻页、筛选及错误日志 |
| `选课日志.jsonl` | 持续追加的成功选课历史，不覆盖 |
| `enrollment_results.json` | 最近一轮汇总，会覆盖上一轮 |
| `grid_structure.json` | 网格识别异常时的结构诊断信息 |

运行数据、真实凭据和虚拟环境已加入 `.gitignore`。代码、说明、依赖、测试、`config.json` 和空凭据模板均可提交到 GitHub。
请勿分享 `credentials.json` 或浏览器会话。

## 环境配置（Windows / PowerShell）

需要可用的 Python 3.10 或以上版本、Microsoft Edge，以及能访问学校系统的网络。
以下命令在项目根目录执行。建议使用独立虚拟环境：

```powershell
py --version
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

首次下载后，在项目根目录复制空凭据模板，再编辑生成的 `credentials.json`，填写自己的学号和密码：

```powershell
Copy-Item -LiteralPath credentials.example.json -Destination credentials.json
```

仅在本机还没有 `credentials.json` 时执行复制，避免覆盖已有账号。按需修改随项目提供的 `config.json` 筛选条件与扫描间隔，再运行 `main.py`。

依赖说明：

- `playwright`：浏览器自动化，运行时使用已安装的 Microsoft Edge。
- `plyer`：系统桌面通知；缺失时不会影响选课和 Windows 原生成功弹窗。

正常运行使用 Edge，不需要另外下载 Playwright Chromium。只有执行网页结构测试时才需要下载 Chromium。
IDE 的 Python 解释器请选择项目的 `.venv\Scripts\python.exe`。

若提示 `did not find executable at ...Python314...`，说明旧虚拟环境指向的 Python 已不存在。
先安装或选定可用 Python，再将旧 `.venv` 改名留存，重新创建 `.venv` 并安装依赖。不要直接复制其他电脑的虚拟环境。
无需激活环境也可使用上述完整路径运行命令；若需激活，执行 `.\.venv\Scripts\Activate.ps1`。

## 两个配置文件

现有配置已保留，无需用示例覆盖。修改后重启程序生效。

### credentials.json：个人登录信息

```json
{
  "student_id": "你的学号",
  "password": "你的统一身份认证密码"
}
```

学号和密码均填写字符串，学号字母按学校要求大写。这是本地明文文件，不要提交或分享。
已有有效登录会话时直接复用，仅需要填写登录表单时才读取这个文件。

### config.json：运行及筛选设置

```json
{
  "portal_url": "https://yjs1.ustc.edu.cn/gsapp/sys/yjsemaphome/portal/index.do",
  "login": {"timeout_seconds": 120, "manual_timeout_seconds": 300},
  "login_only": false,
  "scheduled_monitor": true,
  "batch_enroll_all": false,
  "test_enroll_one": false,
  "interval_seconds": 600,
  "dry_run": false,
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

| 设置 | 含义 |
| --- | --- |
| `login_only` | 只登录，按 Enter 结束 |
| `scheduled_monitor` | 自动循环检测；每轮结束等待 `interval_seconds` 秒 |
| `batch_enroll_all` | 执行一轮批量选课，仍遵守筛选条件 |
| `test_enroll_one` | 执行一轮试选，最多提交一场 |
| `dry_run` | `true` 仅记录候选，`false` 实际提交 |
| `interval_seconds` | 每轮之间的等待时间，600 为十分钟，至少 30 秒 |
| `login.timeout_seconds` | 自动登录等待时间 |
| `login.manual_timeout_seconds` | 手动验证或登录的等待时间 |

模式优先级为：仅登录 → 定时检测 → 单轮批量 → 单场试选。建议只开启需要的模式。
四项都关闭时沿用普通循环检测流程。

筛选规则：

- `最多遍历页数` 必须是正整数。未选报告扫描和最终已选报告核验都不超过该上限。
- 地点、题目、院系、报告人填写 `"任意"` 表示该字段不限制。
- `"地点": "高新"` 表示地点包含高新；`["高新", "西区"]` 表示符合任一个关键词即可。
- 不同字段需要同时满足；英文匹配不区分大小写。
- 排除题目、排除院系命中任一个关键词就跳过；`[]` 表示不排除，排除优先于包含条件。
- “任意”不会取消余量和选课入口检查。有入口也可能被系统拒绝，程序会关闭明确拒绝的提示并继续。

JSON 使用英文双引号和逗号，不支持注释或末尾多余逗号。密码中的 `"` 写作 `\"`，反斜杠写作 `\\`。

## 启动与停止

```powershell
.\.venv\Scripts\python.exe main.py
```

也可以在选好解释器的 IDE 中直接运行 `main.py`。

1. 启动后自动登录，不需要按 Enter 开始。
2. 偶尔出现手机验证码等验证时，在浏览器手动完成并点击登录或确认。
3. 自动尝试打开“培养 → 学术报告管理 → 学术报告选课”。若未成功，请在浏览器手动进入，程序识别后自动继续。
4. 逐页处理，每次提交后重新读取当前页，避免列表移动造成漏选；达到页数上限就结束本轮。
5. 批量处理结束后只进入一次“已选报告”，统一核验。定时模式随后等待下一轮。

停止时切回运行程序的终端，按 **Enter**，也可以按 **Ctrl+C**。
已发出的选课请求可能已经生效，停止不会自动退选。电脑需保持唤醒、网络连通，终端与浏览器可以最小化。
页面异常、登录失效或有未确认结果时，程序会暂停或停止供检查；不会无限重试提交。

## 成功提醒与选课日志

核验成功后显示 Windows 置顶弹窗，包含报告名称、报告时间、地点和选课时间。
弹窗在独立线程中依次显示，不阻塞扫描；程序退出后未显示的弹窗不会继续弹出。

`选课日志.jsonl` 每行一条 JSON，持续追加：

- 报告名称、报告时间、地点。
- 选课时间：提交请求的北京时间。
- 核验时间：确认进入已选报告的北京时间。

网页未提供报告时间时记录“未提供”。最终核验页数上限内未找到的记录会保留为未确认，不虚报成功。
桌面通知依赖 `plyer` 和 Windows 设置，原生成功弹窗不依赖 `plyer`。

## 测试与排查

不访问学校网站的逻辑测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_filters.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_private_config.py -v
```

运行全部测试（包含本地网页结构测试）：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试不会使用真实凭据或提交学校选课。导入程序模块不会自动读取本机配置、打开浏览器或创建日志。
遇到问题先查看 `bot.log` 最近一轮的翻页范围、弹窗处理和汇总。分享报错时遮住个人信息。
学校页面结构变化可能需要进一步适配；日志中的警告不等于选课已成功，以已选报告核验为准。
