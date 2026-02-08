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


class GenerateModFiles:
    def __init__(self, json_path, output_root):
        self.json_path = json_path
        self.output_root = output_root
        self.data = self._load_json(json_path)
        self.loc_data = {}
        self.importer = MetaImporter(META_IMPORTER_WORKSPACE)
        self._meta_data = self.importer.run_import()
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
                f"\n        ledger = civilian\n        cost = {b_data.get('cost', 150)}\n        removal_cost = {b_data.get('removal_cost', -1)}\n    }}")
        output.append("}")
        self._write_file(target_path, output)

    def _apply_meta_to_structure(self, category, v_full_id, meta_type, indent_level=0, custom_tooltip=""):
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
        if custom_tooltip:
            match category:
                case "modifier":
                    if meta_type == "modifier":
                        raw_meta += f"\ncustom_modifier_tooltip = {custom_tooltip}"
                    else:
                        logger.warning(f"LawParser._apply_meta_to_structure: {category}: {meta_type} 没有 custom_tooltip 属性")
                case "effect":
                    raw_meta += f"\ncustom_effect_tooltip = {custom_tooltip}"
                case _:
                    logger.warning(f"LawParser._apply_meta_to_structure: {category} 没有 custom_tooltip 属性")
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
        根据传入的字典生成本地化文件，支持注释提取和状态标记
        """
        lang_folder = f"{lang}"
        full_filename = f"{filename}_l_{lang}.yml"
        target_path = self._get_path("localisation", lang_folder, full_filename)

        output = [f"l_{lang}:"]
        sorted_keys = sorted(loc_map.keys())

        for key in sorted_keys:
            value = str(loc_map.get(key, ""))

            # --- 1. 处理纯注释逻辑 (例如 value 为 '"# 某种注释"') ---
            if value.startswith('"# ') and value.endswith('"'):
                comment_text = value[3:-1]
                output.append(f'  # {key}: {comment_text}')
                continue

            # --- 2. 状态识别 ---
            # 检查是否为动态文本标记
            is_dy_loc = "DY_LOC" in value
            # 检查是否为待编写标记
            is_to_be_written = "TO_BE_WRITTEN" in value or not value.strip()

            # --- 3. 文本清洗与格式化 ---
            # 如果是待编写，给一个空值或保留原始占位符，否则清理转义符
            if is_to_be_written:
                clean_value = ""
                note = " # TODO: To be written"
            elif is_dy_loc:
                output.append(f' # {key} DY_LOC')
                continue
            else:
                # 正常文本处理：转义双引号，转换换行符
                clean_value = value.replace('"', '\\"').replace('\n', '\\n')
                note = ""

            # --- 4. 生成 YML 行 ---
            # 格式示例: key:0 "value" # note
            output.append(f'  {key}:0 "{clean_value}"{note}')

            # 更新内存中的 loc_data 供自检使用
            # 如果是待编写，内存中存入空或 key 本身以防报错
            self.loc_data[key] = clean_value if not is_to_be_written else f"MISSING_{key}"

        # 使用 utf-8-sig 写入
        self._write_file(target_path, output, encoding='utf-8-sig')
        # logger.info(f"本地化文件已生成: {full_filename}")

    def validate_and_sync_localization(self):
        """
        自检方法：追踪 Meta 与本地化数据的一致性
        1. 当 Meta 名称为空但 Loc 中有值时，自动填充 Meta 索引。
        2. 当两者名称不匹配时，输出警告（条目可能被修改或移动）。
        3. 当 Meta 中的 ID 在 Loc 中不存在时，输出警告（条目可能被删除）。
        """
        logger.info("--- 开始元数据一致性自检 ---")

        sync_count = 0  # 自动填充计数
        mismatch_count = 0  # 名字不匹配计数
        missing_count = 0  # ID 缺失计数

        # 遍历 MetaImporter 导入的原始列表
        # 结构: {"category": [{"v_full_id": "...", "v_name": "...", ...}, ...]}
        for category, items in self._meta_data.items():
            for item in items:
                v_id = item['v_full_id']
                # 脚本中的注释名
                script_name = item.get('v_name', "").strip()
                if script_name == "None":
                    script_name = ""
                # 内存中现有的本地化文本（由 create_loc_file 或加载过程更新）
                loc_name = self.loc_data.get(v_id, "").strip()

                # 1. 检查 ID 是否存在于本地化字典中
                if v_id not in self.loc_data:
                    logger.warning(f"[{category}] 潜在删除: ID '{v_id}' 在本地化数据中未找到。")
                    missing_count += 1
                    continue

                # 2. 自动填充逻辑：Meta 为空，Loc 有值
                if not script_name and loc_name:
                    item['v_name'] = loc_name
                    # 同时更新索引中的数据，确保写入脚本时带上注释
                    if v_id in self.meta_index.get(category, {}):
                        # 这里假设你索引里也存了 v_name，或者你之后会根据 item 重新构建索引
                        pass
                    logger.info(f"[{category}] 自动填充: ID '{v_id}' 已同步本地化名称 '{loc_name}'。")
                    sync_count += 1
                    continue

                # 3. 比较名称是否一致
                # 只要 script_name 有值且与 loc_name 不同，就触发警告
                if script_name and script_name != loc_name:
                    logger.warning(f"[{category}] 内容不一致: ID '{v_id}'")
                    logger.warning(f"  -> 脚本注释: '{script_name}'")
                    logger.warning(f"  -> 本地化文本: '{loc_name}'")
                    logger.info(f"  提示：该条目可能已被修改、移动或设置为动态文本。")
                    mismatch_count += 1

        logger.info(f"自检报告: 同步 {sync_count} 条, 冲突 {mismatch_count} 条, 缺失 {missing_count} 条。")

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
                    v_name = v_data.get("name", '"# TO_BE_WRITTEN"')
                    v_desc = v_data.get("desc", '"# TO_BE_WRITTEN"')
                    use_id_name = v_data.get("use_id_name", True)
                    v_full_id = self._get_full_id(b_key, id_key, v_key)
                    if v_name:
                        v_full_name = f"{id_name}{COLON_STYLE}{v_name}" if use_id_name else v_name
                        loc_map.setdefault(v_full_id, v_full_name)
                        output.append(f"        {v_full_id} = {{ # {v_full_name}")
                    else:
                        scripted_full_id = f"get_{v_full_id}"
                        scripted_id_map["loc"].append((scripted_full_id, v_full_id))
                        loc_map.setdefault(v_full_id, '"# DY_LOC"')
                        output.append(f"        {v_full_id} = {{ # DY_LOC")
                    if v_desc:
                        loc_map.setdefault(f"{v_full_id}_desc", v_desc)
                    else:
                        scripted_full_id = f"get_{v_full_id}_desc"
                        scripted_id_map["loc"].append((scripted_full_id, v_full_id))
                        loc_map.setdefault(f"{v_full_id}_desc", '"# DY_LOC"')

                    # 1. Level & Default & cancel_if_invalid
                    if v_data.get("level", 0) > 0:
                        output.append(f"            level = {v_data['level']}")
                    if v_data.get("default", False):
                        output.append("            default = yes")
                        output.append("            cancel_if_invalid = yes")
                    elif v_data.get("cancel_if_invalid", False):
                        output.append("            cancel_if_invalid = yes")

                    # 2. Allowed Civil War
                    acw = v_data.get("allowed_civil_war_flag", 1)
                    if acw > 0:
                        output.append("            allowed_civil_war = { always = yes }")
                    elif acw < 0:
                        scripted_full_id = f"TRIGGER_{v_full_id}_allowed_cv"
                        scripted_id_map["trigger"].append((scripted_full_id, v_full_id))
                        output.append(f"            allowed_civil_war = {{ {scripted_full_id} = yes }}")

                    # 3. Available
                    if v_data.get("available", True):
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
                    custom_modifier_tooltip = f"custom_modifier_tooltip = {v_full_id}_tooltip" if v_data.get("custom_modifier_tooltip") else ""
                    if custom_modifier_tooltip:
                        loc_map.setdefault(f"{v_full_id}_modifier_tooltip", "")
                    output.append("            modifier = {")
                    output.append(
                        self._apply_meta_to_structure("modifier", v_full_id, "modifier", 4, custom_modifier_tooltip)
                    )
                    output.append("            }")

                    # 7. Other Meta (同级脚本块)
                    other_meta = v_data.get("other_meta", {})
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
                        val = other_meta.get(key)
                        if val and val is not False:
                            # 1. 生成用于 ideas 文件的脚本行
                            formatted_line = f"            {key} = {{ {cfg['template'].format(id=v_full_id)} }}"
                            output.append(formatted_line)

                            # 2. 提取并记录对应的 scripted_full_id
                            # 根据前缀判定前缀名（FUN_ 或 TRIGGER_）
                            id_prefix = "EFFECT" if cfg['mode'] == "effect" else "TRIGGER"
                            scripted_full_id = f"{id_prefix}_{v_full_id}{cfg['suffix']}"

                            # 3. 保证正确添加到字典中
                            if cfg['mode'] in scripted_id_map:
                                scripted_id_map[cfg['mode']].append((scripted_full_id, v_full_id))

                    # 8. Bonus Blocks
                    for bonus_type in ["research_bonus", "equipment_bonus"]:
                        bonus_meta = other_meta.get(bonus_type, "").strip()
                        if bonus_meta:
                            output.append(f"            {bonus_type} = {{")
                            output.append(
                                self._apply_meta_to_structure("preferences", v_full_id, bonus_type, 4)
                            )
                            output.append("            }")

                    # 9. Ai will do
                    ai_will_do = v_data.get("ai_will_do", {"base": 1.0, "preferences": True})
                    ai_preferences_base = ai_will_do.get("base", -1.0)
                    ai_preferences_factor = ai_will_do.get("factor", -1.0)
                    ai_preferences_meta = ai_will_do.get("preferences", False)
                    if (ai_preferences_base >= 0) ^ (ai_preferences_factor >= 0):
                        ai_preferences_value = f"base = {ai_preferences_base}" if ai_preferences_base >= 0 else f"factor = {ai_preferences_factor}"
                    else:
                        ai_preferences_value = "base = 1"
                        logging.warning(f"GenerateModFiles: {v_full_id}: Ai will do base属性和factor属性同时出现，已重置为base = 1")
                    output.append("            ai_will_do = {")
                    output.append(f"                {ai_preferences_value}")
                    if ai_preferences_meta:
                        output.append(self._apply_meta_to_structure("preferences", v_full_id, "preferences", 5))
                    output.append("            }")

                    output.append("        }\n")
                output.append("    }")

        output.append("}")
        self._write_file(target_path, output)
        self._create_loc_file(loc_map)
        # _create_scripted_file必须在_create_loc_file后
        self._create_scripted_file(scripted_id_map)


if __name__ == "__main__":
    parser = GenerateModFiles(JSON5_PATH, OUTPUT_ROOT)
    parser.create_idea_tags()
    parser.create_ideas()
    parser.validate_and_sync_localization()
