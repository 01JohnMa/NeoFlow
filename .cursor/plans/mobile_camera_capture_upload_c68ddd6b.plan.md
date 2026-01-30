---
name: 手机端相机拍照上传
overview: 调整手机端上传使用 input capture 调起系统相机，并在手机端隐藏内置相机按钮，桌面端保持不变。
todos:
  - id: add-mobile-detection
    content: 在 Upload.tsx 添加手机/粗指针环境检测。
    status: completed
  - id: update-file-inputs
    content: 为手机端文件输入添加 capture/accept 设置。
    status: completed
  - id: hide-camera-button-mobile
    content: 手机端隐藏 getUserMedia 相机按钮。
    status: completed
isProject: false
---

# 计划：手机端相机拍照上传

## 方案

- 在 [`web/src/pages/Upload.tsx`](web/src/pages/Upload.tsx) 中检测手机/粗指针环境，作为行为开关。
- 手机端为隐藏文件输入添加 `capture="environment"` 与更偏向图片的 `accept`，点击上传区域直接调起系统相机。
- 手机端隐藏现有“打开相机”（getUserMedia）按钮，桌面端保留。

## 修改文件

- [`web/src/pages/Upload.tsx`](web/src/pages/Upload.tsx)
                - 在组件初始化附近增加 `isMobile`/`isCoarsePointer` 判断。
                - 更新质量自动识别与照明合并的文件输入，加入 `capture` 与手机端 `accept`。
                - 相机按钮渲染增加 `!isMobile` 条件，手机端改用系统相机。

## 备注

- 相关输入位置如下：
                - Quality auto mode input and camera button:```394:418:web/src/pages/Upload.tsx

<input

ref={fileInputRef}

type="file"

accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"

onChange={handleInputChange}

className="hidden"

/>

...

{isCameraSupported && (

<div className="mt-6 text-center">

...

<Button variant="outline" onClick={openCamera}>

````
  - Lighting merge inputs:```478:487:web/src/pages/Upload.tsx
                    <input
                      ref={(el) => { mergeFileInputRefs.current[item.id] = el }}
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
                      onChange={(e) => { ... }}
                      className="hidden"
                    />
````

- `capture` 在不同浏览器上会优先调用相机，同时仍可能允许选择相册/文件。