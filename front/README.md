# Spatial Clustering Comparison Viewer

PySide6 reusable visualization tool for comparing spatial clustering results.

Two comparison modes:
- **Overlay** ? scatter plot with error analysis (reads CSV/TSV from DLPFC dataset)
- **Side-by-Side** ? side-by-side image comparison (reads PNG from DLPFC_result)

---

## Project Structure

```
AI_exercise/
??? front/
?   ??? main.py                  # Entry point
?   ??? requirements.txt
?   ??? README.md
?   ??? model/
?   ?   ??? training_log.py      # Excel parsing, curve column selection
?   ?   ??? image_manager.py     # Image scanning, matching, loading
?   ?   ??? overlay_data.py      # Overlay cell data, error analysis, CSV/TSV loading
?   ??? view/
?   ?   ??? status_bar.py        # Status bar + params display
?   ?   ??? training_curve.py    # Matplotlib embedded training curve
?   ?   ??? comparison_view.py   # Side-by-side image comparison + zoom/pan
?   ?   ??? overlay_view.py      # Matplotlib scatter overlay view
?   ?   ??? main_window.py       # Main window layout + mode toggle + nav
?   ??? controller/
?   ?   ??? main_controller.py   # Coordinates model and view
?   ??? utils/
?       ??? logger.py            # Logging config
??? dataset/
?   ??? DLPFC/
?       ??? 151507/ ... 151676/  # Section data (metadata.tsv, positions CSV, images)
?       ??? DLPFC_result/        # Ground truth result images for side-by-side
??? reference/
    ??? SpaTopic/                # Reference R package
```

---

## Environment Setup

- Python 3.11+
- Windows / Linux / macOS

```bash
cd front
python -m venv .venv

# Windows
.venv\Scriptsctivate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Launch

```bash
cd front
python main.py
```

---

## Data Preparation

| Directory | Purpose | Required |
|-----------|---------|----------|
| `dataset/DLPFC/{section}/` | Metadata TSV + tissue positions CSV | Yes (overlay) |
| `dataset/DLPFC/DLPFC_result/` | Ground truth result images (PNG) | No (side-by-side) |
| `logs/training/` | Training log xlsx files | No |

---

## Overlay Mode (Error Explorer)

Reads structured data from `metadata.tsv` and `tissue_positions_list.csv` in each section folder.

**Error Classification:**
| Category | Color | Shape | Condition |
|----------|-------|-------|-----------|
| Correct | Gray | Circle | GT == Prediction |
| Misclassification | Orange | Diamond | GT != Prediction |

**Visual Encoding:**
- Correct cells: low saturation, semi-transparent, background role
- Error cells: high saturation, strong contrast, foreground role

Navigate sections with prev/next arrows or slider.

## Side-by-Side Mode

Displays ground truth images side by side.

- Lock/Unlock sync toggle for synchronized pan/zoom
- Double-click to reset view
- Mouse wheel zoom, drag to pan

---

## Module Interfaces

### `model/overlay_data.py`

```python
class ErrorType(Enum):
    CORRECT, MISCLASSIFICATION, EMBEDDING_SHIFT, CRITICAL_ERROR

@dataclass
class OverlayCellData:
    cell_id: str
    x: float; y: float
    ground_truth: str; prediction: str
    pred_x: Optional[float]; pred_y: Optional[float]

@dataclass
class OverlayDataset:
    section_id: str
    cells: list[OverlayCellData]
    image_path: Optional[Path]

def load_overlay_dataset(data_root, section_id, gt_column, pred_column) -> Optional[OverlayDataset]
def load_all_overlay_datasets(data_root, section_ids, ...) -> list[OverlayDataset]
```

### `view/overlay_view.py`

```python
class OverlayViewWidget(QWidget):
    def set_dataset(dataset: Optional[OverlayDataset])
    def show_no_data()
    def update_theme(dark: bool)
```

---

## Paths

Data paths are configured in `controller/main_controller.py`:

```python
DATA_ROOT = Path(r"E:\Code\AI_exercise\dataset\DLPFC")
GT_IMAGE_DIR = DATA_ROOT / "DLPFC_result"
LOG_DIR = Path(r"E:\Code\AI_exercise\logs\training")
SECTION_IDS = ["151507", ..., "151676"]
```

---

## Logging

Output to `logs/app.log`, records:
- Startup / exit
- Excel reading (path, epochs, columns)
- Overlay section loading (cells, errors, error rate)
- Image scan results (match pairs, directory status)
- File missing warnings
- Errors with stack traces
