"""Find widgets that are squashed or cut in a shown window (offscreen Qt).

Leo's v0.2.7 (2026-10-22): the 定时启动 rows were squashed and cut while every
earlier check passed, because none looked at the real window as it opens.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractScrollArea, QLabel, QScrollArea, QSizePolicy, QWidget

SLACK = 1  # px of rounding


def _inside_scroll(widget: QWidget, root: QWidget) -> bool:
    parent = widget.parentWidget()
    while parent is not None and parent is not root:
        if isinstance(parent, QAbstractScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def _in_scroll_bar(widget: QWidget, root: QWidget) -> bool:
    """A scroll bar's own parts (qfluentwidgets keeps hidden arrows at 10 px)."""
    while widget is not None and widget is not root:
        if "ScrollBar" in type(widget).__name__:
            return True
        widget = widget.parentWidget()
    return False


def problems(root: QWidget) -> list[str]:
    """One line per widget that is squashed below its least size, cut by its
    parent's edge, or a one-line label narrower than its text."""
    found = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisibleTo(root) or widget.isWindow() or _in_scroll_bar(widget, root):
            continue
        name = f"{type(widget).__name__} {getattr(widget, 'text', lambda: '')()!r}"
        least = widget.minimumSizeHint()
        policy = widget.sizePolicy().verticalPolicy()
        if (
            least.isValid()
            and policy != QSizePolicy.Ignored
            and widget.height() + SLACK < least.height()
        ):
            found.append(f"{name}: {widget.height()} px tall, needs {least.height()}")
        parent = widget.parentWidget()
        if parent is not None and not _inside_scroll(widget, root):
            box = widget.geometry()
            area = parent.rect().adjusted(-SLACK, -SLACK, SLACK, SLACK)
            if not area.contains(box):
                found.append(f"{name}: {box.getRect()} sticks out of {type(parent).__name__} {parent.rect().getRect()}")
        if isinstance(widget, QLabel) and not widget.wordWrap() and widget.text():
            need = widget.sizeHint()
            if widget.width() + SLACK < need.width() and not widget.toolTip():
                found.append(f"{name}: {widget.width()} px wide, text needs {need.width()}")
            if widget.height() + SLACK < need.height():
                found.append(f"{name}: {widget.height()} px tall, text needs {need.height()}")
    for area in root.findChildren(QScrollArea):
        content = area.widget()
        if (
            area.isVisibleTo(root)
            and content is not None
            and area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
            and content.width() > area.viewport().width() + SLACK
        ):
            # Nothing scrolls sideways: the right part is simply cut off.
            found.append(
                f"{type(area).__name__}: content {content.width()} px wide in a "
                f"{area.viewport().width()} px view"
            )
    return found
