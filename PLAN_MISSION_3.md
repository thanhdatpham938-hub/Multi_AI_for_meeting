# MeetSync – Kế hoạch Mission 3

Tài liệu điều phối cho Claude Code. Đọc hết trước khi bắt đầu. Làm đúng thứ tự pha ở mục 4.

Repo: `https://github.com/thanhdatpham938-hub/Multi_AI_for_meeting.git`, nhánh `main`.
Mốc bắt đầu: commit `532ee14` (pha 4 giai đoạn 2 đang dở, chưa soát).

> **Trạng thái:** bản nháp 21/10. Đã quyết: đo bằng bộ nhanh ≈ $0,5–0,6/lần, không đo giữa chừng sau M4, mốc M3 chấm lại offline (chưa chạy eval tốn tiền khi triển khai). Các chỗ ⏳ là điểm phải báo giá/xin duyệt khi tới nơi.

## 1. Mục tiêu

Mission 3 cần thể hiện rõ hơn năm khả năng. "Thể hiện" nghĩa là **đo được bằng số** trên bộ đánh giá, không chỉ có tính năng.

| # | Khả năng | Hiện trạng (mốc 21/10 + lần chạy thật) | Hướng làm |
| --- | --- | --- | --- |
| K1 | Hiểu diễn biến xuyên suốt cuộc họp | Mỗi chủ đề xử lý riêng: case 2 tách sampling thành 2 mục mâu thuẫn, "cái này" gắn nhầm chủ đề | Dàn ý dòng thời gian + bước đối soát toàn cuộc họp + gộp chủ đề (L3) |
| K2 | Tránh quyết định / việc cần làm giả | Chốt nhầm 0%, nhưng precision việc cần làm 60%: 3 việc thừa (đã làm xong ×2, xung phong "nếu cần"), 1 hạn bịa cho quyết định | Nhãn cam kết – code quyết định có phải việc cần làm; quyết định không có hạn; tìm bằng chứng phản bác bằng code |
| K3 | Liên kết dữ liệu với bằng chứng | Chỉ kiểm tra ID câu tồn tại; owner/deadline so chuỗi trong câu (quy tắc 2) – xóa nhầm khi ủy quyền | Đoạn trích nguyên văn được code kiểm chứng + nguồn gốc từng trường (owner, deadline, điều kiện) |
| K4 | Xử lý nội dung chưa chốt / mơ hồ | Có trạng thái `deferred/conditional/open`, nhưng không ghi chờ ai/chờ gì; "phương án đó" chỉ trông vào việc AI không bịa | Trường "đang chờ" + người theo dõi; cờ `unresolved_reference`; danh sách "Cần làm rõ" có câu hỏi gợi ý |
| K5 | Phân biệt việc hiện tại với tri thức dài hạn | `knowledge` là rổ chung ("server staging hôm qua chậm" lẫn với "sandbox hết hạn sau 15 phút") | Nhãn phạm vi `ephemeral / project / reusable`; cờ cần kiểm tra lại; "Kho tri thức" xuất riêng |

## 2. Tiêu chí đo (định nghĩa hoàn thành)

Đo trên **bộ nhanh** (đã quyết 21/10, ≈ $0,5–0,6 mỗi lần): 7 ca ngắn × 1 + case 2 – TeaGo (140 câu) × 1. Case 2 được chọn vì chứa hầu hết bẫy của K1/K2/K4. Đáp án JSON của cả 5 cuộc họp dài vẫn làm ở M1 để chạy **bộ đầy đủ** (≈ $2) khi chủ dự án yêu cầu riêng. Chỉ số dựa trên < 10 mục ghi rõ là tham khảo.

