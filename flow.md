# Các Luồng Hoạt Động - Fingerprint Jetson Nano Worker

Tài liệu này mô tả chi tiết 6 luồng hoạt động cốt lõi của ứng dụng `fingerprint-jetson-nano`.

## Luồng 1: Kết nối với Orchestrator (Khởi động)

Khi ứng dụng Worker trên Jetson Nano khởi động, nó sẽ tự động kết nối với máy chủ trung tâm (Orchestrator) thông qua giao thức MQTT để thông báo trạng thái hoạt động.

```mermaid
sequenceDiagram
    participant Worker as Jetson Worker (MQTT Client)
    participant MQTT as MQTT Broker
    participant Orch as Orchestrator

    Worker->>MQTT: Connect (thông tin đăng nhập & ClientID)
    MQTT-->>Worker: Xuất tín hiệu CONNACK (Thành công)
    Worker->>MQTT: Nhấn Subscribe các topic (đệnh lệnh từ Orch)
    Worker->>MQTT: Publish `worker/status` (Device Info, IP, Version)
    MQTT->>Orch: Forward `worker/status`
    Orch-->>MQTT: Ghi nhận Worker online

    loop Heartbeat
        Worker->>MQTT: PINGREQ / Nháy Publish trạng thái (mỗi 10-60 giây)
        MQTT-->>Worker: PINGRESP
    end
```

## Luồng 2: Kéo Model

Khi có bản cập nhật thuật toán nhận diện vân tay mới từ chuyên gia AI, Orchestrator sẽ ra lệnh cho Jetson tải model mới xuống, biên dịch thành TensorRT và khởi động lại luồng chạy.

```mermaid
sequenceDiagram
    participant Orch as Orchestrator
    participant MQTT as MQTT Broker
    participant API as Jetson (Manager)
    participant TRT as TensorRT Pipeline
    participant MinIO as Cổng Tải Model (MinIO/S3)

    Orch->>MQTT: Publish lệnh `worker/update_model` (kèm URL model ONNX)
    MQTT->>API: Forward tín hiệu đổi model
    API->>TRT: Tạm dừng tiến trình phân tích ảnh
    API->>MinIO: Tải file `.onnx` model AI mới nhất
    MinIO-->>API: Trả về file model
    Note over API, TRT: Compile model ONNX thành engine TensorRT<br>(Mất 1-3 phút tuỳ độ trễ GPU)
    API->>TRT: Reload engine AI mới
    API->>MQTT: Publish `worker/model_status` (Thành công)
    MQTT->>Orch: Nhận báo cáo thành công
```

## Luồng 3: Streaming (Hiển thị thời gian thực)

Ngay khi màn hình cảm ứng (hoặc GUI) được bật lên, kỹ thuật Streaming qua WebSocket được áp dụng để duy trì độ trễ khung hình của vân tay cực thấp (< 50ms) cho người dùng nhìn thấy.

```mermaid
sequenceDiagram
    participant Sensor as USB Fingerprint Sensor
    participant Worker as Jetson API
    participant GUI as Giao diện Màn Hình

    GUI->>Worker: Mở kết nối `ws://.../ws/verification` (WebSocket)
    Worker-->>GUI: Chấp nhận kết nối

    loop Stream mỗi 30-50ms (FPS)
        Sensor->>Worker: Quét cảm ứng, gửi ảnh thô (RAW)
        Note over Worker: Chuyển mảng Bytes thành JPEG / Base64.
        Worker->>GUI: Bắn dữ liệu `capture_preview` kèm chuỗi Base64
        GUI-->>GUI: Render ảnh vân tay lên UI mượt mà
    end
```

## Luồng 4: User Register (Đăng ký vân tay)

Luồng đăng ký người dùng mới tại trực tiếp máy Jetson Nano khi _có mạng_. Khi người dùng đăng ký xong trên máy, dữ liệu sẽ ghim thẳng sang Server qua MQTT.

```mermaid
sequenceDiagram
    participant User as Người dùng
    participant Sensor as Cảm biến & GUI
    participant API as Jetson AI Pipeline
    participant DB as Local Database
    participant Orch as Orchestrator

    User->>Sensor: Chạm ngón tay (3-5 lần để quét đủ góc)
    Sensor->>API: Gửi hình ảnh
    Note over API: Đẩy vào TensorRT rút gọn thành Vector 256 chiều
    API->>DB: Lưu UserID + Vector nhúng + Metadata
    DB-->>API: Confirm thành công
    API->>Sensor: Báo UI đăng ký thành công
    API->>Orch: Publish event `user/enrolled` kèm UserID & Vector qua MQTT
    Note over Orch: Đồng bộ Vector vào bộ nhớ trung tâm
```

## Luồng 5: User Register Trong Lúc Mất Kết Nối (Offline Mode)

Điểm mạnh của Edge AI: Nếu Jetson Nano đứt mạng (ví dụ: đứt cáp Internet), người dùng vẫn có thể đăng ký bình thường. Máy sẽ tạo cờ chờ (Queue).

```mermaid
sequenceDiagram
    participant User as Người dùng
    participant API as Jetson AI Pipeline
    participant DB as Local DB (SQLite)
    participant Sync as Background Sync Job
    participant Orch as Orchestrator

    Note over API, Orch: Đứt kết nối internet / MQTT

    User->>API: Chạm đăng ký vân tay mới qua Giao diện
    Note over API: Vẫn đưa hình qua TensorRT để lấy Vector
    API->>DB: Lưu Vector + Đánh dấu `is_synced = False`
    API-->>User: Đăng ký cục bộ thành công!

    Note over Sync: Máy sẽ chờ mạng định kỳ

    Note over Sync, Orch: ... Một lúc sau, có Internet ...
    Sync->>Orch: Quét DB: Gửi toàn bộ Vector có cờ `is_synced = False`
    Orch-->>Sync: Xác nhận nạp thành công
    Sync->>DB: Đổi dấu DB `is_synced = True`
```

## Luồng 6: User Verify (Xác thực 1:N)

Khi người dùng bình thường đập thẳng ngón tay vào để cửa mở / ra vào chấm công. Tốc độ đòi hỏi trên Edge phải siêu nhanh (dưới 0.2s).

```mermaid
sequenceDiagram
    participant User as Người dùng
    participant API as Jetson AI Pipeline
    participant DB as FAISS Local (Vector Search)
    participant GUI as Giao diện
    participant Orch as Orchestrator

    User->>API: Bấm chạm vân tay một chạm
    Note over API: TensorRT Engine tính ra đường nhúng Vector

    API->>DB: Tìm người giống nhất (KNN - L2 / Cosine Similarity)
    Note over DB: Quét tất cả vector đang lưu trữ ngầm tại máy Edge.
    DB-->>API: Trả về [UserID, Score = 96%]

    alt Score > Ngưỡng Threshold (vd > 0.55)
        API->>GUI: Phát âm báo "Hợp lệ" / Kích hoạt Rele (Mở cửa)
        API->>Orch: Bắn MQTT lệnh check-in: `{userID, timestamp, status: success}`
    else Score <= Ngưỡng
        API->>GUI: Hiện "Không nhận diện được"
        API->>Orch: Báo alert an ninh (Tùy chọn) qua MQTT
    end
```
