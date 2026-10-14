<p align="center"><img src="app/assets/meetsync_logo.png" alt="MeetSync" width="420"></p>

# MeetSync – AI trích xuất quyết định cuộc họp (MVP)

Hệ thống nhận **transcript cuộc họp tiếng Việt** (`.txt`, `.vtt`) và trả về danh sách có cấu trúc:
quyết định cuối cùng, việc cần làm, vướng mắc, yêu cầu, vấn đề chưa chốt và tri thức mới.
Mỗi mục có **trích dẫn câu gốc** (ID câu), **trạng thái** và **lịch sử thay đổi**.

Nguyên tắc cốt lõi: **không biến ý kiến trung gian thành quyết định chính thức.** Đầu buổi đề xuất A,
cuối buổi chốt B → B là `confirmed`, A chỉ nằm trong lịch sử với trạng thái `superseded`.

Đặc tả đầy đủ: [CLAUDE.md](CLAUDE.md).

## Kiến trúc

```
Transcript (+ thông tin cuộc họp, tùy chọn)
 → [Code]    parsing.py      tách câu, gắn ID u001…, người nói, thời điểm
 → [Agent 1] segmenter       chia chủ đề, gộp các lần quay lại ("vụ lúc nãy")   MODEL_LIGHT
 → [Agent 2] extractor       ứng viên theo từng chủ đề, kể cả phương án bị bỏ    MODEL_LIGHT
 → [Agent 3] tracker         lịch sử + trạng thái cuối + độ tin cậy              MODEL_STRONG
 → [Agent 4] verifier        kiểm chứng decision/action với câu bằng chứng       MODEL_STRONG
             └─ không đạt → chạy lại Agent 2 + 3 cho chủ đề đó đúng 1 lần, vẫn sai → cờ verify_failed
 → [Code]    rules.py        8 quy tắc hậu kiểm (ID tồn tại, owner/deadline bịa, cờ…)
 → [UI]      con người duyệt: Chấp nhận / Sửa / Loại → xuất JSON, Excel
```

Bộ điều phối là hàm Python gọi tuần tự (`pipeline.py`), không dùng framework agent. Mọi lời gọi LLM
yêu cầu JSON, được kiểm tra bằng Pydantic và thử lại tối đa 2 lần kèm thông báo lỗi. Prompt nằm
trong `src/meeting_extractor/prompts/*.md`; hash của từng prompt được lưu trong mỗi kết quả.

## Cài đặt (≈ 5 phút)

Yêu cầu Python 3.11+.

```bash
git clone https://github.com/thanhdatpham938-hub/Multi_AI_for_meeting.git
cd Multi_AI_for_meeting

# Cách 1 – uv (khuyên dùng)
uv sync

# Cách 2 – pip
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
pip install -e .
```

