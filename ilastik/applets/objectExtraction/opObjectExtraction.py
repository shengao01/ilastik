import numpy
import h5py
import vigra.analysis

from lazyflow.graph import Operator, InputSlot, OutputSlot
from lazyflow.stype import Opaque
from lazyflow.rtype import Everything, SubRegion, List
from lazyflow.operators.ioOperators.opStreamingHdf5Reader import OpStreamingHdf5Reader

import ctracking
from lazyflow.roi import roiToSlice
import os
import tempfile


class OpLabelImage( Operator ):
    BinaryImage = InputSlot()
    BackgroundLabel = InputSlot()
    
    LabelImage = OutputSlot()

    def __init__(self, parent=None, graph=None):
        super(OpLabelImage, self).__init__(parent=parent,graph=graph)
        print "OpLabelImage::__init__"
#        self._mem_h5 = h5py.File(self._unique_file("LabelImage.h5"), backing_store=False)
        self._mem_h5 = h5py.File(str(id(self)), driver='core', backing_store=False)        
        self._processedTimeSteps = []
        self._fixed = True
        
    def setupOutputs( self ):
        print 'OpLabelImage::setupOutputs'
        self.LabelImage.meta.assignFrom( self.BinaryImage.meta )
        self.LabelImage.meta.dtype = numpy.uint32
        print 'OptLabelImage::setupOutputs: LabelImage.meta = ' + str(self.LabelImage.meta)
        m = self.LabelImage.meta        
        self._mem_h5.create_dataset( 'LabelImage', shape=m.shape, dtype=numpy.uint32, compression=4 )        
#        self._mem_h5.create_dataset( 'LabelImage', shape=m.shape, dtype=numpy.uint32, compression=1 )
        

    def __del__( self ):
        self._mem_h5.close()
        
    def execute( self, slot, subindex, roi, destination ):
        print 'OpLabelImage::execute'
        
        if slot is self.LabelImage:
#            a = self.BinaryImage.get(roi).wait()
#            assert(a.shape[0] == 1)
#            assert(a.shape[-1] == 1)
#            destination[0,...,0] = vigra.analysis.labelVolumeWithBackground( a[0,...,0] )
#            return destination
        
            if self._fixed:
                destination[:] = 0
                return destination
            
            # assumes t,x,y,z,c
            for t in range(roi.start[0],roi.stop[0]):
                if t not in self._processedTimeSteps:
                    print "Calculating LabelImage at", t
                    start = roi.start
                    stop = roi.stop
                    start[0] = t
                    stop[0] = t+1
                    print 'OpLabelImage::execute: start = ' + str(start) + ', stop = ' + str(stop)
                    a = self.BinaryImage.get(SubRegion(self.BinaryImage, start=start, stop=stop)).wait()        
                    a = a[0,...,0]        
                    r = vigra.analysis.labelVolumeWithBackground( a, background_value = self.BackgroundLabel.value )
                    self._mem_h5['LabelImage'][t,...,0] = r
                    del r
                    self._processedTimeSteps.append(t)
                                        
            
            result = self._mem_h5['LabelImage'][roi.toSlice()]
            return result

#    def _unique_file(self, file_name):
#        dirname, filename = os.path.split(file_name)
#        prefix, suffix = os.path.splitext(filename)
#    
#        fd, filename = tempfile.mkstemp(suffix, prefix+"_", dirname)
#        return filename


class OpRegionFeatures( Operator ):
    LabelImage = InputSlot()
    Output = OutputSlot( stype=Opaque, rtype=List )

    def __init__( self, parent=None, graph=None ):
        super(OpRegionFeatures, self).__init__(parent=parent,
                                              graph=graph)
        self._cache = {}
        self.fixed = True

    def setupOutputs( self ):
        pass
    
    def execute( self, slot, subindex, roi, result ):
        if slot is self.Output:
            def extract( a ):
                labels = numpy.asarray(a, dtype=numpy.uint32)
                data = numpy.asarray(a, dtype=numpy.float32)
                feats = vigra.analysis.extractRegionFeatures(data, labels, features=['RegionCenter', 'Count', 'Coord<ArgMaxWeight>'], ignoreLabel=0)
                return feats
                centers = numpy.asarray(feats['RegionCenter'], dtype=numpy.uint16)
                centers = centers[1:,:]
                return centers
                
            feats = {}
            for t in roi:
                print "RegionFeatures at", t
                if t in self._cache:
                    feats_at = self._cache[t]
                elif self.fixed:                    
                    feats_at = { 'RegionCenter': numpy.asarray([]), 'Count': numpy.asarray([]), 'Coord<ArgMaxWeight>': numpy.asarray([]) }                    
                else:                    
                    troi = SubRegion( self.LabelImage, start = [t,] + (len(self.LabelImage.meta.shape) - 1) * [0,], stop = [t+1,] + list(self.LabelImage.meta.shape[1:]))
                    a = self.LabelImage.get(troi).wait()
                    a = a[0,...,0] # assumes t,x,y,z,c
                    feats_at = extract(a)
                    self._cache[t] = feats_at
                feats[t] = feats_at

            return feats
        
    def propagateDirty(self, slot, roi):
        if slot is self.LabelImage:
            self.Output.setDirty(List(self.Output, range(roi.start[0], roi.stop[0]))) 



