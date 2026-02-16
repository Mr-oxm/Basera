
import os
import glob
import math
from photo_editor.vector.svg import svg_d_to_path, import_svg_string
from photo_editor.vector.path import VectorPath, PathNode, HandleMode, SegmentType
from photo_editor.vector.geometry import Vec2

def check_path_quality(name: str, path: VectorPath):
    """Check a path for anomalies like spikes (huge distances) or NaNs."""
    print(f"Checking {name}...")
    
    node_count = 0
    max_dist = 0.0
    has_nan = False
    
    for sub in path.sub_paths:
        if not sub.nodes:
            continue
            
        points = []
        for i, node in enumerate(sub.nodes):
            node_count += 1
            pos = node.position
            if math.isnan(pos.x) or math.isnan(pos.y):
                has_nan = True
                print(f"  NAN detected at node {i}")
            
            points.append(pos)
            
            # Check handles safely
            if node.in_handle:
                if math.isnan(node.in_handle.x) or math.isnan(node.in_handle.y):
                    has_nan = True
                    print(f"  NAN in_handle at node {i}")
                
            if node.out_handle:
                if math.isnan(node.out_handle.x) or math.isnan(node.out_handle.y):
                    has_nan = True
                    print(f"  NAN out_handle at node {i}")

            # Check handle lengths if they exist
            if node.in_handle:
                d_in = (node.in_handle - pos).length()
                if d_in > 1000:
                    print(f"  Huge in_handle at node {i}: {d_in:.1f}")
            if node.out_handle:
                d_out = (node.out_handle - pos).length()
                if d_out > 1000:
                    print(f"  Huge out_handle at node {i}: {d_out:.1f}")

        # Check distances between sequential nodes
        for i in range(len(points) - 1):
            d = (points[i+1] - points[i]).length()
            if d > max_dist:
                max_dist = d
            if d > 2000:
                print(f"  Huge jump between {i} and {i+1}: {d:.1f}")
                
    print(f"  Nodes: {node_count}, Max Jump: {max_dist:.1f}, Has NaN: {has_nan}")

def test_specific_case():
    print("\n--- Testing Specific Sharp -> Smooth Case ---")
    # L followed by S. S should interpret prev control point as current point.
    d = "M 0 0 L 10 10 S 20 20 30 30"
    path = svg_d_to_path(d)
    
    if len(path.sub_paths[0].nodes) < 3:
        print("FAIL: Not enough nodes")
        return

    node1 = path.sub_paths[0].nodes[1] # At 10,10. End of L, Start of S.
    # Its out_handle is the first CP of the curve.
    out_handle = node1.out_handle
    dist = (out_handle - node1.position).length()
    
    print(f"Node 1 pos: {node1.position}")
    print(f"Node 1 out_handle: {out_handle}")
    print(f"Handle length: {dist}")
    
    if dist < 0.001:
        print("PASS: Handle length determines sharp start for S after L")
    else:
        print("FAIL: Spiky handle detected!")

def scan_files():
    svg_files = glob.glob("e:/OXM/Projects/PhotoEditor/svgs/*.svg")
    print(f"\nScanning {len(svg_files)} SVG files...")
    
    for fpath in svg_files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            d_strs = re.findall(r' d="([^"]+)"', content)
            for i, d in enumerate(d_strs):
                if not d: continue
                path = svg_d_to_path(d)
                check_path_quality(f"{fname} path {i}", path)

        except Exception as e:
            print(f"Error checking {fname}: {e}")

if __name__ == "__main__":
    test_specific_case()
    scan_files()
