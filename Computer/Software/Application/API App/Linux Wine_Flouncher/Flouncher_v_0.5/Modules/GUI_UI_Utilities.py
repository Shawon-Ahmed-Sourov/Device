
from PyQt5.QtWidgets import QHBoxLayout, QFrame

class UIUtils:
	
    @staticmethod
    def row(*widgets):
        layout = QHBoxLayout()
        for w in widgets: 
            layout.addWidget(w)
        return layout

    @staticmethod
    def sep():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line
