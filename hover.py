from PyQt5.QtWidgets import QPushButton, QApplication, QWidget, QVBoxLayout
from PyQt5.QtCore import QEvent, QObject
import sys

class MyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Event Filter Example")

        self.button = QPushButton("Hover to see in console")
        
        # Install an event filter on the button,
        # with 'self' (MyWindow instance) as the filter object
        self.button.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.button)
        self.show()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        Filters events for objects it's installed on.
        Returns True if the event was handled and should stop propagation.
        Returns False if the event should continue to be processed.
        """
        if obj == self.button:
            if event.type() == QEvent.Enter:
                print("Mouse entered button via event filter!")
                # You could change style here too, or do other logic
            elif event.type() == QEvent.Leave:
                print("Mouse left button via event filter!")
        
        # Pass the event to the original object's event handler
        return super().eventFilter(obj, event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MyWindow()
    sys.exit(app.exec_())