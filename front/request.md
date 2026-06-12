Build a React + TypeScript scientific visualization interface for comparing clustering results (Ground Truth vs Prediction).

# Layout

* Fixed left sidebar for app navigation.
* Right side is a vertically scrollable main panel.
* Main panel supports two comparison modes switched by a single toggle button.

Modes:

* Overlay
* Side-by-Side

---

# Data Source

Overlay mode uses structured data (CSV/JSON), not screenshots.

Each cell contains:

```ts
{
    cell_id: string | number,
    x: number,
    y: number,
    ground_truth: string,
    prediction: string,

    // optional
    pred_x?: number,
    pred_y?: number
}
```

Side-by-Side mode uses existing PNG/JPG images.

---

# Overlay Mode (Error Explorer)

Purpose:
Analyze prediction errors.

Visualization:

* Use two semi-transparent acrylic panels.
* Front panel: Ground Truth.
* Back panel: Prediction.
* Panels have glass-like appearance, subtle highlights, and depth separation.

Interactions:

* Drag to rotate the acrylic object freely.
* Mouse wheel zoom.
* Double-click reset view.
* Smooth inertial animation.
* Support flipping 180° around the vertical axis to switch GT/Prediction emphasis.
* Support panel self-rotation around its center.

---

# Error Logic

For each cell:

Correct:

* GT label == Prediction label
* Position difference ≤ threshold (if pred_x/pred_y exist)

Misclassification:

* GT label != Prediction label
* Position difference ≤ threshold

Embedding Shift:

* GT label == Prediction label
* Position difference > threshold

Critical Error:

* GT label != Prediction label
* Position difference > threshold

If prediction coordinates do not exist:

* Only evaluate classification errors.

---

# Visual Encoding

Correct cells:

* Low saturation.
* Monet-style palette.
* Semi-transparent.
* Background role.

Errors:

* High saturation.
* Strong contrast.
* Glow/highlight effect.
* Foreground role.

Suggested mapping:

Correct:

* soft muted cluster colors.

Misclassification:

* orange.

Embedding Shift:

* bright cyan.

Critical Error:

* neon red.

Use different shapes in addition to colors:

Correct:
●

Misclassification:
◆

Embedding Shift:
▲

Critical Error:
✦

---

# Hover

Hovering an error cell displays:

* Cell ID
* Ground Truth label
* Prediction label
* Error Type
* Severity

If position errors exist:

* GT position
* Prediction position
* Shift distance

Hover should simultaneously emphasize the corresponding GT and Prediction points.

---

# Side-by-Side Mode

Purpose:
Global inspection and presentation.

Visualization:

* Display Ground Truth image and Prediction image side by side.
* No visible borders.
* Invisible interaction bounds equal to image dimensions.

Interactions:

Two operation modes:

Independent:

* Pan
* Zoom
* Rotate
* Operate separately.

Synchronized:

* Pan
* Zoom
* Rotate
* Mirror operations on both images.

Support:

* Lock / Unlock toggle.
* Double-click reset.

When synchronization is enabled after images have diverged:

* Both images return to their initial state before synchronization begins.

---

# Interaction Flow

Users should naturally switch between modes:

Side-by-Side:
Observe global differences.

Overlay:
Investigate why errors occur.

The design priority is:

"Do not make users search for errors; make errors actively stand out."

Favor clarity, scientific usefulness, and performance over decorative effects.

---

# Technical Suggestions

* React
* TypeScript
* React Three Fiber / Three.js for Overlay mode
* Framer Motion for transitions
* Zustand for state management
* InstancedMesh for large-scale scatter rendering

Target performance:
20k–100k cells with interactive frame rates.
