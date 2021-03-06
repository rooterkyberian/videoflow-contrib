from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import numpy as np

from videoflow.core.node import ProcessorNode
from videoflow.core.constants import CPU, GPU
from videoflow.processors.vision.detectors import ObjectDetector
from .tensorflow_utils import TensorflowModel, TfliteModel
from videoflow.utils.downloader import get_file

import tensorflow as tf

BASE_URL_DETECTION = 'https://github.com/videoflow/videoflow-contrib/releases/download/detector_tf/'

class TfliteObjectDetector(ObjectDetector):
    def __init__(self, path_to_pb_file,
                num_classes = 1):
        self._num_classes = num_classes
        self._path_to_pb_file = path_to_pb_file
        self._tflite_model = None
        super(TfliteObjectDetector, self).__init__(nb_tasks = 1, device_type = CPU)
    
    def open(self):
        '''
        Creates session with tensorflow model
        '''
        self._tflite_model = TfliteModel(
            self._path_to_pb_file,
            ["image_tensor:0"],
            ["detection_boxes:0", "detection_scores:0", "detection_classes:0", "num_detections:0"]
        )
    
    def close(self):
        pass

    def _detect(self, im: np.array) -> np.array:
        h, w, _ = im.shape
        im_expanded = np.expand_dims(im, axis = 0)
        boxes, scores, classes, num = self._tflite_model.run_on_input(im_expanded)
        boxes, scores, classes = np.squeeze(boxes, axis = 0), np.squeeze(scores, axis = 0), np.squeeze(classes, axis = 0)

        # boxes denormalization
        boxes[:,[0, 2]] = boxes[:,[0, 2]] * h
        boxes[:,[1, 3]] = boxes[:,[1, 3]] * w

        indexes = np.where(scores > self._min_score_threshold)[0]
        boxes, scores, classes = boxes[indexes], scores[indexes], classes[indexes]
        scores, classes = np.expand_dims(scores, axis = 1), np.expand_dims(classes, axis = 1)
        return np.concatenate((boxes, classes, scores), axis = 1)

class TensorflowObjectDetector(ObjectDetector):
    '''
    Finds object detections by running a Tensorflow model on an image.

    Initializes the tensorflow model.  If ``path_to_pb_file`` is provided, it uses a local
    model. If not, it uses ``architecture`` and ``dataset`` parameters to download tensorflow
    pretrained models.  
    
    .. csv-table:: Models supported COCO Dataset
        
        "Model","Speed (ms)","COCO mAP"
        "ssd-mobilenetv2_coco","30","21"
        "ssd-resnet50-fpn_coco","76","35"
        "fasterrcnn-resnet101_coco","106","32"

    .. csv-table:: Models supported Kitti Dataset
        
        "Model","Speed (ms)", "Pascal mAP@0.5"
        "fasterrcnn-resnet101_kitti","79","87"

    .. csv-table:: Models supported Open Images V4 Dataset
        
        "Model","Speed (ms)", "Open Images V4 mAP@0.5"
        "fasterrcnn-inception-resnetv2-atrous_oidv4.1","425","54"
        "ssd-mobilenetv2_oidv4","89","36"
    
    .. csv-table:: Modesl supported Faces dataset
        "Model","Speed (ms)", "Open Images V4 mAP@0.5"
        "ssd-mobilenetv2_faces","89","79"
    
    - Arguments:
        - num_classes (int): number of classes that the detector can recognize.
        - path_to_pb_file (str): Path where model pb file is \
            It expects the model to have the following input tensors: ``image_tensor:0``, and \
            the following output tensors: ``detection_boxes:0``, ``detection_scores:0``, \
            ``detection_classes:0``, and ``num_detections:0``.  If no path is provided, then \
            it will download the model from the internet using the values provided for ``architecture``\
            and ``dataset``.
        - architecture (str): One of the architectures mentioned in the tables above.
        - dataset (str): `coco`, `kitti` and `oidv4` are accepted.
        - min_score_threshold (float): detection will filter out entries with score below threshold score
    '''
    supported_models = [
        "ssd-mobilenetv2_coco",
        "ssd-resnet50-fpn_coco",
        "fasterrcnn-resnet101_coco",
        "fasterrcnn-resnet101_kitti",
        "fasterrcnn-inception-resnetv2-atrous_oidv4.1",
        "ssd-mobilenetv2_oidv4",
        "ssd-mobilenetv2_faces"
    ]

    def __init__(self, 
                num_classes = 90,
                path_to_pb_file = None,
                architecture = 'ssd-resnet50-fpn',
                dataset = 'coco',
                min_score_threshold = 0.5,
                nb_tasks = 1,
                device_type = GPU):
        self._tensorflow_model = None
        self._num_classes = num_classes
        self._path_to_pb_file = path_to_pb_file
        
        if path_to_pb_file is None and (architecture is None or dataset is None):
            raise ValueError('If path_to_pb_file is None, then architecture and dataset cannot be None')

        if path_to_pb_file is None:
            remote_model_id = f'{architecture}_{dataset}'
            if remote_model_id not in self.supported_models:
                raise ValueError('model is not one of supported models: {}'.format(', '.join(self.supported_models)))        
            self._remote_model_file_name = f'{architecture}_{dataset}.pb'

        self._min_score_threshold = min_score_threshold
        super(TensorflowObjectDetector, self).__init__(nb_tasks = nb_tasks, device_type = device_type)
    
    def open(self):
        '''
        Creates session with tensorflow model
        '''
        if self.device_type == CPU:
            device_id = 'cpu'
        elif self.device_type == GPU:
            device_id = 'gpu'
        else:
            device_id = 'cpu'
        
        if self._path_to_pb_file is None:
            remote_url = BASE_URL_DETECTION + self._remote_model_file_name
            self._path_to_pb_file = get_file(self._remote_model_file_name, remote_url)

        self._tensorflow_model = TensorflowModel(
            self._path_to_pb_file,
            ["image_tensor:0"],
            ["detection_boxes:0", "detection_scores:0", "detection_classes:0", "num_detections:0"],
            device_id = device_id
        )
    
    def close(self):
        '''
        Closes tensorflow model session.
        '''
        self._tensorflow_model._close_session()

    def _detect(self, im : np.array) -> np.array:
        '''
        - Arguments:
            - im (np.array): (h, w, 3)
        
        - Returns:
            - dets: np.array of shape (nb_boxes, 6) \
                Specifically (nb_boxes, [ymin, xmin, ymax, xmax, class_index, score])
        '''
        h, w, _ = im.shape
        im_expanded = np.expand_dims(im, axis = 0)
        boxes, scores, classes, num = self._tensorflow_model.run_on_input(im_expanded)
        boxes, scores, classes = np.squeeze(boxes, axis = 0), np.squeeze(scores, axis = 0), np.squeeze(classes, axis = 0)
        
        # boxes denormalization
        boxes[:,[0, 2]] = boxes[:,[0, 2]] * h
        boxes[:,[1, 3]] = boxes[:,[1, 3]] * w

        indexes = np.where(scores > self._min_score_threshold)[0]
        boxes, scores, classes = boxes[indexes], scores[indexes], classes[indexes]
        scores, classes = np.expand_dims(scores, axis = 1), np.expand_dims(classes, axis = 1)
        return np.concatenate((boxes, classes, scores), axis = 1)
