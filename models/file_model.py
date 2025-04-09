# Required Imports
import os
from PyQt5 import QtCore
from typing import List, Any, Dict, Optional, Union, Optional
# Import helper functions for tag formatting and parsing.
from utils.helpers import format_multi_dim_tags, parse_multi_dim_tags, format_duration

# -------------------------- File Table Model --------------------------
class FileTableModel(QtCore.QAbstractTableModel):
    """
    Custom model to hold file data.
    Columns: File Path, File Name, Size, Modified Date, Duration, BPM, Key, Used, Sample Rate, Channels, Tags.
    """
    COLUMN_HEADERS = [
        "File Path",
        "File Name",
        "Size",
        "Modified Date",
        "Duration",
        "BPM",
        "Key",
        "Used",
        "Sample Rate",
        "Channels",
        "Tags"
    ]

    def __init__(self, files: Optional[List[Dict[str, Any]]] = None, size_unit: str = "KB", parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._files = files if files is not None else []
        self.size_unit = size_unit

    def rowCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self._files)

    def columnCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self.COLUMN_HEADERS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        file_info = self._files[index.row()]
        col = index.column()
        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                return os.path.dirname(file_info['path'])
            elif col == 1:
                return os.path.basename(file_info['path'])
            elif col == 2:
                return self.format_size(file_info['size'])
            elif col == 3:
                return file_info['mod_time'].strftime("%Y-%m-%d %H:%M:%S")
            elif col == 4:
                return format_duration(file_info.get('duration'))
            elif col == 5:
                return str(file_info.get('bpm', ""))
            elif col == 6:
                return file_info.get('key', "")
            elif col == 7:
                return ""
            elif col == 8:
                return str(file_info.get('samplerate', ""))
            elif col == 9:
                return str(file_info.get('channels', ""))
            elif col == 10:
                tags_data = file_info.get('tags', {})
                if isinstance(tags_data, list):
                    tags_data = {"general": tags_data}
                return format_multi_dim_tags(tags_data)
        if role == QtCore.Qt.CheckStateRole and col == 7:
            return QtCore.Qt.Checked if file_info.get('used', False) else QtCore.Qt.Unchecked
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if 0 <= section < len(self.COLUMN_HEADERS):
                return self.COLUMN_HEADERS[section]
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        base_flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        col = index.column()
        if col == 7:
            return base_flags | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable
        elif col in [4, 5, 6, 10]:
            return base_flags | QtCore.Qt.ItemIsEditable
        else:
            return base_flags

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        file_info = self._files[index.row()]
        col = index.column()
        if role == QtCore.Qt.CheckStateRole and col == 7:
            file_info['used'] = (value == QtCore.Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        if role == QtCore.Qt.EditRole:
            if col == 4:  # Duration
                new_duration = self._parse_duration(value)
                if new_duration is not None:
                    file_info['duration'] = new_duration
                else:
                    return False
            elif col == 5:  # BPM
                try:
                    file_info['bpm'] = int(value) if value.strip() else None
                except ValueError:
                    return False
            elif col == 6:  # Key
                file_info['key'] = value.strip().upper() if value else ""
            elif col == 10:
                tag_dict = parse_multi_dim_tags(value)
                file_info['tags'] = tag_dict
                self.dataChanged.emit(index, index, [role])
                return True
            else:
                return False
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def _parse_duration(self, text: str) -> Optional[float]:
        try:
            parts = text.split(':')
            if len(parts) != 2:
                return None
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        except Exception:
            return None

    def format_size(self, size_in_bytes: Union[int, float]) -> str:
        if self.size_unit == "KB":
            return f"{size_in_bytes / 1024:.2f} KB"
        elif self.size_unit == "MB":
            return f"{size_in_bytes / (1024 ** 2):.2f} MB"
        elif self.size_unit == "GB":
            return f"{size_in_bytes / (1024 ** 3):.2f} GB"
        else:
            return str(size_in_bytes)

    def updateData(self, files: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._files = files
        self.endResetModel()

    def getFileAt(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

# -------------------------- Filter Proxy Model --------------------------
class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model for filtering files by their path, tags, and optionally by "used" status.
    """
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterKeyColumn(1)
        self.onlyUnused = False

    def setOnlyUnused(self, flag: bool) -> None:
        self.onlyUnused = flag
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        if self.onlyUnused:
            source_model = self.sourceModel()
            file_info = source_model.getFileAt(source_row)
            if file_info and file_info.get('used', False):
                return False
        return True
