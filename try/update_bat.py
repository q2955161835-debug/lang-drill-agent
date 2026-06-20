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

## 2026-06-03 21:34 ~ 2026-06-03 21:36

本阶段完成内容：在根目录新增了两个批处理脚本，用于一键启动服务（启动前后端并打开浏览器）和一键关闭服务（清理对应窗口与占用端口）。
新增/修改/生成的文件清单与用途说明：
- `start.bat`：一键启动后端服务与前端服务，并在启动后自动打开浏览器访问本地网页。
- `stop.bat`：一键关闭项目相关的终端窗口与对应占用端口（8000, 5173），释放后台进程。
错误汇报：无
"""

txt = txt.replace("# 进展记录\r\n", new_content)
txt = txt.replace("# 进展记录\n", new_content)

with open(p, 'wb') as f:
    f.write(txt.encode('utf-8'))
