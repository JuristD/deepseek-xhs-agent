#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek 技能执行器 - 小红书专业版
- 自动发现技能包（支持 SKILL 或 SKILL.md）
- 嵌入严格的写作规范（标题字数、排版、干货、进度条限制）
- 自动保存文案到技能包根目录下的独立子文件夹
- 默认使用新版渲染器 (render_xhs_v2.py)，旧版仅当用户要求时使用
- 自动执行渲染和发布命令（私密发布）
"""

import os
import re
import json
import subprocess
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not API_KEY:
    print("❌ 错误: 未找到 DEEPSEEK_API_KEY")
    print("请在项目根目录创建 .env 文件，内容为: DEEPSEEK_API_KEY=你的密钥")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# ============================================================
# 技能发现路径
# ============================================================
SKILL_PATHS = [
    Path.cwd() / "skills",               # 项目级技能目录
    Path.home() / ".claude" / "skills",  # Claude 用户级标准目录
]

# ============================================================
# 技能类（兼容 SKILL 和 SKILL.md）
# ============================================================
class Skill:
    def __init__(self, path: Path):
        self.path = path
        self.name = path.name
        self.description = ""
        self.instruction = ""
        self._load()

    def _load(self):
        skill_file = self.path / "SKILL.md"
        if not skill_file.exists():
            skill_file = self.path / "SKILL"
        if not skill_file.exists():
            return
        content = skill_file.read_text(encoding='utf-8')
        match = re.search(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
        if match:
            import yaml
            try:
                metadata = yaml.safe_load(match.group(1))
                if metadata.get("name"):
                    self.name = metadata["name"]
                if metadata.get("description"):
                    self.description = metadata["description"]
                self.instruction = match.group(2).strip()
            except:
                pass
        if not self.description:
            text = re.sub(r'[#*>\-]', '', content[:200])
            self.description = text.strip().split('\n')[0][:80]
        if not self.description:
            self.description = f"技能 '{self.name}' 可根据说明执行任务"

# ============================================================
# 全局技能字典
# ============================================================
_skills_dict = {}

def find_skill_by_name(name: str):
    if not name:
        return None
    if name in _skills_dict:
        return _skills_dict[name]
    norm_name = name.replace('-', '_')
    if norm_name in _skills_dict:
        return _skills_dict[norm_name]
    lower_name = name.lower()
    for key, skill in _skills_dict.items():
        if key.lower() == lower_name or skill.name.lower() == lower_name:
            return skill
    return None

# ============================================================
# 工具函数（支持子目录创建、编码修复）
# ============================================================
def save_markdown_file(skill_name: str, filename: str, content: str) -> str:
    skill = find_skill_by_name(skill_name)
    if not skill:
        return f"❌ 错误：未找到名为 '{skill_name}' 的技能包"
    try:
        if not filename.endswith('.md'):
            filename += '.md'
        filepath = skill.path / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)  # 自动创建子目录
        filepath.write_text(content, encoding='utf-8')
        return f"✅ 文件已保存到: {filepath}"
    except Exception as e:
        return f"❌ 保存失败: {str(e)}"

def run_powershell_command(skill_name: str, command: str) -> str:
    skill = find_skill_by_name(skill_name)
    if not skill:
        return f"❌ 错误：未找到名为 '{skill_name}' 的技能包"
    try:
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',   # 避免 Unicode 解码报错
            timeout=120,
            cwd=str(skill.path)
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            return f"✅ 命令执行成功\n输出: {output if output else '(无输出)'}"
        else:
            error = result.stderr.strip()
            return f"❌ 命令执行失败 (返回码 {result.returncode})\n错误: {error}"
    except subprocess.TimeoutExpired:
        return "❌ 命令执行超时（超过120秒）"
    except Exception as e:
        return f"❌ 执行出错: {str(e)}"

# ============================================================
# 工具定义（供 DeepSeek 调用）
# ============================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_markdown_file",
            "description": "将生成的Markdown文案保存到指定技能包下的文件中，支持子目录（如 '2026-06-16_主题/文件名.md'）。需要指定技能包名称、文件名和内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "技能包名称，例如 '小红书写手'"},
                    "filename": {"type": "string", "description": "文件名（可含子目录，如 '2026-06-16_AI新闻/AI新闻.md'）"},
                    "content": {"type": "string", "description": "完整的Markdown文案内容"}
                },
                "required": ["skill_name", "filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell_command",
            "description": "在技能包根目录下执行PowerShell命令。需要指定技能包名称和命令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "技能包名称，例如 '小红书写手'"},
                    "command": {"type": "string", "description": "要执行的PowerShell命令，例如 'cd .\\2026-06-16_AI新闻 && python ..\\scripts\\render_xhs_v2.py .\\AI新闻.md'"}
                },
                "required": ["skill_name", "command"]
            }
        }
    }
]

# ============================================================
# 主函数
# ============================================================
def main():
    global _skills_dict
    print("\n🤖 DeepSeek 小红书技能执行器启动中...\n")

    # 发现技能
    skills = {}
    for base_path in SKILL_PATHS:
        if not base_path.exists():
            continue
        for skill_dir in base_path.iterdir():
            if not skill_dir.is_dir():
                continue
            if not (skill_dir / "SKILL.md").exists() and not (skill_dir / "SKILL").exists():
                continue
            skill = Skill(skill_dir)
            norm_name = skill.name.replace('-', '_')
            skills[norm_name] = skill
            skills[skill.name] = skill
            print(f"✅ 发现技能: {skill.name} - {skill.description[:60]}...")

    if not skills:
        print("\n❌ 未找到任何有效技能。请确保：")
        print("1. 在项目目录下创建 'skills' 文件夹")
        print("2. 将技能包文件夹放入 'skills' 内")
        print("3. 技能包文件夹中包含 'SKILL.md' 或 'SKILL' 文件")
        return

    _skills_dict = skills

    # ============================================================
    # 小红书写作铁律 + 渲染器说明 + 产物隔离规则
    # ============================================================
    writing_rules = """
