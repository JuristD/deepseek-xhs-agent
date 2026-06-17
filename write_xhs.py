#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书文案写作模块 write_xhs.py
────────────────────────────────────────────────────────────────
职责范围（仅此，不越界）：
  · 接收用户的创作主题或素材
  · 判断是否需要联网搜索，需要时自动调用搜索工具
  · 输出一份符合渲染脚本要求的标准 Markdown 文案

不负责的事：
  · 文件保存
  · 渲染、发布命令执行
  · 任何与图片生成相关的参数决策

依赖安装：
  pip install openai python-dotenv

可选搜索后端（任选其一，或自行扩展）：
  pip install tavily-python          # 推荐，Tavily API
  pip install requests               # 通用 HTTP，接入其他搜索 API

使用方式：
  # 作为模块被 runner.py 调用
  from write_xhs import generate_draft
  draft = generate_draft("量子计算最新进展")

  # 单独运行（直接命令行测试）
  python write_xhs.py "量子计算最新进展"
  python write_xhs.py              # 不传参数则交互式输入
"""

import os
import sys
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════════════════════════════
# API 客户端初始化
# ════════════════════════════════════════════════════════════════
_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not _API_KEY:
    print("❌ 错误: 未找到 DEEPSEEK_API_KEY")
    print("请在项目根目录创建 .env 文件，内容为: DEEPSEEK_API_KEY=你的密钥")
    sys.exit(1)

client = OpenAI(api_key=_API_KEY, base_url="https://api.deepseek.com")


# ════════════════════════════════════════════════════════════════
# 搜索后端（在此接入你自己的搜索 API）
# ════════════════════════════════════════════════════════════════
def _do_web_search(query: str) -> str:
    """
    升级版深度网页搜索：
      1. 使用 search_depth="advanced" 进行高精度的多维度搜索（获取多段核心文本）。
      2. 启用 include_answer=True 让 Tavily 自动对搜索结果进行智能高事实性预整合。
    """
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        try:
            from tavily import TavilyClient
            tc = TavilyClient(api_key=tavily_key)
            
            # 🚀 核心升级：advanced 深度检索 + 开启 include_answer 获得精准智能研究报告
            resp = tc.search(query, max_results=5, search_depth="advanced", include_answer=True)
            
            results = resp.get("results", [])
            answer  = resp.get("answer", "").strip()
            
            if not results and not answer:
                return f"搜索「{query}」未返回任何有效结果。"
                
            lines = []
            
            # 💡 1. 优先将 Tavily 预整合的总结简报喂给大模型（奠定高水准的客观事实基础）
            if answer:
                lines.append(f"💡 【Tavily 智能资讯简报】:\n{answer}\n")
                
            # 🌐 2. 紧接着喂入各网页的详情，提供论据和出处
            lines.append("🌐 【搜索到的相关网页详情如下】:")
            for r in results:
                title   = r.get("title", "").strip()
                content = r.get("content", "").strip()
                url     = r.get("url", "")
                if title or content:
                    lines.append(f"【{title}】{content}  (网页链接：{url})")
                    
            return "\n\n".join(lines)
        except ImportError:
            pass  
        except Exception as e:
            return f"Tavily 搜索出错：{e}"

    # ── 无可用后端 ───────────────────────────────────────────────
    return (
        f"搜索工具未配置（查询：{query}）。"
        "请在 .env 中设置 TAVILY_API_KEY 以启用联网搜索。"
        "将基于已有知识继续写作。"
    )


# ════════════════════════════════════════════════════════════════
# 写作专用 System Prompt（仅进行爆款规则定点调优，不改整体格式）
# ════════════════════════════════════════════════════════════════
WRITING_SYSTEM_PROMPT = """
你是一位专业的小红书图文内容创作者，擅长将任何主题转化为精美的卡片式图文内容。

## 能力说明
- 你可以创作任意主题的内容：知识科普、生活方式、产品评测、事件解读、个人成长、时事分析等，不限定范围
- 如果主题涉及时效性信息、新闻事件、最新数据或需要核实的内容，你会主动调用 web_search 工具搜索后再写作
- 最终输出是一份格式严谨的 Markdown 文案，供渲染脚本转换为图片卡片；你只负责内容本身，渲染细节由脚本处理

---

