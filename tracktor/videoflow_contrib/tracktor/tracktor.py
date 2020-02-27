from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import torch
from videoflow.core.node import OneTaskProcessorNode
from videoflow.utils.downloader import get_file

from .tracker import Tracker
from .frcnn_fpn import FRCNN_FPN
from .reid import resnet50

URL_REID_MODEL = 'https://github.com/videoflow/videoflow-contrib/releases/download/tracktor/detection.pth'
URL_DETECTION_MODEL = 'https://github.com/videoflow/videoflow-contrib/releases/download/tracktor/reid.pth'

class TracktorFromFrames(OneTaskProcessorNode):
    '''
    Tracktor algorithm with REID taken from
    https://github.com/phil-bergmann/tracking_wo_bnw
    '''

    def __init__(self, interpolate):
        self._tracker = None
        super(Tracktor, self).__init__()
    
    def open(self):
        #1. Load detection model
        detection_model_path = get_file('detection.pkl', URL_DETECTION_MODEL)
        obj_detect = FRCNN_FPN(num_classes = 2)
        obj_detect.load_state_dict(
            torch.load(detection_model_path, map_location = lambda storage, loc: storage)
        )
        obj_detect.eval()
        obj_detect.cuda()

        #2. Load re-identification model
        reid_model_path = get_file('reid.pkl', URL_REID_MODEL)
        reid_network = resnet(pretrained = False, {'output_dim': 128})
        reid_network.load_state_dict(
            torch.load(reid_model_path, map_location = lambda storage, loc: storage)
        )

        #3. Creater tracker
        self._tracker = Tracker(
            obj_detect, 
            reid_network, 
            detection_person_thresh = 0.5,
            regression_person_thresh = 0.5,
            detection_nms_thresh = 0.3,
            regression_nms_thresh = 0.6,
            public_detections = False,
            inactive_patience = 10,
            do_reid = True,
            max_features_num = 10,
            reid_sim_threshold = 2.0,
            reid_iou_threshold = 0.2,
            motion_model_cfg = {
                'enabled': False,
                n_steps: 1,
                center_only: True
            },
            warp_mode = 'cv2.MOTION_EUCLIDEAN',
            number_of_iterations = 100,
            termination_eps = 0.00001,
            do_align = False
        )
        

    def process(self, frame):
        '''
        - Arguments:
            - frame (np.array) (h, w, 3)
        
        - Returns:
            - tracks: (np.array) (nb_boxes, 5) \
                Specifically (nb_boxes, [xmin, ymin, xmax, ymax, score, track_id])
        '''
        self._tracker.step(frame)
        results = self._tracker.get_current_tracks()
        return results
    

class TracktorFromBoxes(OneTaskProcessorNode):
    pass