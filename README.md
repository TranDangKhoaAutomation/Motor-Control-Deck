# TranDangKhoaAutomation Control Deck

Project này là một bộ điều khiển hoàn chỉnh cho hệ truyền động 4 động cơ, gồm:
- app desktop điều khiển và giám sát
- firmware `STM32F103C8T6` chạy USB CDC bridge
- bộ source logic đã tách riêng để port sang `STM32F407VGT6`

Mục tiêu của project:
- điều khiển chuyển động base 4 bánh từ máy tính qua USB CDC
- test riêng từng động cơ qua STM32
- test trực tiếp UART driver mà không cần đi qua STM32
- theo dõi frame gửi đi, phản hồi nhận về và gói UART 3 byte thực tế của từng motor

**Project Làm Được Gì**
- Điều khiển base với các hướng: `STOP`, `FWD`, `BACK`, `LEFT`, `RIGHT`
- Hỗ trợ đi chéo bằng tổ hợp phím giữ cùng lúc:
  - `W + A` -> `FWD_LEFT`
  - `W + D` -> `FWD_RIGHT`
  - `S + A` -> `BACK_LEFT`
  - `S + D` -> `BACK_RIGHT`
- Gửi lệnh test trực tiếp 4 motor qua STM32 bằng frame `MOTOR,...`
- Gửi trực tiếp gói UART 3 byte ra driver bằng một cổng COM riêng
- Hiển thị phản hồi `ACK`, `ERR`, `EVENT,TIMEOUT`, `EVENT,LINK_OK`, `TRACE,UART`
- Tự cập nhật danh sách COM
- Tự kết nối lại khi rút cáp rồi cắm lại đúng COM cũ
- Hiển thị mô tả cổng COM kèm tên thiết bị và `VID:PID`

**Cấu Trúc Thư Mục**
- [APP](APP): app desktop Python
- [STM32F103C8T6](STM32F103C8T6): project firmware chính đang dùng
- [STM32F407VGT6](STM32F407VGT6): bộ source logic để port sang project F407

**App Desktop**
File chính là [app.py](APP/app.py).

App dùng:
- `Python`
- `customtkinter`
- `pyserial`
- `Pillow`

Chức năng trên giao diện:
- `Base Control`
  - điều khiển hướng base bằng nút hoặc bàn phím
  - gửi frame `BASE,<lệnh>,<tốc_độ>,<khóa_bánh>`
  - giữ phím hoặc giữ nút thì app stream lệnh mỗi `20 ms`
  - nhả ra thì gửi `STOP`
- `STM32 Bridge`
  - chỉnh riêng hướng và tốc độ của 4 motor
  - gửi frame `MOTOR,<dir1>,<speed1>,...,<dir4>,<speed4>`
  - xem ngay `Last TX`, `Last RX`, `Bridge Feedback`, `TRACE,UART`
- `Direct UART`
  - dùng một COM riêng, không đi qua STM32
  - tự tạo gói nhị phân 3 byte để gửi thẳng vào driver
  - có `Send Once`, `Start Continuous`, `Send For N Seconds`, `Stop`
  - hiển thị `TX frame`, `Latest RX`, bộ đếm số lần gửi, thời gian chạy

Chạy app:
```powershell
python APP\app.py
```

**Firmware STM32F103C8T6**
Project chính nằm tại [STM32F103C8T6](STM32F103C8T6).

Các file quan trọng:
- [main.c](STM32F103C8T6/Core/Src/main.c)
- [usb_command_bridge.c](STM32F103C8T6/Core/Src/usb_command_bridge.c)
- [robot_motion.c](STM32F103C8T6/Core/Src/robot_motion.c)
- [STM32F103C8T6.ioc](STM32F103C8T6/STM32F103C8T6.ioc)
- [STM32F103C8T6.uvprojx](STM32F103C8T6/MDK-ARM/STM32F103C8T6.uvprojx)

Firmware đảm nhiệm:
- nhận lệnh ASCII từ USB CDC
- parse lệnh `STOP`, `BASE,...`, `MOTOR,...`
- duy trì control tick `20 ms`
- giám sát timeout đường truyền
- chuyển lệnh thành 4 gói UART 3 byte để phát ra 4 driver địa chỉ `1..4`
- phản hồi telemetry ngược về app qua USB CDC

Thông số mặc định hiện tại:
- UART driver mặc định: `115200`
- chu kỳ điều khiển: `20 ms`
- timeout mất link: `250 ms`

