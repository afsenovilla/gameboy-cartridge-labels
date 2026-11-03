import glob, json, os, platform, subprocess

# The text on photos, for add-photos and read-text: read() writes, per photo, every line of text found with its corners
# in the photo, into <out_dir>/<photo's stem>.json. Two engines give the same output:
# - "vision": macOS's Vision framework (src/ocr, compiled from src/ocr.swift). Only on macOS, and the better reader.
# - "rapidocr": RapidOCR (src/ocr_rapid.py), on every system.
# macOS uses Vision if it can; OCR_ENGINE=vision or rapidocr chooses. Files record their engine next to the photos'
# lines (<stem>.json is a plain list, as the fitter reads it; the engine that made a folder is in ENGINE_FILE).
OCR = "src/ocr"
ENGINE_FILE = "engine.txt"


def engine():
    chosen = os.environ.get("OCR_ENGINE")
    if chosen:
        return chosen
    return "vision" if platform.system() == "Darwin" else "rapidocr"


def code_paths():
    """The files whose change means the text has to be read again."""
    return ["src/ocr.swift"] if engine() == "vision" else ["src/ocr_rapid.py"]


def read(paths, out_dir, batch=20, workers=8):
    """Reads the text on the photos into <out_dir>/<photo's stem>.json."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, ENGINE_FILE), "w", encoding="utf-8", newline="\n") as f:
        f.write(engine() + "\n")
    if engine() == "vision":
        import concurrent.futures
        batches = [paths[i:i + batch] for i in range(0, len(paths), batch)]
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            for done, _ in enumerate(pool.map(lambda b: subprocess.run([OCR, out_dir] + b, check=True), batches), 1):
                print(f"read {min(done * batch, len(paths))} of {len(paths)}", flush=True)
        return
    import ocr_rapid
    for done, path in enumerate(paths, 1):
        lines = ocr_rapid.read_file(path)
        if lines is not None:  # as src/ocr: a photo that can't be read has no file
            with open(os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(lines, f, ensure_ascii=False)
        if done % 20 == 0 or done == len(paths):
            print(f"read {done} of {len(paths)}", flush=True)
