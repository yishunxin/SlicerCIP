import os, sys, string
import unittest
import vtk, qt, ctk, slicer
import numpy as np
import SimpleITK as sitk
import sitkUtils

from slicer.ScriptedLoadableModule import *

from CIP.logic.SlicerUtil import SlicerUtil
#
# Calc Scoring
#

class MouseInteractorActor(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self):
        self.AddObserver('LeftButtonPressEvent', self.onLeftButtonPressEvent)
        self.AddObserver('MouseMoveEvent', self.onMouseMoveEvent)
        self.AddObserver('LeftButtonReleaseEvent', self.onLeftButtonReleaseEvent)
        self._lastPickedActor = None
        self._lastPickedProperty = vtk.vtkProperty()
        self._mouseMoved = False
    def lastPickedActor(self):
        return self._lastPickedActor() if self._lastPickedActor else None
    def onLeftButtonPressEvent(self, obj, evt):
        self._mouseMoved = False
        self.OnLeftButtonDown()
    def onMouseMoveEvent(self, obj, evt):
        self._mouseMoved = True
        self.OnMouseMove()
    def onLeftButtonReleaseEvent(self, obj, evt):
        if not self._mouseMoved:
            clickPos = self.GetInteractor().GetEventPosition()
            #Pick from this location
            picker = vtk.vtkPropPicker()
            picker.Pick(clickPos[0], clickPos[1], 0, self.GetDefaultRenderer())
            #If we picked something before, reset its property
            if self.lastPickedActor():
                self.lastPickedActor().GetProperty().DeepCopy(self._lastPickedProperty)
            self._lastPickedActor = picker.GetActor() if picker.GetActor() else None
            if self.lastPickedActor():
                #Save the property of the picked actor
                self._lastPickedProperty.DeepCopy(self.lastPickedActor().GetProperty())
                #Highlight the picked actor
                self.lastPickedActor().GetProperty().SetColor(1.0, 0.0, 0.0)
                self.lastPickedActor().GetProperty().SetDiffuse(1.0)
                self.lastPickedActor().GetProperty().SetSpecular(0.0)
            else:
                print 'No actor get pickered'
        #Call parent member
        self.OnLeftButtonUp()