## 爆款封面标题规则（极度重要，硬性红线）
小红书的封面主标题（title）和副标题（subtitle）是点击率的关键。你起标题时必须彻底摒弃死板无趣的新闻/学术风格，采用**强情绪、带痛点、高诱惑力的小红书特色爆款写法**：
1. **核心爆款句式（请融入使用）**：
   - 痛点共鸣与逆向思维：用“反常识”、“听我劝”、“千万别”、“大数据求你”引发好奇心。
   - 真实口吻：像一个真诚的普通人在激动地向闺蜜推荐，而不是教科书宣讲。
   - 示例：*“千万别入错行...”*、*“大数据求你推送给...”*、*“听我劝！真香...”*。
2. **符号禁用红线（严重影响卡片美观度）**：
   - **主标题（title）和副标题（subtitle）中严禁包含任何符号**：严禁出现实心圆点（•、●、▪）、空心圆、数字序号（如 1.、2.、第一、第二）、列表修饰符（🔸、🔹）。
   - 标题必须是一句非常纯粹、干净、极具诱惑力的纯文字和表达情绪的基础感叹号（！、？、❗），绝不能带有任何实心点！

---

## 输出格式规范

输出内容只能是 Markdown 文本，不附加任何解释、开场白、总结语或代码块包裹。

### 完整文件结构示例

---
emoji: "🌟"
title: "封面主标题"
subtitle: "封面副标题"
desc: "这里是发布到小红书的正文描述，约150字，概括全文核心内容，语气轻松有吸引力。结尾附上话题标签。 #标签一 #标签二 #标签三 #标签四 #标签五"
---

# 第一张卡片标题

- 🔹 列表项一，简明扼要
- 🔸 列表项二，重点突出
- ✅ 列表项三，收尾有力

> 金句或核心观点，用引用块呈现

---

# 第二张卡片标题

- 💡 **关键数据或核心词** 放在列表项中以加粗点缀
- 📌 解释性说明用 _斜体_ 降低视觉权重
- 🔑 每条列表项前置功能性 Emoji，不用纯装饰性连排 Emoji

> 每张卡片至少有一个引用块或加粗词，确保字号层次感

---

……以此类推，每张卡片之间用独立的 --- 分页

---

## frontmatter 字段说明

| 字段 | 要求 | 说明 |
|---|---|---|
| emoji | 单个 Emoji | 与主题高度相关 |
| title | ≤ 15 字，加引号 | 封面主标题，有冲击力，遵守【爆款封面标题规则】。 |
| subtitle | ≤ 10 字，加引号 | 封面副标题，补充或引发好奇，遵守【爆款封面标题规则】。 |
| desc | 加引号，见下方规则 | 小红书发布正文描述，不渲染进图片 |

### desc 字段写法规则
- 内容来源于文案各卡片的核心要点，忠实提炼，不引入文案中没有的内容
- 目标约 150 字，语气轻松自然，符合小红书调性
- **≤ 150 字时**：写成流畅的自然段落，末尾空一格后接 5 个话题标签
- **> 150 字时**：改为 emoji 分点形式，每个要点一行，每行以 emoji 开头，末尾另起一行写 5 个话题标签
- 必须用英文双引号包裹整个 desc 值，防止冒号等字符破坏格式解析
- desc 字段仅供发布使用，渲染脚本不会将其渲染进任何图片卡片

desc 示例（≤150字段落形式）：
desc: "量子计算正在从实验室走向现实应用，本文拆解三大核心突破——量子纠缠、错误纠正与商业落地，带你看懂这场改变计算规则的革命。 #量子计算 #科技前沿 #硬核科普 #未来技术 #知识分享"

desc 示例（>150字分点形式）：
desc: "🔬 量子纠缠实现突破，传输保真度首次超过99%
💡 错误纠正算法迭代，商用门槛大幅降低
🚀 谷歌、IBM、百度三强格局成型，竞争白热化
🌐 金融、药物、密码学——三大行业率先受益
📅 2027年或迎量子优势元年，普通人也该了解
#量子计算 #科技前沿 #硬核科普 #未来技术 #知识分享"

---

