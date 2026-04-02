# STM32F407VGT6

Bộ thư mục này chứa phần logic điều khiển đã được tách riêng cho `STM32F407VGT6`.

Những file đã có sẵn:
- `Core/Inc/usb_command_bridge.h`
- `Core/Inc/robot_motion.h`
- `Core/Src/usb_command_bridge.c`
- `Core/Src/robot_motion.c`
- `USB_DEVICE/App/usbd_cdc_if.h`
- `USB_DEVICE/App/usbd_cdc_if.c`

Mục đích:
- dùng lại toàn bộ logic USB CDC bridge, base control, motor bridge và direct UART packet như bản `STM32F103C8T6`
- tách riêng khỏi project F103 để bạn port sang project CubeMX của `STM32F407VGT6`

Những phần bạn vẫn cần tạo bằng CubeMX cho F407:
- `main.c`
- `main.h`
- `usb_device.c/.h`
- `usbd_desc.c/.h`
- `usbd_conf.c`
- clock tree
- chân USB FS
- timer tick 20 ms
- UART dùng để phát 3 byte sang driver

Yêu cầu khi tích hợp:
1. Trong `main.c`, gọi `MX_USB_DEVICE_Init();`
2. Trong `main.c`, sau khi init ngoại vi xong, gọi `DeRobotDieuKhien_Init();`
3. Trong vòng lặp `while(1)`, gọi `DeRobotDieuKhien_Task();`
4. Trong callback timer 20 ms, gọi `DeRobotDieuKhien_Tick20ms();`
5. Nếu bạn không dùng `huart2` làm UART ra driver, hãy định nghĩa lại `PID_UART_HANDLE` trước khi include `robot_motion.h`
6. Nếu bạn không dùng `htim1` làm timer 20 ms, hãy định nghĩa lại `BASE_TICK_TIM` trước khi include `usb_command_bridge.h`

Gợi ý cấu hình:
- USB CDC FS
- UART driver baud mặc định: `115200`
- timer control tick: `20 ms`

Lưu ý:
- Bộ mã này là phần logic đã port sẵn, không phải full project CubeMX hoàn chỉnh cho `STM32F407VGT6`
- Lý do là F407 còn phụ thuộc chính xác vào sơ đồ chân, clock và cách bạn cấu hình USB/UART trên phần cứng thực tế