class OpRegionCenters( Operator ):
    LabelImage = InputSlot()
    Output = OutputSlot( stype=Opaque, rtype=List )

    
    def __init__( self, parent=None, graph=None ):
        super(OpRegionCenters, self).__init__(parent=parent,
                                              graph=graph)
        self._cache = {}
        self.fixed = True

    def setupOutputs( self ):
        self.Output.meta.shape = self.LabelImage.meta.shape
        self.Output.meta.dtype = self.LabelImage.meta.dtype
    
    def execute( self, slot, subindex, roi, result ):
        if slot is self.Output:
            def extract( a ):
                labels = numpy.asarray(a, dtype=numpy.uint32)
                data = numpy.asarray(a, dtype=numpy.float32)
                feats = vigra.analysis.extractRegionFeatures(data, labels, features=['RegionCenter', 'Count'], ignoreLabel=0)
                centers = numpy.asarray(feats['RegionCenter'], dtype=numpy.uint16)
                centers = centers[1:,:]
                return centers
                
            centers = {}
            for t in roi:
                print "RegionCenters at", t
                if t in self._cache:
                    centers_at = self._cache[t]
                elif self.fixed:
                    centers_at = numpy.asarray([], dtype=numpy.uint16)
                else:
                    troi = SubRegion( self.LabelImage, start = [t,] + (len(self.LabelImage.meta.shape) - 1) * [0,], stop = [t+1,] + list(self.LabelImage.meta.shape[1:]))
                    a = self.LabelImage.get(troi).wait()
                    a = a[0,...,0] # assumes t,x,y,z,c
                    centers_at = extract(a)
                    self._cache[t] = centers_at
                centers[t] = centers_at

            return centers
        
    def propagateDirty(self, slot, roi):
        if slot is self.LabelImage:
            self.Output.setDirty(List(self.Output, range(roi.start[0], roi.stop[0]))) 

class OpObjectExtraction( Operator ):
    name = "Object Extraction"

    #RawData = InputSlot()
    BinaryImage = InputSlot()
    BackgroundLabel = InputSlot()
    #FeatureNames = InputSlot( stype=Opaque )

    LabelImage = OutputSlot()
    ObjectCenterImage = OutputSlot()
    RegionCenters = OutputSlot( stype=Opaque, rtype=List )
    RegionFeatures = OutputSlot( stype=Opaque, rtype=List )

    def __init__( self, parent = None, graph = None ):
        super(OpObjectExtraction, self).__init__(parent=parent,graph=graph)

#        self._mem_h5 = h5py.File(str(id(self)), driver='core', backing_store=False)
        self._reg_cents = {}

        self._opLabelImage = OpLabelImage( graph = graph )
        self._opLabelImage.BinaryImage.connect( self.BinaryImage )
        self._opLabelImage.BackgroundLabel.connect( self.BackgroundLabel)
        self.LabelImage.connect(self._opLabelImage.LabelImage)
        
        self._opRegCent = OpRegionCenters( graph = graph )
        self._opRegCent.LabelImage.connect( self.LabelImage )

        self._opRegFeats = OpRegionFeatures( graph = graph )
        self._opRegFeats.LabelImage.connect( self.LabelImage )
        
    
#    def __del__( self ):
#        self._mem_h5.close()

    def setupOutputs(self):        
        print 'OpObjectExtraction::setupOutputs'
