#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — 小红书自动化代理主入口
────────────────────────────────────────────────────────────────
目录结构预期：
  my_agent/
    skill_runner.py     ← 本文件
    草稿.md             ← 用户复用草稿（工作流 B 固定入口）
    skills/
      .env              ← 存放 DEEPSEEK_API_KEY 和发布 Cookie 
      write_xhs.py      ← 写作模块
      scripts/
        render_xhs_v2.py   ← 渲染新版 Python（默认）
        render_xhs.py      ← 渲染旧版 Python
        publish_xhs.py     ← 发布脚本
    outputs/
      YYYY-MM-DD_关键词/
        草稿.md / 文案.md
        cover.png
        card_1.png ...

工作流：
  A. 写作+执行  — 用户输入主题，write_xhs 生成文案，渲染，发布
  B. 直接执行   — 用户说"草稿"，读取草稿.md，渲染，发布
  B2. 草稿扩写  — 用户说"以草稿为..."，草稿内容+要求传给写作模块

渲染版本：
  默认                      → render_xhs_v2.py
  旧版 / 经典版 / v1版      → render_xhs.py
"""

import os
import re
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

ROOT = Path(__file__).parent

# ── 写作模块（同 skills/ 目录）────────────────────────────────
sys.path.insert(0, str(ROOT / "skills"))
from write_xhs import generate_draft

# ════════════════════════════════════════════════════════════════
# 路径常量
# ════════════════════════════════════════════════════════════════
SKILLS_DIR  = ROOT / "skills"
SCRIPTS_DIR = SKILLS_DIR / "scripts"
OUTPUTS_DIR = ROOT / "outputs"
DRAFT_FILE  = ROOT / "草稿.md"

RENDER_DEFAULT = SCRIPTS_DIR / "render_xhs_v2.py"   # Python 新版 (默认)
RENDER_V1_PY   = SCRIPTS_DIR / "render_xhs.py"       # Python 旧版
PUBLISH_PY     = SCRIPTS_DIR / "publish_xhs.py"

# ════════════════════════════════════════════════════════════════
# API 客户端
# ════════════════════════════════════════════════════════════════
# 强制读取 skills 目录下的 .env 以确保进程全局变量统一
load_dotenv(SKILLS_DIR / ".env", override=True)
_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not _API_KEY:
    print("❌ 未在 skills/.env 文件中找到 DEEPSEEK_API_KEY")
    sys.exit(1)

client = OpenAI(api_key=_API_KEY, base_url="https://api.deepseek.com")


# ════════════════════════════════════════════════════════════════
# 渲染版本识别
# ════════════════════════════════════════════════════════════════
def detect_render_version(user_input: str) -> tuple[Path, str]:
    """
    根据用户输入判断使用哪个渲染脚本。
    返回 (脚本路径, 执行命令前缀)
    """
    text = user_input.lower()

    # 1. 输入包含“旧版/经典/v1”：运行旧版 render_xhs.py (Python)
    if any(k in text for k in ["旧版", "经典版", "v1版", "v1渲染", "render旧"]):
        return RENDER_V1_PY, "python"

    # 2. 默认：直接运行新版 render_xhs_v2.py (Python)
    return RENDER_DEFAULT, "python"


# ════════════════════════════════════════════════════════════════
# Markdown 工具函数
# ════════════════════════════════════════════════════════════════
def parse_frontmatter(md_content: str) -> dict:
    """提取 YAML frontmatter 字段，返回 dict（不依赖 pyyaml）"""
    # 改为 search，防止大模型在开头说废话导致匹配失败
    pattern = r'---\s*\n(.*?)\n---\s*\n'
    match = re.search(pattern, md_content, re.DOTALL)
    if not match:
        return {}
    result = {}
    for line in match.group(1).splitlines():
        if ':' in line:
            key, _, val = line.partition(':')
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def extract_body(md_content: str) -> str:
    """去除 frontmatter，返回正文"""
    pattern = r'^---\s*\n.*?\n---\s*\n'
    return re.sub(pattern, '', md_content, count=1, flags=re.DOTALL).strip()


# ════════════════════════════════════════════════════════════════
# 输出文件夹命名
# ════════════════════════════════════════════════════════════════
def make_output_folder_name(title: str) -> str:
    """
    根据标题生成输出文件夹名：YYYY-MM-DD_关键词
    取标题前 10 字，去除特殊字符
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    # 清理文件名不合法字符
    safe_title = re.sub(r'[\\/:*?"<>|]', '', title).strip()
    keyword = safe_title[:10]
    return f"{date_str}_{keyword}"


