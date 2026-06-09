# Training Validation Viewer — 前端对后端需求清单

## 版本

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-06-09 | 初版 |

---

## 1. 概述

前端（Training Validation Viewer）是一个基于 PySide6 的桌面 GUI 应用，用于可视化训练过程中的日志与推理结果。  **不负责生成任何内容，只负责图片以及训练参数的读取**。
后端（训练/推理管线）需按约定格式输出数据，前端自动读取并展示。

---

## 2. 目录结构约定

```
project/
├─ logs/
│  └─ training/          ← 训练日志输出目录
├─ DLPFC_result/         ← Ground Truth 图片目录
└─ result/               ← Prediction 图片目录
```

> 三个目录均可缺失，前端不会崩溃，仅显示对应的缺省提示。

---

## 3. 训练日志 — Excel 格式

### 位置

`logs/training/` 目录下，**按文件修改时间取最新**的一个 `.xlsx` 文件。

### 格式要求

| 要求 | 说明 |
|------|------|
| 文件格式 | `.xlsx`（由 openpyxl 读取） |
| 表结构 | 每行 = 一个 epoch，按行号顺序排列 |
| 列名 | **动态读取**，禁止写死字段名 |
| 数值 | 所有列应为可转换为 `float` 的数值 |

### 推荐的列

| 列名 | 类型 | 用途 |
|------|------|------|
| `epoch` | int | X 轴（若缺失则使用行号） |
| `loss` | float | 曲线优先绘制 |
| `acc` 或 `accuracy` | float | 曲线优先绘制 |

> 若 `loss` / `acc` 均不存在，前端自动选择**前两个**数值列绘图。

### 示例

| epoch | loss | acc | val_loss | val_acc |
|-------|------|-----|----------|---------|
| 1 | 2.345 | 0.512 | 2.567 | 0.498 |
| 2 | 1.876 | 0.634 | 2.123 | 0.612 |
| ... | ... | ... | ... | ... |
| 50 | 0.023 | 0.997 | 0.045 | 0.992 |

> **不要**添加额外的 header、merge cell、公式或非数值行。第一行即为列头。

---

## 4. 状态指示含义

| 状态 | 含义 |
|------|------|
| `Loaded` | 数据存在且读取成功 |
| `Missing` | 目录不存在 / 目录为空 / 无匹配文件 |
| `Error` | 目录存在但读取失败（文件损坏、权限等） |

三种状态分别以 **绿色 / 橙色 / 红色** 显示。

---

## 5. 图片 — 目录结构

### Ground Truth 目录：`DLPFC_result/`
- 这个存放正确的数据集
```
DLPFC_result/
├─ subject_001/
│   ├─ img_0001.png
│   ├─ img_0002.png
│   └─ ...
├─ subject_002/
│   ├─ img_0001.png
│   └─ ...
└─ ...
```

### Prediction 目录：`result/`
- 用于存放后端训练后测试的图片结果
```
result/
├─ subject_001/
│   ├─ img_0001.png     ← 与 DLPFC_result/subject_001/img_0001.png 匹配
│   ├─ img_0002.png
│   └─ ...
├─ subject_002/
│   ├─ img_0001.png
│   └─ ...
└─ ...
```

### 匹配规则

- **按相对路径**匹配（相对于各自基目录）。
- 例如 `DLPFC_result/subject_001/img_0001.png` ↔ `result/subject_001/img_0001.png`。
- 若 Prediction 目录中缺少某个文件，前端自动回退显示对应的 Ground Truth，并标注 `Prediction Missing / Showing Ground Truth Only`。
- 若 Prediction 目录整体缺失或为空，两端均显示 Ground Truth，并标注 `No Training Result Available / Showing Ground Truth Only`。

### 支持的图片格式

| 格式 | 扩展名 |
|------|--------|
| PNG | `.png` |
| JPEG | `.jpg`, `.jpeg` |
| BMP | `.bmp` |
| TIFF | `.tif`, `.tiff` |

### 图片要求

- 颜色空间：**RGB**（前端读取后用 OpenCV 转换，BGR 也支持）
- 尺寸：无硬限制，建议单边 ≤ 4096 px
- 数量：支持 100 ~ 1000+ 张（前端实现 Lazy Load，仅渲染可见区域）

---

## 6. 前端功能汇总（供后端了解能力范围）

| 功能 | 说明 |
|------|------|
| 训练曲线 | Matplotlib 嵌入，双 Y 曲线 |
| 状态栏 | 三状态实时指示 |
| 参数表 | 动态读取 Excel 最后一行动态展示 |
| 图片对比 | GT（左） / Prediction（右） 并排 |
| 缩放 | 滚轮缩放（0.1x ~ 10x） |
| 拖拽 | 鼠标拖拽平移 |
| 双击复位 | 双击恢复 1:1 |
| 锁定同步 | 左右图片操作绑定 |
| 主题切换 | 深色 / 浅色 |
| 导航 | 滑块 + 前后按钮切换图片 |
| Lazy Load | 防抖加载，仅加载当前图片 |
| 日志 | 输出到 `logs/app.log` |
| 容错 | 目录缺失 / 文件损坏均不崩溃 |

---

## 7. 变更说明

后端输出格式若有变更，需同步更新此文档并告知前端开发者（Jupiter）。
