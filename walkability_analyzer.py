import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsMessageLog, Qgis


class WalkabilityAnalyzer:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.menu = '&Walkability Analyzer'
        self.actions = []
        self.dlg = None
        self.first_start = True
        

    def add_action(self, icon_path, text, callback):
        icon = QIcon(icon_path) if icon_path and os.path.exists(icon_path) else QIcon()
        action = QAction(icon, text, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.add_action(icon_path, 'Walkability Analyzer', self.run)

    def unload(self):
        for a in self.actions:
            self.iface.removePluginMenu(self.menu, a)
            self.iface.removeToolBarIcon(a)
        self.actions = []
        if self.dlg:
            self.dlg.close()
            self.dlg = None

    def run(self):
        if self.first_start:
            self.first_start = False
            from .walkability_analyzer_dialog import WalkabilityAnalyzerDialog
            self.dlg = WalkabilityAnalyzerDialog()
            QgsMessageLog.logMessage("Walkability dialog loaded.", "Walkability", Qgis.Info)

        self.dlg.show()
        self.dlg.exec_()
