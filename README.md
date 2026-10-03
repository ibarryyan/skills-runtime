# Skills Runtime + LLM Demo

这是一个从 0 实现的最小 Agent Skills Runtime，并接入 OpenAI-compatible `/chat/completions` API。

## 架构

```text
User Task
   |
   v
Skill Discovery
   |
   v
Skill Registry
   |
   +-----> LLM Skill Selector
   |              |
   v              v
Skill Metadata -> Selected Skill
                    |
                    v
                Skill Loader
                    |
                    v
              Context Builder
                    |
                    v
                LLM Agent
                    |
                    v
                Final Answer
```

## 运行

### 1. 准备配置

复制示例配置并填入真实值：

```bash
cp .env.example .env
```

`.env` 至少包含：

```bash
LLM_BASE_URL=https://your-api.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model
```

`.env` 已被 `.gitignore` 忽略，不会被提交；`.env.example` 是模板，可以提交。

### 2. 执行

Python 不会自动读取 `.env`，需要先把变量导出到当前 shell：

```bash
set -a && source .env && set +a
python3 main.py
```

也可以手动导出（不依赖 `.env` 文件）：

```bash
export LLM_BASE_URL="https://your-api.example.com/v1"
export LLM_API_KEY="your-api-key"
export LLM_MODEL="your-model"
python3 main.py
```

两个命令建议分开执行：`set -a && source .env && set +a` 只对当前 shell 生效，需要在同一终端中再运行 `python3 main.py`。

### 3. 常见错误

`LLM Error: Missing environment variables: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL`

说明这三个变量没有进入进程环境，按顺序检查：

1. 是否执行了 `source .env`（直接 `python3 main.py` 不会加载 `.env`）。
2. `.env` 是否在项目根目录，且键名没有多余空格。
3. 是否切换过终端或新开了 shell（导出的变量不会跨终端保留）。

## 内部 HTTPS / 自签名证书

如果访问公司内部的 AI API 时出现：

```text
SSL: CERTIFICATE_VERIFY_FAILED
certificate verify failed: self-signed certificate in certificate chain
```

优先使用公司根 CA，而不是关闭证书校验：

```bash
export LLM_SSL_VERIFY=true
export LLM_CA_BUNDLE="/path/to/company-root-ca.pem"
```

如果只是为了开发环境临时验证链路，也可以：

```bash
export LLM_SSL_VERIFY=false
```

**不要在生产环境使用 `LLM_SSL_VERIFY=false`。**

## 验证

无需真实 API Key，也可以运行集成测试。测试会启动本地 mock OpenAI-compatible 服务，验证：

1. Runtime 能发现 Skill。
2. LLM Selector 能选择 Skill。
3. 被选择的 Skill 会按需加载。
4. Skill Context 会进入第二次 LLM 调用。
5. 最终得到 Agent 回复。

```bash
python3 -m unittest discover -s tests -v
```

## 注意

当前版本负责 Skill discovery、selection、loading 和 context injection。

虽然 Skill 可以包含 `scripts/`、`references/`、`assets/`，但 Runtime 目前只发现这些资源，不会自动执行脚本或读取所有 reference 内容。
