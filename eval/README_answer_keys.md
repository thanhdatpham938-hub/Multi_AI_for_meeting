# Đáp án đánh giá (answer keys)

Mỗi cuộc họp có một file đáp án JSON: `tests/fixtures/tcN.expected.json` (7 ca ngắn) và
`test_cases_3_muc_do (1)/case*/expected.json` (5 cuộc họp dài, chuyển từ `expected_result.md`).
Câu trong đáp án được trỏ bằng ID (`u001`, `u002`…) theo thứ tự dòng của transcript (`parsing.parse_file`).

## Khóa cấp ca

| Khóa | Ý nghĩa |
| --- | --- |
| `case` | Tên ca. |
| `description` | Mô tả ngắn (chỉ để đọc). |
| `items` | Danh sách mục đáp án (xem dưới). |
| `forbidden` | Danh sách quy tắc cấm (xem dưới). |
| `expect_no_confirmed` | `true` nếu cả ca không được có mục `confirmed` nào. |
| `known_limitation` | `true` nếu là giới hạn đã biết: chạy và in kết quả nhưng không tính vào chỉ số tổng. |
| `same_topic` | Danh sách nhóm ID câu; mỗi nhóm phải nằm trong đúng một chủ đề (kiểm tra gộp chủ đề). |
| `expect_flags_any` | Danh sách cờ; mỗi cờ phải xuất hiện ở ít nhất một mục (ví dụ `["unresolved_reference"]`). M1B chấm. |
| `expect_no_conflicts` | `true` nếu hệ thống không được có cặp quyết định mâu thuẫn mà thiếu cờ `conflicting_decision`. M1B chấm. |

## Khóa của một mục (`items[]`)

| Khóa | Ý nghĩa |
| --- | --- |
| `type` | `decision`, `action`, `blocker`, `request`, `open_issue`, `knowledge`. Khớp bắt buộc cùng `type`. |
| `status` | Trạng thái đúng (chỉ với `decision`). |
| `accept_statuses` | Các trạng thái đều được coi là đúng (thay cho `status`). Ví dụ `["deferred", "open"]`. |
| `content` | Nội dung tham chiếu (dùng khi so khớp bằng LLM và khi in lỗi). |
| `owner`, `deadline`, `condition` | Giá trị đúng hoặc `null`. Hệ thống điền khác `null` khi đáp án `null` là "bịa". `deadline` so bằng chuỗi con không phân biệt hoa thường. |
| `accept_owners` | (Khóa mới, M1B cần đọc.) Danh sách owner đều được chấp nhận, có thể chứa `null`. Dùng khi md chấp nhận nhiều người (ví dụ `["Tuấn", null]`) hoặc nhiều cách gọi (`"Speaker 2"` hoặc `"Vân"`). `owner` ghi giá trị chuẩn. |
| `evidence` | ID câu bằng chứng chính. Khớp mục hệ thống với đáp án khi giao nhau ở đây; có thể nhiều câu. |
| `optional` | `true` nếu bỏ sót vẫn đạt (chi tiết phụ, hoặc md ghi "chấp nhận nếu bỏ sót"). |
| `required_flags` | Cờ bắt buộc có. Chỉ ghi khi md nêu rõ và nội dung đáp án chắc chắn khiến quy tắc code gắn cờ (ví dụ `number_check` chỉ khi nội dung có số tiền, phần trăm hoặc ngày dạng `15/11`). |
| `min_confidence`, `max_confidence` | Giới hạn độ tin cậy. |
| `history_superseded` | Các phương án bị thay thế phải có trong `history` với trạng thái `superseded`: `{"content", "evidence"}`; khớp khi giao nhau ở `evidence`. |
| `knowledge_scope` | (Chỉ mục `knowledge`, M1B chấm.) `ephemeral`, `project` hoặc `reusable`. |
| `pending_on` | (Chỉ mục `deferred`, M1B chấm.) Chuỗi ngắn tiếng Việt nói chờ ai hoặc chờ gì. |

## Khóa của quy tắc cấm (`forbidden[]`)

`{"type", "statuses", "evidence_only", "note"}`: vi phạm khi có mục cùng `type`, trạng thái nằm trong
`statuses` và mọi `evidence` của nó đều nằm trong `evidence_only`. Dùng cho "không phải quyết định" và
"tuyệt đối không được `confirmed`". Mục có thêm câu bằng chứng khác (ví dụ câu tóm lại) không bị bắt ở đây,
nhưng nếu khớp với một mục đáp án thì trạng thái vẫn bị kiểm tra theo `status`/`accept_statuses`.

## Phạm vi tri thức (`knowledge_scope`)

- `ephemeral`: cập nhật trạng thái hoặc việc chỉ có giá trị trong cuộc họp hoặc vài ngày.
  Ví dụ: "server staging hôm qua chậm", "Sprint 6 xong 34/38 điểm".
- `project`: ràng buộc, số liệu, năng lực, giá… dùng suốt dự án nhưng có thể đổi.
  Ví dụ: "giải ngân 420/600 triệu", "đối thủ TikTok 3 triệu view".
- `reusable`: quy tắc hoặc bài học dùng lại cho dự án khác.
  Ví dụ: "giao dịch sandbox VNPay hết hạn sau 15 phút", "chờ PCCC thường mất ~2 tuần".

Khi mơ hồ, chọn theo câu hỏi: "Sang tuần sau còn dùng được không?" (không: `ephemeral`), rồi "Sang dự án khác còn dùng được không?"
(có: `reusable`, không: `project`).

## Ghi chú đã biết

- **`number_check` chỉ xét nội dung.** Quy tắc 4 hiện chỉ xem `content`/`condition`, không xem `deadline`. Md case 1 liệt kê `number_check`
  cho các việc có hạn dd/mm (Trang 16/10, Hải 22/10, Đức 21/10, Vy 24/10, Long 23/10), nhưng ngày chỉ nằm ở `deadline` nên đáp án
  không đòi cờ này (chỉ việc "Đức trực phát hành tối 28/10", có ngày trong nội dung, mới đòi). Đây là khoảng trống đã biết của quy tắc hiện tại.
- **TC7 mong đợi cờ `unresolved_reference`** (`expect_flags_any`). Cờ này chỉ có sau pha M4, nên `--suite short` sẽ báo TC7 trượt
  cho đến lúc đó. Đây là điều dự kiến, không phải lỗi pipeline.
