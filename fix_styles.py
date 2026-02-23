import re

with open('photo_editor/ui/dialogs/layer_styles_dialog.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Make the constants functions that return strings based on the theme
text = text.replace(
    '_LBL_STYLE = "font-size: 9pt; color: #ccc;"',
    'def _lbl_style() -> str:\n    from ...theme import ThemeManager\n    p = ThemeManager.instance().active_palette\n    return f"font-size: 9pt; color: {p[\'fg_dim\']};"'
)

text = text.replace(
    '_HEADER_STYLE = "font-size: 10pt; font-weight: bold; color: #ddd; margin-bottom: 4px;"',
    'def _header_style() -> str:\n    from ...theme import ThemeManager\n    p = ThemeManager.instance().active_palette\n    return f"font-size: 10pt; font-weight: bold; color: {p[\'fg\']}; margin-bottom: 4px;"'
)

# _LIST_STYLE replacement
text = re.sub(
    r'_LIST_STYLE = \"\"\"(.*?)\"\"\"',
    '''def _list_style() -> str:
    from ...theme import ThemeManager
    p = ThemeManager.instance().active_palette
    return f\"\"\"
    QListWidget {{
        background: {p['bg1_alt']};
        border: 1px solid {p['border']};
        border-radius: 3px;
        font-size: 10pt;
    }}
    QListWidget::item {{ padding: 4px 6px; }}
    QListWidget::item:selected {{ background: {p['accent']}; color: {p.get('fg_accent', '#ffffff')}; }}
\"\"\"''',
    text, flags=re.DOTALL
)

# _INLINE_BTN
text = re.sub(
    r'_INLINE_BTN = \"\"\"(.*?)\"\"\"',
    '''def _inline_btn() -> str:
    from ...theme import ThemeManager
    p = ThemeManager.instance().active_palette
    return f\"\"\"
    QPushButton {{
        font-size: 11pt; font-weight: bold; padding: 0;
        border: none; background: transparent; color: {p['fg_dim']};
        min-width: 20px; max-width: 20px;
        min-height: 20px; max-height: 20px;
    }}
    QPushButton:hover {{ color: {p['fg']}; }}
\"\"\"''',
    text, flags=re.DOTALL
)

# _INLINE_DEL_BTN
text = re.sub(
    r'_INLINE_DEL_BTN = \"\"\"(.*?)\"\"\"',
    '''def _inline_del_btn() -> str:
    from ...theme import ThemeManager
    p = ThemeManager.instance().active_palette
    return f\"\"\"
    QPushButton {{
        font-size: 11pt; font-weight: bold; padding: 0;
        border: none; background: transparent; color: {p['fg_dim']};
        min-width: 20px; max-width: 20px;
        min-height: 20px; max-height: 20px;
    }}
    QPushButton:hover {{ color: #e74c3c; }}
\"\"\"''',
    text, flags=re.DOTALL
)

text = text.replace('setStyleSheet(_LBL_STYLE)', 'setStyleSheet(_lbl_style())')
text = text.replace('setStyleSheet(_HEADER_STYLE)', 'setStyleSheet(_header_style())')
text = text.replace('setStyleSheet(_LIST_STYLE)', 'setStyleSheet(_list_style())')
text = text.replace('setStyleSheet(_INLINE_BTN)', 'setStyleSheet(_inline_btn())')
text = text.replace('setStyleSheet(_INLINE_DEL_BTN)', 'setStyleSheet(_inline_del_btn())')

with open('photo_editor/ui/dialogs/layer_styles_dialog.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Done.")
