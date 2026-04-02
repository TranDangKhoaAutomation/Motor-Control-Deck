# STM32F103C8T6

Thư mục này là project hiện tại dành cho `STM32F103C8T6`.

Điểm chính:
- USB CDC bridge điều khiển từ app desktop
- base control dùng 1 tốc độ
- hỗ trợ lệnh tiến, lùi, trái, phải và 4 hướng chéo
- bridge gửi gói UART 3 byte cho 4 driver
- có phản hồi `ACK`, `ERR`, `EVENT`, `TRACE,UART`

Vị trí source chính:
- `Core/Src/usb_command_bridge.c`
- `Core/Src/robot_motion.c`
- `Core/Src/main.c`
- `USB_DEVICE/App/usbd_cdc_if.c`

File cấu hình CubeMX:
- `STM32F103C8T6.ioc`
