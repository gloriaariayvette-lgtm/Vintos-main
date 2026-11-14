"""Local AprilTag detection on each sampled frame: CPU only, no model, nothing kept.

Backend: pupil-apriltags (AprilRobotics C library) when installed; otherwise detection is reported as unavailable
and the stream runs without it. Pose needs the camera intrinsics (fx, fy, cx, cy in pixels) and the printed tag
size in metres; without them a detection carries pose None."""
import numpy as np

FAMILY = "tag36h11"


def gray(rgb):
    x = np.asarray(rgb, dtype=np.float32)
    return np.clip(x[..., 0] * .299 + x[..., 1] * .587 + x[..., 2] * .114, 0, 255).astype(np.uint8)


class TagDetector:
    def __init__(self, families=FAMILY, intrinsics=None, tag_size=None, backend=None, min_margin=20.):
        self.families, self.intrinsics, self.tag_size, self.min_margin = families, intrinsics, tag_size, float(min_margin)
        if intrinsics is not None and (len(intrinsics) != 4 or not tag_size or tag_size <= 0):
            raise ValueError("Pose needs fx, fy, cx, cy and a positive tag size")
        if backend is None:
            try:
                from pupil_apriltags import Detector
            except ImportError:
                self.backend = None
                return
            backend = Detector(families=families, nthreads=2, quad_decimate=1.0)
        self.backend = backend

    @property
    def available(self):
        return self.backend is not None

    def detect(self, rgb):
        if self.backend is None:
            return []
        pose = self.intrinsics is not None
        found = self.backend.detect(gray(rgb), estimate_tag_pose=pose, camera_params=self.intrinsics,
                                    tag_size=self.tag_size)
        out = []
        for d in found:
            if float(d.decision_margin) < self.min_margin or int(getattr(d, "hamming", 0)) > 0:
                continue   # weak or bit-corrected reads are not trusted to open a memory
            row = {"tag_id": int(d.tag_id), "family": str(d.tag_family.decode() if isinstance(d.tag_family, bytes) else d.tag_family),
                   "decision_margin": round(float(d.decision_margin), 2),
                   "center": [round(float(v), 1) for v in d.center],
                   "corners": [[round(float(v), 1) for v in c] for c in d.corners], "pose": None}
            if pose and getattr(d, "pose_t", None) is not None:
                row["pose"] = {"t_m": [round(float(v), 4) for v in np.asarray(d.pose_t).ravel()],
                               "R": [[round(float(v), 5) for v in r] for r in np.asarray(d.pose_R)],
                               "error": float(getattr(d, "pose_err", 0) or 0)}
            out.append(row)
        return out