## 【小红书文案写作铁律 - 必须100%遵守】

### 1. 标题字数硬性限制
- 封面主标题 ≤15字
- 封面副标题 ≤10字
- 发布时的 `--title` 参数内容 **必须 ≤18字**（包括标点、数字、英文字母）。超出一条都算失败。

### 2. Markdown 文件格式（必须严格遵守）
- **文件开头必须包含以下 YAML frontmatter**，用于生成封面图：

---
emoji: "📚"
title: "封面主标题（≤15字）"
subtitle: "封面副标题（≤10字）"
---

这三行之后空一行，再写正文内容。

### 3. 正文卡片排版规则
- 每张卡片包含：一个标题 + 3~4 行带 emoji 的列表项 + 可选一句 `> 金句`（推荐使用）。
- 每行列表项以功能性 emoji 开头（如 📌、🔑、💡、✨），不要整行纯装饰 emoji。
- 可使用 **加粗**（`**文字**`）、`代码块`（`` `代码` ``）或 `==高亮==` 增强层次。
- 卡片之间用 `---` 分隔。
- 尽量让文字在卡片中均匀分布，最终排版效果以渲染脚本为准。

### 4. 进度条使用规则
- 不是固定格式。仅在需要展示完成度时使用，最多 5 个方块（`█████ 80%`），严禁使用长条。

### 5. 内容质量要求（干货感）
- 像行业专家分享经验、方法、数据或洞察。
- 严禁口语化表达（如“我觉得”“大家一定要试试”）。
- 每张卡片传递一个清晰的知识点，连起来构成完整价值。

### 6. 禁止事项
- 严禁出现任何中英文括号：`()` `[]` `{}` `【】`。
- 严禁在卡片底部添加多余的整行装饰 emoji。

### 7. 卡片数量
- 根据内容多少自动决定，通常 3~5 张。

## 【渲染器执行说明】
- **默认使用新版渲染器** `scripts/render_xhs_v2.py`（功能更丰富，支持封面元数据解析）。
- **仅当用户明确要求“旧版”或“初代”时**，才使用 `scripts/render_xhs.py`。
- 文案排版建议：让文字在卡片中均匀分布；用 `> ` 创建高亮金句，用 `` `代码` `` 或 `==高亮==` 增强视觉层次。最终渲染效果以脚本实际执行为准。

## 【产物隔离规则】
- 每次运行必须生成一个独立的子文件夹，命名格式：`YYYY-MM-DD_主题关键词`（例如 `2026-06-16_AI立法`）。
- 所有产物（.md 文件、cover.png、card_*.png）必须存放在该子文件夹内，严禁混在技能包根目录。
- 渲染和发布命令执行前，必须通过 `cd` 切换到该子文件夹，以确保图片生成在正确位置。
- 禁止重复使用旧封面图或旧卡片图。

## 【发布指令参数】

### 必填参数
| 参数 | 说明 | 限制 |
| :--- | :--- | :--- |
| `--title` | 小红书笔记标题 | **必须 ≤18字** |
| `--desc` | 小红书笔记正文 | 150字左右，超过需分段/分点，末尾带5个标签 |
| `--images` | 图片列表 | `cover.png card_1.png ...` |

