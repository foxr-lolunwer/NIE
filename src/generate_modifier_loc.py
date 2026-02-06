import re
import json5

# --- 配置区 ---
INPUT_FILE = r"common\ideas\NIE_laws_and_ideas.txt"
DESC_FILE = r"src\law_name_and_desc.json5"
OUTPUT_FILE = r"src\out\localisation_output.yml"

# 1. 效果正负逻辑 (黑名单)
MODIFIER_LOGIC = {
    "training_time_factor": False,
    "training_time_army_factor": False,
    "consumer_goods_factor": False,
}

# 2. 百分比显示黑名单
VALUE_BLACKLIST = [
    "political_power_gain",
]

def format_value(name, value):
    try:
        val = float(value)
        if name in VALUE_BLACKLIST:
            return f"{val:+.3f}" if val != 0 else "0"
        return f"{val * 100:+.1f}%"
    except:
        return value

def is_good_modifier(name, value):
    try:
        val = float(value)
        return val > 0 if MODIFIER_LOGIC.get(name, True) else val < 0
    except:
        return True

def parse_all_ideas(content):
    ideas_data = []
    # 匹配模式：NIE_law_branch_1_id_1_value_1_idea
    idea_pattern = re.compile(r'(NIE_law_branch_(\d+)_id_(\d+)_value_(\d+)_idea)\s*=\s*\{')

    for match in idea_pattern.finditer(content):
        full_id = match.group(1)
        b_num, i_num, v_num = match.group(2), match.group(3), match.group(4)

        start_pos = match.end()
        count, end_pos = 1, start_pos
        while count > 0 and end_pos < len(content):
            if content[end_pos] == '{': count += 1
            elif content[end_pos] == '}': count -= 1
            end_pos += 1

        idea_block = content[start_pos:end_pos-1]
        modifier_match = re.search(r'modifier\s*=\s*\{([^}]*)\}', idea_block)

        modifiers = []
        if modifier_match:
            kv_pairs = re.findall(r'([a-zA-Z0-9_]+)\s*=\s*([-0-9.]+)', modifier_match.group(1))
            for k, v in kv_pairs:
                color = "G" if is_good_modifier(k, v) else "R"
                display_val = format_value(k, v)
                modifiers.append(f"  $MODIFIER_{k.upper()}$：§{color}{display_val}§!")

        ideas_data.append({
            "id": full_id,
            "path": (f"branch{b_num}", f"id{i_num}", f"value{v_num}"),
            "branch": b_num,
            "mods": modifiers
        })
    return ideas_data

def run():
    # 读取 JSON5 描述
    with open(DESC_FILE, 'r', encoding='utf-8') as f:
        desc_data = json5.load(f)

    # 读取并预处理 Idea TXT
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = re.sub(r'#.*', '', f.read())
        content = ' '.join(content.split())

    parsed_ideas = parse_all_ideas(content)

    # 生成 YML
    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig') as f:
        f.write("l_simplified_chinese:\n")
        for item in parsed_ideas:
            idx = item['id']
            b, i, v = item['path']

            # 从 JSON5 获取数据，若缺失则返回占位符
            try:
                name = desc_data[b][i][v]['name']
                desc = desc_data[b][i][v]['desc']
            except KeyError:
                name, desc = "Unknown Law", "No Description"

            mod_lines = "\\n".join(item['mods'])

            # 写入本地化条目
            f.write(f'  {idx}: "{name}"\n')
            f.write(f'  {idx}_desc: "${idx}_modifier$\\n\\n{desc}"\n')
            # 按照要求的格式生成 modifier 行
            f.write(f'  {idx}_modifier: "§Y${idx}$§!：\\n{mod_lines}"\n')

            f.write(f'  {idx}_adopt_cost: "$NIE_law_branch_default_adopt_cost_template$"\n')
            f.write(f'  {idx}_impl_cost: "$NIE_law_branch_default_impl_cost_template$"\n')

if __name__ == "__main__":
    run()
    print("Localisation generated successfully.")