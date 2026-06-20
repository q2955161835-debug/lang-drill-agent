p = 'd:/1Folder/语言学习-lang-drill/语言学习-lang-drill-agent/doc/进展记录.md'
with open(p, 'rb') as f:
    content = f.read()

try:
    txt = content.decode('utf-8')
except UnicodeDecodeError:
    try:
        txt = content.decode('gbk')
    except Exception:
        txt = content.decode('utf-8', 'ignore')

new_content = """# 进展记录

## 2026-06-03 21:30 ~ 2026-06-03 21:35

本阶段完成内容：读取了 Mimo API key，配置了 `.env` 环境变量使用 `mimo-v2.5` 模型。对 Agent 后端内核进行了系统测试（`pytest try`）和 CLI 端冒烟测试。
新增/修改/生成的文件清单与用途说明：
- `.env`：新增真实配置文件，记录了 `LANGDRILL_DEFAULT_PROVIDER` 为 `mimo`，指定模型为 `mimo-v2.5`，并写入了 API key。
错误汇报：无
"""

txt = txt.replace("# 进展记录\r\n", new_content)
txt = txt.replace("# 进展记录\n", new_content)

with open(p, 'wb') as f:
    f.write(txt.encode('utf-8'))
