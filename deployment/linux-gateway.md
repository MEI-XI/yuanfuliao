# Linux 网关部署说明

生产环境使用 Python 3.12，在项目独立虚拟环境中安装 `requirements-gateway.lock`。清单根据当前已安装包的依赖元数据递归生成，按 Linux x86_64 / Python 3.12 的环境标记解析，并保留 `psycopg[binary]` 所需依赖。包括核心业务依赖、`numpy` 和 `python-dotenv`，不安装本地 OCR、训练或测试依赖。服务器安装后执行 `python -m pip check`，确认 Linux 包的实际依赖一致。

OCR 与 DeepSeek 继续调用原网关，不在应用服务器部署模型。设置环境变量 `OCR_GATEWAY_CONFIG` 指向私有配置文件，例如 `/workspace/yuanfuliao/secrets/ocr-gateway.json`：

```json
{
  "base_url": "http://192.168.0.101:18080/v1",
  "model": "PaddleOCR-VL-1.5-0.9B",
  "api_key_file": "gateway.key"
}
```

`gateway.key` 存放现有网关密钥的原值；相对路径以配置文件目录为基准，也可使用绝对路径。该文件不放进 Git、网页发布目录或公开下载目录，设置为仅服务账号可读（同一账号使用 `0600`，专用服务组使用 `0640`）。不将密钥写入命令行或日志。原 Windows `protected_key` 配置仍使用 DPAPI 解密，不能直接把 Windows 密文当成 Linux 密钥。

`data/credential.key` 是业务账号凭据的另一把加密密钥，必须与业务数据库一并迁移并保留；它不是模型网关密钥。
