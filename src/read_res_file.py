import logging
import os
import re
import textwrap

from log import log_manager

logger = log_manager.init_logger(level=logging.DEBUG, log_folder="pdx_logs")


class MetaImporter:
    def __init__(self, workspace_folder):
        self.workspace_folder = workspace_folder
        # 匹配正则: 前缀_ID_类型 = { # 名称
        # 组1: 前缀, 组2: v_full_id, 组3: type, 组4: v_name
        self.header_pattern = re.compile(
            r'^(EFFECT|MODIFIER|TRIGGER|PREFERENCES)_(NIE_law_branch_\d+_id_\d+_value_\d+_idea)_([a-zA-Z0-9_]+)\s*=\s*{\s*(?:#\s*(.*?))?\s*$'
        )

    @staticmethod
    def _process_meta_content(lines):
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
            line_strip = line.strip()
            if not line_strip:
                continue

            # 尝试匹配条目开始
            header_match = self.header_pattern.match(line_strip)

            if header_match:
                raw_name = header_match.group(4)
                current_item = {
                    "prefix": header_match.group(1),
                    "v_full_id": header_match.group(2),
                    "type": header_match.group(3),
                    "v_name": raw_name.strip() if raw_name else "None",
                    "source_file": file_path,
                }
                if current_item["v_name"] == "None" or not current_item["v_name"]:
                    logger.warning(f"MetaImporter: {file_path}: {current_item['v_full_id']}没有标记名称")
                block_lines = []
                brace_level = 1
                continue

            if current_item:
                # 统计大括号确定块范围
                brace_level += line.count('{')
                brace_level -= line.count('}')

                if brace_level <= 0:
                    # 块结束
                    current_item["meta"] = self._process_meta_content(block_lines)
                    extracted_data.append(current_item)
                    current_item = None
                else:
                    # 记录内容
                    block_lines.append(line)

        return extracted_data

    def run_import(self):
        """核心导入逻辑"""
        all_meta_results = {
            "effect": [],
            "modifier": [],
            "trigger": [],
            "preferences": []
        }
        # 定义对应的子文件夹
        sub_folders = all_meta_results.keys()

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

    def update_meta_files(self, meta_data_dict):
        """
        将同步后的 v_name 写回到物理文件中
        :param meta_data_dict: 经过 LawParser 自检修正后的 self._meta_data
        """
        logger.info("MetaImporter: 开始执行元数据物理写回...")
        update_count = 0

        for category, items in meta_data_dict.items():
            # 按文件归类，减少开关文件的次数
            file_map = {}
            for item in items:
                f_path = item.get('source_file')  # 需在 parse_file 时记录源路径
                if f_path:
                    file_map.setdefault(f_path, []).append(item)

            for file_path, file_items in file_map.items():
                if self._update_single_file(file_path, file_items):
                    update_count += 1

        logger.info(f"MetaImporter: 写回完成，共更新 {update_count} 个元数据文件。")

    def _update_single_file(self, file_path, items):
        """更新单个文件中的 header 注释"""
        if not os.path.exists(file_path):
            return False

        with open(file_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        modified = False
        new_lines = []

        # 将 items 转换为 ID 映射，方便快速查找
        items_by_id = {(it['v_full_id'], it['type']): it for it in items}

        for line in lines:
            line_strip = line.strip()
            header_match = self.header_pattern.match(line_strip)

            if header_match:
                prefix = header_match.group(1)
                v_id = header_match.group(2)
                m_type = header_match.group(3)

                # 匹配对应的更新项
                if (v_id, m_type) in items_by_id:
                    updated_item = items_by_id[(v_id, m_type)]
                    new_name = (updated_item.get('v_name') or "").strip()

                    # 构建新的 header 行
                    # 格式：PREFIX_ID_TYPE = { # 注释
                    comment_part = f" # {new_name}" if new_name else ""
                    # 保持原行的缩进（如果有的话）
                    indent = line[:line.find(header_match.group(1))]
                    new_line = f"{indent}{prefix}_{v_id}_{m_type} = {{{comment_part}\n"

                    if new_line != line:
                        new_lines.append(new_line)
                        modified = True
                        continue

            new_lines.append(line)

        if modified:
            with open(file_path, 'w', encoding='utf-8-sig') as f:
                f.writelines(new_lines)
            return True
        return False


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
