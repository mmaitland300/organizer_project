"""
DuplicateManagerDialog – a dialog to display and manage duplicate files.

Provides options for selecting, deleting, or keeping the first copy.
"""

import os
from typing import List, Dict, Any, Optional
from PyQt5 import QtWidgets, QtCore
from utils.helpers import bytes_to_unit

class DuplicateManagerDialog(QtWidgets.QDialog):
    def __init__(self, duplicate_groups: List[List[Dict[str, Any]]], size_unit: str = "KB", use_recycle_bin: bool = True, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate Files Manager")
        self.resize(900, 500)
        self.size_unit = size_unit
        self.use_recycle_bin = use_recycle_bin
        
        main_layout = QtWidgets.QVBoxLayout(self)
        self.tree = QtWidgets.QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["File Path", "Size", "Modified Date", "MD5 Hash"])
        self.tree.setSortingEnabled(True)
        self.tree.header().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        main_layout.addWidget(self.tree)
        
        btn_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(btn_layout)
        
        self.btnSelectAll = QtWidgets.QPushButton("Select All", self)
        self.btnSelectAll.clicked.connect(self.selectAll)
        btn_layout.addWidget(self.btnSelectAll)
        
        self.btnDeselectAll = QtWidgets.QPushButton("Deselect All", self)
        self.btnDeselectAll.clicked.connect(self.deselectAll)
        btn_layout.addWidget(self.btnDeselectAll)
        
        self.btnDeleteSelected = QtWidgets.QPushButton("Delete Selected", self)
        self.btnDeleteSelected.clicked.connect(self.deleteSelected)
        btn_layout.addWidget(self.btnDeleteSelected)
        
        self.btnKeepOnlyFirst = QtWidgets.QPushButton("Keep Only First", self)
        self.btnKeepOnlyFirst.clicked.connect(self.keepOnlyFirst)
        btn_layout.addWidget(self.btnKeepOnlyFirst)
        
        self.btnOpenFolder = QtWidgets.QPushButton("Open Containing Folder", self)
        self.btnOpenFolder.clicked.connect(self.openContainingFolder)
        btn_layout.addWidget(self.btnOpenFolder)
        
        self.btnViewWaveform = QtWidgets.QPushButton("View Waveform", self)
        self.btnViewWaveform.clicked.connect(self.viewWaveform)
        btn_layout.addWidget(self.btnViewWaveform)
        
        self.btnClose = QtWidgets.QPushButton("Close", self)
        self.btnClose.clicked.connect(self.accept)
        btn_layout.addWidget(self.btnClose)
        
        self.populateTree(duplicate_groups)
    
    def populateTree(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        self.tree.clear()
        for group_index, group in enumerate(duplicate_groups, start=1):
            parent_item = QtWidgets.QTreeWidgetItem(self.tree)
            parent_item.setText(0, f"Group {group_index} ({len(group)} files)")
            parent_item.setFlags(parent_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            for info in group:
                child = QtWidgets.QTreeWidgetItem(parent_item)
                child.setText(0, info["path"])
                size_value = bytes_to_unit(info["size"], self.size_unit)
                child.setText(1, f"{size_value:.2f} {self.size_unit}")
                child.setText(2, info["mod_time"].strftime("%Y-%m-%d %H:%M:%S"))
                child.setText(3, info.get("hash", ""))
                child.setFlags(child.flags() | QtCore.Qt.ItemIsUserCheckable)
                child.setCheckState(0, QtCore.Qt.Unchecked)
        self.tree.expandAll()
    
    def selectAll(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)
    
    def deselectAll(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Unchecked)
    
    def deleteSelected(self) -> None:
        items_to_delete = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == QtCore.Qt.Checked:
                    items_to_delete.append((parent, child))
        if not items_to_delete:
            QtWidgets.QMessageBox.information(self, "No Selection", "No files selected for deletion.")
            return
        
        reply = QtWidgets.QMessageBox.question(self, "Confirm Deletion",
                                                 f"Are you sure you want to delete {len(items_to_delete)} file(s)?",
                                                 QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        errors = []
        for parent, child in items_to_delete:
            file_path = child.text(0)
            try:
                if self.use_recycle_bin:
                    from send2trash import send2trash
                    send2trash(file_path)
                else:
                    os.remove(file_path)
            except Exception as e:
                errors.append(f"Error deleting {file_path}: {str(e)}")
            else:
                parent.removeChild(child)
        if errors:
            QtWidgets.QMessageBox.critical(self, "Deletion Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(self, "Deletion", "Selected files deleted successfully.")
        for i in reversed(range(root.childCount())):
            parent = root.child(i)
            if parent.childCount() == 0:
                root.removeChild(parent)
    
    def keepOnlyFirst(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(1, parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)
        self.deleteSelected()
    
    def openContainingFolder(self) -> None:
        selected_items = self.tree.selectedItems()
        file_path = None
        for item in selected_items:
            if item.parent() is not None:
                file_path = item.text(0)
                break
        if file_path:
            from utils.helpers import open_file_location
            open_file_location(file_path)
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a file entry first.")
    
    def viewWaveform(self) -> None:
        selected_items = self.tree.selectedItems()
        file_path = None
        for item in selected_items:
            if item.parent() is not None:
                file_path = item.text(0)
                break
        if not file_path:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select an audio file entry first.")
            return
        ext = os.path.splitext(file_path)[1].lower()
        from config.settings import AUDIO_EXTENSIONS, ENABLE_WAVEFORM_PREVIEW
        if ext not in AUDIO_EXTENSIONS:
            QtWidgets.QMessageBox.information(self, "Not Audio", "Selected file is not an audio file.")
            return
        if ENABLE_WAVEFORM_PREVIEW:
            dialog = WaveformDialog(file_path, parent=self)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "Feature Unavailable", "Waveform preview is not available.")
