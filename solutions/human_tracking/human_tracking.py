import sys

import numpy as np
import cv2

import videoflow
import videoflow.core.flow as flow
from videoflow.core.constants import BATCH
from videoflow.consumers import VideofileWriter
from videoflow.producers import VideofileReader
from videoflow_contrib.detectron2 import Detectron2HumanPose, HumanPoseAnnotator
from videoflow_contrib.tracker_deepsort import DeepSort
from videoflow_contrib.humanencoder import HumanEncoder
from videoflow.processors.vision.annotators import TrackerAnnotator
from videoflow.utils.downloader import get_file


BASE_URL_EXAMPLES = "https://github.com/videoflow/videoflow-contrib/releases/download/example_videos/"
VIDEO_NAME = "people_walking.mp4"
URL_VIDEO = BASE_URL_EXAMPLES + VIDEO_NAME

class FrameIndexSplitter(videoflow.core.node.ProcessorNode):
    def __init__(self):
        super(FrameIndexSplitter, self).__init__()
    
    def process(self, data):
        index, frame = data
        return frame

class KeypointsExtractor(videoflow.core.node.ProcessorNode):
    def __init__(self):
        super(KeypointsExtractor, self).__init__()
    
    def process(self, data):
        keypoints, bounding_boxes = data
        return keypoints

class BoundingBoxesExtractor(videoflow.core.node.ProcessorNode):
    def __init__(self):
        super(BoundingBoxesExtractor, self).__init__()
    
    def process(self, data):
        '''
        Returns:
            - bounding_boxes: (nb_boxes, [ymin, xmin, width, height, klass, score])
        '''
        keypoints, bounding_boxes = data
        scores = np.ones((bounding_boxes.shape[0], 1))
        bounding_boxes = np.concatenate(
            [bounding_boxes[:, [1, 0]], 
            np.expand_dims(bounding_boxes[:,2] - bounding_boxes[:,0], 1),
            np.expand_dims(bounding_boxes[:,3] - bounding_boxes[:,1], 1)], axis = 1)
        bounding_boxes = np.concatenate([bounding_boxes, scores], axis = 1)
        bounding_boxes = bounding_boxes.astype(np.int32)
        return bounding_boxes

class CropBoundingBoxes(videoflow.core.node.ProcessorNode):
    def __init__(self):
        super(CropBoundingBoxes, self).__init__()

    def process(self, im, bounding_boxes):
        '''
        - Arguments:
            - im: np.array of shape (h, w, 3)
            - bounding_boxes: np.array of shape (nb_boxes, [ymin, xmin, ymax, xmax, score])

        - Returns:
            - im_list: list of np.array (h, w, 3)
        '''
        to_return = []
        for bbox in bounding_boxes:
            ymin, xmin, width, height, _= bbox
            crop = im[ymin:ymin + height, xmin:xmin + width, :]
            to_return.append(crop)
        return to_return

class AppendFeaturesToBoundingBoxes(videoflow.core.node.ProcessorNode):
    def __init__(self):
        super(AppendFeaturesToBoundingBoxes, self).__init__()
    
    def process(self, bboxes, features):
        '''
        - Arguments:
            - bboxes: (batch, [ymin, xmin, width, height, score])
            - features: (batch, nb_features)
        '''
        to_return = np.concatenate([bboxes, features], axis = 1)
        return to_return

class ConvertTracksForAnotation(videoflow.core.node.ProcessorNode):
    def __init__(self):
        super(ConvertTracksForAnotation, self).__init__()
    
    def process(self, tracks):
        '''
        - Arguments:
            - tracks: (nb_tracks, [ymin, xmin, width, height, track_id])
        
        - Returns:
            - tracks: (nb_tracks, [ymin, xmin, ymax, xmax, track_id])
        '''

        if len(tracks) > 0:
            to_return = np.concatenate(
                [
                    tracks[:, [0, 1]],
                    tracks[:, 0] + tracks[:, 3],
                    tracks[:, 1] + tracks[:, 2],
                    tracks[:, 4]
                ],
                axis = 1
            ).astype(np.int32)
            return to_return
        else:
            return tracks

def track_humans():
    input_file_path = get_file(VIDEO_NAME, URL_VIDEO)
    output_file = 'annotated_video.avi'
    reader = VideofileReader(input_file_path)
    frame = FrameIndexSplitter()(reader)
    results = Detectron2HumanPose(architecture = 'R50_FPN_3x', device_type = 'cpu')(frame)
    keypoints = KeypointsExtractor()(results)
    bounding_boxes = BoundingBoxesExtractor()(results)
    anotated_keypoints = HumanPoseAnnotator()(frame, keypoints)
    cropped_humans = CropBoundingBoxes()(frame, bounding_boxes)
    human_features = HumanEncoder()(cropped_humans)
    tracker_input = AppendFeaturesToBoundingBoxes()(bounding_boxes, human_features)
    tracks = DeepSort()(tracker_input)
    tracks_anotator_input = ConvertTracksForAnotation()(tracks)
    anotated_tracks = TrackerAnnotator()(anotated_keypoints, tracks_anotator_input)
    writer = VideofileWriter(output_file)(anotated_tracks)
    fl = flow.Flow([reader], [writer], flow_type = BATCH)
    fl.run()
    fl.join()

if __name__ == '__main__':
    track_humans()