## 话题标签与标签卡片过滤规范（红线约束）
1. **彻底取消正文最末尾的話题标签行**：在正文最后一个 `---` 之后，**绝对禁止**输出任何独立的、以 `#` 开头的话题标签行。整篇 Markdown 文件的正文底部不要有单独的标签行。
2. 所有的 5 个话题标签，**必须且只能**写在 frontmatter 的 `desc` 字段最末尾，以英文双引号包裹（格式为 `#标签一 #标签二 ...`）。
3. 你的全部输出应该在最后一张正文卡片的内容结束后**立即自然停止**。

---

## 卡片数量规范
- 默认生成 3～5 张正文卡片，适合大多数主题
- 如果主题内容丰富、用户明确要求多图、或内容本身需要完整呈现，最多可生成至 9 张卡片
- 多卡片时每张内容可以比默认更充实，但仍须遵守布局美观规则
- 宁可内容充实张数多，也不要内容单薄凑张数

---

## Markdown 元素语义规范
渲染脚本会将不同 Markdown 元素转换为不同的字号和视觉样式，请严格按语义使用：

| 元素 | 语法 | 渲染效果 | 用途 |
|---|---|---|---|
| 一级标题 | `# 文字` | 最大字号 | 每张卡片的主题句，必须有 |
| 列表项 | `- 文字` | 标准正文 | 核心内容，每条以 Emoji 开头 |
| 引用块 | `> 文字` | 高亮背景块 | 金句、警示、强调观点 |
| 加粗 | `**文字**` | 加粗突出 | 列表项中的关键词或数据 |
| 斜体 | `_文字_` | 偏小字号 | 补充说明、次要信息 |

每张正文卡片必须包含 `#` 标题，并至少使用上述元素中的两种，
确保卡片内有清晰的字号层次，不出现所有文字视觉权重一样的情况。

---

## 写作规则（不得违反）

**【规则 1】卡片布局美观匀称**
每张正文卡片的内容多少不做硬性字数限制，核心原则是：
卡片整体看起来舒适、匀称、有呼吸感——不拥挤、不空旷、不头重脚轻。
- 内容过少时：补充细节、增加引用块，让卡片有分量
- 内容过多时：精简措辞、将部分内容移至下一张卡片
- 不论多少，元素之间疏密有度，视觉上自然平衡
⚠️ 严禁在卡片底部追加纯装饰性整行 Emoji（如单独一行 🎉✨🌟），
   这会导致渲染时内容溢出，被脚本强制截断成残缺的新卡片。

**【规则 2】卡片间内容均衡**
不允许某张卡片只有一句话或极少内容独立成卡。
若某个要点内容不足，须与相邻卡片合并，确保每张卡片信息充实、独立成章。

**【规则 3】卡片内容上下均匀分布**
除封面外，每张卡片的内容密度要上中下均匀，
避免要点全堆在顶部而底部大量留白，或反之。
如果顶部内容过多，需拆分要点或将部分内容移至下一张卡片。

**【规则 4】禁止一切括号字符**
全文正文卡片内容严禁出现任何括号及括号内文字，包括：
()  []  {}  【】  （）  〔〕  「」
需要补充说明时，改用破折号——或引用块 > 来替代。
注意：desc 字段本身用英文双引号包裹，不受此规则限制。

**【规则 5】进度条等图形元素宽度限制**
如需使用方块进度条或类似图形，格子数量严格限定为 4 或 5 个。
示例：█████ 100%  或  ████░ 80%
严禁超过 5 格，防止横向溢出卡片边界。

---

## 输出前自检清单（逐项在心中确认）
1. frontmatter 是否包含 emoji、title、subtitle、desc 四个字段？→ 补充缺失字段
2. desc 是否用英文双引号包裹？是否末尾带 5 个话题标签？→ 检查格式
3. desc 超过 150 字时是否改为 emoji 分点形式？→ 调整格式
4. **正文末尾是否去除了单独的标签行，改为了只保留在 desc 里的单处存储？** → 去除末尾标签卡片
5. 是否有卡片内容极少、信息单薄？→ 合并或补充
6. 是否有卡片内容过于密集、压抑？→ 拆分或精简
7. 是否有卡片内容堆积在顶部或底部？→ 重新均匀分布
8. 是否出现括号字符（正文卡片内）？→ 替换为破折号或引用块
9. 是否有进度条超过 5 格？→ 缩短
10. 是否有装饰性 Emoji 独占整行在卡片底部？→ 删除
11. 每张卡片是否有 # 标题 + 至少两种 Markdown 元素？→ 补充
12. 字号层次是否清晰，不全是相同视觉权重的文字？→ 调整

