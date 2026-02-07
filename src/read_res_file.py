import os
import re
import textwrap


class MetaImporter:
    def __init__(self, workspace_folder):
        self.workspace_folder = workspace_folder
        # 匹配正则: 前缀_ID_类型 = { # 名称
        # 组1: 前缀, 组2: v_full_id, 组3: type, 组4: v_name
        self.header_pattern = re.compile(
            r'^(EFFECT|MODIFIER|TRIGGER)_(NIE_law_branch_\d+_id_\d+_value_\d+_idea)_([a-zA-Z0-9_]+)\s*=\s*{\s*#\s*(.*)'
        )

    def _process_meta_content(self, lines):
        """处理内容块，去除最小缩进量并清理首尾"""
        if not lines:
            return ""
        # 合并为长字符串
        content = "".join(lines)
        # textwrap.dedent 会自动移除所有行共有的前置空格
        dedented_content = textwrap.dedent(content)
        return dedented_content.strip()

    def parse_file(self, file_path):
        """解析单个文件内的所有条目"""
        extracted_data = []
        if not os.path.exists(file_path):
            return extracted_data

        with open(file_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        current_item = None
        block_lines = []
        brace_level = 0

        for line in lines:
            # 尝试匹配条目开始
            header_match = self.header_pattern.match(line.strip())

            if header_match:
                current_item = {
                    "prefix": header_match.group(1),
                    "v_full_id": header_match.group(2),
                    "type": header_match.group(3),
                    "v_name": header_match.group(4).strip()
                }
                block_lines = []
                brace_level = 1
                continue

            if current_item:
                # 统计大括号确定块范围
                brace_level += line.count('{')
                brace_level -= line.count('}')

                if brace_level <= 0:
                    # 块结束，保存并清理
                    current_item["meta"] = self._process_meta_content(block_lines)
                    extracted_data.append(current_item)
                    current_item = None
                else:
                    # 记录内容（保留原始行缩进，供 dedent 分析）
                    block_lines.append(line)

        return extracted_data

    def run_import(self):
        """核心导入逻辑"""
        all_meta_results = {
            "effect": [],
            "modifier": [],
            "trigger": []
        }
        # 定义对应的子文件夹
        sub_folders = ["effect", "modifier", "trigger"]

        for folder in sub_folders:
            folder_path = os.path.join(self.workspace_folder, folder)
            if not os.path.exists(folder_path):
                print(f"跳过不存在的文件夹: {folder}")
                continue

            for filename in os.listdir(folder_path):
                if filename.endswith(".txt"):
                    full_path = os.path.join(folder_path, filename)
                    print(f"正在解析: {full_path}")
                    file_data = self.parse_file(full_path)
                    all_meta_results[folder].extend(file_data)

        return all_meta_results


# --- 执行示例 ---
if __name__ == "__main__":
    WORKSPACE = r"meta_files"
    importer = MetaImporter(WORKSPACE)
    results = importer.run_import()

    # 打印提取结果示例
    for key in results:
        print(f"--- {key} ---")
        for data in results[key][:5]:  # 仅展示前两条
            print("--- Entry Found ---")
            print(f"ID:   {data['v_full_id']}")
            print(f"Type: {data['type']}")
            print(f"Name: {data['v_name']}")
            print(f"Meta:\n{data['meta']}")
            print("-" * 20)
