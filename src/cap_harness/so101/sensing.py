"""Public virtual SO-101 fingertip readings, independent of task evaluators."""

from __future__ import annotations

import numpy as np


def finger_geom_ids(model) -> dict[str, int]:
    """Resolve the original colliding meshes, excluding visual duplicates and motors."""
    names = {"fixed": "so101_wrist_roll_follower_so101_v1", "moving": "so101_moving_jaw_so101_v1"}
    result = {}
    for side, name in names.items():
        matches = [
            index
            for index in range(model.ngeom)
            if model.geom_contype[index]
            and model.geom_dataid[index] >= 0
            and model.mesh(int(model.geom_dataid[index])).name == name
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one original collision mesh for the {side} finger")
        result[side] = matches[0]
    return result

def read_finger_contacts(env) -> dict:
    """Virtual fingertip sensors: report every contacted object, without task labels or scores.

    The stock robot has no such tactile sensors; these readings are simulation-only.
    Local positions use the manufacturer's gripperframe axes at each contact sample.
    """
    import mujoco

    fingers = finger_geom_ids(env.model)
    records = {side: [] for side in fingers}
    tcp = env.sim.data.get_site_xpos("so101_gripperframe")
    rotation = env.sim.data.get_site_xmat("so101_gripperframe")
    for index, contact in enumerate(env.sim.data.contact):
        if contact.dist > 0:
            continue
        pair = (int(contact.geom1), int(contact.geom2))
        local = (contact.pos - tcp) @ rotation
        if not fingertip_region(local):
            continue
        wrench = np.zeros(6)
        mujoco.mj_contactForce(env.model, env.sim.data._data, index, wrench)
        for side, geom in fingers.items():
            if geom in pair:
                records[side].append(
                    {
                        "normal_force_n": max(0.0, float(wrench[0])),
                        "local_position_m": local.tolist(),
                    }
                )
    return {
        "source": "virtual_simulation_sensors; not stock SO-101 hardware",
        "timestamp_s": float(env.sim.data.time),
        **{
            side: {
                "normal_force_n": sum(c["normal_force_n"] for c in contacts),
                "contact_count": len(contacts),
                "contacts": contacts,
            }
            for side, contacts in records.items()
        },
    }

def fingertip_region(local) -> bool:
    """Restrict qualifying contact to the distal 3 cm, rather than the palm or servo."""
    return bool(-0.03 <= local[0] <= 0.02 and abs(local[1]) <= 0.03 and -0.015 <= local[2] <= 0.06)