# ════════════════════════════════════════════════════════════════
# 发布参数提取（直接从 frontmatter 读取，由写作模块负责生成）
# ════════════════════════════════════════════════════════════════
def build_publish_params(md_content: str) -> dict:
    """
    从 frontmatter 直接提取发布参数。
    title 和 desc 均由写作模块在生成文案时一并写入，
    runner.py 只做读取，不做任何推断或改写。
    """
    meta = parse_frontmatter(md_content)

    title = meta.get("title", "")
    if not title:
        raise ValueError("❌ frontmatter 缺少 title 字段，请检查文案")

    desc = meta.get("desc", "")
    if not desc:
        raise ValueError("❌ frontmatter 缺少 desc 字段，请检查写作模块输出")

    # 发布标题截断到 18 字（frontmatter title ≤15字，此处作为保险）
    pub_title = title[:18]

    return {
        "title": pub_title,
        "desc":  desc,
    }


# ════════════════════════════════════════════════════════════════
# 命令执行
# ════════════════════════════════════════════════════════════════
def run_command(command: str, cwd: Path, label: str = "") -> bool:
    """
    执行 shell 命令，打印输出，返回是否成功。
    """
    print(f"\n  ▶ {label or command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=False,   # 直接输出到终端，方便调试
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180
        )
        if result.returncode == 0:
            print(f"  ✅ 成功")
            return True
        else:
            print(f"  ❌ 失败（返回码 {result.returncode}）")
            return False
    except subprocess.TimeoutExpired:
        print("  ❌ 超时（超过 180 秒）")
        return False
    except Exception as e:
        print(f"  ❌ 执行出错：{e}")
        return False


# ════════════════════════════════════════════════════════════════
# 渲染
# ════════════════════════════════════════════════════════════════
def render(md_path: Path, output_dir: Path,
           render_script: Path, render_cmd: str) -> bool:
    """
    调用渲染脚本，将 md 文件渲染为图片，输出到 output_dir。
    md_path 和 output_dir 均为绝对路径。
    """
    # 相对于 output_dir 的 md 文件名（渲染脚本在 output_dir 里执行）
    md_rel    = md_path.name
    script_abs = render_script.resolve()

    if render_cmd == "node":
        cmd = f'node "{script_abs}" "{md_rel}" -o .'
    else:
        cmd = f'python "{script_abs}" "{md_rel}" --output-dir .'

    return run_command(cmd, cwd=output_dir, label=f"渲染 [{render_script.name}]")


# ════════════════════════════════════════════════════════════════
# 发布
# ════════════════════════════════════════════════════════════════
def publish(output_dir: Path, pub_params: dict, public: bool = False) -> bool:
    """
    扫描 output_dir 中的图片，构建发布命令并执行。
    图片顺序：cover.png 优先，然后 card_1.png ... card_9.png
    """
    # 收集图片文件
    images = []
    cover = output_dir / "cover.png"
    if cover.exists():
        images.append("cover.png")

    for i in range(1, 10):
        card = output_dir / f"card_{i}.png"
        if card.exists():
            images.append(f"card_{i}.png")

    if not images:
        print("  ❌ 未找到任何图片文件，发布中止")
        return False

    print(f"  📸 共找到 {len(images)} 张图片：{', '.join(images)}")

    # 转义引号，防止 desc 中的特殊字符破坏命令
    title_safe = pub_params["title"].replace('"', '\\"')
    desc_safe  = pub_params["desc"].replace('"', '\\"')
    images_str = " ".join(f'"{img}"' for img in images)
    script_abs = PUBLISH_PY.resolve()

    cmd = (
        f'python "{script_abs}"'
        f' --title "{title_safe}"'
        f' --desc "{desc_safe}"'
        f' --images {images_str}'
    )
    if public:
        cmd += " --public"

    return run_command(cmd, cwd=output_dir, label="发布到小红书")


