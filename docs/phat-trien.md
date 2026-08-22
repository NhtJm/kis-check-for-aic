# Phát triển

## Build lại

Trang là một file HTML tự chứa, đã nhúng sẵn index `media-info/` (873 video)
nên chạy được offline trừ phần player YouTube.

```bash
python3 build_viewer.py media-info kis-viewer.html [submission.csv]
```

Tham số CSV thứ ba là tuỳ chọn — nếu có, file đó được nạp sẵn khi mở trang, và
build sẽ hỏi YouTube xem video nào đã bị gỡ / để riêng tư. Thêm `--no-check` để bỏ bước đó.