| Khả năng | Chỉ số | Mốc hiện tại | Mục tiêu |
| --- | --- | --- | --- |
| K2 | Tỷ lệ chốt nhầm | 0% (7 ca ngắn) | **0%** trên bộ nhanh |
| K2 | Precision việc cần làm | 60% (5 việc) | ≥ 80% trên bộ nhanh |
| K2 | Owner/deadline bịa | 1 | 0 |
| K1 | Recall quyết định trên case 2 | chưa đo bằng đáp án JSON | ≥ 85% |
| K1 | Kiểm tra cùng chủ đề (`same_topic`) đạt | 1/1 ca ngắn | 100% trên bộ nhanh (TC3 + kênh quảng cáo, sampling ở case 2) |
| K1 | Quyết định mâu thuẫn không gắn cờ | case 2: 1 cặp | 0 |
| K3 | Đoạn trích kiểm chứng được (có thật trong câu) | chưa có | ≥ 95% mục |
| K3 | Owner/deadline có câu nguồn riêng | chưa có | 100% khi khác null |
| K4 | Trạng thái đúng cho mục chưa chốt (deferred/conditional/open) | chưa đo riêng | ≥ 80% |
| K4 | Cờ `unresolved_reference` ở TC7 | chưa có | có (case 3 kiểm khi chạy bộ đầy đủ) |
| K5 | Phân loại phạm vi tri thức đúng | chưa có | ≥ 75% mục tri thức có nhãn trong đáp án |
| Chung | Độ ổn định | 0% (mốc 21/10, 3 lần) | ≤ 10% – chỉ đo lại nếu chủ dự án duyệt thêm 2 lần chạy ca ngắn (≈ $0,36) |

Ngoài ra: `pytest` xanh không cần API key; toàn bộ pha đã commit và push; README và báo cáo có bảng **trước/sau** cho từng khả năng.

## 3. Quy tắc chung

Giữ nguyên **mục 2 của `PLAN_GIAI_DOAN_2.md`**, gồm:

- Subagent chỉ sửa file được giao; test để trong file mới của riêng mình.
- `pytest` xanh trước khi báo xong; không gọi API thật trong test.
- Prompt nằm trong `prompts/*.md`.
- **Báo giá và xin duyệt trước mọi lần chạy tốn tiền API**; subagent không bao giờ tự chạy.
- Agent điều phối commit sau mỗi pha, sau khi `meetsync-reviewer` không còn lỗi chặn.

Thêm cho Mission 3:

- **Mọi nhãn mới do AI gán đều phải an toàn khi thiếu hoặc sai**: giá trị lạ → `None` + warning, không bao giờ làm rơi cả mục (bài học pha 1 và 3A).
- **Không thay đổi prompt khi chưa có mốc** (pha M3 – chấm lại offline).
- Nhiều nhất **3 subagent chạy song song** (giới hạn phiên đã làm ngắt pha 4).

## 4. Thứ tự pha

```
M0  (tuần tự)                 Hoàn tất pha 4 giai đoạn 2 + sửa đáp án TC3
M1  (SONG SONG, 2 subagent)   Mở rộng bộ đánh giá: đáp án JSON 5 cuộc họp dài · chỉ số mới
M2  (tuần tự, agent chính)    Đổi schema một lần cho mọi nhãn/trường mới
M3  (agent chính, KHÔNG PHÍ)  Mốc "trước": chấm lại offline các run đã lưu
M4  (SONG SONG, 3 subagent)   Nhãn Agent 3 · Quy tắc code · Bằng chứng phản bác
M5  (SONG SONG, 2 subagent)   Diễn biến xuyên suốt · Giao diện và xuất
M6  (tuần tự, CÓ PHÍ)         Eval cuối trên bộ nhanh (≈ $0,6), so sánh, tài liệu
```

---

## M0 – Hoàn tất phần dở (~1–2 giờ)

1. Gửi tin cho subagent pha 4 (đã lưu tiến độ) để làm tiếp theo mục "Pha 4" của `PLAN_GIAI_DOAN_2.md`; xong thì `meetsync-reviewer` soát toàn bộ phần pha 4 (cả commit `532ee14`). Commit `feat(pha-4): …`.
2. Kiểm tra giao diện bằng mắt (ảnh chụp): bảng giải thích độ tin cậy, tải audio, tab Hỏi đáp.
3. Sửa đáp án `tests/fixtures/tc3.expected.json`: thêm `u019` vào `history_superseded[].evidence` (lỗi đáp án đã ghi trong `eval/baseline_2026-10-21.md`).
4. Pha 5A của giai đoạn 2 (L3 gộp chủ đề) **chuyển sang M5A**; pha 5B/5C chuyển sang M6.

