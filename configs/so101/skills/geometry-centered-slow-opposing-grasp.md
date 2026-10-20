# Two-view fruit localization with asymmetric geometry-centered supervised closure

Verification contract: grasp_ripe_fruit_v1

Trigger: Synthetic SO101 ripe fruit visible unambiguously in both calibrated cameras, radial horizontal approach reachable, goal grasp_ripe_fruit_v1. Proposed only; no independent verification.

```python
# Inputs: injected public segment_text, mask_to_point_cloud, so101 geometry/contact/gripper APIs, get_robot_state, solve_ik, move_to_joints, step, Pose, RobotAction and ArmCommand. No external coordinates. Full measured candidate below. 2px erosion and 5% trim suppress boundary depth/outliers; 20-point minimum, .03 ranking gap, .10m span and .04m view gates reject uncertainty. Horizontal radial orientation uses tool X forward and roll -pi/2. Geometry at opening .3 is the tested centering hypothesis, not symmetric TCP. .06/.03m approach stages limit final travel. Closure .25 normalized/s needs at least 4s from fully open; 5s allows settling. 8N stop bounds force below the 12N exercise limit with measured overshoot; 12 hold steps at 20Hz exceed .5s. Paths have no obstacle certificate; typed IK/motion errors abort. Final localization self-report is stale and must not be used as read-only localization evidence. Qualification requires registered physical predicate, not closure alone.
import math
centers = []
for camera in ['agentview', 'sideview']:
    detection = segment_text(camera, 'ripe strawberry')
    if not detection.ok or len(detection.segmentations) == 0:
        raise ValueError('Missing SAM3 detection')
    ranked = sorted(detection.segmentations, key=lambda item: item.score, reverse=True)
    print('scores', camera, [item.score for item in ranked])
    if len(ranked)>1 and ranked[0].score-ranked[1].score<0.03:
        raise ValueError('Ambiguous semantic ranking')
    cloud = mask_to_point_cloud(ranked[0].mask, camera, target_frame='so101_base', erosion_pixels=2)
    points = cloud.points.tolist()
    if len(points)<20:
        raise ValueError('Insufficient depth')
    center=[]
    spans=[]
    for axis in range(3):
        values=sorted([p[axis] for p in points])
        lo=values[int(0.05*(len(values)-1))]
        hi=values[int(0.95*(len(values)-1))]
        center.append((lo+hi)/2)
        spans.append(hi-lo)
    print('surface',camera,len(points),center,spans)
    if max(spans)>0.10:
        raise ValueError('Depth dispersion')
    centers.append(center)
if sum([(centers[0][i]-centers[1][i])**2 for i in range(3)])>0.04**2:
    raise ValueError('View disagreement')
point=[(centers[0][i]+centers[1][i])/2 for i in range(3)]
print('target',point)
geometry=so101.get_gripper_geometry(0.3)
print('geometry',geometry)
state=get_robot_state()
yaw=math.atan2(point[1],point[0])
q=[math.cos(yaw/2)*math.cos(-math.pi/4),math.cos(yaw/2)*math.sin(-math.pi/4),math.sin(yaw/2)*math.sin(-math.pi/4),math.sin(yaw/2)*math.cos(-math.pi/4)]
def rotate(v):
    u=q[1:]
    uv=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    uuv=[u[1]*uv[2]-u[2]*uv[1],u[2]*uv[0]-u[0]*uv[2],u[0]*uv[1]-u[1]*uv[0]]
    return [v[i]+2*q[0]*uv[i]+2*uuv[i] for i in range(3)]
offset=rotate(geometry['grasp_center_in_tcp_m'])
target=[point[i]-offset[i] for i in range(3)]
forward=rotate([1,0,0])
for distance in [0.06,0.03,0.0]:
    pose=Pose([target[i]-distance*forward[i] for i in range(3)],q,frame='so101_base')
    ik=solve_ik(pose,seed_joints=get_robot_state().joint_positions['primary'])
    print('ik',distance,ik)
    if not ik.ok:
        raise ValueError('Typed IK failure: '+str(ik.error))
    motion=move_to_joints(ik.joint_positions,max_steps=100)
    print('motion',motion.ok)
    if not motion.ok:
        raise ValueError('Approach failed')
grip=so101.command_gripper(0.0,duration_s=5.0,speed=0.25,force_limit_n=8.0,stop_on_contact=False)
print('closure',grip.ok,grip.diagnostics)
if not grip.ok:
    raise ValueError('Gripper failure')
joints=get_robot_state().joint_positions['primary']
opening=get_robot_state().gripper_positions['primary']
for tick in range(12):
    motion=step(RobotAction({'primary':ArmCommand('joint_position',joints,gripper_position=opening,embodiment='so101')}))
    if not motion.ok or motion.truncated:
        raise ValueError('Hold failed')
print('contacts',so101.get_finger_contacts())
result={'skill_results':{'localize_ripe_fruit_v1':{'point_m':point,'frame':'so101_base','timestamp_s':0.0,'camera_names':['agentview','sideview']}}}

```

Evidence: c-8ca0a3467a7570ec inspected results and both cameras for both cases show program_ok 2/2 and grasp_ripe_fruit_v1 2/2. Grasp qualified 4.710/4.776s; peaks <=10.082N, maximum penetration <=.522mm; final opposing forces >=1.174N. Initial c-1fc7106687009d27 failed both due to 2.5s duration at .25 speed before contact; five-second duration fixed it without changing approach. Full harvest 0/2: fruit remains attached. Synthetic development evidence only; provenance PENDING, independent verification and reproduction required.
