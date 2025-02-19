from PyQt5 import QtWidgets, QtCore
import sys, time, os, pathlib, json
import numpy as np
import multiprocessing # for the camera streams !!
from ctypes import c_char_p
import pyqtgraph as pg
import subprocess

from physion.acquisition.settings import get_config_list
from physion.utils.files import last_datafolder_in_dayfolder, day_folder
from physion.utils.paths import FOLDERS
from physion.visual_stim.screens import SCREENS
from physion.acquisition.settings import load_settings
from physion.assembling.gui import build_cmd

def multimodal(self,
               tab_id=0):

    tab = self.tabs[tab_id]

    self.cleanup_tab(tab)

    self.config = None
    self.subject, self.protocol = None, {}
    self.MODALITIES = ['Locomotion',
                       'FaceCamera',
                       'EphysLFP',
                       'EphysVm',
                       'CaImaging']

    ##########################################
    ######## Multiprocessing quantities  #####
    ##########################################
    # to be used through multiprocessing.Process:
    self.run_event = multiprocessing.Event() # to turn on/off recordings 
    self.run_event.clear()
    self.closeFaceCamera_event = multiprocessing.Event()
    self.closeFaceCamera_event.clear()
    self.quit_event = multiprocessing.Event()
    self.quit_event.clear()
    self.manager = multiprocessing.Manager() # to share a str across processes
    self.datafolder = self.manager.Value(c_char_p,\
            str(os.path.join(os.path.expanduser('~'), 'DATA', 'trash')))

    ##########################################
    ######   acquisition states/values  ######
    ##########################################
    self.stim, self.acq, self.init = None, None, False,
    self.screen, self.stop_flag = None, False
    self.FaceCamera_process = None
    self.RigView_process = None
    self.params_window = None

    ##########################################################
    ####### GUI settings
    ##########################################################

    # ========================================================
    #------------------- SIDE PANELS FIRST -------------------
    # folder box
    self.add_side_widget(tab.layout,
            QtWidgets.QLabel('data folder:'))
    self.folderBox = QtWidgets.QComboBox(self)
    self.folderBox.addItems(FOLDERS.keys())
    self.add_side_widget(tab.layout, self.folderBox)
    self.add_side_widget(tab.layout, QtWidgets.QLabel(' '))
    self.add_side_widget(tab.layout, QtWidgets.QLabel(' '))
    # -------------------------------------------------------
    self.add_side_widget(tab.layout,
            QtWidgets.QLabel('* Recording Modalities *'))
    for i, k in enumerate(self.MODALITIES):
        setattr(self,k+'Button', QtWidgets.QPushButton(k, self))
        getattr(self,k+'Button').setCheckable(True)
        self.add_side_widget(tab.layout, getattr(self, k+'Button'))
    self.add_side_widget(tab.layout, QtWidgets.QLabel(' '))
    self.add_side_widget(tab.layout, QtWidgets.QLabel(' '))

    self.FaceCameraButton.clicked.connect(self.toggle_FaceCamera_process)

    # -------------------------------------------------------
    self.add_side_widget(tab.layout,
            QtWidgets.QLabel(' * Monitoring * '))
    self.webcamButton = QtWidgets.QPushButton('Webcam', self)
    self.webcamButton.setCheckable(True)
    self.add_side_widget(tab.layout, self.webcamButton)

    self.add_side_widget(tab.layout, QtWidgets.QLabel(' '))
    self.add_side_widget(tab.layout,
            QtWidgets.QLabel(' * Notes * '))
    self.qmNotes = QtWidgets.QTextEdit(self)
    self.add_side_widget(tab.layout, self.qmNotes)

    # -------------------------------------------------------
    self.add_side_widget(tab.layout, QtWidgets.QLabel(' '))

    self.demoW = QtWidgets.QCheckBox('demo', self)
    self.add_side_widget(tab.layout, self.demoW, 'small-right')

    self.saveSetB = QtWidgets.QPushButton('save settings', self)
    self.saveSetB.clicked.connect(self.save_settings)
    self.add_side_widget(tab.layout, self.saveSetB)

    self.buildNWB = QtWidgets.QPushButton('build NWB for last', self)
    self.buildNWB.clicked.connect(build_NWB_for_last)
    self.add_side_widget(tab.layout, self.buildNWB)

    # ========================================================

    # ========================================================
    #------------------- THEN MAIN PANEL   -------------------
    ip, width = 0, 3
    tab.layout.addWidget(\
        QtWidgets.QLabel(40*' '+'** Config **', self),
                         ip, self.side_wdgt_length, 
                         1, width)
    ip+=1
    # -
    self.configBox = QtWidgets.QComboBox(self)
    self.configBox.activated.connect(self.update_config)
    tab.layout.addWidget(self.configBox,\
                         ip, self.side_wdgt_length+1, 
                         1, width)
    ip+=1
    # -
    tab.layout.addWidget(\
        QtWidgets.QLabel(40*' '+'** Subject **', self),
                         ip, self.side_wdgt_length, 
                         1, width)
    ip+=1
    # -
    self.subjectBox = QtWidgets.QComboBox(self)
    self.subjectBox.activated.connect(self.update_subject)
    tab.layout.addWidget(self.subjectBox,\
                         ip, self.side_wdgt_length+1, 
                         1, width)
    ip+=1
    # -
    tab.layout.addWidget(\
        QtWidgets.QLabel(40*' '+'** Screen **', self),
                         ip, self.side_wdgt_length, 
                         1, width)
    ip+=1
    # -
    self.screenBox = QtWidgets.QComboBox(self)
    self.screenBox.addItems(['']+list(SCREENS.keys()))
    tab.layout.addWidget(self.screenBox,\
                         ip, self.side_wdgt_length+1, 
                         1, width)
    ip+=1
    # -
    tab.layout.addWidget(\
        QtWidgets.QLabel(40*' '+'** Visual Protocol **', self),
                         ip, self.side_wdgt_length, 
                         1, width)
    ip+=1
    # -
    self.protocolBox= QtWidgets.QComboBox(self)
    tab.layout.addWidget(self.protocolBox,\
                         ip, self.side_wdgt_length+1, 
                         1, width)
    ip+=1
    # -
    tab.layout.addWidget(\
        QtWidgets.QLabel(40*' '+'** Intervention **', self),
                         ip, self.side_wdgt_length, 
                         1, width)
    ip+=1
    # -
    self.interventionBox = QtWidgets.QComboBox(self)
    tab.layout.addWidget(self.interventionBox,\
                         ip, self.side_wdgt_length+1, 
                         1, width)
    ip+=1

    # image panels layout:
    self.winImg = pg.GraphicsLayoutWidget()
    tab.layout.addWidget(self.winImg,
                         ip, self.side_wdgt_length,
                         self.nWidgetRow-ip, 
                         self.nWidgetCol-self.side_wdgt_length)

    # FaceCamera panel
    self.pFace = self.winImg.addViewBox(lockAspect=True,
                        invertY=True, border=[1, 1, 1])
    self.pFaceimg = pg.ImageItem(np.ones((10,12))*50)
    self.pFace.addItem(self.pFaceimg)

    # NOW MENU INTERACTION BUTTONS
    ip, width = 1, 5
    self.initButton = QtWidgets.QPushButton(' * Initialize * ')
    self.initButton.clicked.connect(self.initialize)
    tab.layout.addWidget(self.initButton,
                         ip, 10, 1, width)
    ip+=1
    self.bufferButton = QtWidgets.QPushButton(' * Buffer * ')
    self.bufferButton.clicked.connect(self.buffer_stim)
    tab.layout.addWidget(self.bufferButton,
                         ip, 10, 1, width)
    ip+=2
    self.runButton = QtWidgets.QPushButton(' * RUN *')
    self.runButton.clicked.connect(self.run)
    tab.layout.addWidget(self.runButton,
                         ip, 10, 1, width)
    ip+=1
    self.stopButton = QtWidgets.QPushButton(' * Stop *')
    self.stopButton.clicked.connect(self.stop)
    tab.layout.addWidget(self.stopButton,
                         ip, 10, 1, width)

    for button in [self.initButton, self.bufferButton,
            self.runButton, self.stopButton]:
        button.setStyleSheet("font-weight: bold")

    ip+=2
    tab.layout.addWidget(QtWidgets.QLabel(' FOV: '),
                         ip, 10, 1, 4)
    ip+=1
    self.fovPick= QtWidgets.QComboBox()
    tab.layout.addWidget(self.fovPick,
                         ip, 10, 1, 4)

    self.refresh_tab(tab)

    # READ CONFIGS
    get_config_list(self) # first
    load_settings(self)

def build_NWB_for_last():
    # last folder
    folder = last_datafolder_in_dayfolder(day_folder(FOLDERS['~/DATA']))
    print(folder)
    if os.path.isdir(folder):
        cmd, cwd = build_cmd(folder)
        print('\n launching the command \n :  %s \n ' % cmd)
        p = subprocess.Popen(cmd,
                             cwd=cwd,
                             shell=True)


