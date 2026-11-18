# make_cartridge: a Game Boy cartridge 3D model (.3mf, as 3D printing sites offer them) to cartridge.json, the mesh
# build_site.py draws when someone views a label "on a cartridge". The model is in millimetres, 57 x 65 x 7.75, with the label
# side up (+z) and the connector end at y = 0.
#   python run.py py src/make_cartridge.py Game_Boy_Cartridge.3mf [cartridge.json]
# The mesh is not in this repository: check the model's licence before publishing a page that carries it.
import base64
import json
import re
import sys
import zipfile

import numpy as np

# The label's recess in that model (mm): x 6.5-50.5, y 8-47, 0.25 deep, floor at z = 7.5.
RECESS = {"x": [6.5, 50.5], "y": [8, 47], "z": 7.5}


def mesh(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".model"))
        xml = z.read(name).decode("utf-8")
    v = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', xml), float)
    t = np.array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', xml), int)
    return v, t


def pack(v, t):
    return {"size": [float(x) for x in v.max(0)], "recess": RECESS,
            "v": base64.b64encode(np.round(v * 100).astype("<i2").tobytes()).decode(),
            "t": base64.b64encode(t.astype("<u2").tobytes()).decode()}


def main(args):
    v, t = mesh(args[0])
    out = args[1] if len(args) > 1 else "cartridge.json"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pack(v, t), f, separators=(",", ":"))
    print(len(v), "vertices,", len(t), "triangles:", out)


if __name__ == "__main__":
    main(sys.argv[1:])
