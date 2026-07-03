# Lang Drill Agent Product Site

这是 Lang Drill Agent 的独立产品展示网站，不改动主应用 `frontend/`。

## 本地运行

```powershell
cd 演示web
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:4173
```

## 构建

```powershell
cd 演示web
npm run build
```

构建产物在 `演示web/dist/`。Vite `base` 使用 `./`，适配 GitHub Pages 子路径部署。

## 静态站点限制

- 网站不连接真实后端，不读取 `.env`。
- 演示工作台中的模型回复是固定模拟内容。
- 技能目录和数据路径使用虚构或系统通用路径，避免暴露真实主机地址。
- GitHub Pages 部署时只需要上传构建产物或配置 Actions 构建。