## M1 – Mở rộng bộ đánh giá (2 subagent song song, offline, ~4 giờ)

### M1A. Đáp án JSON cho 5 cuộc họp dài (subagent 1)

> Chuyển `expected_result.md` của 5 thư mục trong `test_cases_3_muc_do (1)/` thành `expected.json` cùng thư mục, theo đúng schema của `tests/fixtures/tc*.expected.json` (xem `eval/metrics.py` để biết các khóa: `items`, `optional`, `accept_statuses`, `required_flags`, `min/max_confidence`, `history_superseded`, `forbidden`, `same_topic`, `expect_no_confirmed`, `known_limitation`).
>
> Mốc thời gian trong file md → ID câu bằng `parsing.parse_file` (ID theo thứ tự dòng). Mục md ghi "chấp nhận nếu bỏ sót" → `optional: true`. Mục "trạng thái A hoặc B" → `accept_statuses`. Các danh sách "tuyệt đối không được `confirmed`" → `forbidden`. Case 3 → `known_limitation: true`.
>
> Thêm khóa mới (M1B sẽ chấm): `knowledge_scope` cho mục `knowledge` (`ephemeral` | `project` | `reusable`), `pending_on` (chuỗi ngắn) cho mục `deferred`, `expect_flags_any` cho TC7/case 3 (`["unresolved_reference"]`), và ở cấp ca `expect_no_conflicts: true`. Ghi định nghĩa ba phạm vi ở đầu mỗi file hoặc trong `eval/README_answer_keys.md`.
>
> Thêm nhãn `knowledge_scope` cho các mục `knowledge` trong 7 đáp án ngắn nếu có.
>
> Test: mọi ID trong đáp án tồn tại trong transcript tương ứng; JSON hợp lệ; mỗi case dài có ≥ 5 mục bắt buộc.
>
> File được phép: `test_cases_3_muc_do (1)/*/expected.json` (mới), `tests/fixtures/*.expected.json`, `eval/README_answer_keys.md` (mới), `tests/test_answer_keys.py` (mới).

⏳ **Chủ dự án duyệt nhanh các đáp án JSON** trước pha M3 (subagent tự chuyển từ md nên có thể hiểu sai ý).

### M1B. Chỉ số mới và chạy cuộc họp dài (subagent 2)

> Mở rộng `eval/metrics.py` và `eval/run_eval.py`:
> - `run_eval.py` nhận `--suite quick|short|long|all` (mặc định `short` để không đổi hành vi cũ). `quick` = 7 ca ngắn + `case2_kho_du_lieu_khong_ro_rang`, mỗi ca 1 lần. `long` đọc `test_cases_3_muc_do (1)/*/transcript.txt` + `meeting_meta.json` + `expected.json`; `--repeat` áp riêng được cho từng bộ (`--repeat-long`, mặc định 1).
> - **In ước tính chi phí trước khi chạy** (số lần phân tích × chi phí trung bình theo số câu, dùng mốc $0,026/ca ngắn và ~$0,0026/câu cho cuộc họp dài) và yêu cầu cờ `--yes` mới chạy thật – để không ai vô tình chạy tốn tiền.
> - Chỉ số mới (bảng in riêng theo bộ ngắn / dài / tổng):
>   - `unresolved_status_accuracy`: trong các mục đáp án có trạng thái `deferred/conditional/open` được khớp, tỷ lệ trạng thái hệ thống nằm trong `accept_statuses`.
>   - `quote_validity`: tỷ lệ mục có `evidence_quotes` mà mọi đoạn trích là chuỗi con (chuẩn hóa khoảng trắng, không phân biệt hoa thường) của câu được dẫn. Mục chưa có trường này → không tính (để chạy được trên kết quả cũ).
>   - `field_provenance`: tỷ lệ owner/deadline khác null có câu nguồn riêng trong `field_evidence`.
>   - `knowledge_scope_accuracy`: trên mục `knowledge` khớp đáp án có `knowledge_scope`.
>   - `unflagged_conflicts`: số cặp quyết định cùng chủ đề, một `confirmed` và một không phải `superseded`, mà không có cờ `conflicting_decision`.
>   - `expect_flags_any`: kiểm tra từng ca.
> - Đọc trường mới bằng `getattr(item, ..., None)` để chạy được trước khi M2 thêm schema.
> - Ghi chi phí theo từng bộ vào `latest.json`.
>
> Test offline với kết quả giả (theo kiểu `tests/test_metrics.py`).
>
> File được phép: `eval/metrics.py`, `eval/run_eval.py`, `tests/test_metrics_m3.py` (mới).

