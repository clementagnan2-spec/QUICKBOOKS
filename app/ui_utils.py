from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PyQt5.QtCore import Qt


def fmt_money(value, currency="GHS"):
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0
    sign = "-" if v < 0 else ""
    return f"{sign}{currency} {abs(v):,.2f}"


def make_table(headers):
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setStyleSheet(
        """
        QTableWidget { gridline-color:#e0e0e0; font-size:13px; }
        QHeaderView::section { background-color:#f4f4f4; padding:6px; border:none;
                                border-bottom:2px solid #2CA01C; font-weight:bold; }
        QTableWidget::item:selected { background-color:#e6f4ea; color:black; }
        """
    )
    return table


def set_row(table, row, values, align_right_cols=()):
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
        if col in align_right_cols:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        table.setItem(row, col, item)
