# AutoClick Macro UI (bản dựng lại)

Thư mục hiện không có mã nguồn của ứng dụng cũ, nên `auto_click_ui.py` là giao diện thay thế đọc các macro JSON hiện có; nó không sửa `AutoClick_Macro_Pro.exe`.

## Chạy

1. Cài Python 3.10 trở lên.
2. Trong thư mục này, cài thư viện:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Mở giao diện:

   ```powershell
   python .\auto_click_ui.py
   ```

Giao diện đọc macro ở thư mục gốc và `macros\`, thiết lập từ `macro_settings.json`, ảnh điều kiện từ `macros\images\`, và tiêu đề cửa sổ từ `window_config.json`.

## Chạy macro

- Chọn một macro để xem các bước; chỉnh điều kiện, tốc độ, số vòng, độ trễ và các thiết lập ảnh.
- Nút chạy yêu cầu xác nhận trước khi gửi click/phím tới cửa sổ mục tiêu.
- Tọa độ click được tính tương đối từ góc trên bên trái cửa sổ mục tiêu.
- Đưa con trỏ chuột vào góc trên bên trái màn hình sẽ kích hoạt cơ chế dừng khẩn cấp mặc định của PyAutoGUI; nút **Dừng ngay** cũng dừng giữa các bước.
- Chỉ chạy khi đã kiểm tra đúng cửa sổ và hiểu rõ các thao tác trong macro.

Đây là bản dựng lại dựa trên định dạng JSON quan sát được, không phải bản sao đã xác minh của engine cũ. Hãy thử từng macro trên một cửa sổ/phiên an toàn trước; điều kiện ảnh và các nhánh dự phòng được diễn giải theo cấu hình hiện có.
