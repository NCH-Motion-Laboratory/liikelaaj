# -*- coding: utf-8 -*-
"""
Created on Wed Feb  3 18:56:52 2016

@author: jussi
"""
from __future__ import print_function

from builtins import str
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *

class MyQSpinBox(QSpinBox):

    def __init__(self):
        super(self.__class__, self).__init__()
        print('jee!')
    
    def Enter(self, event):
        print('enter')
        self.clear()
        QSpinBox.Enter(self, event)

class spindemo(QWidget):
   def __init__(self, parent = None):
      super(spindemo, self).__init__(parent)
      
      layout = QVBoxLayout()
      self.l1 = QLabel("current value:")
      self.l1.setAlignment(Qt.AlignCenter)
      layout.addWidget(self.l1)
      self.sp1 = MyQSpinBox()
      self.sp2 = MyQSpinBox()
      self.btn = QPushButton()
      #self.btn.clicked.connect(self.sp.selectAll)
      self.sp1.setValue(1)
      self.sp2.setValue(1)
      layout.addWidget(self.sp1)
      layout.addWidget(self.sp2)
      layout.addWidget(self.btn)
      #self.sp.valueChanged.connect(self.valuechange)
      self.setLayout(layout)
      self.setWindowTitle("SpinBox demo")
		
   def valuechange(self):
      self.l1.setText("current value:"+str(self.sp.value()))

def main():
   app = QApplication(sys.argv)
   ex = spindemo()
   ex.show()
   sys.exit(app.exec_())
	
if __name__ == '__main__':
   main()
   