### 可选参数
| 参数 | 说明 |
| :--- | :--- |
| `--public` | 公开发布（默认不加，即私密） |
| `--post-time` | 定时发布 |
| `--dry-run` | 预演模式 |

### 发布命令示例
```bash
# 私密发布（默认）
python scripts/publish_xhs.py --title "18字内标题" --desc "描述（建议150字左右，超过则用emoji如✅、📌、🌟等进行分段，让内容活泼有层次）  #标签1 #标签2 #标签3 #标签4 #标签5" --images cover.png card_1.png card_2.png

"""

    skills_list = "\n".join([f"- {name}" for name in skills.keys()])
    system_prompt = rf"""你是一个能够自主执行任务的AI助手。你可以使用以下工具：保存文件、执行PowerShell命令。

当前已安装的技能包：
{skills_list}

{writing_rules}

## 当用户要求使用某个技能时，你必须严格按照以下步骤自主完成：

1. **生成一个唯一的文件夹名**，格式为：`YYYY-MM-DD_主题关键词`（例如 `2026-06-16_AI立法`）。该文件夹将用于存放本次生成的所有产物。

2. 根据用户提供的主题或素材，按照上述「小红书文案写作铁律」生成完整的小红书笔记内容（不要用代码框包裹，直接输出纯文本），格式必须符合技能包要求的 Markdown 结构，并且 **必须包含 YAML frontmatter**（即文件开头有 `---` 包裹的 `emoji`、`title`、`subtitle` 元数据）。

3. 调用 `save_markdown_file` 工具，参数中 `skill_name` 填写技能包名称，`filename` 填写 **`{{文件夹名}}/{{文件名}}.md`**（例如 `2026-06-16_AI立法/AI立法时代.md`），`content` 填写你刚生成的完整文案。

4. **调用 `run_powershell_command` 工具，执行渲染命令**：
   - **默认使用新版**：`cd .\{{文件夹名}} && python ..\scripts\render_xhs_v2.py .\{{文件名}}.md [用户要求的其他参数]`
   - 若用户明确要求“旧版”或“初代”，则使用：`cd .\{{文件夹名}} && python ..\scripts\render_xhs.py .\{{文件名}}.md [参数]`
   - 若用户未指定参数，直接执行（脚本将使用内置默认值）。
   - 不要解释参数，直接按用户要求构建命令。

5. **调用 `run_powershell_command` 工具，执行发布命令**：
   - 在子文件夹内执行：`cd .\{{文件夹名}} && python ..\scripts\publish_xhs.py --title "标题" --desc "描述  #标签1 #标签2 #标签3 #标签4 #标签5" --images cover.png card_1.png ...`
   - 标题必须 ≤18字，默认不加 `--public`（私密发布）。
   - 仅当用户明确要求“公开发布”时，才在命令末尾添加 `--public`。

注意：
- 生成文案时必须在文件开头包含 YAML frontmatter，否则封面图无法生成。
- 渲染命令默认使用 V2 版，旧版需用户明确要求。
- 所有产物（md、图片）必须放在独立的子文件夹内。
- 不要询问用户确认，直接执行所有步骤。
- 如果任何步骤失败，请向用户报告错误。"""

    messages = [{"role": "system", "content": system_prompt}]

    print("\n✨ 就绪！直接输入您的需求即可。")
    print("💡 示例：使用小红书写手技能，以『AI立法时代』为主题写一篇帖子并发布\n")

    while True:
        user_input = input("🧑 您: ").strip()
        if user_input.lower() in ["退出", "exit", "quit"]:
            print("👋 再见！")
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        while True:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            assistant_msg = response.choices[0].message
            messages.append(assistant_msg)

            if assistant_msg.tool_calls:
                for tool_call in assistant_msg.tool_calls:
                    tool_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    print(f"\n🔧 执行工具: {tool_name}")
                    if tool_name == "save_markdown_file":
                        result = save_markdown_file(
                            args.get("skill_name", ""),
                            args.get("filename", ""),
                            args.get("content", "")
                        )
                    elif tool_name == "run_powershell_command":
                        result = run_powershell_command(
                            args.get("skill_name", ""),
                            args.get("command", "")
                        )
                    else:
                        result = f"未知工具: {tool_name}"
                    print(f"📋 结果: {result[:200]}...")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                continue
            else:
                if assistant_msg.content:
                    print(f"\n🤖 {assistant_msg.content}\n")
                break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 再见！")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
  