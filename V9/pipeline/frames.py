"""Reads a clip from disk as it is needed, so only the frames in use are ever in memory.
A 1080p frame is about 6 MB, so holding a whole clip took gigabytes; this keeps a run in a few hundred MB.
Frame numbers are 0-based, counted in decode order, exactly as reading the whole clip would number them."""
import cv2


def resize(frame, width):
    """None keeps the clip's own size; a frame narrower than width is never enlarged."""
    h, w = frame.shape[:2]
    if width and w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    return frame


class Clip:
    def __init__(self, path, width=None):
        self.path, self.width, self._count = path, width, None

    def __len__(self):
        """The number of frames, counted by decoding, because the container's own count can be wrong."""
        if self._count is None:
            cap, count = cv2.VideoCapture(self.path), 0
            while cap.grab():
                count += 1
            cap.release()
            if not count:
                raise ValueError("could not read any frames from the clip")
            self._count = count
        return self._count

    def frames(self, wanted):
        """Yields (index, frame) for each wanted index, in time order, one frame at a time."""
        wanted = set(wanted)
        if not wanted:
            return
        last, cap, index = max(wanted), cv2.VideoCapture(self.path), 0
        try:
            while index <= last:
                if index in wanted:
                    ok, f = cap.read()
                    if not ok:
                        break
                    yield index, resize(f, self.width)
                elif not cap.grab():   # skipped frames are decoded but never converted or kept
                    break
                index += 1
        finally:
            cap.release()

    def read(self, wanted):
        """{index: frame} for a few frames, such as the ones around each key moment."""
        return dict(self.frames(wanted))


def frames_at(source, idxs):
    """(index, frame) pairs from a Clip, or from a plain list of frames (used by the tests)."""
    if isinstance(source, Clip):
        return source.frames(idxs)
    return ((k, source[k]) for k in idxs)