## M2 – Đổi schema một lần (agent chính, ~1 giờ)

Trong `models.py` (và `TrackedItem` tương ứng), tất cả đều tùy chọn, mặc định `None`/rỗng:

```python
class Item(BaseModel):
    # ... giữ nguyên ...
    commitment: str | None = None          # assigned | accepted | volunteered_conditional | already_done | hypothetical
    evidence_quotes: dict[str, str] = {}   # ID câu → đoạn trích nguyên văn
    field_evidence: dict[str, list[str]] = {}   # "owner" | "deadline" | "condition" → ID câu nguồn
    knowledge_scope: str | None = None     # ephemeral | project | reusable (chỉ cho knowledge)
    pending_on: str | None = None          # cho deferred/conditional: chờ ai/chờ gì
    follow_up_owner: str | None = None     # ai theo dõi mục chưa chốt
    related_items: list[str] = []          # item_id liên quan (quyết định → việc cần làm, vướng mắc → quyết định)
```

- `VALID_FLAGS += unresolved_reference, needs_recheck, quote_mismatch`, kèm nhãn và màu trong `export.FLAG_LABELS` và `review_app.FLAG_STYLE`.
- Hằng số giá trị hợp lệ (`COMMITMENTS`, `KNOWLEDGE_SCOPES`) để code chuyển giá trị lạ về `None`.
- `related_items` tham chiếu `item_id` – được gán sau khi quy tắc 8 đặt ID (M5A ghi lại liên kết theo chỉ số tạm rồi đổi sang ID).

Chạy `pytest`, kiểm tra kết quả cũ trong `runs/` vẫn mở được, commit `chore(m2): schema cho Mission 3`.

## M3 – Mốc "trước" bằng cách chấm lại offline (agent chính, KHÔNG PHÍ, ~30 phút)

Đã quyết 21/10: chưa chạy eval tốn tiền. Mốc "trước" lấy bằng cách **chấm lại các lần chạy đã lưu** trong `runs/` bằng đáp án JSON và chỉ số mới của M1 – không gọi API:

- 7 ca ngắn: các run trong `eval/results/latest.json` (`run_ids`, mốc 21/10, prompt `track` cũ).
- Case 2: run `20261015-010747-488916_transcript` (15/10, trước pha 1).

Thêm vào `eval/run_eval.py` (M1B) chế độ `--rescore <latest.json | run_dir…>`: đọc kết quả đã lưu, chấm bằng `match_items` theo evidence (không dùng LLM so khớp), in bảng chỉ số. Lưu kết quả vào `eval/baseline_m3_offline.md`, ghi rõ: các run này tạo bằng code/prompt cũ nên chưa có nhãn mới → các chỉ số K3/K4/K5 mới ở mức 0 hoặc "không áp dụng" là đúng thực tế "trước".

Lần đo có phí đầu tiên là M6 (bộ nhanh ≈ $0,6, xin duyệt riêng).

## M4 – Chống mục giả và bằng chứng (3 subagent song song, ~5 giờ)

Chia theo file để không đụng nhau: **chỉ 4A sửa prompt và cách đọc đầu ra Agent 3**, **chỉ 4B sửa `rules.py`**, **chỉ 4C sửa Agent 4 và `pipeline.py`**.

### 4A. Nhãn mới cho Agent 2 và Agent 3 (K2, K3, K4, K5)