# ════════════════════════════════════════════════════════════════
# 工作流 A：写作 + 执行
# ════════════════════════════════════════════════════════════════
def workflow_a(user_input: str, render_script: Path, render_cmd: str,
               public: bool = False) -> None:
    """
    完整工作流：写作 → 保存 → 渲染 → 发布
    """
    print("\n📝 【工作流 A】写作模式")
    print("─" * 50)

    # 1. 生成文案
    draft = generate_draft(user_input, verbose=True)
    if not draft:
        print("❌ 文案生成失败，流程终止")
        return

    # 2. 解析标题，创建输出文件夹
    meta = parse_frontmatter(draft)
    title = meta.get("title", "")
    if not title:
        print("❌ 生成的文案缺少 title 字段，流程终止")
        return

    folder_name = make_output_folder_name(title)
    output_dir  = OUTPUTS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  📁 输出文件夹：{output_dir}")

    # 3. 自动清洗：过滤开头废话和联网搜索未配置提示（保留从第一个 --- 开始的正文）
    if "---" in draft:
        draft = draft[draft.find("---"):]

    # 4. 自动清洗：防止生成单独的“标签卡片”（图片里不画标签，发布正文里已有标签）
    parts = draft.split("---")
    if len(parts) > 1:
        last_part = parts[-1].strip()
        if last_part.count("#") >= 3 and "# " not in last_part:
            draft = "---".join(parts[:-1])

    # 5. 保存 md 文件
    md_filename = re.sub(r'[\\/:*?"<>|]', '', title)[:20] + ".md"
    md_path     = output_dir / md_filename
    md_path.write_text(draft.strip(), encoding="utf-8")
    print(f"  💾 文案已保存：{md_path.name}")

    # 6. 渲染
    print("\n🎨 渲染阶段")
    print("─" * 50)
    ok = render(md_path, output_dir, render_script, render_cmd)
    if not ok:
        print("❌ 渲染失败，流程终止")
        return

    # 7. 生成发布参数
    pub_params = build_publish_params(draft)
    print(f"\n  📋 发布标题：{pub_params['title']}")
    print(f"  📋 desc 字数：{len(pub_params['desc'])} 字")

    # 8. 发布
    print("\n🚀 发布阶段")
    print("─" * 50)
    publish(output_dir, pub_params, public=public)

    print(f"\n✨ 全部完成！产物位于：{output_dir}")


# ════════════════════════════════════════════════════════════════
# 工作流 B：直接执行草稿
# ════════════════════════════════════════════════════════════════
def workflow_b(render_script: Path, render_cmd: str,
               public: bool = False) -> None:
    """
    直接执行工作流：读取草稿.md → 复制到输出目录 → 渲染 → 发布
    """
    print("\n📄 【工作流 B】草稿直发模式")
    print("─" * 50)

    # 1. 读取草稿
    if not DRAFT_FILE.exists():
        print(f"❌ 未找到草稿文件：{DRAFT_FILE}")
        print("请在 my_agent/ 根目录放置「草稿.md」文件")
        return

    draft = DRAFT_FILE.read_text(encoding="utf-8")
    print(f"  📖 已读取：{DRAFT_FILE.name}（{len(draft)} 字符）")

    # 2. 验证 title 字段
    meta  = parse_frontmatter(draft)
    title = meta.get("title", "")
    if not title:
        print("❌ 草稿.md 的 frontmatter 中缺少 title 字段，请补充后重试")
        return

    # 3. 创建输出文件夹
    folder_name = make_output_folder_name(title)
    output_dir  = OUTPUTS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  📁 输出文件夹：{output_dir}")

    # 4. 复制草稿到输出文件夹（原文件保留，便于复用）
    md_dest = output_dir / "草稿.md"
    shutil.copy2(DRAFT_FILE, md_dest)
    print(f"  📋 草稿已复制到输出目录（原文件保留）")

    # 5. 渲染
    print("\n🎨 渲染阶段")
    print("─" * 50)
    ok = render(md_dest, output_dir, render_script, render_cmd)
    if not ok:
        print("❌ 渲染失败，流程终止")
        return

    # 6. 生成发布参数
    pub_params = build_publish_params(draft)
    print(f"\n  📋 发布标题：{pub_params['title']}")
    print(f"  📋 desc 字数：{len(pub_params['desc'])} 字")

    # 7. 发布
    print("\n🚀 发布阶段")
    print("─" * 50)
    publish(output_dir, pub_params, public=public)

    print(f"\n✨ 全部完成！产物位于：{output_dir}")


# ════════════════════════════════════════════════════════════════
# 工作流 B2：以草稿为基础扩写
# ════════════════════════════════════════════════════════════════
def workflow_b2(user_input: str, render_script: Path, render_cmd: str,
                public: bool = False) -> None:
    """
    草稿扩写工作流：读取草稿正文 + 用户要求 → 写作模块 → 渲染 → 发布
    frontmatter 不传入，由写作模块重新生成。
    """
    print("\n✏️  【工作流 B2】草稿扩写模式")
    print("─" * 50)

    # 1. 读取草稿正文（不含 frontmatter）
    if not DRAFT_FILE.exists():
        print(f"❌ 未找到草稿文件：{DRAFT_FILE}")
        return

    raw     = DRAFT_FILE.read_text(encoding="utf-8")
    body    = extract_body(raw)
    print(f"  📖 草稿正文已读取（{len(body)} 字符）")

    # 2. 拼合写作指令：草稿内容 + 用户附加要求
    combined_input = (
        f"{user_input}\n\n"
        f"以下是参考草稿内容，可作为提纲、素材或要求参考，"
        f"请基于此重新创作完整文案：\n\n{body}"
    )

    # 3. 调用写作模块（走工作流 A 的后续步骤）
    workflow_a(combined_input, render_script, render_cmd, public=public)


