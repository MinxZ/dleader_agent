from bs4 import BeautifulSoup, NavigableString, Tag
import json
from pathlib import Path
import re


def parse_patent_html(html_path, output_path=None):
    """
    解析HTML文件，最小化处理，保留所有有价值的内容
    """
    if output_path is None:
        output_path = Path(html_path).with_suffix(".sections.json")

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    # 只移除明确无用的标签，保留其他所有内容
    for tag in soup(["script", "style"]):
        tag.decompose()

    # 查找所有可能的标题元素 - 扩大范围以免遗漏
    heading_selectors = [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "heading", "[role='heading']",
        ".heading", ".title", ".section-title", ".patent-section-title",
        "*[class*='heading']", "*[class*='title']", "*[class*='section']"
    ]

    heads = []
    for selector in heading_selectors:
        found_heads = soup.select(selector)
        for h in found_heads:
            if isinstance(h, Tag) and h not in heads:
                # 最宽松的过滤，只去掉明显的导航元素
                text = h.get_text(strip=True)
                if text and len(text) > 0:
                    # 只过滤明显的导航/UI元素
                    if not re.match(r'^(menu|nav|header|footer|home|back|next|previous|login|logout)$', text.lower()):
                        heads.append(h)

    # 按文档顺序排序
    if heads:
        try:
            heads = sorted(heads, key=lambda x: list(
                soup.descendants).index(x))
        except ValueError:
            # 如果排序失败，保持原顺序
            pass

    sections = []

    # 提取第一个标题之前的内容 - 完整保留
    if heads:
        intro_content = get_content_before_element(soup, heads[0])
        intro_content_cleaned = clean_content_minimal(intro_content)
        if intro_content_cleaned.strip():
            sections.append({
                "heading": "Document Introduction",
                "content": intro_content_cleaned
            })

    # 提取每个标题和对应内容 - 完整保留
    for i, heading in enumerate(heads):
        heading_text = heading.get_text(" ", strip=True)

        # 找到下一个同级或更高级标题作为边界
        next_heading = None
        current_level = get_heading_level(heading)

        for j in range(i + 1, len(heads)):
            next_level = get_heading_level(heads[j])
            if next_level <= current_level:
                next_heading = heads[j]
                break

        # 提取内容 - 保留完整HTML结构
        content = get_content_between_elements(heading, next_heading)
        content_cleaned = clean_content_minimal(content)

        if heading_text or content_cleaned.strip():
            sections.append({
                "heading": heading_text.strip() if heading_text else "Untitled Section",
                "content": content_cleaned
            })

    # 如果没找到任何标题，将整个body作为一个大段落
    if not sections:
        body = soup.find('body')
        if body:
            full_content = clean_content_minimal(str(body))
            sections.append({
                "heading": "Full Document",
                "content": full_content
            })

    # 保存JSON
    sections_dict = {s["heading"]: s["content"] for s in sections}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sections_dict, f, ensure_ascii=False, indent=2)


    print(f"提取完成: {len(sections)} 个章节 -> {output_path}")
    return sections


def get_heading_level(heading):
    """获取标题级别 - 简化判断"""
    if heading.name and heading.name.startswith("h") and len(heading.name) == 2:
        try:
            return int(heading.name[1:])
        except:
            pass

    if heading.has_attr("aria-level"):
        try:
            return int(heading["aria-level"])
        except:
            pass

    return 2  # 默认级别


def clean_content_minimal(content):
    """最小化清理 - 只做必要的格式整理"""
    if not content:
        return ""

    # 使用BeautifulSoup重新解析以规范化HTML
    temp_soup = BeautifulSoup(content, "lxml")

    # 移除明显的空白标签，但保留所有其他内容
    for tag in temp_soup.find_all():
        if not tag.get_text(strip=True) and not tag.find_all(['img', 'br', 'hr', 'input']):
            tag.decompose()

    # 获取清理后的HTML，移除wrapper标签
    cleaned = str(temp_soup.body) if temp_soup.body else str(temp_soup)

    # 移除BeautifulSoup添加的wrapper标签
    cleaned = re.sub(r'^<body>', '', cleaned)
    cleaned = re.sub(r'</body>$', '', cleaned)
    cleaned = re.sub(r'^<html><body>', '', cleaned)
    cleaned = re.sub(r'</body></html>$', '', cleaned)

    # 规范化空白，但保留结构
    cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)  # 多个空行变两个
    cleaned = re.sub(r'>\s+<', '><', cleaned)  # 标签间多余空格

    return cleaned.strip()


def get_content_before_element(soup, target_element):
    """获取目标元素之前的所有内容 - 完整保留"""
    content_parts = []

    def collect_before(element):
        for child in element.children:
            if child == target_element:
                return True

            if isinstance(child, NavigableString):
                text = str(child)
                if text.strip():  # 保留所有非空文本
                    content_parts.append(text)
            elif isinstance(child, Tag):
                if collect_before(child):
                    return True
                # 保留所有标签（除了目标元素）
                content_parts.append(str(child))
        return False

    body = soup.find('body') or soup
    collect_before(body)

    return "".join(content_parts)


def get_content_between_elements(start_element, end_element):
    """获取两个元素之间的内容 - 完整保留"""
    content_parts = []

    # 方法1: 收集直接兄弟节点
    current = start_element.next_sibling
    while current:
        if current == end_element:
            break

        if isinstance(current, NavigableString):
            text = str(current)
            if text.strip():  # 保留所有非空文本
                content_parts.append(text)
        elif isinstance(current, Tag):
            content_parts.append(str(current))

        current = current.next_sibling

    # 方法2: 如果方法1没有找到内容，尝试在父容器中查找
    if not content_parts and start_element.parent:
        parent = start_element.parent
        collecting = False

        for child in parent.descendants:
            if child == start_element:
                collecting = True
                continue

            if collecting:
                if child == end_element:
                    break

                if isinstance(child, NavigableString):
                    text = str(child)
                    if text.strip():
                        content_parts.append(text)
                elif isinstance(child, Tag) and child.parent == parent:
                    # 只收集直接子元素，避免重复
                    content_parts.append(str(child))
                    # 跳过这个标签的所有子元素
                    for desc in child.descendants:
                        pass

    # 方法3: 如果还是没有内容，查找下一个相邻的内容块
    if not content_parts:
        next_elem = start_element.find_next_sibling()
        while next_elem and next_elem != end_element:
            content_parts.append(str(next_elem))
            next_elem = next_elem.find_next_sibling()

    return "".join(content_parts)


# 运行解析
if __name__ == "__main__":
    html_path = "/home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1.html"
    
    sections = parse_patent_html(html_path)

    # 显示提取结果概览
    # print(f"\n=== 提取概览 ===")
    # for i, section in enumerate(sections):
    #     content_preview = section['content'][:200].replace('\n', ' ')
    #     print(f"{i+1}. {section['heading']}")
    #     print(f"   长度: {len(section['content'])} 字符")
    #     print(f"   预览: {content_preview}...")
    #     print()
