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

设置环境变量：

```bash
export LLM_BASE_URL="https://your-api.example.com/v1"
export LLM_API_KEY="your-api-key"
export LLM_MODEL="your-model"
```

然后：

```bash
python3 main.py
```

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
