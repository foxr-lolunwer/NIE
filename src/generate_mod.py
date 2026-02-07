import logging
import os
import textwrap
from collections import defaultdict

import json5

from log import log_manager
from read_res_file import MetaImporter

# --- 核心路径配置 ---
JSON5_PATH = r"structure.json5"
OUTPUT_ROOT = r"dist_mod"
MOD_ID = "NIE"
COLON_STYLE = "："
META_IMPORTER_WORKSPACE = r"meta_files"

logger = log_manager.init_logger(level=logging.DEBUG, log_folder="pdx_logs")


class LawParser:
    def __init__(self, json_path, output_root):
        self.json_path = json_path
        self.output_root = output_root
        self.data = self._load_json(json_path)
        self.loc_data = {}
        self._meta_data = MetaImporter(META_IMPORTER_WORKSPACE).run_import()
        self.meta_index = defaultdict(lambda: defaultdict(dict))
        for category, items in self._meta_data.items():
            for item in items:
                v_id = item['v_full_id']
                m_type = item['type']
                # 直接赋值，defaultdict() 会处理中间层的自动创建
                self.meta_index[category][v_id][m_type] = item['meta']

    @staticmethod
    def _load_json(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json5.load(f)
        except Exception as e:
            print(f"读取 JSON5 失败: {e}")
            return {}

    def _get_path(self, *sub_paths):
        full_path = os.path.join(self.output_root, *sub_paths)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        return full_path

    @staticmethod
    def _write_file(path, lines, encoding='utf-8'):
        """
        通用写文件方法
        :param path: 文件路径
        :param lines: 文本行列表
        :param encoding: 编码格式，默认为 utf-8，本地化使用 utf-8-sig
        """
        try:
            with open(path, 'w', encoding=encoding) as f:
                # HOI4 本地化文件第一行通常需要声明语言
                f.write("\n".join(lines))
            print(f"已生成: {path} (Encoding: {encoding})")
        except Exception as e:
            print(f"写入失败 {path}: {e}")

    @staticmethod
    def _get_full_id(b_key, id_key="", v_key="", mod_id=MOD_ID):
        if b_key and id_key and v_key:
            return f"{mod_id}_law_{b_key}_{id_key}_{v_key}_idea"
        elif b_key and id_key:
            return f"{mod_id}_law_{b_key}_{id_key}_laws"
        elif b_key:
            return f"{mod_id}_law_{b_key}"
        else:
            return mod_id

    def create_idea_tags(self, file_name=f"{MOD_ID}_law_tags"):
        target_path = self._get_path("common", "idea_tags", f"{file_name}.txt")
        output = ["idea_categories = {"]
        for b_key, b_data in self.data.items():
            if not b_key.startswith("branch_"):
                continue
            output.append(f"    {self._get_full_id(b_key)} = {{")
            ids = sorted([k for k in b_data.keys() if k.startswith("id_")], key=lambda x: int(x.split('_')[1]))
            for id_key in ids:
                output.append(f"        slot = {self._get_full_id(b_key, id_key)}")
            output.append(
                f"\n        ledger = civilian\n        cost = {b_data.get('cost', 150)}\n        removal_cost = {b_data.get('removal_cost', 0)}\n    }}")
        output.append("}")
        self._write_file(target_path, output)

    @staticmethod
    def _format_modifier_block(block_name, content, indent_level=1, custom_tooltip=""):
        """
        专门处理类似 modifier 或其它脚本块文本。
        :param block_name: 修正名称 (如 modifier, available 等)
        :param content: 原始字符串（内部已包含 PDX 缩进）
        :param indent_level: 块本身的缩进层级
        :param custom_tooltip: 自定义文本提示框 (custom_modifier_tooltip)
        :return: 格式化后的字符串
        """
        base_indent = "    " * max(0, indent_level)
        content_indent = base_indent + "    "
        # 处理空内容情况
        if (not content or not content.strip()) and not custom_tooltip:
            return f"{base_indent}{block_name} = {{}}"
        # 1. 准备块头
        output = [f"{base_indent}{block_name} = {{"]
        # 2. 处理主体内容 (使用 textwrap.indent 整体平移)
        if content and content.strip():
            # 先对 content 做一次 dedent 确保它是左对齐起步的
            clean_content = textwrap.dedent(content).strip()
            shifted_content = textwrap.indent(
                clean_content,
                content_indent,
                predicate=lambda line: line.strip() != ""
            )
            output.append(shifted_content)
        # 3. 处理自定义提示
        if custom_tooltip:
            output.append(f"{content_indent}custom_modifier_tooltip = {custom_tooltip}")
        # 4. 闭合大括号
        output.append(f"{base_indent}}}")
        return "\n".join(output)

    def apply_meta_to_structure(self, category, v_full_id, meta_type, indent_level=0):
        """
        从三层索引中精准提取 meta 内容并应用平移缩进
        :param category: 分类 (effect/modifier/trigger)
        :param v_full_id: 法案 ID
        :param meta_type: 具体类型
        :param indent_level: 缩进等级
        """
        # 安全地进行链式取值
        try:
            raw_meta = self.meta_index.get(category, {}).get(v_full_id, {}).get(meta_type, "")
        except KeyError:
            raw_meta = ""
        if not raw_meta:
            return ""

        # 执行整体平移
        prefix = " " * (indent_level * 4)
        return textwrap.indent(
            raw_meta,
            prefix,
            predicate=lambda line: line.strip() != ""
        )

    def _create_scripted_file(self, id_map):
        """
        根据传入的字典自动生成对应的脚本文件
        :param id_map: 字典，格式如 {"trigger": [(scripted_full_id, v_full_id)...], "effect": [...], "loc": [...]}
        """
        # 定义不同模式的配置映射
        configs = {
            "trigger": {
                "folder": "scripted_triggers",
                "file_prefix": f"{MOD_ID}_laws_TRIGGER",
            },
            "effect": {
                "folder": "scripted_effects",
                "file_prefix": f"{MOD_ID}_laws_FUN",
            },
            "loc": {
                "folder": "scripted_localisation",
                "file_prefix": f"{MOD_ID}_laws_DY_LOC",
            }
        }

        # 遍历字典中的每种模式进行处理
        for mode, tuple_list in id_map.items():
            if mode not in configs or not tuple_list:
                continue

            cfg = configs[mode]

            # 组合完整路径：common/xxx/NIE_laws_PREFIX_suffix.txt
            target_path = self._get_path("common", cfg['folder'], f"{cfg['file_prefix']}.txt")

            output = []
            # 按照传入列表的顺序生成内容
            for scripted_full_id, v_full_id in tuple_list:
                if mode == "loc":
                    # 脚本化本地化的特殊结构
                    output.append(f"defined_text = {{ # {self.loc_data.get(v_full_id, 'LOC FIND ERROR')}")
                    output.append(f"    name = {scripted_full_id}")
                    output.append("    text = {")
                    output.append("")
                    output.append("    }")
                    output.append("}")
                else:
                    # Trigger 和 Effect 的标准结构
                    output.append(f"{scripted_full_id} = {{ # {self.loc_data.get(v_full_id, 'LOC FIND ERROR')}")
                    output.append("")
                    output.append("}")
                output.append("")  # 条目间的空行

            # 调用已有的 _write_file 方法执行写入
            self._write_file(target_path, output)

    def _create_loc_file(self, loc_map, lang="simp_chinese", filename=f"{MOD_ID}_laws"):
        """
        根据传入的字典生成本地化文件
        :param filename: 文件名（不含后缀和语言后缀）
        :param lang: 语言代码，如 "simp_chinese"
        :param loc_map: 字典，格式为 { "key": "value", "key_desc": "value" }
        """
        # 路径处理：localisation/l_simp_chinese/filename_l_simp_chinese.yml
        lang_folder = f"{lang}"
        full_filename = f"{filename}_l_{lang}.yml"
        target_path = self._get_path("localisation", lang_folder, full_filename)

        output = [f"l_{lang}:"]
        # 按照 key 排序可以使 yml 文件更有序，方便 Git 追踪对比
        sorted_keys = sorted(loc_map.keys())

        for key in sorted_keys:
            value = loc_map[key]
            if value.startswith('"# ') and value.endswith('"') and value.count('"') == 2:
                # 提取注释内容：去掉前三个字符 '"# ' 和最后一个字符 '"'
                comment_text = value[3:-1]
                # 生成只含键的注释行
                output.append(f'  # {key} {comment_text}')
                continue
            # 处理字符串中的换行，确保输出到 yml 是文本形式的 \n
            # 同时处理可能的双引号嵌套
            clean_value = str(value).replace('"', '\\"').replace('\n', '\\n')

            # HOI4 标准格式：  key:0 "value"
            output.append(f'  {key}: "{clean_value}"')
            self.loc_data.setdefault(key, clean_value)

        # 使用 utf-8-sig 编码写入文件
        self._write_file(target_path, output, encoding='utf-8-sig')

    def create_ideas(self, file_name=f"{MOD_ID}_laws"):
        target_path = self._get_path("common", "ideas", f"{file_name}.txt")
        output = ["ideas = {"]
        scripted_id_map = {
            "trigger": [],
            "effect": [],
            "loc": []
        }
        scripted_full_id: str
        loc_map = {}

        for b_key, b_data in self.data.items():
            if not b_key.startswith("branch_"):
                continue

            b_cost = b_data.get("cost", 150)
            b_rem_cost = b_data.get("removal_cost", 0)
            loc_map.setdefault(self._get_full_id(b_key), b_data.get("name", "Unknown Value"))

            ids = sorted([k for k in b_data.keys() if k.startswith("id_")], key=lambda x: int(x.split('_')[1]))

            for id_key in ids:
                id_data = b_data[id_key]
                id_name = id_data.get("name", "Unknown Value")
                loc_map.setdefault(self._get_full_id(b_key, id_key), id_name)
                # 槽位名，例如 NIE_branch_1_id_1_laws
                output.append(f"    {self._get_full_id(b_key, id_key)} = {{ # {id_name}")
                output.append("        law = yes")
                output.append("        use_list_view = yes\n")

                values = sorted([k for k in id_data.keys() if k.startswith("value_")],
                                key=lambda x: int(x.split('_')[1]))
                for v_key in values:
                    v_data = id_data[v_key]
                    v_name = v_data.get("name", "")
                    use_id_name = v_data.get("use_id_name", True)
                    v_full_id = self._get_full_id(b_key, id_key, v_key)
                    if v_name:
                        v_full_name = f"{id_name}{COLON_STYLE}{v_name}" if use_id_name else v_name
                        loc_map.setdefault(v_full_id, v_full_name)
                        v_desc = v_data.get("desc", "")
                        loc_map.setdefault(f"{v_full_id}_desc", v_desc)
                    else:
                        scripted_full_id = f"get_{v_full_id}"
                        scripted_id_map["loc"].append((scripted_full_id, v_full_id))
                        v_full_name = scripted_full_id
                        loc_map.setdefault(v_full_id, '"# DY_LOC"')
                        loc_map.setdefault(f"{v_full_id}_desc", '"# DY_LOC"')
                    output.append(f"        {v_full_id} = {{ # {v_full_name}")

                    # 1. Level & Default
                    if v_data.get("level", 0) > 0:
                        output.append(f"            level = {v_data['level']}")
                    if v_data.get("default"):
                        output.append("            default = yes")

                    # 2. Allowed Civil War
                    acw = v_data.get("allowed_civil_war_flag", 0)
                    if isinstance(acw, str):
                        output.append(f"            allowed_civil_war = {{ {acw} }}")
                    elif acw > 0:
                        output.append("            allowed_civil_war = { always = yes }")
                    elif acw < 0:
                        scripted_full_id = f"TRIGGER_{v_full_id}_allowed_cv"
                        scripted_id_map["trigger"].append((scripted_full_id, v_full_id))
                        output.append(f"            allowed_civil_war = {{ {scripted_full_id} = yes }}")

                    # 3. Available
                    if v_data.get("available") and v_data["available"] is not False:
                        scripted_full_id = f"TRIGGER_{v_full_id}_available"
                        scripted_id_map["trigger"].append((scripted_full_id, v_full_id))
                        output.append(f"            available = {{ {scripted_full_id} = yes }}")

                    # 4. Cost 逻辑
                    v_cost = v_data.get("cost", b_cost)
                    if v_cost != b_cost and v_cost >= 0:
                        output.append(f"            cost = {v_cost}")
                    v_rem = v_data.get("removal_cost", b_rem_cost)
                    if v_rem != b_rem_cost and v_rem >= 0:
                        output.append(f"            removal_cost = {v_rem}")

                    # 5.6. Modifier,Tooltip
                    mod_meta = v_data.get("modifier_meta", "").strip()
                    custom_modifier_tooltip = f"custom_modifier_tooltip = {v_full_id}_tooltip" if v_data.get("custom_modifier_tooltip") else ""
                    output.append(self._format_modifier_block("modifier", mod_meta, 3, custom_modifier_tooltip))

                    # 7. Other Meta (同级脚本块)
                    other = v_data.get("other_meta", {})
                    # 假设在调用此段代码前，你已经初始化了：
                    # scripted_id_map = {"trigger": [], "effect": [], "loc": []}

                    mapping = {
                        "on_add": {"template": "FUN_{id}_on_add = yes", "mode": "effect", "suffix": "_on_add"},
                        "on_remove": {"template": "FUN_{id}_on_remove = yes", "mode": "effect", "suffix": "_on_remove"},
                        "do_effect": {"template": "TRIGGER_{id}_do_effect = yes", "mode": "trigger",
                                      "suffix": "_do_effect"},
                        "allowed": {"template": "TRIGGER_{id}_allowed = yes", "mode": "trigger", "suffix": "_allowed"},
                        "allowed_to_remove": {"template": "TRIGGER_{id}_allowed_rm = yes", "mode": "trigger",
                                              "suffix": "_allowed_rm"},
                        "visible": {"template": "TRIGGER_{id}_visible = yes", "mode": "trigger", "suffix": "_visible"}
                    }

                    for key, cfg in mapping.items():
                        val = other.get(key)
                        if val and val is not False:
                            # 1. 生成用于 ideas 文件的脚本行
                            formatted_line = f"            {key} = {{ {cfg['template'].format(id=v_full_id)} }}"
                            output.append(formatted_line)

                            # 2. 提取并记录对应的 scripted_full_id
                            # 根据前缀判定前缀名（FUN_ 或 TRIGGER_）
                            id_prefix = "FUN" if cfg['mode'] == "effect" else "TRIGGER"
                            scripted_full_id = f"{id_prefix}_{v_full_id}{cfg['suffix']}"

                            # 3. 保证正确添加到字典中
                            if cfg['mode'] in scripted_id_map:
                                scripted_id_map[cfg['mode']].append((scripted_full_id, v_full_id))

                    # 8. Bonus Blocks (换行逻辑同 modifier)
                    for b_type in ["research_bonus", "equipment_bonus"]:
                        b_meta = other.get(b_type, "").strip()
                        if b_meta:
                            self._format_modifier_block(b_type, b_meta, 3)

                    output.append("        }\n")
                output.append("    }")

        output.append("}")
        self._write_file(target_path, output)
        self._create_loc_file(loc_map)
        # _create_scripted_file必须在_create_loc_file后
        self._create_scripted_file(scripted_id_map)


if __name__ == "__main__":
    a = 1/0
    parser = LawParser(JSON5_PATH, OUTPUT_ROOT)
    parser.create_idea_tags()
    parser.create_ideas()
