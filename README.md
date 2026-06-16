# deepseek-xhs-agent
> 基于 DeepSeek API 的智能小红书内容创作与发布工具，通过自然语言对话驱动完整的「文案生成 → 图片渲染 → 自动发布」工作流。

---

## ✨ 项目简介

本项目是 [Auto-Redbook-Skills](https://github.com/comeonzhj/Auto-Redbook-Skills) 的智能化上层封装。原项目提供了两大核心能力：

- **渲染能力**：将 Markdown 文案渲染为小红书风格的卡片图片（支持多主题、多分页模式）
- **发布能力**：将渲染后的图片自动发布到小红书（支持私密/公开、定时发布）

但原项目需要用户手动编写 Markdown 文案，并手动执行渲染和发布命令。

**本项目在此基础上引入 DeepSeek 作为「大脑」**：你只需要用一句话描述主题，AI 就会自动完成文案创作、保存 Markdown、调用渲染和发布脚本的全流程。整个过程完全由对话驱动，无需手动编写或执行任何命令。

| 组件 | 职责 |
| :--- | :--- |
| **Auto-Redbook-Skills** | 渲染引擎 + 发布引擎（把 Markdown 变成图片并发布） |
| **本项目** | AI 大脑（替你写 Markdown，再自动调用渲染和发布引擎） |

---

## 🎯 核心功能

| 功能 | 说明 |
| :--- | :--- |
| 🤖 **一句话驱动全流程** | 输入主题，DeepSeek 自动完成「写文案 → 存文件 → 渲染 → 发布」全部步骤 |
| 📝 **严格排版控制** | 标题 ≤18字、卡片字数适中、禁止括号、进度条限制等硬性规则 |
| 🎨 **双渲染器支持** | 默认使用新版 `render_xhs_v2.py`（8种主题 + 4种分页模式），可指定旧版 |
| 📁 **产物自动隔离** | 每次运行自动创建 `YYYY-MM-DD_主题` 独立文件夹，不再污染根目录 |
| 🔒 **默认私密发布** | 默认私密发布，避免错误内容公开；用户明确要求时再加 `--public` |
| 🛠️ **技能包自动发现** | 自动扫描 `./skills/` 目录，发现并加载标准技能包（含 render 和 publish 脚本） |

---

## 🚀 快速开始

### 1. 克隆与安装

```bash
git clone https://github.com/你的用户名/deepseek-xhs-agent.git
cd deepseek-xhs-agent
pip install openai python-dotenv pyyaml
```

### 2. 准备技能包（含渲染和发布脚本）

本项目依赖 Auto-Redbook-Skills 作为后端引擎，需要将它的完整技能包（包含 `scripts/render_xhs_v2.py` 和 `scripts/publish_xhs.py`）放入 `skills/` 目录：

```bash
git clone https://github.com/comeonzhj/Auto-Redbook-Skills.git skills/小红书写手
```

### 3. 安装 Playwright（渲染依赖）

```bash
pip install playwright
playwright install chromium
```

### 4. 配置 API 密钥

在项目根目录创建 `.env` 文件：

```text
DEEPSEEK_API_KEY=你的DeepSeek API密钥
```

### 5. 运行

```bash
python skill_runner.py
```

---

## 💬 使用示例

启动后，直接输入需求：

```
🧑 您: 使用小红书写手技能，以『AI立法时代正式开启』为主题写一篇小红书帖子并发布
```

AI 会自动完成：

1. 生成包含 YAML frontmatter 的 Markdown 文案（确保封面图正常生成）
2. 保存到独立子文件夹（如 `2026-06-16_AI立法时代/`）
3. 默认使用新版渲染器生成封面和卡片图片
4. 调用发布脚本私密发布到小红书

**指定旧版渲染器：**

```
🧑 您: 用初代渲染器，以『AI立法时代』为主题写一篇帖子
```

**公开发布：**

```
🧑 您: 公开发布，以『AI立法时代』为主题写一篇帖子
```

---

## 📋 文案写作铁律

> AI 自动遵守以下规则，无需手动干预。

| 规则 | 说明 |
| :--- | :--- |
| **标题字数** | 封面主标题 ≤15字，副标题 ≤10字，发布标题 ≤18字 |
| **YAML frontmatter** | 文件开头必须包含 `emoji`、`title`、`subtitle` 元数据 |
| **卡片排版** | 每张卡片 3~4 行带 emoji 的列表项，可选 `> 金句` 高亮块 |
| **进度条** | 最多 5 个方块（`█████ 80%`），严禁长条 |
| **禁止事项** | 严禁中英文括号，严禁底部整行装饰 emoji |
| **干货感** | 像行业专家分享，严禁口语化表达 |

---

## 🙏 致谢与渊源

本项目深度依赖 **[Auto-Redbook-Skills](https://github.com/comeonzhj/Auto-Redbook-Skills)** 提供的渲染和发布能力，原项目采用 MIT 许可证。

- **原项目作者：** @comeonzhj
- **本项目的创新：** 引入 DeepSeek API 作为 AI 大脑，实现从「写 Markdown → 渲染 → 发布」的全流程自动化，用户仅需一句自然语言即可完成

感谢原作者的出色工作！

---

## 📌 相关链接

- [Auto-Redbook-Skills（原项目）](https://github.com/comeonzhj/Auto-Redbook-Skills)
- [DeepSeek API 文档](https://platform.deepseek.com/usage)

---

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
