# Training Validation Viewer

基于 PySide6 的训练验证结果可视化工具。三区域布局：状态栏 + 训练参数 → 训练曲线 → GT / Prediction 对比。

---

## 项目结构

```
project/
├─ main.py                  # 入口
├─ requirements.txt
├─ README.md
├─ logs/
│  ├─ training/             # 训练日志 xlsx 文件（每行一个 epoch）
│  └─ app.log               # 应用运行日志（自动生成）
├─ DLPFC_result/            # Ground Truth 图片目录
├─ result/                  # Prediction 图片目录
├─ model/
│  ├─ training_log.py       # Excel 解析、曲线列选择
│  └─ image_manager.py      # 图片扫描、匹配、加载
├─ view/
│  ├─ status_bar.py         # 状态栏 + 参数显示
│  ├─ training_curve.py     # Matplotlib 嵌入曲线
│  ├─ comparison_view.py    # 左右对比 + 缩放/拖拽
│  └─ main_window.py        # 主窗口布局 + 导航
├─ controller/
│  └─ main_controller.py    # 协调 Model 与 View
└─ utils/
   └─ logger.py             # logging 配置
```

---

## 环境配置

### 系统要求

- Python 3.11+
- Windows / Linux / macOS

### 安装

```bash
# 推荐使用虚拟环境
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 启动

```bash
python main.py
```

### 数据准备

| 目录 | 用途 | 必需 |
|------|------|------|
| `logs/training/` | 放入训练日志 xlsx 文件，按修改时间取最新 | 否 |
| `DLPFC_result/` | 放入 Ground Truth 图片（.png / .jpg / .jpeg / .bmp / .tif） | 否 |
| `result/` | 放入 Prediction 图片（与 GT 同名匹配） | 否 |

全部目录缺失时程序仍正常启动，显示对应缺省提示。

---

## 模块接口

### `model/training_log.py`

```python
@dataclass
class TrainingLog:
    file_path: Path | None
    epochs: list[EpochData]
    columns: list[str]
    last_row: dict[str, float]
    status: str            # "Loaded" | "Missing" | "Error"

def load_training_log(log_dir: Path) -> TrainingLog
    """读取 log_dir 中最新 xlsx，返回 TrainingLog。"""

def get_plot_columns(log: TrainingLog) -> tuple[str | None, str | None, str | None]
    """返回 (x_col, y1_col, y2_col)。
    优先 epoch → loss/acc → 前两个数值列。
    """
```

### `model/image_manager.py`

```python
@dataclass
class ImagePair:
    filename: str
    gt_path: Path | None
    pred_path: Path | None
    gt_missing: bool
    pred_missing: bool

@dataclass
class ImageCollection:
    pairs: list[ImagePair]
    gt_dir_status: str       # "Loaded" | "Missing" | "Error"
    pred_dir_status: str
    fallback_mode: bool
    has_pred: bool

def scan_images(gt_dir: Path, pred_dir: Path) -> ImageCollection
    """扫描两个目录，按文件名 stem 匹配，返回 ImageCollection。"""

def load_image(path: Path) -> np.ndarray | None
    """加载单张图片（RGB），失败返回 None。"""
```

### `view/status_bar.py`

```python
class StatusWidget(QWidget):
    def set_status(self, status: str) -> None
        # 设置状态文本及颜色（Loaded=绿 / Missing=橙 / Error=红）

class StatusBarWidget(QWidget):
    # 包含 .training_status / .result_status / .gt_status 三个 StatusWidget

class ParamsWidget(QWidget):
    def set_params(self, params: dict[str, float]) -> None
        # 动态生成参数标签
    def clear(self) -> None
```

### `view/training_curve.py`

```python
class TrainingCurveWidget(QWidget):
    def plot(self, epochs, y1_name, y1_values, y2_name=None, y2_values=None)
        # 绘制训练曲线
    def show_no_data(self)
```

### `view/comparison_view.py`

```python
class ZoomableImageLabel(QLabel):
    # 滚轮缩放 | 拖拽平移 | 双击复位

class ImagePanel(QWidget):
    def show_image(self, image, filename, notice="")
    def clear(self)

class ComparisonViewWidget(QWidget):
    def show_pair(self, pair: ImagePair)
    def show_fallback(self, pair: ImagePair)
    def show_no_data(self)
```

### `view/main_window.py`

```python
class MainWindow(QMainWindow):
    def set_collection(self, collection: ImageCollection)
    def show_status_message(self, message: str)
```

### `controller/main_controller.py`

```python
class MainController(QObject):
    def initialize(self)
        # 加载训练数据 + 图片数据，填充所有 View 组件
```

---

## 日志

输出到 `logs/app.log`，记录：

- 启动 / 退出
- Excel 读取（路径、epoch 数、列名）
- 图片扫描结果（匹配对数、目录状态）
- 文件缺失警告
- 错误信息及异常堆栈

---

