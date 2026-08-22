# Chấm điểm bằng AI

## Chấm điểm query bằng AI

Nhập câu query, hệ thống lấy frame thật ra và chấm mức khớp theo %.
Chỉ chạy khi bạn mở bằng `serve.py` ở máy mình — bản GitHub Pages là trang tĩnh
nên thanh query tự ẩn.

```bash
pip install yt-dlp sentencepiece
python3 fetch_videos.py submission.csv    # tải video 360p về thư mục videos/
python3 serve.py                          # rồi mở http://localhost:8777/
```

Hoặc chạy thẳng ngoài dòng lệnh:

```bash
python3 score_query.py --csv submission.csv --query "bốn phi hành gia mặc áo đen"
```

Với mỗi dòng, script lấy thêm vài frame trước/sau (`--window 90 --step 30`
= ±3 giây, mỗi giây một frame) rồi báo: điểm tại đúng frame đó, điểm cao nhất
trong cửa sổ, và lệch bao nhiêu frame — để biết frame chỉ hơi trượt hay sai hẳn.

### Ba chế độ chấm

| Chế độ | Cách chạy | Tốc độ | Chi phí |
|---|---|---|---|
| `siglip` | SigLIP đa ngữ chạy local trên MPS | ~700 frame / 26s | miễn phí |
| `hybrid` | SigLIP lọc trước, VLM chấm lại top 20 | thêm ~140 request | thấp |
| `api` | VLM chấm toàn bộ frame | ~700 request | cao |

### Cấu hình API

Khoá đọc từ file `.env` ở thư mục gốc dự án, hoặc từ biến môi trường.
`.env` đã nằm trong `.gitignore` — **không bao giờ commit nó**.

```bash
cp .env.example .env      # rồi mở ra điền khoá
python3 api_backend.py    # kiểm tra: gọi thử 1 ảnh mẫu
```

```ini
KIS_API_BASE=https://agentrouter.org/v1
KIS_API_KEY=sk-...
KIS_API_MODEL=claude-opus-5
```

Biến môi trường thật luôn thắng `.env`, nên khi deploy thì đặt env var ở
dashboard của host thay vì mang file `.env` lên.

Khi đủ ba giá trị, `serve.py` tự mở khoá hai chế độ `hybrid` và `api` trong UI.

### Đọc con số thế nào cho đúng

SigLIP huấn luyện bằng sigmoid loss nên `sigmoid(scale·cos + bias)` là **xác suất
khớp tuyệt đối** — khác CLIP vốn chỉ so tương đối được. Nó tách rất tốt khớp /
không khớp: trong lần chạy thử, query đúng cho 99.9%, "một tô phở bò" 0.00%,
"cầu thủ sút bóng" 0.00%.

Nhưng nó **bão hoà ở đỉnh**: nhiều frame thật sự khớp đều đội trần ~100% và không
xếp hạng được với nhau. Vì vậy cột `cosine` được xuất kèm và dùng để phá thế hoà —
nó còn nguyên độ phân giải. Rê chuột lên badge % để xem.

Câu query nên viết **tiếng Việt**: cùng một nội dung, bản tiếng Việt cho 99.9%
còn bản tiếng Anh chỉ 13.2%.

## Chọn model cho rerank: đo thật, đừng đoán

Trực giác "chọn model nhẹ cho rẻ" **sai với ảnh**. `gpt-4o-mini` nhân token ảnh
lên ~33 lần để bù giá token rẻ, nên cuối cùng đắt hơn cả `gpt-4o`.

Số đo thật, một frame 512px, `detail:"low"`, chấm frame có phi hành gia áo đen:

| Model | token/ảnh | $/frame | 700 frame | Chấm |
|---|---|---|---|---|
| **gpt-4o** | **117** | **$0.00034** | **$0.24** | 90 ✓ |
| gpt-4o-mini | 2865 | $0.00043 | $0.30 | 90 ✓ |
| gpt-4o-mini (detail auto) | 8532 | $0.00128 | $0.90 | 90 ✓ |
| gpt-4.1-mini | 265 | $0.00011 | $0.08 | 30 ✗ |
| gpt-4.1-nano | 386 | $0.00004 | $0.03 | 10 ✗ |

Hai kết luận: `detail:"low"` giảm 3 lần chi phí mà đáp án không đổi (đã bật mặc
định trong `api_backend.py`), và hai model nano/mini rẻ thật nhưng **chấm sai** —
cho 30 và 10 đúng cái frame mà gpt-4o và gpt-4o-mini đều chấm 90.

Kiểm tra trước khi chấm cả bộ, chỉ tốn một lệnh gọi:

```bash
python3 deploy/test_api.py           # gọi đúng đường chạy thật, in usage + chi phí
python3 deploy/test_api.py --list    # xem model nào dùng được
```