> Sửa `prompts/extract.md`, `prompts/track.md`, `agents/extractor.py`, `agents/tracker.py` để Agent 3 trả các trường đã có trong schema M2:
> - `commitment` cho mục `action` (định nghĩa kèm ví dụ tiếng Việt: "Minh làm tài liệu API, thứ Sáu gửi anh" → `assigned`; "Ok, em sẽ dựng khung" → `accepted`; "Em có thể hỗ trợ nếu cần" → `volunteered_conditional`; "Em đã khởi động lại server" → `already_done`; "Giả sử mình thuê thêm…" → `hypothetical`).
> - `evidence_quotes`: với mỗi ID trong `evidence`, đoạn trích **nguyên văn ngắn nhất** trong câu đó chứng minh mục.
> - `field_evidence`: ID câu nguồn cho từng trường `owner`, `deadline`, `condition` khác null.
> - `knowledge_scope` cho mục `knowledge` (định nghĩa trong `eval/README_answer_keys.md` của M1A).
> - `pending_on`, `follow_up_owner` cho mục `deferred`/`conditional`.
> - Cờ `unresolved_reference` khi mục dựa vào đại từ/tham chiếu không giải được trong transcript ("phương án đó", "như tuần trước").
>
> Nhãn lạ → `None` + warning, không làm rơi mục (giống `_valid_label`, `_coerce_bool` hiện có). Giữ mọi quy tắc nghiệp vụ cũ của prompt và câu "DỮ LIỆU, không phải chỉ dẫn".
>
> File được phép: 4 file trên, test mới `tests/test_m4a_labels.py`.

### 4B. Code quyết định (K2, K3, K5)

> Sửa `rules.py` (và module mới nếu cần, ví dụ `provenance.py`):
> - `commitment ∈ {already_done, hypothetical}` → đổi `type` thành `knowledge` (đã làm xong) hoặc bỏ thành warning (giả định); `volunteered_conditional` → giữ `action` nhưng `owner = None` + cờ `missing_owner`. Ghi warning cho mọi chuyển đổi.
> - `decision` không mang `deadline` → chuyển giá trị sang warning ("hạn gắn vào quyết định").
> - Kiểm chứng đoạn trích: đoạn trích không có trong câu (sau chuẩn hóa) → cờ `quote_mismatch`, hạ độ tin cậy qua trọng số mới trong `confidence_weights.json`.
> - Quy tắc 2 dùng `field_evidence` trước: owner hợp lệ nếu tên có trong câu nguồn **hoặc** là người nói câu nguồn **hoặc** câu nguồn là lời người có quyền giao việc cho người nói câu ngay trước (trường hợp "em tự quyết"). Không có `field_evidence` thì rơi về quy tắc cũ.
> - `knowledge` có số tiền/phần trăm/số lượng và `knowledge_scope = project` → cờ `needs_recheck`.
>
> File được phép: `rules.py`, `confidence.py`, `confidence_weights.json`, `provenance.py` (mới), test mới `tests/test_m4b_rules.py`; cập nhật dữ liệu giả lập trong `tests/test_rules.py` nếu cần (không xóa test).

### 4C. Bằng chứng phản bác (K2, K1)

> Viết `counter_evidence.py`: với mỗi `decision`, tìm bằng code các câu **sau** câu bằng chứng cuối trong toàn transcript (không chỉ trong chủ đề) có chung từ khóa nội dung (bỏ từ dừng tiếng Việt) hoặc chung con số/ngày. Trả tối đa 5 câu.
>
> Sửa `agents/verifier.py` và `prompts/verify.md`: Agent 4 nhận thêm các câu này với câu hỏi "có câu nào phản bác, thay đổi hoặc rút lại nội dung này không?" và trả thêm `contradicted_by: list[str]`. Có câu phản bác hợp lệ → `contradicted_later = True` (ghi đè nhãn AI), ghi ID vào `field_evidence["contradicted_by"]`.
>
> Sửa `pipeline.py` chỉ ở chỗ gọi verify. Không đụng logic chống mất dữ liệu của pha 1.
>
> File được phép: `counter_evidence.py` (mới), `agents/verifier.py`, `prompts/verify.md`, `pipeline.py`, test mới `tests/test_m4c_counter.py`.

