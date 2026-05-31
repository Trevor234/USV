import sys, math
sys.path.insert(0, "/home/sgh/MPC/ros/usv_mpc_ws/src/usv_planning/usv_planning")
from dubins_path import plan_dubins

DEMO_WAYPOINTS = [
    {"x": 0.0, "y": 0.0, "heading_deg": 0.0},
    {"x": 20.0, "y": 0.0, "heading_deg": 45.0},
    {"x": 40.0, "y": 20.0, "heading_deg": 90.0},
    {"x": 40.0, "y": 40.0, "heading_deg": 135.0},
    {"x": 20.0, "y": 40.0, "heading_deg": 180.0},
    {"x": 0.0, "y": 40.0, "heading_deg": 225.0},
    {"x": 0.0, "y": 0.0, "heading_deg": 270.0},
]
TURN_RADIUS = 5.0
PATH_RESOLUTION = 0.5

all_points = []
wps = [{"x": w["x"], "y": w["y"], "heading": math.radians(w["heading_deg"])} for w in DEMO_WAYPOINTS]

for i in range(len(wps) - 1):
    start = (wps[i]["x"], wps[i]["y"], wps[i]["heading"])
    end = (wps[i+1]["x"], wps[i+1]["y"], wps[i+1]["heading"])
    used = False
    if wps[i]["heading"] != 0.0 or wps[i+1]["heading"] != 0.0:
        dp = plan_dubins(start, end, TURN_RADIUS)
        if dp is not None and dp.total_length < 500:
            s = dp.sample(start[0], start[1], start[2], TURN_RADIUS, PATH_RESOLUTION)
            if i > 0:
                s = s[1:]
            all_points.extend(s)
            used = True
            print("Seg %d->%d: Dubins %s, L=%.2f, n=%d" % (i, i+1, dp.type, dp.total_length, len(s)))
    if not used:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        seg_len = math.hypot(dx, dy)
        n_pts = max(2, int(seg_len / PATH_RESOLUTION))
        heading = math.atan2(dy, dx)
        for j in range(n_pts):
            if i == 0 or j > 0:
                t = j / (n_pts - 1) if n_pts > 1 else 0
                all_points.append((start[0] + t*dx, start[1] + t*dy, heading))
        print("Seg %d->%d: LINEAR n=%d" % (i, i+1, n_pts))

usv_x, usv_y = 18.3, 33.5
xs = [p[0] for p in all_points]
ys = [p[1] for p in all_points]
nearest_idx = min(range(len(all_points)), key=lambda i: math.hypot(all_points[i][0]-usv_x, all_points[i][1]-usv_y))
nearest_dist = math.hypot(all_points[nearest_idx][0]-usv_x, all_points[nearest_idx][1]-usv_y)

print()
print("=" * 60)
print("Total path points: %d" % len(all_points))
print("Path X range: [%.2f, %.2f]" % (min(xs), max(xs)))
print("Path Y range: [%.2f, %.2f]" % (min(ys), max(ys)))
print("USV position: (%s, %s)" % (usv_x, usv_y))
print("Nearest path index: %d" % nearest_idx)
nx, ny, npsi = all_points[nearest_idx]
print("Nearest path point: x=%.3f, y=%.3f, psi=%.2f deg" % (nx, ny, math.degrees(npsi)))
print("Distance from USV: %.3f m" % nearest_dist)
print("Position from end: %d of %d" % (len(all_points)-1-nearest_idx, len(all_points)-1))
print()
print("10 points from nearest_idx=%d forward:" % nearest_idx)
for k in range(10):
    idx = nearest_idx + k
    if idx >= len(all_points):
        print("  idx=%d: <out of range>" % idx)
        break
    x, y, psi = all_points[idx]
    print("  idx=%d: x=%.3f, y=%.3f, psi_deg=%.2f" % (idx, x, y, math.degrees(psi)))
