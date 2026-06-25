with open("upload_view.py", "r", encoding="utf-8-sig") as f:
    lines = f.readlines()

# Fix the file: remove broken inline set_dark, restore __init__, add proper set_dark
new_lines = []
in_broken_set_dark = False
in_init = False
added_set_dark = False

for i, line in enumerate(lines):
    stripped = line.strip()
    
    # Detect __init__ method
    if stripped.startswith("def __init__"):
        in_init = True
        new_lines.append(line)
        continue
    
    if in_init and not stripped.startswith("def ") and line.startswith("    def "):
        in_init = False
    
    # Skip the broken inline set_dark
    if stripped.startswith("def set_dark") and not line.startswith("    def set_dark"):
        in_broken_set_dark = True
        continue
    if in_broken_set_dark:
        if line.startswith("        ") and not stripped:
            pass  # skip empty lines inside
        elif line.startswith("    ") and not line.startswith("        "):
            in_broken_set_dark = False
        else:
            continue  # skip lines inside broken set_dark

    # If we see the next class method (4-space def), add set_dark before it
    if not added_set_dark and line.startswith("    def ") and not stripped.startswith("def __init__") and not stripped.startswith("def set_dark"):
        new_lines.append("\n")
        new_lines.append("    def set_dark(self, dark: bool) -> None:\n")
        new_lines.append("        self._dark = dark\n")
        new_lines.append('        self._path_label.setStyleSheet("color: #aaa; font-size: 12px;" if dark else "color: #888; font-size: 12px;")\n')
        added_set_dark = True
    
    new_lines.append(line)

# Add at end if not found
if not added_set_dark:
    new_lines.append("\n")
    new_lines.append("    def set_dark(self, dark: bool) -> None:\n")
    new_lines.append("        self._dark = dark\n")
    new_lines.append('        self._path_label.setStyleSheet("color: #aaa; font-size: 12px;" if dark else "color: #888; font-size: 12px;")\n')

with open("upload_view.py", "w", encoding="utf-8-sig") as f:
    f.writelines(new_lines)
print("OK")