class CIP_CalciumScoring(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent = parent
        self.parent.title = "Calcium Scoring"
        self.parent.contributors = ["Alex Yarmarkovich", "Applied Chest Imaging Laboratory",
                                    "Brigham and Women's Hospital"]
        self.parent.categories = SlicerUtil.CIP_ModulesCategory
        self.parent.dependencies = [SlicerUtil.CIP_ModuleName]
        self.parent.acknowledgementText = SlicerUtil.ACIL_AcknowledgementText

        # Add this test to the SelfTest module's list for discovery when the module
        # is created.  Since this module may be discovered before SelfTests itself,
        # create the list if it doesn't already exist.
    #     try:
    #         slicer.selfTests
    #     except AttributeError:
    #         slicer.selfTests = {}
    #     slicer.selfTests['CIP_CalciumScoring'] = self.runTest
    #
    # def runTest(self):
    #     tester = CIP_CalciumScoringTest()
    #     tester.runTest()
    #     print "runTest"


#
# qCIP_CalciumScoringWidget
#

class CIP_CalciumScoringWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        settings = qt.QSettings()
        self.developerMode = settings.value('Developer/DeveloperMode').lower() == 'true'
        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.layout = self.parent.layout()
        if not parent:
            self.setup()
            self.parent.show()

        self.priority = 2
        self.calcinationType = 0
        self.ThresholdMin = 130.0
        self.ThresholdMax = 2000.0
        self.MinimumLesionSize = 1
        self.MaximumLesionSize = 2000
        self.croppedVolumeNode = slicer.vtkMRMLScalarVolumeNode()
        self.threshImage = vtk.vtkImageData()
        self.marchingCubes = vtk.vtkDiscreteMarchingCubes()
        self.transformPolyData = vtk.vtkTransformPolyDataFilter()

        self.selectedLableList = []
        self.labelScores = []
        self.selectedLables = {}
        self.modelNodes = []
        self.voxelVolume = 1
        self.selectedRGB = [1,0,0]
        self.observerTags = []
        self.xy = []

        self.totalScore = 0

    def __del__(self):
        for observee,tag in self.observerTags:
            observee.RemoveObserver(tag)
        self.observerTags = []

    def enter(self):
        print "Enter"
    def exit(self):
        print "Exit"

    def setup(self):
        # Instantiate and connect widgets ...
        ScriptedLoadableModuleWidget.setup(self)

        #self.logic = CIP_CalciumScoringLogic()

        #
        # Parameters Area
        #
        parametersCollapsibleButton = ctk.ctkCollapsibleButton()
        parametersCollapsibleButton.text = "Parameters"
        self.layout.addWidget(parametersCollapsibleButton)

        # Layout within the dummy collapsible button
        parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

        #
        # target volume selector
        #
        self.inputSelector = slicer.qMRMLNodeComboBox()
        self.inputSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
        self.inputSelector.addEnabled = False
        self.inputSelector.removeEnabled = False
        self.inputSelector.noneEnabled = False
        self.inputSelector.showHidden = False
        self.inputSelector.showChildNodeTypes = False
        self.inputSelector.setMRMLScene( slicer.mrmlScene )
        self.inputSelector.setToolTip( "Pick the input to the algorithm." )
        parametersFormLayout.addRow("Target Volume: ", self.inputSelector)
        self.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onVolumeChanged)
        self.volumeNode = self.inputSelector.currentNode()
        
        #
        # Calcination type
        #
        self.calcinationTypeBox = qt.QComboBox()
        self.calcinationTypeBox.addItem("Heart")
        self.calcinationTypeBox.addItem("Aorta")
        parametersFormLayout.addRow("Calcination Region", self.calcinationTypeBox)
        self.calcinationTypeBox.connect("currentIndexChanged(int)", self.onTypeChanged)

        self.ThresholdRange = ctk.ctkRangeWidget()
        self.ThresholdRange.minimum = 0
        self.ThresholdRange.maximum = 3000
        self.ThresholdRange.setMinimumValue(self.ThresholdMin)
        self.ThresholdRange.setMaximumValue(self.ThresholdMax)
        self.ThresholdRange.connect("minimumValueChanged(double)", self.onThresholdMinChanged)
        self.ThresholdRange.connect("maximumValueChanged(double)", self.onThresholdMaxChanged)
        parametersFormLayout.addRow("Threshold Value", self.ThresholdRange)
        self.ThresholdRange.setMinimumValue(self.ThresholdMin)
        self.ThresholdRange.setMaximumValue(self.ThresholdMax)

        self.LesionSizeRange= ctk.ctkRangeWidget()
        self.LesionSizeRange.minimum = 1
        self.LesionSizeRange.maximum = 1000
        self.LesionSizeRange.setMinimumValue(self.MinimumLesionSize)
        self.LesionSizeRange.setMaximumValue(self.MaximumLesionSize)
        self.LesionSizeRange.connect("minimumValueChanged(double)", self.onMinSizeChanged)
        self.LesionSizeRange.connect("maximumValueChanged(double)", self.onMaxSizeChanged)
        parametersFormLayout.addRow("Lesion Size (mm^3)", self.LesionSizeRange)
        self.LesionSizeRange.setMinimumValue(self.MinimumLesionSize)
        self.LesionSizeRange.setMaximumValue(self.MaximumLesionSize)

        self.scoreField = qt.QLineEdit()
        self.scoreField.setText(self.totalScore)
        parametersFormLayout.addRow("Total Score", self.scoreField)
        
        #
        # Select table
        #
        self.selectLabels = qt.QTableWidget()
        self.selectLabels.horizontalHeader().hide()
        self.selectLabels.verticalHeader().hide()
        self.selectLabels.setColumnCount(2)
        self.selectLabels.itemClicked.connect(self.handleItemClicked)
        parametersFormLayout.addRow("", self.selectLabels)

        #
        # ROI Area
        #
        self.roiCollapsibleButton = ctk.ctkCollapsibleButton()
        self.roiCollapsibleButton.text = "Heart ROI"
        self.roiCollapsibleButton.setChecked(False)
        self.layout.addWidget(self.roiCollapsibleButton)

        # Layout within the dummy collapsible button
        roiFormLayout = qt.QFormLayout(self.roiCollapsibleButton)

        #
        # ROI
        #
        self.ROIWidget = slicer.qMRMLAnnotationROIWidget()
        self.roiNode = slicer.vtkMRMLAnnotationROINode()
        slicer.mrmlScene.AddNode(self.roiNode)
        self.ROIWidget.setMRMLAnnotationROINode(self.roiNode)
        roiFormLayout.addRow("", self.ROIWidget)
        self.roiNode.AddObserver("ModifiedEvent", self.onROIChangedEvent, 1)

        # Add vertical spacer
        self.layout.addStretch(1)

        # Add temp nodes
        self.croppedNode=slicer.vtkMRMLScalarVolumeNode()
        self.croppedNode.SetHideFromEditors(1)
        slicer.mrmlScene.AddNode(self.croppedNode)
        self.labelsNode=slicer.vtkMRMLLabelMapVolumeNode()
        slicer.mrmlScene.AddNode(self.labelsNode)
        
        if self.inputSelector.currentNode():
            self.onVolumeChanged(self.inputSelector.currentNode())
            self.createModels()

    def addLabel(self, row, rgb, val):
        #print "add row", row, rgb
        self.selectLabels.setRowCount(row+1)

        item0 = qt.QTableWidgetItem('')
        item0.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled)
        item0.setCheckState(qt.Qt.Unchecked)
        self.selectLabels.setItem(row,0,item0)

        item1 = qt.QTableWidgetItem('')
        color=qt.QColor()
        color.setRgbF(rgb[0],rgb[1],rgb[2])
        item1.setData(qt.Qt.BackgroundRole,color)
        item1.setText(val)
        self.selectLabels.setItem(row,1,item1)

    def handleItemClicked(self, item):
        if item.checkState() == qt.Qt.Checked:
            self.selectedLableList[item.row()] = 1
        else:
            self.selectedLableList[item.row()] = 0
        #print "LIST=", self.selectedLableList
        self.computeTotalScore()
        self.updateModels()

    def computeTotalScore(self):
        self.totalScore = 0
        for n in range(0, len(self.selectedLableList)):
            if self.selectedLableList[n] == 1:
                self.totalScore = self.totalScore + self.labelScores[n]

        self.scoreField.setText(self.totalScore)

    def updateModels(self):
        for n in range(0, len(self.selectedLableList)):
            model = self.modelNodes[n]
            dnode = model.GetDisplayNode()
            rgb = [1,0,0]
            if self.selectedLableList[n] == 1:
                rgb = self.selectedRGB
            else:
                ct=slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeLabels')
                ct.GetLookupTable().GetColor(n+1,rgb)
            dnode.SetColor(rgb)

    def setInteractor(self):
        self.renderWindow = slicer.app.layoutManager().threeDWidget(0).threeDView().renderWindow()
        self.iren = self.renderWindow.GetInteractor()
        lm = slicer.app.layoutManager()
        for v in range(lm.threeDViewCount):
            td = lm.threeDWidget(v)
            ms = vtk.vtkCollection()
            td.getDisplayableManagers(ms)
            for i in range(ms.GetNumberOfItems()):
                m = ms.GetItemAsObject(i)
                if m.GetClassName() == "vtkMRMLModelDisplayableManager":
                    self.dispManager = m
                    break

        self.propPicker = vtk.vtkPropPicker()
        self.iren.SetPicker(self.propPicker)
        #self.propPicker.AddObserver("EndPickEvent", self.PickProp)
        #self.propPicker.AddObserver("PickEvent", self.PickProp)
        self.renderer = slicer.app.layoutManager().threeDWidget(0).threeDView().renderWindow().GetRenderers().GetFirstRenderer()
        tag = self.iren.AddObserver("LeftButtonReleaseEvent", self.processEvent, self.priority)
        self.observerTags.append([self.iren,tag])
        tag = self.iren.AddObserver("MouseMoveEvent", self.processEvent, self.priority)
        self.observerTags.append([self.iren,tag])

        self.mouseInteractor = MouseInteractorActor()
        self.mouseInteractor.SetDefaultRenderer(self.renderer)
        self.iterStyleSave = iren.GetInteractorStyle()
        self.iren.SetInteractorStyle(self.mouseInteractor)

    def onVolumeChanged(self, value):
        self.volumeNode = self.inputSelector.currentNode()
        if self.volumeNode != None: 
            xyz = [0,0,0]
            c=[0,0,0]
            slicer.vtkMRMLSliceLogic.GetVolumeRASBox(self.volumeNode,xyz,c)
            xyz[:]=[x*0.2 for x in xyz]
            self.roiNode.SetXYZ(c)
            self.roiNode.SetRadiusXYZ(xyz)
            sp = self.volumeNode.GetSpacing()
            self.voxelVolume = sp[0]*sp[1]*sp[2]
        self.createModels()

    def onTypeChanged(self, value):
        self.calcinationType = value
        if self.calcinationType == 0:
            self.roiCollapsibleButton.setEnabled(1)
            self.ROIWidget.setEnabled(1)
            self.roiNode.SetDisplayVisibility(1)
            #self.logic.cropVolumeWithROI(self.volumeNode, self.roiNode, self.croppedVolumeNode)
        else:
            self.roiCollapsibleButton.setEnabled(0)
            self.ROIWidget.setEnabled(0)
            self.roiNode.SetDisplayVisibility(0)
        self.createModels()

    def onMinSizeChanged(self, value):
        self.MinimumLesionSize = value
        self.createModels()

    def onMaxSizeChanged(self, value):
        self.MaximumLesionSize = value
        self.createModels()

    def onThresholdMinChanged(self, value):
        self.ThresholdMin = value
        self.createModels()

    def onThresholdMaxChanged(self, value):
        self.ThresholdMax = value
        self.createModels()

    def onROIChangedEvent(self, observee, event):
        self.createModels()

    def deleteModels(self):
        for m in self.modelNodes:
            m.SetAndObservePolyData(None)
            slicer.mrmlScene.RemoveNode(m.GetDisplayNode())
            slicer.mrmlScene.RemoveNode(m)
        self.modelNodes = []
        self.selectedLables = {}

    def PickProp(self, object, event):  
        print "PICK"
        pickedActor = self.propPicker.GetActor()
        poly = pickedActor.GetMapper().GetInput()
        label = self.selectedLables[poly]
        print "picked label = ", label

    def processEvent(self,observee,event):
        print "PICK EVENT", event
        self.xy = self.iren.GetEventPosition()
        self.propPicker.PickProp(self.xy[0], self.xy[1], self.renderer)
        pickedActor = self.propPicker.GetActor()
        if pickedActor:
            poly = pickedActor.GetMapper().GetInput()
            label = self.selectedLables[poly]
            print "picked label = ", label

    def computeScore(self, d):
        score = 0
        if d > 129 and d < 200:
            score = 1
        elif d < 300:
            score = 2
        elif d < 400:
            score = 3
        else:
            score = 4
        return score

    def createModels(self):
        self.deleteModels()
        self.labelScores = []
        self.selectedLableList = []
        if self.calcinationType == 0 and self.volumeNode and self.roiNode:
            #print 'in Heart Create Models'

            slicer.vtkSlicerCropVolumeLogic().CropVoxelBased(self.roiNode, self.volumeNode, self.croppedNode)
            croppedImage    = sitk.ReadImage( sitkUtils.GetSlicerITKReadWriteAddress(self.croppedNode.GetName()))
            thresholdImage  = sitk.BinaryThreshold(croppedImage,self.ThresholdMin, self.ThresholdMax, 1, 0)
            connectedCompImage  =sitk.ConnectedComponent(thresholdImage, True)
            relabelImage  =sitk.RelabelComponent(connectedCompImage)
            labelStatFilter =sitk.LabelStatisticsImageFilter()
            labelStatFilter.Execute(croppedImage, relabelImage)
            if relabelImage.GetPixelID() != sitk.sitkInt16:
                relabelImage = sitk.Cast( relabelImage, sitk.sitkInt16 )
            sitk.WriteImage( relabelImage, sitkUtils.GetSlicerITKReadWriteAddress(self.labelsNode.GetName()))

            nLabels = labelStatFilter.GetNumberOfLabels()
            #print "Number of labels = ", nLabels
            self.totalScore = 0
            count = 0
            for n in range(0,nLabels):
                max = labelStatFilter.GetMaximum(n);
                size = labelStatFilter.GetCount(n)
                score = self.computeScore(max)

                if size*self.voxelVolume > self.MaximumLesionSize:
                    continue

                if size*self.voxelVolume < self.MinimumLesionSize:
                    nLabels = n+1
                    break
                
                #print "label = ", n, "  max = ", max, " score = ", score, " voxels = ", size
                self.labelScores.append(score)
                self.selectedLableList.append(0)
                self.marchingCubes.SetInputData(self.labelsNode.GetImageData())
                self.marchingCubes.SetValue(0, n)
                self.marchingCubes.Update()
                    
                self.transformPolyData.SetInputData(self.marchingCubes.GetOutput())
                mat = vtk.vtkMatrix4x4()
                self.labelsNode.GetIJKToRASMatrix(mat)
                trans = vtk.vtkTransform()
                trans.SetMatrix(mat)
                self.transformPolyData.SetTransform(trans)
                self.transformPolyData.Update()
                poly = vtk.vtkPolyData()
                poly.DeepCopy(self.transformPolyData.GetOutput())
                    
                modelNode = slicer.vtkMRMLModelNode()
                slicer.mrmlScene.AddNode(modelNode)
                dnode = slicer.vtkMRMLModelDisplayNode()
                slicer.mrmlScene.AddNode(dnode)
                modelNode.AddAndObserveDisplayNodeID(dnode.GetID())
                modelNode.SetAndObservePolyData(poly)

                ct=slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeLabels')
                rgb = [0,0,0]
                ct.GetLookupTable().GetColor(count+1,rgb)
                dnode.SetColor(rgb)

                self.addLabel(count, rgb, score)

                self.modelNodes.append(modelNode)
                self.selectedLables[poly] = n
                count = count+1
                #a = slicer.util.array(tn.GetID())
                #sa = sitk.GetImageFromArray(a)
            self.scoreField.setText(self.totalScore)
        else:
            print "not implemented"