#        self._opLabelImage.setupOutputs()
#        self.LabelImage.meta.assignFrom(self.BinaryImage.meta)
#        m = self.LabelImage.meta
        m = self.BinaryImage.meta
#        self._mem_h5.create_dataset( 'LabelImage', shape=m.shape, dtype=numpy.uint32, compression=1 )

        self._reg_cents = dict.fromkeys(xrange(m.shape[0]), numpy.asarray([], dtype=numpy.uint16))        
        self.ObjectCenterImage.meta.assignFrom(self.BinaryImage.meta)
    
    def execute(self, slot, subindex, roi, result):        
        if slot is self.ObjectCenterImage:
            return self._execute_ObjectCenterImage( roi, result )
#        if slot is self.LabelImage:
#            result = self._mem_h5['LabelImage'][roi.toSlice()]
#            return result
        if slot is self.RegionCenters:
            res = self._opRegCent.Output.get( roi ).wait()
            return res
        if slot is self.RegionFeatures:
            res = self._opRegFeats.Output.get( roi ).wait()
            return res

    def propagateDirty(self, inputSlot, roi):
        raise NotImplementedError

#    def updateLabelImage( self ):
#        m = self.LabelImage.meta        
#        for t in range(m.shape[0]):
#            print "Calculating LabelImage at", t
#            start = [t,] + (len(m.shape) - 1) * [0,]
#            stop = [t+1,] + list(m.shape[1:])            
#            a = self.BinaryImage.get(SubRegion(self.BinaryImage, start=start, stop=stop)).wait()
#            a = a[0,...,0]
#            self._mem_h5['LabelImage'][t,...,0] = vigra.analysis.labelVolumeWithBackground( a )
#        roi = SubRegion(self.LabelImage, start=5*(0,), stop=m.shape)
#        self.LabelImage.setDirty(roi)
#
#    def updateLabelImageAt( self, t ):
#        m = self.LabelImage.meta        
#        print "Calculating LabelImage at", t
#        start = [t,] + (len(m.shape) - 1) * [0,]
#        stop = [t+1,] + list(m.shape[1:])        
#        a = self.BinaryImage.get(SubRegion(self.BinaryImage, start=start, stop=stop)).wait()        
#        a = a[0,...,0]        
#        self._mem_h5['LabelImage'][t,...,0] = vigra.analysis.labelVolumeWithBackground( a, background_value = self.BackgroundLabel.value )

    def __contained_in_subregion( self, roi, coords ):
        b = True
        for i in range(len(coords)):
            b = b and (roi.start[i] <= coords[i] and coords[i] < roi.stop[i])
        return b

    def __make_key( self, roi, coords ):
        return (coords[0] - roi.start[0],
                coords[1] - roi.start[1],
                coords[2] - roi.start[2],
                coords[3] - roi.start[3],
                coords[4] - roi.start[4],)
                
    
    def _execute_ObjectCenterImage( self, roi, result ):
        result[:] = 0
        for t in range(roi.start[0], roi.stop[0]):
            centers = self.RegionFeatures( [t] ).wait()[t]['RegionCenter']
            centers = numpy.asarray( centers, dtype=numpy.uint32)
            if centers.size:
                centers = centers[1:,:]
            for row in range(0,centers.shape[0]):
                x = centers[row,0]
                y = centers[row,1]
                z = centers[row,2]
                
                # mark center
                c =  (t,x,y,z,0)
                if self.__contained_in_subregion( roi, c ): 
                    result[self.__make_key(roi,c)] = 255

                # make the point into a cross
                c =  (t,x-1,y,z,0)
                if self.__contained_in_subregion( roi, c ):
                    result[self.__make_key(roi, c)] = 255
                c =  (t,x,y-1,z,0)
                if self.__contained_in_subregion( roi, c ):
                    result[self.__make_key(roi, c)] = 255
                c =  (t,x,y,z-1,0)
                if self.__contained_in_subregion( roi, c ):
                    result[self.__make_key(roi, c)] = 255

                c =  (t,x+1,y,z,0)
                if self.__contained_in_subregion( roi, c ):
                    result[self.__make_key(roi, c)] = 255
                c =  (t,x,y+1,z,0)
                if self.__contained_in_subregion( roi, c ):
                    result[self.__make_key(roi, c)] = 255
                c =  (t,x,y,z+1,0)
                if self.__contained_in_subregion( roi, c ):
                    result[self.__make_key(roi, c)] = 255
        return result
