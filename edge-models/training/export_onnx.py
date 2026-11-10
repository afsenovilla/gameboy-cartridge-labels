# The trained models (models/<shape>-<0 recess, 1 label>.pt) exported to ../<shape>-<part>.onnx for src/edge_fit.py,
# each checked against PyTorch on random strips (run 2026-11-10: largest difference 1.1e-5).
import os, numpy as np, onnxruntime, torch
import train

HERE = os.path.dirname(os.path.abspath(__file__))
for shape in ("dmg", "cgb", "agb"):
    for p, part in ((0, "recess"), (1, "label")):
        m = train.Heatmap(6)
        m.load_state_dict(torch.load(os.path.join(HERE, "models", f"{shape}-{p}.pt"), map_location="cpu"))
        m.eval()
        w, c = torch.rand(4, 3, 201), torch.zeros(4, 6)
        c[:, p] = 1
        c[:, 2] = 1
        out = os.path.join(HERE, "..", f"{shape}-{part}.onnx")
        torch.onnx.export(m, (w, c), out, input_names=["strips", "condition"], output_names=["logits"],
                          dynamic_axes={"strips": {0: "n", 2: "samples"}, "condition": {0: "n"}, "logits": {0: "n", 1: "samples"}},
                          dynamo=False, opset_version=17)
        w2, c2 = torch.rand(7, 3, 201), torch.zeros(7, 6)
        c2[:, p] = 1
        c2[:, 3] = 1
        a = m(w2, c2).detach().numpy()
        b = onnxruntime.InferenceSession(out).run(None, {"strips": w2.numpy(), "condition": c2.numpy()})[0]
        print(shape, part, "largest difference", float(np.abs(a - b).max()))
