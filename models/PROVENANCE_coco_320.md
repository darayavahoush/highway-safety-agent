# yolov8n_coco_320.onnx

- Source weights: Ultralytics yolov8n.pt (stock COCO, 80 classes)
- Export: Ultralytics export(format="onnx", imgsz=320, opset=12, dynamic=False, simplify=True)
- Ultralytics 8.4.187; onnx 1.23.2; onnxslim 0.1.98
- Verified shapes: input [1, 3, 320, 320], output [1, 84, 2100]
- SHA-256: 2d4c483a11e10a8685ff65a126dd202da02674651d6a80a5e991288ae097f78c
- Not committed to git (binary). Regenerate with the export command above.
