import os
os.environ["THEANO_FLAGS"] = "device=gpu"
from sklearn.base import BaseEstimator
import os
from lasagne import layers, nonlinearities
from lasagne.updates import nesterov_momentum, rmsprop, adagrad
from nolearn.lasagne import NeuralNet, BatchIterator
from nolearn.lasagne.handlers import EarlyStopping
import numpy as np
from caffezoo.googlenet import GoogleNet
from itertools import repeat
from sklearn.pipeline import make_pipeline
from scipy.ndimage.interpolation import rotate

#initialize rotation parameters

a = np.arange(64*64)
a = a.reshape(64,64)

angleToOffsetStartAndOffsetEnd = {}
alphaList = []
numRot = 16
unitRot = 360.0/numRot

for mult_alpha in range(numRot):
    alpha = mult_alpha*unitRot
    alphaList.append(alpha)

    theRot = rotate(a,alpha)
    theShape = theRot.shape

    theRest = theShape[0] - 64
    theOffsetEnd = theRest/2
    theOffsetStart = theRest - theRest/2
    
    angleToOffsetStartAndOffsetEnd[alpha] = {'indexStart':theOffsetStart,'indexEnd':theShape[0]-theOffsetEnd,'shape':theShape[0]}

def sample_from_rotation_x_old(x):
    x_extends = []
    for i in range(x.shape[0]):
        x_extends.extend([
        np.array([x[i,:,:,0], x[i,:,:,1], x[i,:,:,2]]),
        np.array([np.rot90(x[i,:,:,0]),np.rot90(x[i,:,:,1]), np.rot90(x[i,:,:,2])]),
        np.array([np.rot90(x[i,:,:,0],2),np.rot90(x[i,:,:,1],2), np.rot90(x[i,:,:,2],2)]),
        np.array([np.rot90(x[i,:,:,0],3),np.rot90(x[i,:,:,1],3), np.rot90(x[i,:,:,2],3)])
        ])
    x_extends = np.array(x_extends) #.transpose((0, 2, 3, 1))
    return x_extends
 
def sample_from_rotation_y_old(y):
    y_extends = []
    for i in y:
        y_extends.extend( repeat( i ,4) )
    return np.array(y_extends)
 
def sample_from_rotation_x(x):
    x_extends = []
    iterOnBigChunk = 0
    numBigChunk = 100
    bigChunk = x.shape[0]/numBigChunk
    for i in range(x.shape[0]):
        
        if i > iterOnBigChunk*bigChunk:
            print 'We have reached the',iterOnBigChunk,'th big chunk of',numBigChunk
            iterOnBigChunk += 1
            
        for alpha in alphaList:
            indexStart = angleToOffsetStartAndOffsetEnd[alpha]['indexStart']
            indexEnd = angleToOffsetStartAndOffsetEnd[alpha]['indexEnd']
            x_extends.append(np.array([rotate(x[i,:,:,0],alpha)[indexStart:indexEnd,indexStart:indexEnd], rotate(x[i,:,:,1],alpha)[indexStart:indexEnd,indexStart:indexEnd], rotate(x[i,:,:,2],alpha)[indexStart:indexEnd,indexStart:indexEnd]]))
    x_extends = np.array(x_extends) #.transpose((0, 2, 3, 1))
    #print x_extends.shape
    return x_extends
 
def sample_from_rotation_y(y):
    y_extends = []
    for i in y:
        y_extends.extend( repeat( i ,numRot) )
    return np.array(y_extends)
 
 
class FlipBatchIterator(BatchIterator):
    def transform(self, Xb, yb):
        Xb, yb = super(FlipBatchIterator, self).transform(Xb, yb)
        # Flip half of the images in this batch at random:
        bs = Xb.shape[0]
        indices = np.random.choice(bs, bs / 2, replace=False)
        Xb[indices] = Xb[indices, :, ::-1, :]
        return Xb, yb
 
def build_model():    
    L=[
        #(layers.InputLayer, {'shape':(None, 3, 64, 64)}),
        (layers.InputLayer, {'shape':(None, 3, 64, 64)}),
        (layers.Conv2DLayer, {'num_filters':32, 'filter_size':(2,2), 'pad':0}),
        (layers.MaxPool2DLayer, {'pool_size': (3, 3)}),
        (layers.Conv2DLayer, {'num_filters':32, 'filter_size':(2,2), 'pad':0}),
        (layers.MaxPool2DLayer, {'pool_size': (2, 2)}),
        (layers.Conv2DLayer, {'num_filters':16, 'filter_size':(2,2), 'pad':0}),
        (layers.MaxPool2DLayer, {'pool_size': (1, 1)}),
        (layers.DenseLayer, {'num_units': 512, 'nonlinearity':nonlinearities.leaky_rectify}),
        (layers.DropoutLayer, {'p':0.5}),
        (layers.DenseLayer, {'num_units': 512, 'nonlinearity':nonlinearities.leaky_rectify}),
        (layers.DropoutLayer, {'p':0.5}),
        (layers.DenseLayer, {'num_units': 256, 'nonlinearity':nonlinearities.tanh}),
        (layers.DropoutLayer, {'p':0.2}),
        (layers.DenseLayer, {'num_units': 18, 'nonlinearity':nonlinearities.softmax}),
    ]
 
 
    net = NeuralNet(
        layers=L,
        update=adagrad,
        update_learning_rate=0.01,
        use_label_encoder=True,
        verbose=1,
        max_epochs=50,
        batch_iterator_train=FlipBatchIterator(batch_size=256),
        on_epoch_finished=[EarlyStopping(patience=50, criterion='valid_loss')]
        )
    return net
 
# currently used
def keep_dim(layers):
    #print len(layers), layers[0].shape
    return layers[0]
 
class Classifier(BaseEstimator):
 
    def __init__(self):
        self.crop_value = 5
        self.net = make_pipeline(
            #GoogleNet(aggregate_function=keep_dim, layer_names=["input"]),
            build_model()
        )
        
    def data_augmentation(self, X, y):
        X = sample_from_rotation_x(X)
        y = sample_from_rotation_y(y)
        return X, y
 
    def preprocess(self, X, transpose=True):
        X = (X / 255.)
        X = X.astype(np.float32)
        X = X[:, self.crop_value:64-self.crop_value, self.crop_value:64-self.crop_value, :]
        if transpose:
            X = X.transpose((0, 3, 1, 2))
        return X
    
    def preprocess_y(self, y):
        return y.astype(np.int32)
 
    def fit(self, X, y):
        print 'Start preprocessing'
        X, y = self.preprocess(X, False), self.preprocess_y(y)
        print 'Start data augmentation'
        X, y = self.data_augmentation(X, y)
        print 'Start fit'
        self.net.fit(X, y)
        return self
 
    def predict(self, X):
        X = self.preprocess(X)
        return self.net.predict(X)
 
    def predict_proba(self, X):
        X = self.preprocess(X)
        return self.net.predict_proba(X)
