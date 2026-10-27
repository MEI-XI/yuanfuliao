# 基础 OCR 网关

基础识别支持 OpenAI 兼容的 `/chat/completions` 图像接口，当前网关模型为 `PaddleOCR-VL-1.5-0.9B`。图片以 JPEG 数据发送，返回文字继续进入现有字段提取、日期计算和人工确认流程。智谱辅助配置独立保留。

Windows 服务默认读取运行账号的 `%LOCALAPPDATA%\Yuanfuliao\ocr-gateway.json`，也可用 `OCR_GATEWAY_CONFIG` 指定项目外的配置文件。文件包含 `base_url`、`model`、`protected_key` 三项；`protected_key` 必须使用同一 Windows 账号通过 `ConvertFrom-SecureString` 生成的 DPAPI 密文，不能填明文。

密钥不经过浏览器，不写入数据库、源码或识别证据。更换运行账号或迁移服务器时，需要在新账号下重新配置密钥。不要将真实配置复制进项目或提交到 Git。

存在网关配置时使用网关；网关失败会提示原因，仍可人工填写，不会悄悄使用其他模型。未配置网关时使用原 RapidOCR。配置路径变更或新增、移除配置后重启服务；现有文件中的模型、地址或密钥更改在下次识别时生效。

网关需要提供 `POST /v1/chat/completions`，接受模型名、`OCR:` 提示及 `image_url` 数据。请求超时为 180 秒，连接超时为 10 秒；认证失败、空响应及截断响应不会作为成功结果保存。
