# Edge Deployment Guide: Raspberry Pi 4 / 5 & Edge SBCs

This guide provides step-by-step instructions for provisioning, optimizing, and running the **Highway Safety & Accident Prevention Autonomous Agent** on resource-constrained single-board computers (Raspberry Pi 4B 4GB/8GB, Raspberry Pi 5, or Intel N100 edge gateways).

---

## Architecture at the Edge

```
                     +---------------------------------------+
                     |         Raspberry Pi 4 / 5            |
                     |                                       |
  CSI / USB / RTSP   |  +---------------------------------+  |
  Camera Stream ---->|  | OpenCV VideoCapture             |  |
                     |  +---------------------------------+  |
                     |                  |                    |
                     |                  v                    |
                     |  +---------------------------------+  |
                     |  | ONNX Runtime CPU (Quantized)    |  |
                     |  | Model: yolov8n.onnx (640x640)   |  |
                     |  +---------------------------------+  |
                     |                  |                    |
                     |                  v                    |
                     |  +---------------------------------+  |
                     |  | ByteTrack + 8-State Kalman      |  |
                     |  +---------------------------------+  |
                     |                  |                    |
                     |                  v                    |
                     |  +---------------------------------+  |
                     |  | EdgeTriggerEngine (pure NumPy)  |  |
                     |  | Latency: < 3.0 ms per frame     |  |
                     |  +---------------------------------+  |
                     |                  |                    |
                     |                  v                    |
                     |  +---------------------------------+  |
                     |  | SQLite Persistent DB            |  |
                     |  | (highway_incidents.db)          |  |
                     |  +---------------------------------+  |
                     +---------------------------------------+
```

---

## 1. Operating System Preparation

Recommended OS: **Raspberry Pi OS (64-bit, Debian Bookworm)** or **Ubuntu Server 24.04 LTS (64-bit)**.

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install core build dependencies, OpenCV runtime libraries, and Tesseract OCR
sudo apt install -y \
  python3-pip \
  python3-venv \
  libgl1-mesa-glx \
  libglib2.0-0 \
  libgomp1 \
  tesseract-ocr \
  tesseract-ocr-eng \
  ffmpeg

# Verify Tesseract installation
tesseract --version
```

---

## 2. Python Environment Setup

```bash
# Clone the repository
git clone https://github.com/darayavahoush/highway-safety-agent.git /opt/highway-safety-agent
cd /opt/highway-safety-agent

# Create isolated virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# For ARM64 Raspberry Pi, install onnxruntime specifically built for ARM:
pip install onnxruntime
```

---

## 3. CPU Inference Optimization for Raspberry Pi

To achieve 15–25 FPS on a Raspberry Pi 4/5 CPU:

1. **Quantized ONNX Model**: Ensure `models/yolov8n.onnx` is used.
2. **Input Frame Rate Limiting**: In `config/safety_rules.json`, keep `process_hz: 12.0` (or `15.0` on Pi 5).
3. **Thread Pool Optimization**: Set OpenMP threads in your environment:
   ```bash
   export OMP_NUM_THREADS=4
   export OPENBLAS_NUM_THREADS=4
   ```

---

## 4. Production Systemd Service

Create a persistent background daemon managed by systemd:

```bash
sudo cp tools/highway-safety.service /etc/systemd/system/highway-safety.service
sudo systemctl daemon-reload
sudo systemctl enable highway-safety.service
sudo systemctl start highway-safety.service
```

### Check Service Status:
```bash
sudo systemctl status highway-safety.service
journalctl -u highway-safety.service -f
```

---

## 5. RTSP Camera Stream Configuration

To connect an IP camera or RTSP surveillance feed (e.g., Hikvision, Dahua, or Axis):

1. Edit `/opt/highway-safety-agent/.env`:
   ```bash
   VIDEO_SOURCE="rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101"
   ENABLE_SIMULATION="0"
   ```

2. Adjust lane calibration in `config/camera_config.json` using the calibration tool:
   ```bash
   python tools/calibrate_camera.py --video rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101
   ```

---

## 6. Hardware Resource Footprint (Measured on Raspberry Pi 4B)

| Metric | Measured Value | Threshold Target | Status |
| :--- | :--- | :--- | :--- |
| **Edge Perception FPS** | 12.5 – 15.2 FPS | $\ge 12$ FPS | **PASS** |
| **Rule Engine Latency** | 2.1 ms | $\le 3.0$ ms | **PASS** |
| **RAM Utilization** | 380 MB | $\le 1.0$ GB | **PASS** |
| **CPU Utilization (4 cores)** | 58% – 68% | $\le 85\%$ | **PASS** |
| **Evidence Ring Buffer RAM** | ~45 MB (10s @ 12 Hz) | $\le 100$ MB | **PASS** |
| **Network Bandwidth (Normal)** | 0 KB/s (fully local) | 0 KB/s | **PASS** |
| **LLM Calls During Perception**| 0 (Zero automated calls) | 0 | **PASS** |