# ════════════════════════════════════════════════════════════════
# 用户意图路由
# ════════════════════════════════════════════════════════════════

# 触发工作流 B（草稿直发）的精确关键词
_DRAFT_DIRECT_TRIGGERS = {"草稿"}

# 触发工作流 B2（草稿扩写）的关键短语
_DRAFT_REF_KEYWORDS = [
    "以草稿", "基于草稿", "参考草稿", "草稿为基础",
    "草稿为提纲", "草稿为参考", "草稿为素材", "草稿为要求",
    "用草稿", "结合草稿"
]

# 公开发布关键词
_PUBLIC_KEYWORDS = ["公开发布", "公开", "公开发", "public"]


def route(user_input: str) -> tuple[str, bool]:
    """
    解析用户输入，返回 (工作流类型, 是否公开发布)
    工作流类型：'A' | 'B' | 'B2'
    """
    text   = user_input.strip()
    public = any(k in text for k in _PUBLIC_KEYWORDS)

    # 工作流 B：单独说"草稿"（精确匹配，去掉公开发布等附加词后看是否只剩草稿）
    clean = text
    for k in _PUBLIC_KEYWORDS:
        clean = clean.replace(k, "").strip()
    if clean in _DRAFT_DIRECT_TRIGGERS:
        return "B", public

    # 工作流 B2：含有草稿参考类短语
    if any(k in text for k in _DRAFT_REF_KEYWORDS):
        return "B2", public

    # 默认：工作流 A
    return "A", public


# ════════════════════════════════════════════════════════════════
# 启动检查
# ════════════════════════════════════════════════════════════════
def startup_check() -> bool:
    """检查关键路径和依赖是否就绪"""
    ok = True
    checks = [
        (SCRIPTS_DIR / "publish_xhs.py",    "发布脚本"),
        (SCRIPTS_DIR / "render_xhs_v2.py",  "渲染脚本（默认 Python）"),
        (SKILLS_DIR  / "write_xhs.py",       "写作模块"),
    ]
    for path, label in checks:
        if path.exists():
            print(f"  ✅ {label}：{path.relative_to(ROOT)}")
        else:
            print(f"  ⚠️  {label} 未找到：{path.relative_to(ROOT)}")
            ok = False

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if DRAFT_FILE.exists():
        print(f"  ✅ 草稿文件：草稿.md")
    else:
        print(f"  ℹ️  草稿文件：草稿.md 不存在（工作流 B/B2 需要时创建）")

    return ok


# ════════════════════════════════════════════════════════════════
# 主循环
# ════════════════════════════════════════════════════════════════
def main():
    print("\n🤖 小红书自动化代理启动")
    print("═" * 50)

    ok = startup_check()
    if not ok:
        print("\n⚠️  部分组件未就绪，请检查目录结构后继续")

    print("\n📌 使用说明：")
    print("  · 输入主题或需求              → 写作+渲染+发布")
    print("  · 输入「草稿」                → 直接发布草稿.md")
    print("  · 输入「以草稿为基础…」       → 草稿扩写后发布")
    print("  · 附加「公开发布」             → 公开发布（默认私密）")
    print("  · 附加「旧版」                 → 切换至经典版渲染（默认新版 py）")
    print("  · 输入「退出」                → 结束程序")
    print("═" * 50)

    while True:
        try:
            user_input = input("\n🧑 您: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        if user_input.lower() in {"退出", "exit", "quit", "q"}:
            print("👋 再见！")
            break

        # 解析渲染版本
        render_script, render_cmd = detect_render_version(user_input)
        print(f"  🎨 渲染脚本：{render_script.name}")

        # 路由到对应工作流
        workflow, public = route(user_input)

        if public:
            print("  📢 发布模式：公开")
        else:
            print("  🔒 发布模式：私密（默认）")

        try:
            if workflow == "B":
                workflow_b(render_script, render_cmd, public=public)
            elif workflow == "B2":
                workflow_b2(user_input, render_script, render_cmd, public=public)
            else:
                workflow_a(user_input, render_script, render_cmd, public=public)
        except Exception as e:
            print(f"\n❌ 执行出错：{e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()