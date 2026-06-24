# PixelRAG × Claude Code 快速上手指南

> 让 Claude Code 像人一样"看"网页，而不是解析 HTML。

---

## 前置要求

- macOS（Apple Silicon 或 Intel）
- Python 环境（Anaconda/conda 或系统 Python 均可）
- 已安装 [Claude Code](https://docs.anthropic.com/claude-code)（`claude` 命令可用）
- 已克隆本仓库：

```bash
git clone git@github.com:StarTrail-org/PixelRAG.git
```

---

## 安装步骤

### 第一步：安装 pixelrag（含 pixelshot CLI）

```bash
pip install pixelrag
```

验证安装成功：

```bash
pixelshot --help
```

看到参数帮助信息即表示安装成功。

---

### 第二步：安装 Claude Code 插件

```bash
claude plugin marketplace add StarTrail-org/PixelRAG
claude plugin install pixelbrowse@pixelrag-plugins
```

成功输出示例：

```
✔ Successfully added marketplace: pixelrag-plugins (declared in user settings)
✔ Successfully installed plugin: pixelbrowse@pixelrag-plugins (scope: user)
```

---

## 使用方法

### 方式一：单独使用 pixelshot 截图

将任意网页或 PDF 渲染为截图图块：

```bash
# 截图网页
pixelshot https://en.wikipedia.org/wiki/Python -o ./tiles

# 截图 PDF（需额外安装 pdf 支持）
pip install 'pixelrag[pdf]'
pixelshot paper.pdf -o ./tiles --dpi 200
```

输出文件会保存在 `./tiles/` 目录中。

---

### 方式二：在 Claude Code 中截图并分析（推荐）

启动 Claude Code 交互模式：

```bash
claude
```

在输入框中使用斜杠命令：

```
/screenshot https://en.wikipedia.org/wiki/Python
```

或者直接用一行命令（需允许权限）：

```bash
claude --dangerously-skip-permissions -p "screenshot https://news.ycombinator.com and summarize the top stories"
```

---

### 方式三：调用免费托管 API（无需安装，零配置）

无需 API Key，直接搜索 828 万篇维基百科页面：

```bash
curl -X POST https://api.pixelrag.ai/search \
  -H "Content-Type: application/json" \
  -d '{"queries": [{"text": "What is the capital of France?"}], "n_docs": 5}'
```

也可以直接在浏览器访问：[pixelrag.ai](https://pixelrag.ai)

---

### 方式四：用自己的文档构建本地索引

```bash
pip install 'pixelrag[index]'

cat > pixelrag.yaml << 'EOF'
source:
  type: local
  path: ./my_docs
embed:
  model: Qwen/Qwen3-VL-Embedding-2B
  device: auto  # 自动选择 CUDA / MPS / CPU
output: ./my_index
EOF

pixelrag index build
pixelrag serve --index-dir ./my_index --port 30001
```

---

## 快速路径选择

| 目标 | 推荐方式 |
|---|---|
| 快速体验，不想安装任何东西 | 访问 pixelrag.ai 或调用托管 API |
| 截图任意网页/PDF | `pip install pixelrag` + `pixelshot` 命令 |
| 让 Claude Code 看懂复杂页面 | 安装 `pixelbrowse` 插件 + `/screenshot` 命令 |
| 搜索自己的文档库 | `pip install 'pixelrag[index]'` + 自建索引 |

---

## 常见问题

**Q：`uv` 命令找不到？**

直接用 `pip install pixelrag` 替代 `uv tool install pixelrag`，功能完全相同。

---

**Q：Claude Code 提示没有权限使用截图工具？**

进入交互模式（`claude`），使用 `/screenshot` 斜杠命令时按提示授权；或启动时加 `--dangerously-skip-permissions` 参数跳过权限检查（仅建议本地开发使用）。

---

**Q：Claude Code 提示 "Claude Fable 5 is currently unavailable"？**

这是模型配置问题，不影响使用。当前会话会自动降级到 Sonnet 4.6，功能正常。

---

**Q：`pixelshot` 在 macOS 上找不到浏览器？**

手动指定 Chrome 路径：

```bash
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
pixelshot https://example.com -o ./tiles
```