> Windows: nếu pip báo `No such file or directory … anthropic\types\beta\…`, đường dẫn đã vượt 260 ký tự –
> đặt thư mục dự án/venv ở đường dẫn ngắn hơn hoặc bật
> [Long Path](https://pip.pypa.io/warnings/enable-long-paths).

## Cấu hình

```bash
cp .env.example .env            # Windows: copy .env.example .env
```

Mở `.env` và điền:

| Biến | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `LLM_PROVIDER` | Nhà cung cấp LLM: `openai` hoặc `anthropic` | `openai` |
| `OPENAI_API_KEY` | API key của OpenAI | (bắt buộc khi dùng OpenAI) |
| `OPENAI_BASE_URL` | Endpoint tương thích OpenAI (Azure, proxy…) | để trống = api.openai.com |
| `MODEL_LIGHT` | Model cho Agent 1, 2 | `gpt-4.1-mini` (Anthropic: `claude-haiku-5-5`) |
| `MODEL_STRONG` | Model cho Agent 3, 4 | `gpt-4.1` (Anthropic: `claude-sonnet-5-5`) |
| `ANTHROPIC_API_KEY` | API key của Anthropic | chỉ cần khi `LLM_PROVIDER=anthropic` |
| `LLM_TEMPERATURE` | Nhiệt độ | `0` – chỉ gửi cho model còn hỗ trợ (xem Giả định) |
| `RUNS_DIR` | Thư mục lưu kết quả | `runs/` |

`.env` và `runs/` đã nằm trong `.gitignore`.

## Chạy từ dòng lệnh

```bash
# Phân tích một transcript (meta là tùy chọn)
uv run python -m meeting_extractor.cli run tests/fixtures/tc1.txt --meta tests/fixtures/tc1.meta.json

# Xuất kết quả: Excel chỉ gồm các mục đã duyệt (accepted/edited)
uv run python -m meeting_extractor.cli export runs/<run_id> --format xlsx
# Xuất cả mục chưa duyệt, có cột "Duyệt" để duyệt ngay trong Excel
uv run python -m meeting_extractor.cli export runs/<run_id> --format xlsx --all
uv run python -m meeting_extractor.cli export runs/<run_id> --format json
```

(Dùng pip thì bỏ tiền tố `uv run`.)

Mỗi lần chạy tạo thư mục `runs/<run_id>/` gồm `result.json`, đầu ra trung gian từng agent
(`segment.json`, `extract_<topic>.json` gồm extract/track/verify và vòng làm lại), `usage.json`
(token, chi phí ước tính) và `reviews.json` (các chỉnh sửa của người duyệt).

### Định dạng transcript

```
[05:12] Nam: Em đề xuất mình dùng server on-premise.
[41:05] Hùng (PM): OK, vậy mình chốt dùng AWS nhé.
```

Dòng không khớp định dạng (ví dụ `(mọi người gật đầu)`) được bỏ qua kèm cảnh báo. File `.vtt`
lấy mốc thời gian bắt đầu và tên người nói từ `<v Tên>` hoặc tiền tố `Tên:`.

Thông tin cuộc họp (tùy chọn) – `meeting_meta.json` hoặc nhập trên giao diện:

```json
{
  "title": "Họp dự án X",
  "date": "12/04/2025", "start_time": "14:00", "end_time": "15:30", "project": "Dự án X",
  "agenda": ["Chọn hạ tầng", "Lịch ra mắt beta"],
  "participants": [{"name": "Hùng", "role": "PM", "can_decide": true}]
}
```

Không có meta hệ thống vẫn chạy; khi đó không kiểm tra thẩm quyền chốt (trừ người nói dạng "Speaker N").

## Giao diện duyệt (Streamlit)

```bash
uv run streamlit run app/review_app.py
```

Mở http://localhost:8501, rồi:

1. **Trang chủ – Phân tích mới**: tải transcript (.txt/.vtt). Ở khung **Thông tin cuộc họp** bên phải,
   nhập tiêu đề, ngày, giờ, dự án, chương trình họp và người tham dự (tick "Quyền chốt" cho người có
   quyền quyết định), hoặc nạp sẵn từ `meeting_meta.json`. Bấm **Phân tích** – tiến trình từng agent hiện trực tiếp.
2. **Trang cuộc họp**: thẻ tổng hợp, các tab Tổng quan / Quyết định / Việc cần làm / Vấn đề còn mở /
   Vấn đề khác. Mục có cờ hoặc độ tin cậy thấp nằm trên đầu; cờ hiện dạng badge màu.
3. Bấm **›** ở một mục để xem nguyên văn câu bằng chứng (thời gian, người nói), timeline lịch sử,
   và **Chấp nhận / Loại / Sửa** (nội dung, trạng thái, điều kiện, người phụ trách, hạn chót).
   **Duyệt nhanh** chấp nhận mọi mục không có cờ và độ tin cậy ≥ 70%.
4. Khung bên phải: thông tin cuộc họp, **gán tên cho "Speaker N"** (áp dụng cho toàn bộ mục),
   tiến độ duyệt, cảnh báo.
5. **⬇ JSON** (toàn bộ, đã áp dụng chỉnh sửa) và **⬇ Excel** (chỉ mục Chấp nhận/Đã sửa, mỗi loại một sheet).
   Chỉnh sửa được lưu ngay vào `runs/<run_id>/reviews.json`.

## Kiểm thử

```bash
uv run pytest            # 77 test, không gọi API, không cần API key
```

Test offline dùng `FakeLLM` (trả JSON kịch bản) cho parser, LLM client (retry/validate), từng agent,
vòng làm lại, 8 quy tắc, pipeline đầu-cuối, CLI, xuất file, metrics và giao diện Streamlit (`AppTest`).

## Đánh giá

```bash
uv run python eval/run_eval.py               # chạy tests/fixtures/tc1..tc7 với API thật
uv run python eval/run_eval.py --repeat 3    # + độ ổn định qua 3 lần chạy
uv run python eval/run_eval.py --cases tc1,tc4 --no-llm-match
```

Bảng chỉ số in ra màn hình và lưu ở `eval/results/latest.md` / `latest.json` (kèm token, chi phí ước
tính, hash prompt, run_id). Khớp mục với đáp án: cùng `type` và giao nhau ở `evidence`; nếu không,
hỏi một LLM nhỏ câu có/không (`prompts/match.md`).

| Chỉ số | Ngưỡng |
| --- | --- |
| Tỷ lệ chốt nhầm | ≤ 5% |
| Recall quyết định | ≥ 85% |
| Precision việc cần làm | ≥ 80% |
| Độ chính xác trích dẫn | ≥ 95% |
| Owner/deadline bịa | 0 |
| Độ ổn định (`--repeat 3`) | ≤ 10% |

Chỉ số tổng hợp tính trên TC1–TC5; TC6 và TC7 chấm theo tiêu chí riêng (giới hạn đã biết).

### Kết quả eval mới nhất

**Chưa có.** Eval cần gọi API thật, và môi trường xây dựng MVP chưa có API key, nên bước
tinh chỉnh prompt theo eval (bước 7) chưa thực hiện. Những gì đã kiểm chứng offline:

- Đáp án của cả 7 ca nhất quán với quy tắc hậu kiểm: một kết quả "hoàn hảo" dựng từ đáp án đi qua
  `rules.py` đạt toàn bộ ngưỡng (`tests/test_metrics.py`).
- Metrics bắt đúng lỗi chốt nhầm, owner bịa, action thừa, trích dẫn lệch và đổi trạng thái giữa các lần chạy.

Sau khi điền key: chạy `uv run python eval/run_eval.py --repeat 3`, sửa prompt theo các ca sai,
chạy lại **toàn bộ** bộ eval sau mỗi lần sửa, rồi dán `eval/results/latest.md` vào mục này.

## Bộ dữ liệu kiểm thử (`tests/fixtures/`)

| Ca | Tình huống | Kỳ vọng |
| --- | --- | --- |
| TC1 | Đề xuất on-premise → chốt AWS | AWS `confirmed` (u019), on-premise `superseded` trong lịch sử |
| TC2 | Việc có/không có hạn | Minh – thứ Sáu; "ai đó cần xem lại" → owner null + `missing_owner` |
| TC3 | Quay lại chủ đề sau 30 phút ("cái đó") | Một chủ đề; 1/11 `superseded`, 15/11 `confirmed` |
| TC4 | Đùa, "ừ", điều kiện, hoãn | Không có `confirmed`; gói B `conditional`; ngân sách `deferred` |
| TC5 | Chỉ có "Speaker N" | React có cờ `authority_unclear`, confidence ≤ 0.6; owner "Speaker 2" |
| TC6 | Lỗi ASR ở con số | "30 triệu" `confirmed` + cờ `number_check` |
| TC7 | Cử chỉ + cuộc họp trước | Không có `confirmed` bịa cho "phương án đó" |

Mỗi ca gồm `tcN.txt`, `tcN.expected.json` và (trừ TC5) `tcN.meta.json`.

## Giới hạn đã biết

- **TC6 – số sai do ASR:** hệ thống chỉ đọc văn bản nên ghi đúng "30 triệu" như transcript và gắn cờ
  `number_check`; **không thể phát hiện số sai khi không có audio**. Người duyệt chịu trách nhiệm kiểm tra.
- **TC7 – cử chỉ và cuộc họp trước:** "mọi người gật đầu" không có trong lời nói, "phương án đó" nằm
  ở cuộc họp tuần trước. Hệ thống không biết nội dung đó; yêu cầu chỉ là không bịa và không `confirmed`
  (bỏ sót hoặc `open` đều chấp nhận được).
- Không xử lý audio/ASR, không liên kết nhiều cuộc họp, không có chatbot hỏi đáp, không đăng nhập/phân quyền.

## Giả định đã chọn

Theo CLAUDE.md §12, những điểm chưa rõ được giải quyết theo cách đơn giản nhất:

1. **Panel "Trợ lý hỏi đáp" trong mẫu UI được thay bằng khung "Thông tin cuộc họp"** – chatbot/RAG
   nằm ngoài phạm vi MVP; khung này là nơi nhập meta mà mẫu đang thiếu.
2. `MeetingMeta` có thêm `date`, `start_time`, `end_time`, `project` (tùy chọn) để hiển thị như mẫu.
3. **Nhà cung cấp LLM:** đặc tả ghi dùng SDK `anthropic`, nhưng dự án dùng key OpenAI nên mặc định là
   `LLM_PROVIDER=openai` (`OpenAILLM`, Chat Completions ở chế độ JSON `response_format={"type": "json_object"}`).
   `AnthropicLLM` vẫn giữ nguyên, chuyển qua bằng `LLM_PROVIDER=anthropic`. Logic chung (validate Pydantic,
   retry 2 lần kèm lỗi, đếm token/chi phí) nằm ở lớp cha `LLMClient`, nên đổi nhà cung cấp không ảnh hưởng agent.
4. **Temperature:** với OpenAI, `gpt-4.1*`/`gpt-4o*` nhận `temperature=0` và `seed=0`; các model suy luận
   (`o1`, `o3`, `o4-mini`, `gpt-5*`) chỉ nhận nhiệt độ mặc định nên hai tham số này không được gửi. Với Anthropic,
   Claude Haiku 5.5 / Sonnet 5.5 cũng từ chối `temperature`. Độ ổn định dựa vào prompt chặt, schema Pydantic và
   quy tắc bằng code; đo bằng `--repeat 3`. Model từ chối trả lời → báo lỗi rõ ràng, chủ đề đó bị bỏ qua kèm cảnh báo.
5. Hai prompt bổ sung ngoài 4 file của đặc tả: `segment_merge.md` (gộp chủ đề khi transcript > 300 câu)
   và `match.md` (LLM so khớp có/không trong eval).
6. **Quy tắc 2:** owner hợp lệ nếu tên xuất hiện trong câu bằng chứng **hoặc** là người nói một câu bằng
   chứng (ví dụ "Speaker 2: Ok, em sẽ dựng khung dự án"). Deadline phải xuất hiện nguyên văn (không phân biệt hoa thường).
7. **Quy tắc 5:** "người nói ở câu chốt" = người nói của câu bằng chứng muộn nhất; áp dụng cho mọi item `decision`.
8. ID item gán theo loại và thứ tự xuất hiện (`d01`, `a01`, `b01`, `r01`, `o01`, `k01`); danh sách sắp
   xếp mục có cờ/độ tin cậy thấp lên đầu.
9. Một chủ đề lỗi LLM sau khi hết lượt thử → bỏ qua chủ đề đó, ghi cảnh báo, các chủ đề khác vẫn chạy.
10. Đáp án `*.expected.json` có thêm khóa phục vụ chấm: `optional` (mục không bắt buộc), `accept_statuses`,
    `required_flags`, `min/max_confidence`, `history_superseded`, `forbidden`, `same_topic`, `expect_no_confirmed`.
11. Độ ổn định tính trên các mục của đáp án: một mục "đổi trạng thái" nếu trạng thái (hoặc việc có/không
    được tìm thấy) khác nhau giữa các lần chạy.

## Cấu trúc thư mục

```
src/meeting_extractor/
  config.py  models.py  parsing.py  llm.py  rules.py  pipeline.py  export.py  cli.py
  prompts/   segment.md  segment_merge.md  extract.md  track.md  verify.md  match.md
  agents/    segmenter.py  extractor.py  tracker.py  verifier.py  common.py
app/review_app.py        giao diện Streamlit (.streamlit/config.toml: theme)
eval/run_eval.py         chạy bộ đánh giá      eval/metrics.py   khớp đáp án, tính chỉ số
tests/                   pytest + fixtures/ (7 transcript, đáp án, meta, 1 file .vtt mẫu)
runs/                    kết quả mỗi lần chạy (gitignore)
```
