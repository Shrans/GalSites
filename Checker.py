from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import time
import cloudscraper
import re


def process_table(lines, section_dict):
    """处理表格数据并提取站点信息"""
    if len(lines) < 3:  # 至少需要表头、分隔线和数据行
        return

    # 处理数据行（跳过表头和分隔线）
    for row in lines[2:]:
        columns = [col.strip() for col in row.split('|') if col.strip()]
        if len(columns) < 2:
            continue

        # 提取站点名称和链接
        name = columns[0]
        url_cell = columns[1]

        # 处理可能的Markdown链接格式
        url_match = re.search(r'\[.*?]\((.*?)\)', url_cell)
        url = url_match.group(1) if url_match else url_cell

        section_dict[name] = url


def content_extractor():
    """从Markdown表格中提取站点信息"""
    sections = {}
    current_section = None
    table_buffer = []
    in_table = False

    with open("README.md", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # 检测章节标题
            if line.startswith("### "):
                if in_table:  # 处理上一个未完成的表格
                    process_table(table_buffer, sections[current_section])
                    table_buffer = []
                    in_table = False
                current_section = line[4:]
                sections[current_section] = {}

            # 检测表格开始
            elif current_section and line.startswith("|"):
                table_buffer.append(line)
                if not in_table:
                    in_table = True

            # 表格结束处理
            elif in_table and not line.startswith("|"):
                process_table(table_buffer, sections[current_section])
                table_buffer = []
                in_table = False

        # 处理文件末尾的表格
        if in_table:
            process_table(table_buffer, sections[current_section])

    return sections


def checker(site):
    """站点可用性检测"""
    scraper = cloudscraper.create_scraper()
    try:
        response = scraper.get(site, timeout=10, allow_redirects=True)
        status = "可用" if 200 <= response.status_code < 400 else "异常"
        msg = f"{status}：【{section_map[site]}】{name_list[url_list.index(site)]}({site}) -> <{response.status_code}>"
    except Exception as e:
        msg = f"异常：【{section_map[site]}】{name_list[url_list.index(site)]}({site}) -> {type(e).__name__}"

    with thread_lock:
        print(msg)


if __name__ == "__main__":
    # 提取站点数据
    site_data = content_extractor()
    total_sites = sum(len(v) for v in site_data.values())

    # 用户选择检测范围
    print(f"可选栏目（共发现 {total_sites} 个站点）:")
    sections = list(site_data.items())
    for i, (name, data) in enumerate(sections):
        print(f"{i + 1}. {name}（{len(data)}个站点）")

    selected = input("请输入需要检测的栏目编号（空格分隔）: ").split()
    selected_sections = [sections[int(i) - 1] for i in selected if i.isdigit()]

    # 准备检测数据
    url_list = []
    name_list = []
    section_map = {}
    for section_name, sites in selected_sections:
        for name, url in sites.items():
            url_list.append(url)
            name_list.append(name)
            section_map[url] = section_name

    # 执行检测
    if url_list:
        print(f"\n开始检测 {len(url_list)} 个站点...")
        thread_lock = Lock()
        start = time()
        with ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(checker, url_list)
        print(f"检测完成，耗时 {time() - start:.2f} 秒")
    else:
        print("未选择有效站点")