### Rerank có tác dụng thật

Đo trên submission 100 dòng, query tiếng Việt, `--rerank api --rerank-topk 20`:

| | Trước rerank (SigLIP) | Sau rerank (gpt-4o) |
|---|---|---|
| `L21_V015,25725` (frame đúng) | hạng 2 | **hạng 1**, chấm 1.00 |
| `L21_V024,20734` (cảnh gần giống) | hạng 1 | hạng 2, chấm 0.50 |
| 18 dòng còn lại | 90-99%, không tách được | 0.00 |

SigLIP bão hoà ở đỉnh nên không xếp hạng nổi trong nhóm đầu; VLM tách dứt khoát.
Tổng 32.7s (689 frame SigLIP miễn phí + 20 lệnh gọi API ~$0.017).

## Viết query bằng tiếng Anh

Đo trên cùng một submission, cùng frame đúng (`L21_V015,25725`):

| Hạng | Query tiếng Anh | Query tiếng Việt |
|---|---|---|
| 1 | **29.77%** ← frame đúng | 99.9% ← frame đúng |
| 2 | 23.44% | 100.0% |
| 3 | 0.17% | 99.7% |
| 4 | 0.06% | 98.4% |

Tiếng Việt dồn cả nhóm đầu vào 98-100%, không xếp hạng được với nhau. Tiếng Anh
tách dứt khoát. Đây là lý do thật để viết query tiếng Anh — không phải vì model
"hiểu tiếng Anh hơn", mà vì nó cho **độ tách** dùng được.

## Tự dịch query sang tiếng Anh

```bash
python3 score_query.py --csv sub.csv --query "hai người phụ nữ cho dê ăn" --translate
```

Trong UI: tick **Dịch sang tiếng Anh** (tự hiện khi server có cấu hình API). Sau
khi chấm, UI hiện câu đã dùng thật để bạn kiểm chứng.

Chỉ tốn **một** lệnh gọi API cho cả lượt chấm (~$0.0002), khác hẳn rerank vốn tốn
một lệnh gọi mỗi frame. Query vốn đã tiếng Anh thì bỏ qua, không gọi API.

Đã kiểm chứng: bản dịch tự động cho kết quả trùng khớp với query tiếng Anh viết tay
— cùng thứ tự, cùng giá trị cosine.

## TRAKE: chấm từng mốc theo đúng sự kiện của nó

CSV của TRAKE có nhiều mốc mỗi dòng (`video,f1,f2,f3`). Chấm cả ba mốc bằng chung
một đoạn mô tả là sai hình — E2 không bao giờ "giống" mô tả của E1.

`score_query.run()` nhận `query` là dict `{"E1": "...", "E2": "..."}` thì mỗi mốc
được chấm theo đúng sự kiện của nó.

Đo trên `query-p1-16-trake` (99 dòng × 3 mốc, 267/300 chấm được):

| Sự kiện | Cao nhất | Nhận xét |
|---|---|---|
| E1 — hai con rồng vàng xoay vòng | 57.4% | đúng, top 3 đều là rồng vàng |
| E2 — lân hoàn tất cú xoay trên trụ | 0.9% | **model không nhận ra** |
| E3 — dùi chạm kẻng đồng | 99.4% | đúng chính xác |

E2 gần 0 dù frame thật sự có lân trên trụ. Lý do: SigLIP nhận **vật thể trong
khung hình** (rồng, kẻng, dùi), không nhận **thời điểm một động tác hoàn tất**.
Những mốc kiểu đó phải để người xem — đừng tin điểm thấp là sai.

## Agent Router không dùng được — và vì sao

Router này chỉ chấp nhận một số client được họ hỗ trợ chính thức. Script tự viết
gọi vào bị từ chối:

```
401 unauthorized client detected
使用官方里支持的这些客户端 / Please use the officially supported harnesses
```

Đã thử và loại trừ hết: khoá mới, prompt tiếng Anh, SDK `openai` chính thức,
User-Agent chuẩn, mọi model. **Kể cả `GET /models`** — endpoint không có nội dung
gì để lọc — cũng trả 401. Đây là chính sách kiểm soát truy cập của họ, không phải
lỗi cấu hình, và không nên tìm cách lách.

Có một chi tiết đáng ghi lại: ban đầu request tiếng Việt trả `400 content-blocked`
còn tiếng Anh trả `401`. Lý do là **bộ lọc nội dung chạy trước khâu xác thực** —
request tiếng Việt bị chặn trước khi kịp chạm tới auth, nên che mất vấn đề thật
nằm ở dưới. Nếu chỉ nhìn lỗi tiếng Việt thì sẽ đi sai hướng.

Dùng OpenAI trực tiếp. Đã đo: chạy tốt, $0.00073/frame với `gpt-4o`.