Sau M4: `pytest`, reviewer soát cả ba, commit. **Không chạy eval ở đây** (đã quyết 21/10: đo gộp ở M6).

## M5 – Diễn biến xuyên suốt, giao diện (2 subagent song song, ~5 giờ)

### 5A. Diễn biến xuyên suốt (K1)

> - **Gộp chủ đề (L3):** sau Agent 1, luôn gọi một lần `prompts/segment_merge.md` với danh sách tất cả chủ đề (dùng lại hàm gộp trong `segmenter.py`). Không so đôi một.
> - **Dàn ý dòng thời gian:** `prompts/digest.md` + `agents/digest.py`, model nhẹ, một lần mỗi cuộc họp: danh sách mốc (phút, người nói, sự kiện: đề xuất / phản bác / chốt / hoãn / chuyển chủ đề). Đưa dàn ý vào Agent 3 làm ngữ cảnh (chỉ thêm chỗ trống `{{DIGEST}}` vào `track.md` – báo 4A nếu còn chạy, nếu không thì sửa trực tiếp).
> - **Đối soát:** `prompts/reconcile.md` + `agents/reconciler.py`, model mạnh, một lần sau mọi chủ đề: nhận danh sách mục (không kèm transcript đầy đủ, chỉ nội dung + trạng thái + câu bằng chứng) và trả các cặp mâu thuẫn + liên kết `related_items`. Code gắn cờ `conflicting_decision` cho cặp mâu thuẫn; **không tự xóa mục nào**.
> - Quy tắc code (không cần LLM): cùng chủ đề có ≥ 2 `decision`, một `confirmed`, mục kia không phải `superseded` → `conflicting_decision`.
> - Chi phí thêm ước tính: +2 lần gọi mỗi cuộc họp (dàn ý ~$0,005 với model nhẹ; đối soát ~$0,02–0,04 với cuộc họp dài).
>
> File được phép: `agents/segmenter.py`, `agents/digest.py` (mới), `agents/reconciler.py` (mới), `prompts/digest.md` (mới), `prompts/reconcile.md` (mới), `prompts/segment_merge.md`, `pipeline.py`, `rules.py` (chỉ quy tắc mâu thuẫn, sau khi 4B đã commit), test mới.

### 5B. Giao diện và xuất (K3, K4, K5)

> - **Bằng chứng:** trong cửa sổ chi tiết, bôi đậm đoạn trích trong câu gốc; hiện thêm 2 câu trước/sau (nhạt màu); trường owner/deadline/điều kiện có nút nhỏ dẫn tới câu nguồn. Mục có `quote_mismatch` hiện cảnh báo.
> - **"Cần làm rõ":** tab mới liệt kê mục có cờ `missing_owner`, `unresolved_reference`, `conflicting_decision`, `needs_recheck`, và mục `deferred` thiếu `follow_up_owner`. Mỗi mục kèm **câu hỏi gợi ý sinh bằng code theo mẫu** (không gọi AI), ví dụ "Ai chịu trách nhiệm: {nội dung}?", "'{đoạn trích}' đang nói tới phương án nào?". Người duyệt trả lời ngay → lưu như chỉnh sửa duyệt.
> - **Kho tri thức:** tab và sheet Excel riêng cho `knowledge` có `knowledge_scope ∈ {project, reusable}`, cột phạm vi, cờ cần kiểm tra lại, nguồn (cuộc họp, ngày, câu); xuất thêm `knowledge.json`. Mục `ephemeral` chỉ nằm ở danh sách thường.
> - **Liên kết:** cửa sổ chi tiết hiện `related_items` dạng link mở mục liên quan.
>
> - **Sửa tồn đọng từ soát pha 4** (reviewer 21/10, không chặn):
>   - N1: nhãn `closer_unknown` → "người chốt không có quyền hoặc chưa xác định" (khóa này gồm cả người có `can_decide=false`).
>   - N2: thống nhất hiển thị độ tin cậy một kiểu (0,72) ở bảng, dialog và chú thích Duyệt nhanh.
>   - N3: kiểm `upload.size` trước khi ghi file audio ra đĩa; không ghi lại file ở mỗi lần rerun.
>   - N4: test `test_audio_path_cannot_escape_run_folder` tạo file thật ở `run_dir/` và ngoài `run_dir/` để chứng minh `..` bị cắt.
>   - N5: test riêng cho `make_llm` ném `LLMError` (thiếu key) ở tab Hỏi đáp.
>   - N6: `analyze_with` bắt thêm `OSError` khi lưu audio, hiện lỗi tiếng Việt.
>
> File được phép: `app/review_app.py`, `export.py`, `tests/test_phase4_ui.py`, test mới `tests/test_m5b_ui.py`.

