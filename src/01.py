def generate_localization_keys():
    keys = []

    # 定义取值范围
    branches = [1]
    ids = range(1, 9)  # 1-8
    values = range(1, 7)  # 1-6

    # 四种类型的key
    key_types = ['name', 'desc', 'adopt_cost', 'impl_cost']

    for branch in branches:
        for id_num in ids:
            for value in values:
                for key_type in key_types:
                    key = f"NIE_law_branch_{branch}_id_{id_num}_value_{value}_{key_type}"
                    keys.append(key)

    return keys

# 生成并输出所有localization_key
localization_keys = generate_localization_keys()

# 打印所有生成的key
print("生成的localization_keys数量:", len(localization_keys))
print("\n所有localization_key:")
print("-" * 50)
for i, key in enumerate(localization_keys, 1):
    print(key)
