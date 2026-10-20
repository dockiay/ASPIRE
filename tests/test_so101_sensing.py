"""Exercise the task-independent sensor against actual MuJoCo contact forces."""

from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.so101.sensing import read_finger_contacts


@pytest.mark.parametrize("inside_region", [True, False])
def test_virtual_contacts_use_native_wrenches_and_tool_local_positions(inside_region):
    mujoco = pytest.importorskip("mujoco")
    # This miniature engineering fixture has two collision meshes and a sphere.
    # It tests the sensor reader; it is not a robot or grasp benchmark.
    vertices = " ".join(
        f"{x} {y} {z}" for x in (-0.005, 0.005) for y in (-0.01, 0.01) for z in (-0.01, 0.01)
    )
    sensor_y = 0 if inside_region else 0.2
    model = mujoco.MjModel.from_xml_string(f"""
    <mujoco>
      <option gravity="0 0 0" timestep="0.002"/>
      <asset>
        <mesh name="so101_wrist_roll_follower_so101_v1" vertex="{vertices}"/>
        <mesh name="so101_moving_jaw_so101_v1" vertex="{vertices}"/>
      </asset>
      <worldbody>
        <site name="so101_gripperframe" pos="0 {sensor_y} 0"/>
        <geom type="mesh" mesh="so101_wrist_roll_follower_so101_v1" pos="-0.015 0 0"/>
        <geom type="mesh" mesh="so101_moving_jaw_so101_v1" pos="0.015 0 0"/>
        <body>
          <freejoint/>
          <geom type="sphere" size="0.012" mass="0.1"/>
        </body>
      </worldbody>
    </mujoco>
    """)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert data.ncon >= 2
    native_forces = []
    for index in range(data.ncon):
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, force)
        native_forces.append(force[0])
    assert max(native_forces) > 0
    site = model.site("so101_gripperframe").id
    public_data = SimpleNamespace(
        contact=data.contact,
        time=data.time,
        get_site_xpos=lambda _name: data.site_xpos[site],
        get_site_xmat=lambda _name: data.site_xmat[site].reshape(3, 3),
        _data=data,
    )
    env = SimpleNamespace(model=model, sim=SimpleNamespace(data=public_data))
    sample = read_finger_contacts(env)
    assert sample["timestamp_s"] == data.time
    for side in ("fixed", "moving"):
        assert bool(sample[side]["contact_count"]) is inside_region
        assert (sample[side]["normal_force_n"] > 0) is inside_region
        for contact in sample[side]["contacts"]:
            assert set(contact) == {"normal_force_n", "local_position_m"}
            assert len(contact["local_position_m"]) == 3
