# Read-only two-view SAM3 RGB-D ripe-fruit center estimation

Verification contract: localize_ripe_fruit_v1

Trigger: Registered localize_ripe_fruit_v1 synthetic SO-101 scenes with ripe fruit visible in both public calibrated cameras; reject ambiguous detections. Proposed, not independently verified.

```python
# Inputs: injected segment_text, mask_to_point_cloud, get_robot_state public APIs.
# agentview and sideview provide calibrated RGB-D; output frame is so101_base.
# No coordinates or pixel prompts are supplied. All centers derive at runtime.
# Two-pixel erosion suppresses boundary background; 5% trimming resists outliers.
# 20 points, .03 score gap, 10 cm span, 4 cm view difference are rejection gates.
# These gates do not guarantee accuracy or persistent object identity.
# Output result implements localize_ripe_fruit_v1; no motion calls occur.
# ValueError replaces the tested candidate's RuntimeError only on rejection paths.
centers = []
for camera in ['agentview', 'sideview']:
    detection = segment_text(camera, 'ripe strawberry')
    if not detection.ok or len(detection.segmentations) == 0:
        raise ValueError('Missing SAM3 detection')
    ranked = sorted(detection.segmentations, key=lambda item: item.score, reverse=True)
    print('scores', camera, [item.score for item in ranked])
    if len(ranked) > 1 and ranked[0].score - ranked[1].score < 0.03:
        raise ValueError('Ambiguous semantic ranking')
    cloud = mask_to_point_cloud(ranked[0].mask, camera, target_frame='so101_base', erosion_pixels=2)
    points = cloud.points.tolist()
    if len(points) < 20:
        raise ValueError('Insufficient depth support')
    center = []
    spans = []
    for axis in range(3):
        values = sorted([p[axis] for p in points])
        lo = values[int(0.05 * (len(values)-1))]
        hi = values[int(0.95 * (len(values)-1))]
        center.append((lo+hi)/2)
        spans.append(hi-lo)
    print('surface', camera, 'count', len(points), 'center', center, 'spans', spans)
    if max(spans) > 0.10:
        raise ValueError('Depth dispersion inconsistent with isolated fruit')
    centers.append(center)
if sum([(centers[0][i]-centers[1][i])**2 for i in range(3)]) > 0.04**2:
    raise ValueError('Inconsistent two-view localization')
point = [(centers[0][i]+centers[1][i])/2 for i in range(3)]
result = {'skill_results': {'localize_ripe_fruit_v1': {'point_m': point, 'frame': 'so101_base', 'timestamp_s': get_robot_state().timestamp_s, 'camera_names': ['agentview', 'sideview']}}}

```

Evidence: Inspected c-9afe5a6212e08183: program_ok 2/2, localization skill_success 2/2, zero control steps. Center errors 4.9077/5.1191 mm, timestamp error zero, displacement error .2940 mm. Both cameras viewed for both cases; 404–420 projected points/view, compact 10–35 mm spans. Complementary surface centers average successfully here. Full harvest unattempted; no independent verification, reserved evaluation or physical-camera validity established. Proposal's exception spelling change preserves rejection semantics but is not a separately measured candidate.
