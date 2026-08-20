# KIS Submission Checker

Công cụ kiểm tra nhanh file submission Known-Item Search (AIC) bằng cách phát
đúng video YouTube tại đúng thời điểm suy ra từ số frame.

**Dùng ngay:** https://nhtjm.github.io/kis-check-for-aic/

## Cách dùng

1. Bấm **Chọn file CSV…**, chọn file submission, rồi bấm **Nạp**
   (hoặc kéo thả thẳng file vào trang — nạp luôn).
2. CSV mỗi dòng: `L21_V015,25725` — mã video, số frame. Dòng header được bỏ qua.
3. Frame đổi ra giây theo **fps** ở thanh trên (mặc định `30`, sửa được).
4. Duyệt bằng `↑`/`↓`, đánh dấu `1` đúng · `2` sai · `3` chưa chắc.
5. **Xuất CSV** để lấy lại bảng kèm timestamp và đánh giá.

Đánh dấu lưu trong `localStorage` theo tên file, đóng tab mở lại vẫn còn.

## Build lại

Trang là một file HTML tự chứa, đã nhúng sẵn index `media-info/` (873 video)
nên chạy được offline trừ phần player YouTube.

```bash
python3 build_viewer.py media-info kis-viewer.html [submission.csv]
```

Tham số CSV thứ ba là tuỳ chọn — nếu có, file đó được nạp sẵn khi mở trang, và
build sẽ hỏi YouTube xem video nào đã bị gỡ / để riêng tư. Thêm `--no-check` để bỏ bước đó.

## Ghi chú về fps

30 fps được xác nhận từ chính dữ liệu: ở 25 fps có entry cho ra timestamp vượt
quá độ dài video (`L21_V007` frame 22809 → 912s > 842s), ở 30 fps thì không có entry nào vượt.
