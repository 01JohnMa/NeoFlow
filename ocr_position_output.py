def ocr_result_to_text(ocr_result, line_threshold=10):
    """
    将 PaddleOCR 结果按阅读顺序整理为纯文本
    
    Args:
        ocr_result: PaddleOCR 返回的原始结果 result[0]
        line_threshold: 判断是否同一行的 Y 轴误差阈值（像素）
    
    Returns:
        text: 整理后的纯文本字符串
    """
    if not ocr_result:
        return ""

    # 提取每个文本块的信息：中心Y、最小X、文本内容
    items = []
    for line in ocr_result:
        box = line[0]
        text = line[1][0]
        # confidence = line[1][1]  # 如需过滤低置信度可在这里加判断

        y_center = sum(p[1] for p in box) / 4  # 四个顶点的 Y 均值
        x_min = min(p[0] for p in box)

        items.append({
            "text": text,
            "y": y_center,
            "x": x_min,
        })

    # 按 Y 坐标排序
    items.sort(key=lambda i: i["y"])

    # 按 Y 坐标分组成"行"
    lines = []
    current_line = [items[0]]

    for item in items[1:]:
        # 与当前行最后一个元素的 Y 差值在阈值内，视为同一行
        if abs(item["y"] - current_line[-1]["y"]) <= line_threshold:
            current_line.append(item)
        else:
            lines.append(current_line)
            current_line = [item]
    lines.append(current_line)

    # 每行内按 X 坐标排序，然后拼接文本
    result_lines = []
    for line in lines:
        line.sort(key=lambda i: i["x"])
        line_text = "    ".join(item["text"] for item in line)  # 同行用空格分隔
        result_lines.append(line_text)

    return "\n".join(result_lines)

# 按页分别输出
for i in range(len(result)):
    page_text =ocr_result_to_text(result[i], line_threshold=15)
    print(f"=== 第 {i+1} 页 ===")
    print(page_text)
    print()  # 空行分隔
