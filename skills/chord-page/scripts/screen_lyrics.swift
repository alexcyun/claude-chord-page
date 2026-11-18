// Reads the text in video frames with macOS's own text recognition (Vision), for screen_lyrics.py: prints
// "file<TAB>y<TAB>text" for each line of text in each image, y being how far down the frame it sits (0 top, 1 bottom).
//   swiftc -O screen_lyrics.swift -o screen_lyrics && ./screen_lyrics frame1.jpg frame2.jpg …
import Foundation
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.usesLanguageCorrection = true
  req.recognitionLanguages = ["en-US"]
  try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
  let name = (path as NSString).lastPathComponent
  for o in (req.results ?? []).sorted(by: { $0.boundingBox.midY > $1.boundingBox.midY }) {
    if let t = o.topCandidates(1).first { print("\(name)\t\(String(format: "%.2f", 1 - o.boundingBox.midY))\t\(t.string)") }
  }
}