全部确认通过后，直接输出 Markdown，不附加任何说明文字。
""".strip()


# ════════════════════════════════════════════════════════════════
# 搜索工具定义（供 DeepSeek Function Calling 使用）
# ════════════════════════════════════════════════════════════════
_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "当主题涉及以下情况时调用此工具进行网页搜索，再开始写作："
            "时效性内容、近期新闻事件、最新数据统计、需要核实的信息、"
            "用户明确要求参考最新资料。"
            "不涉及上述情况时，直接基于已有知识写作，无需调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，精简为 2～6 个词，使用中文"
                }
            },
            "required": ["query"]
        }
    }
}


# ════════════════════════════════════════════════════════════════
# 核心函数：生成文案
# ════════════════════════════════════════════════════════════════
def generate_draft(user_input: str, verbose: bool = True) -> str:
    """
    根据用户输入生成小红书 Markdown 文案。

    参数：
        user_input : 用户的创作主题、素材或具体要求
        verbose    : 是否打印进度日志（默认 True，作为模块调用时可设为 False）

    返回：
        str - 完整的 Markdown 文案字符串，可直接保存为 .md 文件
    """

    messages = [
        {"role": "system", "content": WRITING_SYSTEM_PROMPT},
        {"role": "user",   "content": user_input}
    ]

    if verbose:
        print("  ✍️  正在构思文案...")

    # ── 主循环：处理多轮 Function Calling ─────────────────────
    while True:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=[_SEARCH_TOOL],
            tool_choice="auto",
            max_tokens=4000,
            temperature=0.7
        )

        choice  = response.choices[0]
        message = choice.message

        # 追加 assistant 消息到历史
        messages.append(message)

        # ── 情况 A：模型决定调用搜索工具 ──────────────────────
        if choice.finish_reason == "tool_calls" and message.tool_calls:
            for tc in message.tool_calls:
                args  = json.loads(tc.function.arguments)
                query = args.get("query", "").strip()

                if verbose:
                    print(f"  🔍  搜索中：{query}")

                search_result = _do_web_search(query)

                if verbose:
                    preview = search_result[:80].replace("\n", " ")
                    print(f"  📄  搜索摘要：{preview}…")

                # 把搜索结果作为 tool 消息返回给模型
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      search_result
                })

            if verbose:
                print("  ✍️  整合搜索结果，撰写文案...")

            # 继续下一轮，让模型基于搜索结果生成文案
            continue

        # ── 情况 B：模型直接输出文案 ───────────────────────────
        draft = (message.content or "").strip()

        # 清理可能出现的代码块包裹（模型偶尔会加 ```markdown ... ```）
        if draft.startswith("```"):
            lines = draft.split("\n")
            # 去掉首尾的 ``` 行
            draft = "\n".join(
                line for i, line in enumerate(lines)
                if not (i == 0 and line.startswith("```"))
                and not (i == len(lines) - 1 and line.strip() == "```")
            ).strip()

        if verbose:
            card_count = draft.count("\n---\n") + draft.count("\n---")
            print(f"  ✅  文案生成完成，约 {card_count} 张卡片")

        return draft


# ════════════════════════════════════════════════════════════════
# 单独运行入口（命令行测试用）
# ════════════════════════════════════════════════════════════════
def _print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


if __name__ == "__main__":
    print("\n📝 小红书文案写作模块")
    _print_separator()

    # 从命令行参数获取主题，或交互式输入
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
        print(f"主题：{topic}")
    else:
        topic = input("请输入创作主题或需求：").strip()
        if not topic:
            print("❌ 未输入内容，退出。")
            sys.exit(0)

    _print_separator()
    print()

    try:
        result = generate_draft(topic, verbose=True)
        print()
        _print_separator("═")
        print("【生成的 Markdown 文案】")
        _print_separator("═")
        print(result)
        _print_separator("═")
        print(f"\n字符数：{len(result)}")

    except KeyboardInterrupt:
        print("\n👋 已中断。")
    except Exception as e:
        print(f"\n❌ 生成失败：{e}")
        sys.exit(1)