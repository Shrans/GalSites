import re
from concurrent.futures import ThreadPoolExecutor
from time import time
from typing import Dict, List, Any

import cloudscraper
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table


class SiteChecker:
    """
    一个用于检测 GalGame 资源站点可用性的工具。

    该工具会从 README.md 文件中解析站点列表，
    并使用 rich 库提供美观的命令行界面，
    包括进度条和格式化的结果表格。
    """

    def __init__(self, readme_path: str = "README.md"):
        """
        初始化 SiteChecker。
        :param readme_path: README.md 文件的路径。
        """
        self.readme_path = readme_path
        self.console = Console()
        self.sections: Dict[str, Dict[str, str]] = self._parse_readme()

    def _parse_readme(self) -> Dict[str, Dict[str, str]]:
        """
        从 Markdown 文件中解析出站点列表章节下的栏目和站点信息。
        只解析名称包含“站点列表”的二级标题下的三级标题内容。
        """
        sections = {}
        current_section_name = None
        in_table = False
        in_site_list_section = False  # 是否处于“站点列表”大章节内

        try:
            with open(self.readme_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # 检测二级标题
                    if line.startswith("## "):
                        # 如果标题包含“站点列表”则开始解析
                        if "站点列表" in line:
                            in_site_list_section = True
                        else:
                            in_site_list_section = False

                        # 重置当前栏目状态
                        current_section_name = None
                        in_table = False
                        continue

                    # 只有在“站点列表”章节内才解析三级标题
                    if in_site_list_section and line.startswith("### "):
                        current_section_name = line[4:].strip()
                        sections[current_section_name] = {}
                        in_table = False
                        continue

                    # 解析表格内容（必须在目标章节内）
                    if (
                            in_site_list_section
                            and current_section_name
                            and line.startswith("|")
                            and "---" not in line
                            and "站点名称" not in line
                    ):
                        columns = [col.strip() for col in line.split("|") if col.strip()]
                        if len(columns) < 2:
                            continue

                        name = columns[0]
                        url_cell = columns[1]

                        # 匹配 Markdown 链接
                        url_match = re.search(r'\[.*?]\((.*?)\)', url_cell)
                        url = url_match.group(1) if url_match else url_cell

                        sections[current_section_name][name] = url

            return sections

        except FileNotFoundError:
            self.console.print(
                f"[bold red]错误：找不到文件 '{self.readme_path}'。请确保该文件与脚本在同一目录下。[/bold red]"
            )
            exit()

    def _select_sections(self) -> List[Dict[str, str]]:
        """
        向用户显示可选的章节并获取用户选择。
        :return: 一个包含待检测站点信息的列表。
        """
        total_sites = sum(len(v) for v in self.sections.values())

        # 使用 Panel 美化选项显示
        section_list_str = ""
        section_keys = list(self.sections.keys())
        for i, name in enumerate(section_keys):
            count = len(self.sections[name])
            section_list_str += f"[cyan]{i + 1}[/cyan]. {name} ({count}个站点)\n"

        self.console.print(Panel(
            section_list_str.strip(),
            title="[bold yellow]可选检测栏目[/bold yellow]",
            subtitle=f"共发现 {total_sites} 个站点",
            border_style="green"
        ))

        # 获取用户输入
        selected_indices_str = self.console.input("[bold]请输入需要检测的栏目编号（多个请用空格分隔）:[/bold] > ")

        sites_to_check = []
        try:
            selected_indices = [int(i) - 1 for i in selected_indices_str.split()]
            for i in selected_indices:
                if 0 <= i < len(section_keys):
                    section_name = section_keys[i]
                    for name, url in self.sections[section_name].items():
                        sites_to_check.append({"name": name, "url": url, "section": section_name})
        except ValueError:
            self.console.print("[bold red]输入无效，请输入数字编号。[/bold red]")
            return []

        return sites_to_check

    @staticmethod
    def _check_single_site(site_info: Dict[str, str]) -> Dict[str, Any]:
        """
        检测单个站点的可用性。
        :param site_info: 包含站点名称、URL和章节的字典。
        :return: 包含检测结果的字典。
        """
        scraper = cloudscraper.create_scraper(browser={'custom': 'Mozilla/5.0'})
        url = site_info["url"]
        result = {**site_info, "status": "异常", "result": ""}

        try:
            response = scraper.get(url, timeout=15, allow_redirects=True)
            if 200 <= response.status_code < 400:
                result["status"] = "可用"
            result["result"] = f"[bold]{response.status_code}[/bold]"
        except Exception as e:
            result["result"] = f"[italic]{type(e).__name__}[/italic]"

        return result

    def _display_results(self, results: List[Dict[str, Any]], duration: float):
        """
        使用 rich.table.Table 格式化并显示结果。
        :param results: 检测结果列表。
        :param duration: 检测总耗时。
        """
        table = Table(title="[bold]站点可用性检测报告[/bold]", show_header=True, header_style="bold magenta")
        table.add_column("状态", justify="center", style="cyan")
        table.add_column("栏目", style="yellow")
        table.add_column("站点名称", style="green")
        table.add_column("URL", style="dim")
        table.add_column("结果 (代码/错误)", justify="right")

        results.sort(key=lambda x: (x["section"], x["status"] == "异常"))

        for res in results:
            status_icon = "✅" if res["status"] == "可用" else "❌"
            status_color = "[green]" if res["status"] == "可用" else "[red]"

            table.add_row(
                f"{status_color}{status_icon} {res['status']}[/]",
                res["section"],
                res["name"],
                res["url"],
                f"{status_color}{res['result']}[/]"
            )

        self.console.print(table)
        self.console.print(f"\n检测完成，共 {len(results)} 个站点，耗时 {duration:.2f} 秒。")

    def run(self):
        """
        运行检测程序的主方法。
        """
        sites_to_check = self._select_sections()
        if not sites_to_check:
            self.console.print("[yellow]未选择有效站点，程序退出。[/yellow]")
            return

        self.console.print(f"\n[bold]准备检测 {len(sites_to_check)} 个站点...[/bold]")
        start_time = time()
        results = []

        with Progress(
                SpinnerColumn(),
                "[progress.description]{task.description}",
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.0f}%",
                TextColumn("({task.completed}/{task.total})"),
                TimeRemainingColumn(),
                console=self.console,
        ) as progress:
            task = progress.add_task("[cyan]检测中...", total=len(sites_to_check))
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(self._check_single_site, site) for site in sites_to_check]
                for future in futures:
                    results.append(future.result())
                    progress.update(task, advance=1)

        duration = time() - start_time
        self._display_results(results, duration)


if __name__ == "__main__":
    checker = SiteChecker()
    checker.run()