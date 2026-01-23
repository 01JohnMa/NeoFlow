import os
from unittest import result
from paddleocr import PaddleOCR

def ocr_process()-> list:
    # 指定已经下载的模型路径
    det_model_path = "E:\zhuomian\GNEO_AI\sj_ocr\model\PP-OCRv5_server_det_infer"
    rec_model_path = "E:\zhuomian\GNEO_AI\sj_ocr\model\PP-OCRv5_server_rec_infer"
    ori_model_path = "E:\zhuomian\GNEO_AI\sj_ocr\model\/PP-LCNet_x1_0_textline_ori_infer"
    doc_model_path = "E:\zhuomian\GNEO_AI\sj_ocr\model\PP-LCNet_x1_0_doc_ori_infer"
    
    # 检查模型文件是否存在
    print("检查模型文件...")
    if os.path.exists(det_model_path):
        files = os.listdir(det_model_path)
        print(f"找到 {len(files)} 个文件: {files}")
    else:
        print(f"路径不存在: {det_model_path}")

    # 使用已下载的检测模型，让其他模型自动下载到其他路径
    ocr = PaddleOCR(
        lang='ch',
        det_model_dir=det_model_path,  # 使用已下载的检测模型
        rec_model_dir=rec_model_path,  # 识别模型下载到当前目录
        textline_orientation_model_dir = ori_model_path,
        doc_orientation_classify_model_dir=doc_model_path,
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        # use_textline_orientation=False,  # 使用新参数名
        det_limit_side_len=960,  # 限制检测时图像的最大边长，避免图像过大
        det_limit_type='max' # 限制类型为最大边
        
    )
    result = ocr.predict(
        input=r"E:\zhuomian\GNEO_AI\angent_project\hello-agents\code\chapter6\Langgraph\data\11.11-临海-TJXZ1250910010-G32Z223S.pdf",
        )
    watermarks = ['no', 'noi']
    threshold = 0.5
    filtered_results = []
    for idx, res in enumerate(result):
        texts  = res.get("rec_texts", [])
        scores = res.get("rec_scores", [])
        for text, score in zip(texts, scores):
                if score >= threshold and text not in watermarks:
                    filtered_results.append(text)

    return filtered_results 
