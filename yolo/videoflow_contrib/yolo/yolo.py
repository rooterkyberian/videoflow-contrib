#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run a YOLO_v3 style detection model on test images.
"""

import colorsys
import os
import random
from timeit import time
from timeit import default_timer as timer  ### to calculate FPS

from PIL import Image
import numpy as np
from keras import backend as K
from keras.models import load_model
from PIL import Image, ImageFont, ImageDraw

from videoflow.utils.downloader import get_file
from videoflow.core.node import ProcessorNode

from .yolo3.model import yolo_eval
from .yolo3.utils import letterbox_image
from .yolo3 import preprocessing

class YOLO(ProcessorNode):
    def __init__(self, model_path = None):
        self.model_path = model_path
        self.anchors_path = None
        self.classes_path = None
        self.score = 0.5
        self.iou = 0.5
        super(YOLO, self).__init__()

    def open(self):
        # TODO: Figure out device_id later.
        if self.model_path is None:
            remote_url = 'https://github.com/videoflow/videoflow-contrib/releases/download/models/yolo.h5'
            self.model_path = get_file('yolo.h5', remote_url)
        if self.anchors_path is None:
            self.anchors_path = get_file('yolo_anchors.txt', 'https://github.com/videoflow/videoflow-contrib/releases/download/models/yolo_anchors.txt')
        if self.classes_path is None:
            self.classes_path = get_file('coco_classes.txt', 'https://github.com/videoflow/videoflow-contrib/releases/download/models/yolo_anchors.txt')
    
        self.class_names = self._get_class()
        self.anchors = self._get_anchors()
        self.sess = K.get_session()
        self.model_image_size = (416, 416) # fixed size or (None, None)
        self.is_fixed_size = self.model_image_size != (None, None)
        self.boxes, self.scores, self.classes = self.generate()

    def _get_class(self):
        classes_path = os.path.expanduser(self.classes_path)
        with open(classes_path) as f:
            class_names = f.readlines()
        class_names = [c.strip() for c in class_names]
        return class_names

    def _get_anchors(self):
        anchors_path = os.path.expanduser(self.anchors_path)
        with open(anchors_path) as f:
            anchors = f.readline()
            anchors = [float(x) for x in anchors.split(',')]
            anchors = np.array(anchors).reshape(-1, 2)
        return anchors

    def generate(self):
        model_path = os.path.expanduser(self.model_path)
        assert model_path.endswith('.h5'), 'Keras model must be a .h5 file.'

        self.yolo_model = load_model(model_path, compile=False)
        print('{} model, anchors, and classes loaded.'.format(model_path))

        # Generate colors for drawing bounding boxes.
        hsv_tuples = [(x / len(self.class_names), 1., 1.)
                      for x in range(len(self.class_names))]
        self.colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
        self.colors = list(
            map(lambda x: (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)),
                self.colors))
        random.seed(10101)  # Fixed seed for consistent colors across runs.
        random.shuffle(self.colors)  # Shuffle colors to decorrelate adjacent classes.
        random.seed(None)  # Reset seed to default.

        # Generate output tensor targets for filtered bounding boxes.
        self.input_image_shape = K.placeholder(shape=(2, ))
        boxes, scores, classes = yolo_eval(self.yolo_model.output, self.anchors,
                len(self.class_names), self.input_image_shape,
                score_threshold=self.score, iou_threshold=self.iou)
        return boxes, scores, classes

    def detect_image(self, image):
        '''
        - Arguments:
            - image: np.array (h, w, 3) in rgb format.
        
        - Returns:
            - return_boxs: an array of arrays [[x, y, w, h]]
        '''
        print(image.shape)
        image = Image.fromarray(image)
        if self.is_fixed_size:
            assert self.model_image_size[0]%32 == 0, 'Multiples of 32 required'
            assert self.model_image_size[1]%32 == 0, 'Multiples of 32 required'
            boxed_image = letterbox_image(image, tuple(reversed(self.model_image_size)))
        else:
            new_image_size = (image.width - (image.width % 32),
                              image.height - (image.height % 32))
            boxed_image = letterbox_image(image, new_image_size)
        image_data = np.array(boxed_image, dtype='float32')

        #print(image_data.shape)
        image_data /= 255.
        image_data = np.expand_dims(image_data, 0)  # Add batch dimension.
        
        out_boxes, out_scores, out_classes = self.sess.run(
            [self.boxes, self.scores, self.classes],
            feed_dict={
                self.yolo_model.input: image_data,
                self.input_image_shape: [image.size[1], image.size[0]],
                K.learning_phase(): 0
            })
        return_boxs = []
        for i, c in reversed(list(enumerate(out_classes))):
            predicted_class = self.class_names[c]
            if predicted_class != 'person' :
                continue
            box = out_boxes[i]
           # score = out_scores[i]  
            x = int(box[1])  
            y = int(box[0])  
            w = int(box[3]-box[1])
            h = int(box[2]-box[0])
            if x < 0 :
                w = w + x
                x = 0
            if y < 0 :
                h = h + y
                y = 0 
            return_boxs.append([x,y,w,h])
        
        nms_max_overlap = 1.0
        indices = preprocessing.non_max_suppression(return_boxs, nms_max_overlap)
        return_boxs = [return_boxs[i] for i in indices]
        return return_boxs
    
    def process(self, image):
        return self.detect_image(image)

    def close(self):
        self.sess.close()