// Finds text in photos with macOS's Vision framework (on device, Japanese and English) and writes, per photo, a JSON list
// of {"text", "confidence", "quad"}: the line's corners in the photo's pixels, top left, top right, bottom right, bottom
// left (as the text reads, so they also give its turn). For finding a cartridge by its texts: the embossed "Nintendo
// GAME BOY" above the label, the serial and the strips' texts.
// Build: swiftc -O src/ocr.swift -o src/ocr (make does)
// Usage: ocr <out dir> <photo>...
import Foundation
import ImageIO
import Vision

let args = CommandLine.arguments
let outDir = args[1]
for path in args.dropFirst(2) {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { continue }
    // Phone photos are stored turned, with an EXIF orientation (as OpenCV reads them, turned upright): Vision is given
    // the orientation, and its points are then shares of the upright image.
    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    let raw = (properties?[kCGImagePropertyOrientation] as? UInt32) ?? 1
    let orientation = CGImagePropertyOrientation(rawValue: raw) ?? .up
    let sideways = [.left, .right, .leftMirrored, .rightMirrored].contains(orientation)
    let w = Double(sideways ? image.height : image.width), h = Double(sideways ? image.width : image.height)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["ja-JP", "en-US"]
    request.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: image, orientation: orientation).perform([request])
    var lines: [[String: Any]] = []
    for o in request.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        // Vision's points are shares of the image with y up.
        let quad = [o.topLeft, o.topRight, o.bottomRight, o.bottomLeft].map { [Double($0.x) * w, (1 - Double($0.y)) * h] }
        lines.append(["text": c.string, "confidence": Double(c.confidence), "quad": quad])
    }
    let name = url.deletingPathExtension().lastPathComponent
    let data = try! JSONSerialization.data(withJSONObject: lines, options: [.prettyPrinted])
    try! data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent(name + ".json"))
}
