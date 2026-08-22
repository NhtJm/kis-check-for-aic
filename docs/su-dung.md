# Sử dụng hằng ngày

## Cách dùng

1. Bấm **Chọn file CSV…**, chọn file submission, rồi bấm **Nạp**
   (hoặc kéo thả thẳng file vào trang — nạp luôn).
2. CSV mỗi dòng: `L21_V015,25725` — mã video, số frame. Dòng header được bỏ qua.
3. Frame đổi ra giây theo **fps** ở thanh trên (mặc định `30`, sửa được).
4. Duyệt bằng `↑`/`↓`, đánh dấu `1` đúng · `2` sai · `3` chưa chắc.
   Mặc định video **đứng sẵn ở đúng frame**, bấm mới chạy — bật **Tự phát**
   nếu muốn chọn kết quả là phát ngay. Lựa chọn này được nhớ lại.
5. **Xuất CSV** để lấy lại bảng kèm timestamp và đánh giá.

Đánh dấu lưu trong `localStorage` theo tên file, đóng tab mở lại vẫn còn.

## Nhiều người cùng kiểm tra một submission

Thay cho việc gửi CSV qua Messenger rồi ghép kết quả bằng tay:

1. Ai đó **Nộp CSV** ngay trên web, nhập danh sách người kiểm tra.
2. Server chia việc **theo video**, cân bằng số dòng.
3. Mỗi người mở link, gõ tên mình, thấy đúng phần của mình.
4. Đánh dấu tự lưu lên server; tiến độ cả nhóm hiện realtime.
5. Bấm **File gộp** để tải CSV cuối, đã ghép mọi người.

### Vì sao chia theo video chứ không theo dòng

Thao tác đắt nhất khi kiểm tra là đợi player nạp lại video, không phải xem frame.
Gom trọn một video cho một người thì họ mở một lần rồi check hết mọi dòng thuộc
video đó. Đo trên dữ liệu thật, chia cho 5 người:

| Submission | Chia theo dòng | Chia theo video |
|---|---|---|
| kis-1 (100 dòng, 11 video) | mỗi người mở tới 11 video | **2-3 video** |
| kis-3 (100 dòng, 57 video) | mỗi người mở ~20 video | **11-12 video** |

Cân bằng tải vẫn tốt: 19-21 dòng mỗi người.

### Không cần database

Mỗi người ghi vào đúng file của riêng mình:

```
marks/{submission}/{tên}.json
```

Không file nào bị hai người ghi cùng lúc nên không có tranh chấp, không cần
transaction, không cần Firestore. Gộp = đọc N file nhỏ rồi cộng lại.

### Mật khẩu chung

Đặt `KIS_PASSWORD`; bỏ trống thì ai có link cũng vào được.

```bash
gcloud run services update kis-check-for-aic --region asia-southeast1 \
  --update-env-vars KIS_PASSWORD='...'
```

Đây là rào cho nhóm nội bộ, không phải hệ xác thực thật — mọi người dùng chung
một mật khẩu và tên chỉ để phân việc, không xác minh danh tính.

## Xếp hạng lại và đo chất lượng

Điểm % không nói lên chất lượng — **thứ hạng của frame đúng** mới nói lên. Dùng
`compare.py` để đo, với `--truth` là dòng bạn biết chắc là đúng:

```bash
python3 compare.py --csv submission.csv \
  --query "câu query tiếng Việt" \
  --en "English translation" \
  --truth L21_V015,25725
```

Nó chạy lần lượt các cấu hình và báo frame đúng rơi vào hạng mấy ở từng cấu hình.

### Xếp lại vòng hai

```bash
# VLM qua agent router xếp lại 30 dòng đầu — nhanh, chỉ ~30 request
python3 score_query.py --csv sub.csv --query "..." --rerank api --rerank-topk 30

# hoặc jina-clip-v2 chạy local — không tốn tiền nhưng chậm hơn nhiều
python3 score_query.py --csv sub.csv --query "..." --rerank jinaai/jina-clip-v2
```

Nhóm đã rerank **luôn xếp trên** nhóm còn lại. Đây là chủ ý: điểm của hai model
khác thang đo nhau, trộn chung rồi sort là sai thứ tự. Thứ tự chuẩn nằm ở trường
`rank_final`, không phải ở `score`.

Mặc định VLM chỉ chấm đúng frame đó (offset 0) cho nhanh và rẻ; model chạy local
thì quét cả cửa sổ. Đổi bằng `--rerank-window N`.

### Gộp nhiều biến thể câu query

```bash
python3 score_query.py --csv sub.csv --query "..." --expand 6
```

Nhờ LLM dịch sang tiếng Anh và diễn đạt lại thành N biến thể rồi gộp vector chữ
(`--agg mean_emb`, cách gộp kinh điển của CLIP). Cần cấu hình API.

**Gộp không phải lúc nào cũng tốt hơn.** Trong một phép đo (n=1, query của tôi
chứ không phải của bạn): tiếng Anh thuần đưa frame đúng lên hạng 1, tiếng Việt
thuần hạng 2, còn gộp VI+EN lại tụt về hạng 2. Trung bình vector kéo kết quả về
phía biến thể yếu hơn. Hãy tự đo bằng `compare.py` trên query thật của bạn.
