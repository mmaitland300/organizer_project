"""
MultiDimTagEditorDialog - a dialog for editing multi-dimensional tags.
"""

from typing import Any, Dict, List, Optional
from PyQt5 import QtWidgets

class MultiDimTagEditorDialog(QtWidgets.QDialog):
    def __init__(self, tag_data: Any, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Tags")
        self.resize(400, 300)
        if isinstance(tag_data, list):
            self.tag_data: Dict[str, List[str]] = {"general": tag_data}
        elif isinstance(tag_data, dict):
            self.tag_data = tag_data.copy()
        else:
            self.tag_data = {}
        main_layout = QtWidgets.QVBoxLayout(self)
        self.tableWidget = QtWidgets.QTableWidget(self)
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Dimension", "Tag"])
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        main_layout.addWidget(self.tableWidget)
        self.loadData()
        row_layout = QtWidgets.QHBoxLayout()
        self.dimensionEdit = QtWidgets.QLineEdit(self)
        self.dimensionEdit.setPlaceholderText("Dimension (e.g., genre, mood)")
        self.tagEdit = QtWidgets.QLineEdit(self)
        self.tagEdit.setPlaceholderText("Tag (e.g., ROCK)")
        row_layout.addWidget(self.dimensionEdit)
        row_layout.addWidget(self.tagEdit)
        main_layout.addLayout(row_layout)
        btnAdd = QtWidgets.QPushButton("Add Tag", self)
        btnAdd.clicked.connect(self.addTag)
        main_layout.addWidget(btnAdd)
        btnBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel, self)
        btnBox.accepted.connect(self.accept)
        btnBox.rejected.connect(self.reject)
        main_layout.addWidget(btnBox)
    
    def loadData(self) -> None:
        self.tableWidget.setRowCount(0)
        for dimension, tags in self.tag_data.items():
            for tag in tags:
                row = self.tableWidget.rowCount()
                self.tableWidget.insertRow(row)
                dim_item = QtWidgets.QTableWidgetItem(dimension.capitalize())
                tag_item = QtWidgets.QTableWidgetItem(tag)
                self.tableWidget.setItem(row, 0, dim_item)
                self.tableWidget.setItem(row, 1, tag_item)
    
    def addTag(self) -> None:
        dimension = self.dimensionEdit.text().strip().lower()
        tag = self.tagEdit.text().strip().upper()
        if not dimension or not tag:
            return
        row = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row)
        dim_item = QtWidgets.QTableWidgetItem(dimension.capitalize())
        tag_item = QtWidgets.QTableWidgetItem(tag)
        self.tableWidget.setItem(row, 0, dim_item)
        self.tableWidget.setItem(row, 1, tag_item)
        self.dimensionEdit.clear()
        self.tagEdit.clear()
    
    def get_tags(self) -> Dict[str, List[str]]:
        new_tags: Dict[str, List[str]] = {}
        for row in range(self.tableWidget.rowCount()):
            dim_item = self.tableWidget.item(row, 0)
            tag_item = self.tableWidget.item(row, 1)
            if dim_item and tag_item:
                dimension = dim_item.text().lower()
                tag = tag_item.text().upper()
                new_tags.setdefault(dimension, [])
                if tag not in new_tags[dimension]:
                    new_tags[dimension].append(tag)
        return new_tags
