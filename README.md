# 原辅料智能查验与报告管理系统

通过包装图片识别原辅料信息，结合人工核对与维护的检验标准，按模板导出 Excel 查验台账及 Word 检验报告。

## 当前状态

已实现本地试用版：账号权限、公司台账、图片分组与识别、人工核对、共享检验标准、修改历史、Excel/Word 导出。公司服务器部署在本地验收后进行。

当前电脑双击 `启动本地测试.cmd`，浏览器访问 `http://127.0.0.1:8000`。首次进入建立管理员账号，由管理员分配其他账号。

运行、手机访问、模板签名维护和迁移说明见 [本地运行与模板维护](docs/本地运行与模板维护.md)。OCR 实测方法与边界见 [OCR 实测](docs/OCR实测.md)。

## 项目文档

### Git 提交约定

按用户于 2026-10-17 确认的要求，后续修改直接在 `main` 主分支开发、提交并推送到 `origin/main`；除非用户另有要求，不再默认创建开发分支。提交前检查改动并运行相关验证，只提交本项目文件。

- [完整项目方案](docs/项目方案.md)
- [需求评审与已确认决定](docs/需求评审.md)
- [UI 设计及概念图](docs/UI设计备选.md)
- [业务术语](CONTEXT.md)

## 已确定方向

- 电脑、手机网页使用，区分管理员与普通用户。
- 先进入公司台账，再上传图片、识别及录入。
- 本地开源 OCR 负责基础识别，智谱 GLM-4.1V-Thinking-Flash 云端模型辅助；辅助不可用不影响本地流程。
- 所有公司共享物料与检验标准方案，业务字段允许留空。
- Excel 按公司分工作表，Word 每条记录一份。
- 录入采用图片与字段并排布局，列表采用台账表格布局，全站统一青色。
- 本地测试满意后再部署公司服务器。

仓库中的 UI 图片为概念示意。实际业务模板、预置签名、原始照片、数据库和云端密钥不提交 GitHub。

## 开发与验证

Python 3.12、PostgreSQL 17、Node.js 22 以上。生产依赖锁在 `requirements.lock`，前端依赖锁在 `frontend/package-lock.json`。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
# 按 .env.example 配置 DATABASE_URL，放好 templates 中的办公文件
.\scripts\start.ps1
```

测试使用专用 PostgreSQL 数据库：设置 `TEST_DATABASE_URL` 后执行 `scripts/test.ps1`。浏览器测试在 `frontend` 执行 `npm test`，需安装 Chrome。每个测试使用独立 schema，不读取正式业务数据。首次本地 OCR 会下载开源模型，模型就绪后可离线识别。云端调用需管理员配置自己的智谱密钥。
