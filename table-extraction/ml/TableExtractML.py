import numpy as np

from utils.bbox_utils import get_rectangles, compute_iou
from utils.lines_utils import reorder_lines, get_vertical_and_horizontal, extend_vertical_lines, \
    merge_vertical_lines, merge_horizontal_lines, extend_horizontal_lines
from pdf.pdf_parsers import parse_layout
from pdf.pdf_utils import normalize_pdf, analyze_pages
from utils.display_utils import pdf_to_img
from ml.features import get_alignment_features, get_lines_features
from wand.color import Color
from wand.drawing import Drawing


class TableExtractorML(object):
    """
    Object to extract tables regions from pdf files
    """

    def __init__(self, pdf_file):
        self.pdf_file = pdf_file
        self.elems = {}
        self.font_stats = {}
        self.lines_bboxes = []
        self.alignments_bboxes = []
        self.intersection_bboxes = []
        self.bboxes = []
        self.candidates = []
        self.features = []
        self.iou_thresh = 0.8

    def parse(self):
        for page_num, layout in enumerate(analyze_pages(self.pdf_file)):
            page_num += 1  # indexes start at 1
            elems, font_stat = normalize_pdf(layout, scaler=1)
            self.elems[page_num] = elems
            self.font_stats[page_num] = font_stat

    def get_candidates_and_features(self):
        self.parse()
        for page_num in self.elems.keys():
            page_boxes, page_features = self.get_candidates_and_features_page_num(page_num)
            self.candidates += page_boxes
            self.features += list(page_features)
        return self.candidates, self.features

    def get_candidates_and_features_page_num(self, page_num):
        elems = self.elems[page_num]
        font_stat = self.font_stats[page_num]
        lines_bboxes = self.get_candidates_lines(page_num, elems)
        alignments_bboxes, alignment_features = self.get_candidates_alignments(page_num, elems)
        # print "Page Num: ", page_num, "Line bboxes: ", len(lines_bboxes), ", Alignment bboxes: ", len(alignments_bboxes)
        alignment_features += get_alignment_features(lines_bboxes, elems, font_stat)
        boxes = alignments_bboxes + lines_bboxes
        if len(boxes) == 0:
            return [], []
        lines_features = get_lines_features(boxes, elems)
        features = np.concatenate((np.array(alignment_features), np.array(lines_features)), axis=1)
        return boxes, features

    def get_candidates_lines(self, page_num, elems):
        page_width, page_height = int(elems.layout.width), int(elems.layout.height)
        lines = reorder_lines(elems.segments)
        vertical_lines, horizontal_lines = get_vertical_and_horizontal(lines)
        extended_vertical_lines = extend_vertical_lines(horizontal_lines)
        extended_horizontal_lines = extend_horizontal_lines(vertical_lines)
        vertical_lines = merge_vertical_lines(sorted(extended_vertical_lines + vertical_lines))
        horizontal_lines = merge_horizontal_lines(sorted(extended_horizontal_lines + horizontal_lines))
        rectangles = get_rectangles(sorted(vertical_lines), sorted(horizontal_lines))
        return [(page_num, page_width, page_height) + bbox for bbox in rectangles]

    def get_candidates_alignments(self, page_num, elems):
        page_width, page_height = int(elems.layout.width), int(elems.layout.height)
        font_stat = self.font_stats[page_num]
        try:
            nodes, features = parse_layout(elems, font_stat)
        except:
            nodes, features = [], []
        return [(page_num, page_width, page_height) + (node.y0, node.x0, node.y1, node.x1) for node in nodes], features

    def get_labels(self, gt_tables):
        """
        :param gt_tables: dict, keys are page number and values are list of tables bbox within that page
        :return:
        """
        labels = np.zeros(len(self.candidates))
        for i, candidate in enumerate(self.candidates):
            page_num = candidate[0]
            try:
                tables = gt_tables[page_num]
                for gt_table in tables:
                    page_width, page_height, y0, x0, y1, x1 = gt_table
                    w_ratio = float(candidate[1]) / page_width
                    h_ratio = float(candidate[2]) / page_height
                    rescaled_gt_table = (y0 * h_ratio, x0 * w_ratio, y1 * h_ratio, x1 * w_ratio)
                    iou = compute_iou(candidate[-4:], rescaled_gt_table)
                    if iou > self.iou_thresh:
                        # candidate region is a table
                        labels[i] = 1
            except KeyError:
                # any of the candidates is a true table, all zero labels
                pass
        return labels

    def display_bounding_boxes(self, page_num, bboxes, alternate_colors=True):
        elems = self.elems[page_num]
        page_width, page_height = int(elems.layout.width), int(elems.layout.height)
        img = pdf_to_img(self.pdf_file, page_num, page_width, page_height)
        draw = Drawing()
        draw.fill_color = Color('rgba(0, 0, 0, 0)')
        color=Color('blue')
        draw.stroke_color = color
        for block in bboxes:
            top, left, bottom, right = block[-4:]
            draw.stroke_color = Color('rgba({},{},{}, 1)'.format(
                    str(np.random.randint(255)), str(np.random.randint(255)), str(np.random.randint(255))))
            draw.rectangle(left=float(left), top=float(top), right=float(right), bottom=float(bottom))
        draw(img)
        return img
