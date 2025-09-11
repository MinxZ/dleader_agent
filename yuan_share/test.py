# import json

# file_path = "/home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1.sections.json"

# with open(file_path, "r", encoding="utf-8") as f:
#     data = json.load(f)

# print("Keys:", list(data.keys()))

# for key, value in data.items():
#     if isinstance(value, str):
#         # print(f"{key}: length={len(value)}, example='{value[:10]}{'...' if len(value) > 100 else ''}'")
#         print(f"length={len(value)} {key}: ")
#     elif isinstance(value, list):
#         print(f"{key}: length={len(value)}, example={value[:2] if len(value) > 0 else 'empty list'}")
#     elif isinstance(value, dict):
#         print(f"{key}: length={len(value)}, keys={list(value.keys())[:5]}")
#     else:
#         print(f"{key}: type={type(value)}, value={value}")


#!/usr/bin/env python3

import json

# 读取JSON文件
with open("/home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1.sections.labeled.json", 'r', encoding='utf-8') as f:
    data = json.load(f)

# 打印所有标签
print("所有sections的标签:")
for key, value in data.items():
    label = value['label']
    print(f"{key}: {label}")

print(f"\n总共 {len(data)} 个sections")

# 统计标签分布
label_counts = {}
for value in data.values():
    label = value['label']
    label_counts[label] = label_counts.get(label, 0) + 1

print("\n标签统计:")
for label, count in sorted(label_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"{label}: {count}")