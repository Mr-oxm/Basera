"""Central icon builders for property bars and vector tools."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from ..theme import ThemeManager


def _icon_from_painter(paint_func, size: int = 20) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_func(painter, size)
    painter.end()
    return QIcon(pix)


def _palette_colors() -> tuple[QColor, QColor, QColor, QColor]:
    palette = ThemeManager.instance().active_palette
    return (
        QColor(palette["fg"]),
        QColor(palette["accent"]),
        QColor(palette.get("fg_dim", "#999999")),
        QColor(0, 0, 0, 80),
    )


def _pen(color: QColor, width: float = 1.4) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def move_align_icons() -> dict[str, QIcon]:
    from PySide6.QtCore import QRectF

    icons: dict[str, QIcon] = {}
    main, accent, _dim, shadow = _palette_colors()

    def align_left(p, s):
        p.setPen(_pen(shadow, 2))
        p.drawLine(5, 4, 5, s - 2)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(7, 6, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(7, 13, 7, 3), 1, 1)
        p.setPen(_pen(main, 1.5))
        p.drawLine(4, 3, 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(6, 5, 10, 3), 1, 1)
        p.setBrush(main)
        p.drawRoundedRect(QRectF(6, 12, 7, 3), 1, 1)

    def align_center_h(p, s):
        cx = s / 2
        p.setPen(_pen(shadow, 2))
        p.drawLine(int(cx) + 1, 4, int(cx) + 1, s - 2)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(cx - 4, 6, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(cx - 2.5, 13, 7, 3), 1, 1)
        p.setPen(_pen(main, 1.5))
        p.drawLine(int(cx), 3, int(cx), s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(cx - 5, 5, 10, 3), 1, 1)
        p.setBrush(main)
        p.drawRoundedRect(QRectF(cx - 3.5, 12, 7, 3), 1, 1)

    def align_right(p, s):
        p.setPen(_pen(shadow, 2))
        p.drawLine(s - 3, 4, s - 3, s - 2)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(s - 13, 6, 10, 3), 1, 1)
        p.drawRoundedRect(QRectF(s - 10, 13, 7, 3), 1, 1)
        p.setPen(_pen(main, 1.5))
        p.drawLine(s - 4, 3, s - 4, s - 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(s - 14, 5, 10, 3), 1, 1)
        p.setBrush(main)
        p.drawRoundedRect(QRectF(s - 11, 12, 7, 3), 1, 1)

    def align_top(p, s):
        p.setPen(_pen(shadow, 2))
        p.drawLine(4, 5, s - 2, 5)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(6, 7, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(13, 7, 3, 7), 1, 1)
        p.setPen(_pen(main, 1.5))
        p.drawLine(3, 4, s - 3, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(5, 6, 3, 10), 1, 1)
        p.setBrush(main)
        p.drawRoundedRect(QRectF(12, 6, 3, 7), 1, 1)

    def align_middle_v(p, s):
        cy = s / 2
        p.setPen(_pen(shadow, 2))
        p.drawLine(4, int(cy) + 1, s - 2, int(cy) + 1)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(6, cy - 4, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(13, cy - 2.5, 3, 7), 1, 1)
        p.setPen(_pen(main, 1.5))
        p.drawLine(3, int(cy), s - 3, int(cy))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(5, cy - 5, 3, 10), 1, 1)
        p.setBrush(main)
        p.drawRoundedRect(QRectF(12, cy - 3.5, 3, 7), 1, 1)

    def align_bottom(p, s):
        p.setPen(_pen(shadow, 2))
        p.drawLine(4, s - 3, s - 2, s - 3)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(6, s - 13, 3, 10), 1, 1)
        p.drawRoundedRect(QRectF(13, s - 10, 3, 7), 1, 1)
        p.setPen(_pen(main, 1.5))
        p.drawLine(3, s - 4, s - 3, s - 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(5, s - 14, 3, 10), 1, 1)
        p.setBrush(main)
        p.drawRoundedRect(QRectF(12, s - 11, 3, 7), 1, 1)

    for name, fn in [
        ("align_left", align_left),
        ("align_center_h", align_center_h),
        ("align_right", align_right),
        ("align_top", align_top),
        ("align_middle_v", align_middle_v),
        ("align_bottom", align_bottom),
    ]:
        icons[name] = _icon_from_painter(fn)
    return icons


def move_transform_icons() -> dict[str, QIcon]:
    icons: dict[str, QIcon] = {}
    main, accent, _dim, shadow = _palette_colors()

    def flip_h(p, s):
        mid = s / 2
        dp = QPen(shadow, 1.5)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(mid + 1, 4), QPointF(mid + 1, s - 2))
        dp = QPen(QColor("#b0b4b8"), 1.0)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(mid, 3), QPointF(mid, s - 3))
        p.setPen(_pen(shadow, 2))
        p.drawLine(QPointF(mid - 2, mid + 1), QPointF(4, mid + 1))
        p.drawLine(QPointF(4, mid + 1), QPointF(7, mid - 2))
        p.drawLine(QPointF(4, mid + 1), QPointF(7, mid + 4))
        p.drawLine(QPointF(mid + 4, mid + 1), QPointF(s - 2, mid + 1))
        p.drawLine(QPointF(s - 2, mid + 1), QPointF(s - 5, mid - 2))
        p.drawLine(QPointF(s - 2, mid + 1), QPointF(s - 5, mid + 4))
        p.setPen(_pen(main))
        p.drawLine(QPointF(mid - 3, mid), QPointF(3, mid))
        p.drawLine(QPointF(3, mid), QPointF(6, mid - 3))
        p.drawLine(QPointF(3, mid), QPointF(6, mid + 3))
        p.setPen(_pen(accent))
        p.drawLine(QPointF(mid + 3, mid), QPointF(s - 3, mid))
        p.drawLine(QPointF(s - 3, mid), QPointF(s - 6, mid - 3))
        p.drawLine(QPointF(s - 3, mid), QPointF(s - 6, mid + 3))

    def flip_v(p, s):
        mid = s / 2
        dp = QPen(shadow, 1.5)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(4, mid + 1), QPointF(s - 2, mid + 1))
        dp = QPen(QColor("#b0b4b8"), 1.0)
        dp.setStyle(Qt.PenStyle.DashLine)
        p.setPen(dp)
        p.drawLine(QPointF(3, mid), QPointF(s - 3, mid))
        p.setPen(_pen(shadow, 2))
        p.drawLine(QPointF(mid + 1, mid - 2), QPointF(mid + 1, 4))
        p.drawLine(QPointF(mid + 1, 4), QPointF(mid - 2, 7))
        p.drawLine(QPointF(mid + 1, 4), QPointF(mid + 4, 7))
        p.drawLine(QPointF(mid + 1, mid + 4), QPointF(mid + 1, s - 2))
        p.drawLine(QPointF(mid + 1, s - 2), QPointF(mid - 2, s - 5))
        p.drawLine(QPointF(mid + 1, s - 2), QPointF(mid + 4, s - 5))
        p.setPen(_pen(main))
        p.drawLine(QPointF(mid, mid - 3), QPointF(mid, 3))
        p.drawLine(QPointF(mid, 3), QPointF(mid - 3, 6))
        p.drawLine(QPointF(mid, 3), QPointF(mid + 3, 6))
        p.setPen(_pen(accent))
        p.drawLine(QPointF(mid, mid + 3), QPointF(mid, s - 3))
        p.drawLine(QPointF(mid, s - 3), QPointF(mid - 3, s - 6))
        p.drawLine(QPointF(mid, s - 3), QPointF(mid + 3, s - 6))

    def rotate_cw(p, s):
        rect = QRectF(5, 5, s - 10, s - 10)
        p.setPen(_pen(shadow, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect.translated(1, 1), -90 * 16, -270 * 16)
        ex, ey = s - 5 + 1, s / 2 + 1
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))
        p.setPen(_pen(main, 1.5))
        p.drawArc(rect, -90 * 16, -270 * 16)
        p.setPen(_pen(accent, 1.5))
        ex, ey = s - 5, s / 2
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))

    def rotate_ccw(p, s):
        rect = QRectF(5, 5, s - 10, s - 10)
        p.setPen(_pen(shadow, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect.translated(1, 1), -90 * 16, 270 * 16)
        ex, ey = 5 + 1, s / 2 + 1
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))
        p.setPen(_pen(main, 1.5))
        p.drawArc(rect, -90 * 16, 270 * 16)
        p.setPen(_pen(accent, 1.5))
        ex, ey = 5, s / 2
        p.drawLine(QPointF(ex, ey), QPointF(ex - 3, ey - 3))
        p.drawLine(QPointF(ex, ey), QPointF(ex + 3, ey - 3))

    for name, fn in [
        ("flip_horizontal", flip_h),
        ("flip_vertical", flip_v),
        ("rotate_90_cw", rotate_cw),
        ("rotate_90_ccw", rotate_ccw),
    ]:
        icons[name] = _icon_from_painter(fn)
    return icons


def vector_bool_icon(op: str) -> QIcon:
    main, accent, dim, _shadow = _palette_colors()
    palette = ThemeManager.instance().active_palette
    pix = QPixmap(18, 18)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    path_a = QPainterPath()
    path_a.addRect(2.5, 2.5, 9, 9)
    path_b = QPainterPath()
    path_b.addRect(6.5, 6.5, 9, 9)
    if op == "union":
        result = path_a.united(path_b)
        p.setBrush(accent)
        p.drawPath(result)
        p.setPen(QPen(main, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(result)
    elif op == "subtract":
        result = path_b.subtracted(path_a)
        p.setBrush(accent)
        p.drawPath(result)
        p.setPen(QPen(main, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(result)
        p.setPen(QPen(dim, 1, Qt.PenStyle.DashLine))
        p.drawRect(2.5, 2.5, 9, 9)
    elif op == "intersect":
        result = path_a.intersected(path_b)
        p.setBrush(accent)
        p.drawPath(result)
        p.setPen(QPen(main, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(result)
        p.setPen(QPen(dim, 1, Qt.PenStyle.DashLine))
        p.drawPath(path_a.subtracted(path_b))
        p.drawPath(path_b.subtracted(path_a))
    elif op == "exclude":
        result = path_a.united(path_b).subtracted(path_a.intersected(path_b))
        p.setBrush(accent)
        p.drawPath(result)
        p.setPen(QPen(main, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(result)
        p.setPen(QPen(dim, 1, Qt.PenStyle.DashLine))
        p.drawRect(6.5, 6.5, 5, 5)
    elif op == "divide":
        for offset, result in [((-0.5, -0.5), path_a.subtracted(path_b)), ((0.5, 0.5), path_b.subtracted(path_a)), ((0.0, 0.0), path_a.intersected(path_b))]:
            p.save()
            p.translate(*offset)
            p.setBrush(accent)
            p.setPen(QPen(main, 1))
            p.drawPath(result)
            p.restore()
    elif op == "pick_segments":
        p.setPen(QPen(dim, 1.5, Qt.PenStyle.DashLine))
        p.drawArc(3, 4, 12, 12, 16 * 90, 16 * 90)
        p.setPen(QPen(accent, 2))
        p.drawArc(3, 4, 12, 12, 16 * 0, 16 * 90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(main)
        p.drawRect(1.5, 8.5, 3, 3)
        p.drawRect(7.5, 2.5, 3, 3)
        p.drawRect(13.5, 8.5, 3, 3)
        cursor = QPainterPath()
        cx, cy = 11, 4.5
        cursor.moveTo(cx, cy)
        cursor.lineTo(cx, cy + 7)
        cursor.lineTo(cx + 2, cy + 5)
        cursor.lineTo(cx + 3.5, cy + 8.5)
        cursor.lineTo(cx + 4.5, cy + 8)
        cursor.lineTo(cx + 3, cy + 4.5)
        cursor.lineTo(cx + 6, cy + 4.5)
        cursor.closeSubpath()
        p.setPen(QPen(QColor(palette["bg1"]), 1))
        p.setBrush(main)
        p.drawPath(cursor)
    p.end()
    return QIcon(pix)


def vector_node_icon(op: str) -> QIcon:
    main, accent, dim, _shadow = _palette_colors()
    pix = QPixmap(18, 18)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if op == "sharp":
        p.setPen(QPen(dim, 1.5))
        p.drawLine(3, 14, 9, 4)
        p.drawLine(9, 4, 15, 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRect(7.5, 2.5, 3, 3)
        p.setBrush(main)
        p.drawRect(1.5, 12.5, 3, 3)
        p.drawRect(13.5, 12.5, 3, 3)
    elif op == "smooth":
        p.setPen(QPen(dim, 1.5))
        path = QPainterPath()
        path.moveTo(3, 13)
        path.cubicTo(6, 4, 12, 4, 15, 13)
        p.drawPath(path)
        p.setPen(QPen(accent, 1))
        p.drawLine(5, 7, 13, 7)
        p.setBrush(main)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(4, 6, 2, 2)
        p.drawEllipse(12, 6, 2, 2)
        p.setBrush(accent)
        p.drawRect(7.5, 5.5, 3, 3)
        p.setBrush(main)
        p.drawRect(1.5, 11.5, 3, 3)
        p.drawRect(13.5, 11.5, 3, 3)
    elif op == "symmetric":
        p.setPen(QPen(dim, 1.5))
        path = QPainterPath()
        path.moveTo(3, 13)
        path.cubicTo(6, 4, 12, 4, 15, 13)
        p.drawPath(path)
        p.setPen(QPen(accent, 1.5))
        p.drawLine(6, 7, 12, 7)
        p.setBrush(main)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(5, 6, 2, 2)
        p.drawRect(11, 6, 2, 2)
        p.setBrush(accent)
        p.drawRect(7.5, 5.5, 3, 3)
    elif op == "delete":
        p.setPen(QPen(dim, 1.5))
        p.drawLine(4, 4, 14, 14)
        p.drawLine(14, 4, 4, 14)
    elif op == "break":
        p.setPen(QPen(dim, 1.5))
        path_l = QPainterPath()
        path_l.moveTo(2, 12)
        path_l.quadTo(5, 6, 8, 4)
        p.drawPath(path_l)
        path_r = QPainterPath()
        path_r.moveTo(10, 5)
        path_r.quadTo(13, 7, 16, 13)
        p.drawPath(path_r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRect(6.5, 2.5, 3, 3)
        p.drawRect(8.5, 3.5, 3, 3)
    elif op == "select_all":
        p.setPen(QPen(main, 1, Qt.PenStyle.DashLine))
        p.drawRect(2, 2, 14, 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRect(4, 4, 3, 3)
        p.drawRect(11, 4, 3, 3)
        p.drawRect(4, 11, 3, 3)
        p.drawRect(11, 11, 3, 3)
    p.end()
    return QIcon(pix)


__all__ = [
    "move_align_icons",
    "move_transform_icons",
    "vector_bool_icon",
    "vector_node_icon",
]