#
# CIP_CalciumScoringLogic
#

class CIP_CalciumScoringLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget
    """

    def __init__(self):
        self.cropVolumeLogic = slicer.vtkSlicerCropVolumeLogic()
        self.threshold = vtk.vtkImageThreshold()

    def cropVolumeWithROI(self, volumeNode, roiNode, croppedVolume):
        self.cropVolumeLogic.CropVoxelBased(roiNode, volumeNode, croppedVolume)
        #print croppedVolume

    def thresoldImage(self, inImage, value, threshImage):
        self.threshold.SetInputData(inImage)
        self.threshold.ThresholdByUpper(value)
        self.threshold.SetReplaceIn(1)
        self.threshold.SetReplaceOut(1)
        self.threshold.SetInValue(1)
        self.threshold.SetOutValue(0)
        self.threshold.Update()
        threshImage.DeepCopy(self.threshold.GetOutput())


class CIP_CalciumScoringTest(unittest.TestCase):
    """
    This is the test case for your scripted module.
    """

    def delayDisplay(self, message, msec=1000):
        """This utility method displays a small dialog and waits.
        This does two things: 1) it lets the event loop catch up
        to the state of the test so that rendering and widget updates
        have all taken place before the test continues and 2) it
        shows the user/developer/tester the state of the test
        so that we'll know when it breaks.
        """
        print(message)
        self.info = qt.QDialog()
        self.infoLayout = qt.QVBoxLayout()
        self.info.setLayout(self.infoLayout)
        self.label = qt.QLabel(message, self.info)
        self.infoLayout.addWidget(self.label)
        qt.QTimer.singleShot(msec, self.info.close)
        self.info.exec_()

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear(0)