Sau M5: `pytest`, reviewer soát, kiểm tra giao diện bằng ảnh chụp, commit.

## M6 – Eval cuối và tài liệu (CÓ PHÍ, ~3 giờ)

1. ⏳ **Xin duyệt** chạy `run_eval.py --suite quick` (≈ $0,6 sau khi M5 thêm 2 lần gọi mỗi cuộc họp) và `calibration.py` (không tốn phí). Bộ đầy đủ (≈ $2,0–2,5) chỉ chạy nếu chủ dự án yêu cầu.
2. So với `baseline_m3_*.md`. **Chỉ số nào tệ đi phải tìm ra nguyên nhân trước khi nộp**; đặc biệt tỷ lệ chốt nhầm phải giữ 0%.
3. Tài liệu:
   - README: mục "Mission 3" với bảng trước/sau cho K1–K5, cách dùng tab Cần làm rõ và Kho tri thức.
   - `docs/bao-cao-he-thong.md` (chỉ trên máy): cập nhật số thật.
   - Sửa L18 (link `CLAUDE.md` hỏng, dòng "xem Giả định").

## 5. Ngân sách API dự kiến

Mỗi lần đo dùng **bộ nhanh ≈ $0,5–0,6** (đã quyết 21/10).

| Lần chạy | Ước tính |
| --- | --- |
| M3 mốc (chấm lại offline) | $0 |
| Mỗi vòng tinh chỉnh prompt nếu chỉ số chưa đạt | $0,5–0,6 |
| M6 cuối | ≈ $0,6 |
| **Tổng nếu 1 vòng tinh chỉnh** | **≈ $1,1–1,2** |

Mỗi lần chạy vẫn báo giá và xin duyệt riêng. Bộ đầy đủ (≈ $2) và đo lại độ ổn định (≈ $0,36) chỉ khi chủ dự án yêu cầu.

## 6. Thứ tự cắt nếu chậm

Cắt từ trên xuống:

1. Dàn ý dòng thời gian (5A) – giữ đối soát và gộp chủ đề.
2. Liên kết `related_items` trong giao diện (5B).
3. Câu hỏi gợi ý trong tab "Cần làm rõ" – giữ danh sách.
4. Bằng chứng phản bác bằng code (4C) – giữ nhãn AI `contradicted_later`.

**Không cắt:** M0, M1, M2, M3, 4A, 4B, kho tri thức, eval cuối.

## 7. Rủi ro

| Rủi ro | Cách xử lý |
| --- | --- |
| Đáp án JSON do subagent chuyển từ md hiểu sai ý | Chủ dự án duyệt nhanh ở cuối M1; đáp án có `optional`/`accept_statuses` cho chỗ mơ hồ |
| Thêm nhãn làm prompt Agent 3 dài, AI trả thiếu trường | Mọi trường tùy chọn; thiếu → `None`, không rơi mục; đo `quote_validity`, `field_provenance` để biết |
| Đối soát toàn cuộc họp tự "sửa" quá tay | Đối soát chỉ gắn cờ và liên kết, không xóa hay đổi trạng thái |
| Mẫu đánh giá vẫn nhỏ (bộ nhanh chỉ có 1 cuộc họp dài) | Báo cáo kèm số mục mỗi chỉ số; không kết luận từ chỉ số có < 10 mục; khi cần kết luận chắc thì xin duyệt chạy bộ đầy đủ một lần |
| Giới hạn phiên làm ngắt subagent | Tối đa 3 song song; subagent lưu tiến độ, tiếp tục bằng tin nhắn |