**Bộ Source STM32F407VGT6**
Thư mục [STM32F407VGT6](STM32F407VGT6) không phải full project CubeMX hoàn chỉnh.

Nó là bộ source logic đã tách sẵn gồm:
- [usb_command_bridge.c](STM32F407VGT6/Core/Src/usb_command_bridge.c)
- [robot_motion.c](STM32F407VGT6/Core/Src/robot_motion.c)
- [usbd_cdc_if.c](STM32F407VGT6/USB_DEVICE/App/usbd_cdc_if.c)

Dùng khi bạn muốn port logic hiện tại sang board `STM32F407VGT6` của riêng bạn.

Bạn vẫn cần tự tạo bằng CubeMX:
- `main.c`, `main.h`
- cấu hình clock
- USB FS
- timer tick `20 ms`
- UART phát sang driver
- chân I/O đúng theo phần cứng thực tế

**Giao Thức App <-> STM32**
Lệnh base mới:
```text
BASE,<cmd>,<speed>,<lock>
```

Ví dụ:
```text
BASE,FWD,120,0
BASE,FWD_LEFT,80,0
BASE,STOP,0,1
STOP
```

Lệnh motor trực tiếp qua STM32:
```text
MOTOR,<dir1>,<speed1>,<dir2>,<speed2>,<dir3>,<speed3>,<dir4>,<speed4>
```

Ví dụ:
```text
MOTOR,0,120,1,80,0,0,1,200
```

Firmware vẫn giữ tương thích với frame base cũ:
```text
BASE,<cmd>,<speed1>,<speed2>,<fast>,<lock>
```

Phản hồi từ STM32:
```text
ACK,STOP
ACK,BASE,FWD,120,0
ACK,MOTOR,0,120,1,80,0,0,1,200
ERR,PARSE,...
ERR,MOTOR_FIELDS
EVENT,TIMEOUT
EVENT,LINK_OK
TRACE,UART,01-64-FF,82-32-FF,03-00-FF,84-C8-FF
```

**Giao Thức Direct UART Driver**
Tab `Direct UART` không đi qua STM32. App gửi trực tiếp 3 byte:

```text
byte1 = ((dir & 1) << 7) | (address & 0x7F)
byte2 = speed
byte3 = 0xFF
```

Ý nghĩa:
- `address`: địa chỉ driver `1..127`
- `speed`: tốc độ `0..255`
- `dir`: bit chiều quay
- `byte3`: byte kết thúc cố định

Ví dụ:
- `address = 1`, `dir = 1`, `speed = 150`
- frame hex sẽ là `81 96 FF`

**Luồng Hoạt Động Tổng**
1. App chọn một COM STM32 để điều khiển qua USB CDC.
2. App gửi `BASE,...` hoặc `MOTOR,...` xuống STM32.
3. STM32 parse lệnh, cập nhật trạng thái điều khiển.
4. STM32 phát 4 gói UART 3 byte sang 4 driver.
5. STM32 gửi ngược `ACK/ERR/EVENT/TRACE` để app hiển thị.
6. Nếu muốn test bỏ qua STM32, tab `Direct UART` sẽ dùng một COM UART riêng để phát thẳng 3 byte vào driver.

**Những Điểm Đáng Chú Ý**
- Base hiện dùng mô hình `1 tốc độ`, không còn kiểu `2 speed` trên giao diện mới.
- Lệnh đi chéo đã được xử lý cả ở app và firmware.
- UI chia riêng COM của `STM32` và COM của `Direct UART`, không dùng lẫn nhau.
- Khi mất kết nối, firmware tự về trạng thái an toàn theo logic timeout.
- App log đủ để đối chiếu giữa frame app gửi và gói UART STM32 thực sự phát ra.

**Gợi Ý Sử Dụng**
- Dùng `Base Control` khi muốn lái tổng thể robot.
- Dùng `STM32 Bridge` khi muốn debug từng motor nhưng vẫn muốn STM32 đứng giữa để xem `TRACE,UART`.
- Dùng `Direct UART` khi muốn test driver hoặc motor riêng lẻ mà không phụ thuộc firmware bridge.

**Ghi Chú**
- Project hiện tối ưu theo luồng test và điều khiển 4 driver UART.
- Nếu phần cứng driver thực tế dùng baud khác `115200`, cần đổi lại cả phía app và firmware trước khi test.
- Sau khi đổi file trong project Keil, nếu IDE đang mở sẵn project thì nên đóng và mở lại để cây file cập nhật đúng.
