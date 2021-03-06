/*==============================================================================

  Program: 3D Slicer

  Copyright (c) Kitware Inc.

  See COPYRIGHT.txt
  or http://www.slicer.org/copyright/copyright.txt for details.

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
  and was partially funded by NIH grant 3P41RR013218-12S1

==============================================================================*/

#ifndef __qSlicerAirwayInspectorModuleWidget_h
#define __qSlicerAirwayInspectorModuleWidget_h

// SlicerQt includes
#include "qSlicerAbstractModuleWidget.h"

#include "qSlicerAirwayInspectorModuleExport.h"

#include <vtkCallbackCommand.h>
#include <vtkSmartPointer.h>
#include <vtkWeakPointer.h>

class qSlicerAirwayInspectorModuleWidgetPrivate;
class vtkImageData;
class vtkMRMLNode;
class vtkRenderWindowInteractor;
class vtkRenderer;
class vtkMRMLSliceNode;
class vtkMRMLAirwayNode;
class vtkMRMLScalarVolumeDisplayNode;
class vtkPolyData;

#include <map>

/// \ingroup Slicer_QtModules_AirwayInspector
class Q_SLICER_QTMODULES_AIRWAYINSPECTOR_EXPORT qSlicerAirwayInspectorModuleWidget :
  public qSlicerAbstractModuleWidget
{
  Q_OBJECT

public:

  typedef qSlicerAbstractModuleWidget Superclass;
  qSlicerAirwayInspectorModuleWidget(QWidget *parent=0);
  virtual ~qSlicerAirwayInspectorModuleWidget();

  /// Called after one of the observable event is invoked
  static void DoInteractorCallback(vtkObject* vtk_obj, unsigned long event,
                                   void* client_data, void* call_data);

  void onInteractorEvent(vtkRenderWindowInteractor* interactor, int eventid);

public slots:
  virtual void setMRMLScene(vtkMRMLScene *newScene);
  //void onNodeAddedEvent(vtkObject* scene, vtkObject* node);
  //void onNodeRemovedEvent(vtkObject* scene, vtkObject* node);
  void onLayoutChanged(int);

protected:
  virtual void setup();
  void removeInteractorObservers();
  void addAndObserveInteractors();
  void addAndObserveInteractor(vtkRenderWindowInteractor* newInteractor,
                                vtkMRMLSliceNode* snode);
  void updateReport(vtkMRMLAirwayNode* airwayNode);
  void updateViewer(vtkMRMLAirwayNode* airwayNode);
  void createColorImage(vtkImageData *image, vtkImageData *colorImage);
  void saveAirwayImage(vtkMRMLAirwayNode* airwayNode, char *filename = 0, vtkImageData *img = 0);
  void updateWidgetFromMRML(vtkMRMLAirwayNode* airwayNode);
  void updateMRMLFromWidget(vtkMRMLAirwayNode* airwayNode);
  void updateAirwaySlice();
  void flipPolyData(vtkPolyData *poly, double shift);

protected slots:
  void setMRMLVolumeNode(vtkMRMLNode*);
  void setMRMLAirwayNode(vtkMRMLNode*);
  void analyzeSelected();
  void analyzeAll();
  void writeCSV();
  void onThresholdChanged(double);
  void onToggled(bool);
  void onDrawCahnged(bool);
  void onMethodChanged(int);
  void onWindowLevelChanged();

protected:
  QScopedPointer<qSlicerAirwayInspectorModuleWidgetPrivate> d_ptr;

  std::map<vtkRenderWindowInteractor*, vtkMRMLSliceNode*>   interactors;
  vtkSmartPointer<vtkCallbackCommand>       interactorCallBackCommand;
  vtkSmartPointer<vtkRenderer> Renderer;
  vtkWeakPointer<vtkMRMLScalarVolumeDisplayNode> VolumeDisplayNode;
  bool isUpdating;

  QStringList statsLabels;
  QStringList valuesLabels;

private:
  Q_DECLARE_PRIVATE(qSlicerAirwayInspectorModuleWidget);
  Q_DISABLE_COPY(qSlicerAirwayInspectorModuleWidget);
};

#endif
