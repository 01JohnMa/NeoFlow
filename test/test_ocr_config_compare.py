"""
OCR 配置对比测试
对比当前系统配置与 MVP 配置的识别效果差异
"""

import os
import time
from paddleocr import PaddleOCR


# 测试图片路径
TEST_IMAGE = r"E:\zhuomian\GNEO_AI\sj_ocr\data\外部抽检单及测试报告\确认单\img_v3_02ue_5647817e-f38a-4cf7-8d33-ed803f78222g.jpg"

# 模型路径
MODEL_BASE = r"E:\zhuomian\GNEO_AI\sj_ocr\model"
DET_MODEL = os.path.join(MODEL_BASE, "PP-OCRv5_server_det_infer")
REC_MODEL = os.path.join(MODEL_BASE, "PP-OCRv5_server_rec_infer")
ORI_MODEL = os.path.join(MODEL_BASE, "PP-LCNet_x1_0_textline_ori_infer")
DOC_MODEL = os.path.join(MODEL_BASE, "PP-LCNet_x1_0_doc_ori_infer")


def create_current_ocr():
    """当前系统配置"""
    return PaddleOCR(
        lang='ch',
        det_model_dir=DET_MODEL,
        rec_model_dir=REC_MODEL,
        textline_orientation_model_dir=ORI_MODEL,
        doc_orientation_classify_model_dir=DOC_MODEL,
        use_doc_orientation_classify=False,  # 当前系统: True
        use_doc_unwarping=False,
        # use_textline_orientation 未设置
        det_limit_side_len=640,  # 当前系统: 960
        det_limit_type='max'
    )


def create_mvp_ocr():
    """MVP notebook 配置"""
    return PaddleOCR(
        lang='ch',
        det_model_dir=DET_MODEL,
        rec_model_dir=REC_MODEL,
        textline_orientation_model_dir=ORI_MODEL,
        use_doc_orientation_classify=False,  # MVP: False
        use_doc_unwarping=False,
        use_textline_orientation=False,      # MVP: 显式关闭
        det_limit_side_len=640,              # MVP: 640
        det_limit_type='max'
    )


def run_ocr_test(ocr_engine, image_path, config_name, threshold=0.5):
    """运行 OCR 测试并返回结果"""
    print(f"\n{'='*60}")
    print(f"测试配置: {config_name}")
    print(f"{'='*60}")
    
    start = time.perf_counter()
    result = ocr_engine.ocr(image_path, cls=True)
    elapsed = time.perf_counter() - start
    
    # 统计结果
    total_lines = 0
    filtered_lines = 0
    all_texts = []
    filtered_texts = []
    watermarks = ['no', 'noi', 'copy', '样本', '仅供参考']
    
    if result:
        for page_result in result:
            if page_result is None:
                continue
            for line_info in page_result:
                if line_info is None or len(line_info) < 2:
                    continue
                text_info = line_info[1]
                if isinstance(text_info, tuple) and len(text_info) >= 2:
                    text = str(text_info[0]).strip()
                    score = float(text_info[1])
                    total_lines += 1
                    all_texts.append((text, score))
                    
                    # 应用过滤
                    if (score >= threshold 
                        and text 
                        and not any(wm in text.lower() for wm in watermarks)):
                        filtered_lines += 1
                        filtered_texts.append((text, score))
    
    print(f"识别耗时: {elapsed:.2f}秒")
    print(f"原始识别行数: {total_lines}")
    print(f"过滤后行数 (threshold={threshold}): {filtered_lines}")
    
    # 显示置信度分布
    if all_texts:
        scores = [s for _, s in all_texts]
        print(f"置信度范围: {min(scores):.3f} ~ {max(scores):.3f}")
        print(f"平均置信度: {sum(scores)/len(scores):.3f}")
        
        # 按置信度区间统计
        ranges = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.0)]
        print("\n置信度分布:")
        for low, high in ranges:
            count = sum(1 for _, s in all_texts if low <= s < high)
            print(f"  [{low:.1f}, {high:.1f}): {count} 行")
    
    return {
        'total_lines': total_lines,
        'filtered_lines': filtered_lines,
        'elapsed': elapsed,
        'all_texts': all_texts,
        'filtered_texts': filtered_texts
    }


def show_sample_texts(texts, title, max_lines=15):
    """显示部分识别文本"""
    print(f"\n{title} (前{max_lines}行):")
    for i, (text, score) in enumerate(texts[:max_lines]):
        print(f"  {i+1}. [{score:.3f}] {text}")
    if len(texts) > max_lines:
        print(f"  ... 还有 {len(texts) - max_lines} 行")


def main():
    # 检查测试图片是否存在
    if not os.path.exists(TEST_IMAGE):
        print(f"错误: 测试图片不存在: {TEST_IMAGE}")
        return
    
    print("="*60)
    print("OCR 配置对比测试")
    print("="*60)
    print(f"测试图片: {TEST_IMAGE}")
    
    # 测试 MVP 配置
    print("\n初始化 MVP 配置 OCR 引擎...")
    mvp_ocr = create_mvp_ocr()
    mvp_result = run_ocr_test(mvp_ocr, TEST_IMAGE, "MVP 配置", threshold=0.5)
    
    # 测试当前系统配置
    print("\n初始化当前系统配置 OCR 引擎...")
    current_ocr = create_current_ocr()
    current_result = run_ocr_test(current_ocr, TEST_IMAGE, "当前系统配置", threshold=0.5)
    
    # 对比结果
    print("\n" + "="*60)
    print("对比结果")
    print("="*60)
    print(f"{'配置':<20} {'原始行数':<12} {'过滤后行数':<12} {'耗时':<10}")
    print("-"*60)
    print(f"{'MVP 配置':<20} {mvp_result['total_lines']:<12} {mvp_result['filtered_lines']:<12} {mvp_result['elapsed']:.2f}秒")
    print(f"{'当前系统配置':<20} {current_result['total_lines']:<12} {current_result['filtered_lines']:<12} {current_result['elapsed']:.2f}秒")
    
    diff = mvp_result['total_lines'] - current_result['total_lines']
    if diff > 0:
        print(f"\n结论: MVP 配置多识别了 {diff} 行，建议采用 MVP 配置参数")
    elif diff < 0:
        print(f"\n结论: 当前配置多识别了 {-diff} 行")
    else:
        print(f"\n结论: 两种配置识别行数相同")
    
    # 显示部分文本
    show_sample_texts(mvp_result['filtered_texts'], "MVP 配置识别结果")
    show_sample_texts(current_result['filtered_texts'], "当前系统配置识别结果")


if __name__ == "__main__":
    main()
