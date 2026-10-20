"""Robot-only forward kinematics against the pinned manufacturer model."""

import numpy as np

from cap_harness.robosuite.so101_model import build_so101_scene, load_so101_description


class RobotKinematics:
    def __init__(self):
        import mujoco

        self.mujoco = mujoco
        description = load_so101_description()
        self.model = build_so101_scene(description).compile()
        self.data = mujoco.MjData(self.model)
        self.joints = [self.model.joint(name).id for name in description.scene_joint_names]
        self.addresses = self.model.jnt_qposadr[self.joints]
        actuators = [self.model.actuator(name).id for name in description.scene_joint_names]
        self.low, self.high = self.model.actuator_ctrlrange[actuators].T.copy()
        self.site = self.model.site("so101_gripperframe").id
        self.commit = description.commit

    def forward(self, joints, opening=1.0):
        joints = np.asarray(joints, dtype=float)
        if joints.shape != (5,) or not np.isfinite(joints).all():
            raise ValueError("Forward kinematics requires five finite joint positions")
        if (
            isinstance(opening, (bool, np.bool_))
            or np.ndim(opening) != 0
            or not np.isfinite(opening)
            or not 0 <= opening <= 1
        ):
            raise ValueError("Opening must be a finite scalar between zero and one")
        self.data.qpos[self.addresses] = np.append(
            joints, self.low[5] + opening * (self.high[5] - self.low[5])
        )
        self.mujoco.mj_forward(self.model, self.data)
        return self.data.site_xpos[self.site].copy(), self.data.site_xmat[self.site].reshape(
            3, 3
        ).copy()
