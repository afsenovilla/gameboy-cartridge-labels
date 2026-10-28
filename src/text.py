import concurrent.futures, os, subprocess

# The text on photos, for add-photos and read-text: read() runs the text recognition (src/ocr, macOS's Vision
# framework) and writes, per photo, every line of text found with its corners in the photo.
OCR = "src/ocr"


def read(paths, out_dir, batch=20, workers=8):
    """Reads the text on the photos into <out_dir>/<photo's stem>.json, several batches at a time."""
    os.makedirs(out_dir, exist_ok=True)
    batches = [paths[i:i + batch] for i in range(0, len(paths), batch)]
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        for done, _ in enumerate(pool.map(lambda b: subprocess.run([OCR, out_dir] + b, check=True), batches), 1):
            print(f"read {min(done * batch, len(paths))} of {len(paths)}", flush=True)
