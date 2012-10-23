from lazyflow.graph import Graph, OperatorWrapper

from ilastik.workflow import Workflow

from ilastik.applets.dataSelection import DataSelectionApplet
from ilastik.applets.objectExtraction import ObjectExtractionApplet

from lazyflow.operators.obsolete.valueProviders import OpAttributeSelector
from ilastik.applets.tracking.trackingAppletNN import TrackingAppletNN

class TrackingWorkflowNN( Workflow ):
    def __init__( self ):
        super(TrackingWorkflowNN, self).__init__()
        self._applets = []
        self._imageNameListSlot = None
        self._graph = None

        # Create a graph to be shared by all operators
        graph = Graph()
    
        ######################
        # Interactive workflow
        ######################
        
        ## Create applets 
        self.dataSelectionApplet = DataSelectionApplet(graph, "Input Segmentation", "Input Segmentation", batchDataGui=False)

        self.objectExtractionApplet = ObjectExtractionApplet( graph )
        self.trackingApplet = TrackingAppletNN( graph )

        ## Access applet operators
        opData = self.dataSelectionApplet.topLevelOperator
        opObjExtraction = self.objectExtractionApplet.topLevelOperator
        opTracking = self.trackingApplet.topLevelOperator
        
        ## Connect operators ##
        opObjExtraction.Images.connect( opData.Image )

        opTracking.LabelImage.connect( opObjExtraction.LabelImage )
        opTracking.ObjectFeatures.connect( opObjExtraction.RegionFeatures )
        opTracking.ClassMapping.connect( opObjExtraction.ClassMapping )

        self._applets.append(self.dataSelectionApplet)
        self._applets.append(self.objectExtractionApplet)
        self._applets.append(self.trackingApplet)

        # The shell needs a slot from which he can read the list of image names to switch between.
        # Use an OpAttributeSelector to create a slot containing just the filename from the OpDataSelection's DatasetInfo slot.
        opSelectFilename = OperatorWrapper( OpAttributeSelector, graph=graph )
        opSelectFilename.InputObject.connect( opData.Dataset )
        opSelectFilename.AttributeName.setValue( 'filePath' )

        self._imageNameListSlot = opSelectFilename.Result

    @property
    def applets(self):
        return self._applets

    @property
    def imageNameListSlot(self):
        return self._imageNameListSlot
    
