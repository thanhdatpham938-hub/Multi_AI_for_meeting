# Bản thảo MVP – Hệ thống AI trích xuất quyết định cuộc họp

MVP cần chứng minh đúng một điều: **từ một transcript cuộc họp, hệ thống đưa ra được danh sách quyết định cuối cùng, việc cần làm và vấn đề còn mở, có trích dẫn, và không biến ý kiến trung gian thành quyết định.**

## 1. Mục tiêu và phạm vi

**Người dùng mục tiêu:** người theo dõi sau họp (PM, trưởng nhóm, thư ký).

**Kết quả người dùng nhận được:** trong vài phút sau khi tải transcript lên, có danh sách đã được AI phân loại. Người dùng duyệt (chấp nhận, sửa, loại) rồi xuất ra JSON hoặc Excel.

| Trong phạm vi MVP | Ngoài phạm vi (để sau) |
| --- | --- |
| Nhận transcript văn bản có tên người nói và mốc thời gian (.txt, .vtt, .docx) | Ghi âm trực tiếp, ASR, tách người nói từ audio |
| Chuỗi 4 agent: Chia chủ đề, Trích xuất, Theo dõi quyết định, Kiểm chứng | Agent Hỏi đáp (RAG), embedding tài liệu dự án |
| Theo dõi trạng thái quyết định trong **một** cuộc họp | Liên kết quyết định giữa nhiều cuộc họp |
| Giao diện duyệt đơn giản, xuất JSON/Excel | Đẩy thẳng sang Jira, wiki; tích hợp Zoom, Meet, Teams |
| Tiếng Việt, có lẫn thuật ngữ tiếng Anh | Xử lý thời gian thực trong lúc họp |
| Danh sách người dự và chương trình họp (tùy chọn) | Phân quyền nhiều người dùng, đăng nhập tổ chức |

**Định nghĩa hoàn thành MVP:** chạy hết luồng trên bộ kiểm thử, đạt các ngưỡng ở mục 6, và người dùng thử hoàn thiện biên bản nhanh hơn làm tay.

## 2. Kiến trúc và công nghệ

**Luồng xử lý cố định, điều phối bằng code.** Mỗi agent là một lần gọi LLM với prompt riêng và đầu ra JSON theo schema. Đầu ra của từng bước được lưu lại để biết lỗi bắt đầu từ đâu.

```
Tải transcript (+ người dự, chương trình họp nếu có)
 → [Code] Chuẩn hoá: tách câu, gắn ID câu, người nói, thời điểm
 → [Agent 1] Chia chủ đề
 → [Agent 2] Trích xuất ứng viên (theo từng chủ đề)
 → [Agent 3] Theo dõi quyết định (theo từng chủ đề)
 → [Agent 4] Kiểm chứng ── không đạt → trả Agent 2 làm lại tối đa 1 lần
 → [UI] Con người duyệt: chấp nhận / sửa / loại
 → [Code] Xuất JSON / Excel  +  lưu chỗ sửa làm dữ liệu đánh giá
```

| Thành phần | Lựa chọn đề xuất | Lý do |
| --- | --- | --- |
| Ngôn ngữ, backend | Python + FastAPI | Nhanh, nhiều thư viện xử lý văn bản và LLM |
| Điều phối | Hàm Python gọi tuần tự | Luồng cố định, không cần framework agent phức tạp |
| LLM | Một model mạnh cho Agent 3, 4; model rẻ hơn cho Agent 1, 2 | Cân bằng chất lượng và chi phí |
| Đầu ra có cấu trúc | JSON schema + kiểm tra bằng Pydantic | Bắt lỗi định dạng ngay, dễ so với đáp án |
| Lưu trữ | SQLite hoặc file JSON | Đủ cho MVP, không cần hạ tầng |
| Giao diện duyệt | Streamlit | Dựng nhanh bảng duyệt và nút xuất file |
| Chạy đánh giá | Script Python so kết quả với đáp án gán nhãn | Chạy lại được mỗi khi đổi prompt hoặc model |

**Nguyên tắc kỹ thuật:** nhiệt độ thấp, lưu phiên bản prompt và model cho mỗi lần chạy, transcript luôn được coi là dữ liệu chứ không phải lệnh, không agent nào có công cụ gửi dữ liệu ra ngoài.

## 3. Thiết kế dữ liệu

**Đầu vào sau chuẩn hoá:** mỗi câu có ID riêng để mọi trích dẫn trỏ về đúng câu gốc, không phụ thuộc việc AI chép lại văn bản.

```json
{"id": "u042", "speaker": "Anh Hùng (PM)", "time": "41:05", "text": "OK vậy mình chốt AWS nhé"}
```

**Loại mục được trích xuất:** quyết định, việc cần làm, vướng mắc, yêu cầu, vấn đề chưa chốt, tri thức mới.

**Trạng thái của một quyết định:**

| Trạng thái | Ý nghĩa | Ví dụ câu nói |
| --- | --- | --- |
| `proposed` | Mới được đề xuất, chưa ai chốt | "Hay mình dùng on-premise?" |
| `superseded` | Bị thay bằng phương án khác | "On-premise đắt quá, bỏ đi" |
| `confirmed` | Đã chốt, có tín hiệu rõ và không bị phản bác | "OK vậy mình chốt AWS nhé" |
| `conditional` | Chốt nhưng phụ thuộc điều kiện | "Nếu khách đồng ý giá thì chốt B" |
| `deferred` | Hoãn, chờ thêm thông tin hoặc người khác | "Để anh hỏi sếp đã" |
| `open` | Có thảo luận nhưng không có kết luận | Cuộc tranh luận kết thúc mà không ai chốt |

**Đầu ra một mục:**

```json
{
  "item_id": "d03",
  "type": "decision",
  "topic": "Nhà cung cấp server",
  "content": "Chọn AWS",
  "status": "confirmed",
  "condition": null,
  "history": [
    {"status": "proposed", "content": "On-premise", "evidence": ["u008"]},
    {"status": "superseded", "reason": "chi phí vượt ngân sách", "evidence": ["u017"]},
    {"status": "confirmed", "content": "AWS", "evidence": ["u042"]}
  ],
  "owner": null,
  "deadline": null,
  "confidence": 0.86,
  "flags": [],
  "review": "pending"
}
```

Trường `owner`, `deadline` chỉ được điền khi có câu nói chứng minh, nếu không thì để `null`. Trường `flags` ghi lý do cần xem lại, ví dụ `no_closing_signal`, `authority_unclear`, `number_check`.

## 4. Thiết kế từng agent

| Agent | Đầu vào | Đầu ra | Quy tắc chính |
| --- | --- | --- | --- |
| **1. Chia chủ đề** | Danh sách câu; chương trình họp nếu có | Danh sách chủ đề, mỗi chủ đề gồm các đoạn câu (có thể không liền nhau) | Gộp các lần quay lại cùng một chủ đề. Nội dung ngoài chương trình xếp vào "chủ đề phát sinh". MVP dùng LLM trực tiếp; embedding chỉ thêm khi transcript quá dài |
| **2. Trích xuất** | Các câu của một chủ đề | Ứng viên: loại, nội dung, người nói, ID câu làm bằng chứng | Mọi mục phải có ít nhất 1 ID câu. Không tự điền người phụ trách, hạn chót, con số không có trong câu |
| **3. Theo dõi quyết định** | Ứng viên của một chủ đề, sắp theo thời gian; vai trò người dự nếu có | Trạng thái cuối + lịch sử, độ tin cậy, cờ | Chỉ gán `confirmed` khi có tín hiệu chốt và không bị phản bác sau đó. Ưu tiên câu tóm lại của chủ trì. Câu giả định, câu đùa, câu thuật lại không tính là chốt. Không chắc thì để `open` |
| **4. Kiểm chứng** | Mục `decision` và `action` + các câu bằng chứng | Đạt / không đạt, lý do | Kiểm tra câu bằng chứng có thật sự nói điều mục đó khẳng định không. Không đạt thì trả về Agent 2 làm lại 1 lần, vẫn không đạt thì gắn cờ |

**Các quy tắc bằng code (không cần AI):**

- ID câu trong bằng chứng phải tồn tại trong transcript, nếu không thì loại mục.
- Mục có số tiền, ngày, tên người luôn gắn cờ `number_check`.
- Người chốt không có vai trò chủ trì hoặc trưởng nhóm (khi có danh sách vai trò) thì gắn cờ `authority_unclear`.
- Mục độ tin cậy dưới 0,7 hoặc có cờ được đưa lên đầu danh sách duyệt.

**Bộ mẫu câu tiếng Việt đưa vào prompt:**

- Chốt: "chốt vậy nhé", "thống nhất là", "OK làm theo hướng", "vậy quyết là".
- Hoãn: "để tính sau", "để anh hỏi sếp đã", "tuần sau bàn tiếp".
- Không phải chốt: "hay là…", "giả sử…", "hôm trước sếp bảo…", "ừ" đứng một mình.

## 5. Kế hoạch xây dựng

**Làm theo thứ tự rủi ro giảm dần:** phần khó nhất và quan trọng nhất (theo dõi quyết định) được làm và đo sớm, giao diện làm sau cùng.

| Giai đoạn | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| **0. Chuẩn bị dữ liệu** | Viết và thu thập transcript kiểm thử, gán nhãn đáp án chuẩn theo schema | Có đủ transcript cho các tình huống ở mục 7, mỗi bản có đáp án |
| **1. Nền tảng** | Đọc file transcript, chuẩn hoá câu, định nghĩa schema Pydantic, khung điều phối | Một transcript bất kỳ được chuyển thành danh sách câu có ID |
| **2. Chia chủ đề + Trích xuất** | Prompt Agent 1, 2; quy tắc kiểm tra ID câu | Trích xuất đủ ứng viên, mọi mục có bằng chứng hợp lệ |
| **3. Theo dõi quyết định + Kiểm chứng** | Prompt Agent 3, 4; vòng làm lại 1 lần; các cờ bằng code | Chạy được toàn luồng, ra JSON đúng schema |
| **4. Đánh giá và tinh chỉnh** | Script so kết quả với đáp án, sửa prompt theo lỗi | Đạt ngưỡng ở mục 6 trên bộ kiểm thử |
| **5. Giao diện duyệt + xuất** | Bảng duyệt Streamlit (chấp nhận, sửa, loại), hiển thị trích dẫn và lịch sử, xuất JSON/Excel | Người dùng thử duyệt và xuất được một cuộc họp không cần hướng dẫn |
| **6. Thử với người dùng** | 2–3 người dùng thử trên transcript thật của họ (được phép) | Thu được thời gian hoàn thiện biên bản và tỷ lệ chấp nhận không cần sửa |

Nếu thiếu thời gian, cắt giai đoạn 6 trước và thu gọn giao diện ở giai đoạn 5 thành file Excel có cột duyệt. Không cắt giai đoạn 3 và 4.

## 6. Kế hoạch kiểm thử

**Kiểm thử ở ba mức:** từng agent, toàn luồng so với đáp án, và người dùng thật.

**Bộ dữ liệu:**

- 7 transcript tiếng Việt tự dựng, mỗi bản 10–40 phút, ứng với 7 tình huống ở mục 7.
- 2–3 transcript cuộc họp thật, được người tham dự cho phép và ẩn danh nếu cần.
- Đáp án chuẩn do con người gán theo đúng schema. Chấp nhận rằng bộ tự dựng có thể dễ hơn thực tế, nên kết quả trên transcript thật được báo cáo riêng.

**Các mức kiểm thử:**

| Mức | Kiểm tra gì | Cách làm |
| --- | --- | --- |
| Từng agent | Chia chủ đề đúng ranh giới; trích xuất đủ; trạng thái đúng; kiểm chứng bắt được trích dẫn sai | Cho đầu vào chuẩn từ đáp án, chỉ chạy một agent, so đầu ra |
| Toàn luồng | Kết quả cuối so với đáp án | Script chạy cả bộ, xuất bảng chỉ số |
| Ổn định | Chạy lại cùng transcript có ra cùng kết quả không | Chạy mỗi transcript 3 lần, đếm mục thay đổi trạng thái |
| Người dùng | Có giúp hoàn thiện biên bản nhanh và đúng hơn không | Người dùng thử duyệt kết quả, bấm giờ, ghi lại chỗ sửa |

**Chỉ số và ngưỡng đạt:**

| Chỉ số | Cách tính | Ngưỡng đạt MVP |
| --- | --- | --- |
| **Tỷ lệ chốt nhầm** | Số ý kiến trung gian bị gán `confirmed` / tổng số quyết định `confirmed` | ≤ 5% |
| Recall quyết định | Quyết định đúng tìm được / tổng quyết định trong đáp án | ≥ 85% |
| Precision việc cần làm | Việc đúng / tổng việc hệ thống đưa ra | ≥ 80% |
| Độ chính xác trích dẫn | Mục có câu bằng chứng thật sự chứng minh nội dung / tổng mục | ≥ 95% |
| Người phụ trách, hạn chót bịa | Trường được điền nhưng không có trong transcript | 0 trường hợp |
| Độ ổn định | Mục đổi trạng thái giữa 3 lần chạy | ≤ 10% |
| Tỷ lệ chấp nhận không cần sửa | Mục người dùng duyệt ngay / tổng mục | ≥ 70% |
| Thời gian hoàn thiện biên bản | So với người dùng tự làm tay cùng cuộc họp | Giảm ≥ 50% |
| Chi phí trên mỗi giờ họp | Tổng chi phí gọi LLM | Đo và ghi lại, chưa đặt ngưỡng |

Các ngưỡng là mục tiêu ban đầu, sẽ điều chỉnh sau lần đo đầu tiên. Tỷ lệ chốt nhầm được ưu tiên hơn recall: thà để một quyết định ở trạng thái "chưa chốt" cho người duyệt xác nhận, còn hơn ghi sai một quyết định.

## 7. Tình huống kiểm thử

**7 tình huống: 2 sản phẩm dự kiến làm tốt, 3 khó hoặc dữ liệu không rõ ràng, 2 dự kiến xử lý chưa tốt.** Cột "Kết quả thực tế" để trống, điền sau khi chạy.

| Mã | Nhóm | Tình huống | Kết quả mong đợi | Kết quả thực tế |
| --- | --- | --- | --- | --- |
| TC1 | Làm tốt | A đổi sang B, chủ trì chốt rõ | B `confirmed`, A `superseded` kèm lý do | |
| TC2 | Làm tốt | Việc cần làm có và không có hạn chót | Điền đúng người, hạn; thiếu thì để trống | |
| TC3 | Khó | Chủ đề quay lại sau 30 phút, dùng "cái đó" | Gộp vào cùng chủ đề, lấy kết luận sau | |
| TC4 | Không rõ ràng | Chốt mơ hồ, câu đùa, có điều kiện, hoãn | Đúng 4 trạng thái khác nhau, gắn cờ | |
| TC5 | Không rõ ràng | Transcript chỉ có "Speaker 1, 2", không có vai trò | Chạy được, người phụ trách "chưa xác định", cờ thẩm quyền | |
| TC6 | Chưa tốt | Transcript sai số tiền do lỗi ASR | Chỉ gắn cờ kiểm tra, không tự sửa được | |
| TC7 | Chưa tốt | Quyết định dựa vào cử chỉ và cuộc họp trước | Không nhận ra, để `open` hoặc bỏ sót | |

### TC1. A đổi sang B, chủ trì chốt rõ (làm tốt)

```
[05:12] Nam: Em đề xuất mình dùng server on-premise cho dự án này.
[18:40] Lan: On-premise thì chi phí ban đầu vượt ngân sách quý, không ổn.
[19:02] Lan: Hay mình chuyển qua AWS, trả theo tháng.
[41:05] Hùng (PM): OK, vậy mình chốt dùng AWS nhé.
```

- **Mong đợi:** quyết định "Dùng AWS" `confirmed`, bằng chứng câu 41:05. Lịch sử có on-premise `superseded`, lý do "vượt ngân sách". Không có mục nào ghi on-premise là quyết định.
- **Đạt khi:** trạng thái, lý do và trích dẫn đều đúng; độ tin cậy ≥ 0,8.

### TC2. Việc cần làm có và không có hạn chót (làm tốt)

```
[22:10] Hùng (PM): Minh làm tài liệu API, thứ Sáu này gửi anh nhé.
[22:18] Minh: Dạ vâng.
[23:40] Hùng (PM): Còn phần test tải thì ai đó cần xem lại.
```

- **Mong đợi:** việc 1 có `owner` = Minh, `deadline` = thứ Sáu. Việc 2 có `owner` = null, `deadline` = null, gắn cờ thiếu người phụ trách.
- **Đạt khi:** không tự gán việc 2 cho ai và không tự đặt hạn.

### TC3. Chủ đề quay lại sau 30 phút (khó)

```
[08:00] Lan: Ra mắt bản beta ngày 1/11 được không?
[08:30] Nam: Chắc được, để em xem.
   ... 30 phút bàn chủ đề khác ...
[39:15] Nam: Quay lại vụ lúc nãy, cái đó không kịp đâu, phải lùi sang 15/11.
[39:40] Hùng (PM): Thống nhất 15/11.
```

- **Mong đợi:** hai đoạn được gộp vào một chủ đề "Ngày ra mắt beta". Ngày 1/11 `superseded`, ngày 15/11 `confirmed`.
- **Đạt khi:** không có hai quyết định riêng rẽ; "cái đó" được hiểu là ngày ra mắt.

### TC4. Chốt mơ hồ, câu đùa, có điều kiện, hoãn (không rõ ràng)

```
[12:00] Nam: Hay bỏ luôn tính năng chat cho nhanh, haha.
[12:05] Lan: Ừ.
[25:30] Hùng (PM): Nếu khách đồng ý giá mới thì mình ký hợp đồng gói B.
[33:10] Lan: Ngân sách marketing để anh hỏi sếp đã rồi báo lại.
[45:00] Minh: Ừ thế đi.
```

- **Mong đợi:** bỏ tính năng chat không phải quyết định (câu đùa, "ừ" đứng một mình). Gói B là `conditional` kèm điều kiện. Ngân sách marketing là `deferred`. Câu "ừ thế đi" không rõ chốt cái gì nên không tạo quyết định, hoặc tạo mục `open` có cờ `no_closing_signal`.
- **Đạt khi:** không mục nào trong 4 câu này bị gán `confirmed`.

### TC5. Không có tên và vai trò người nói (không rõ ràng)

```
[10:00] Speaker 1: Tuần sau chốt dùng React cho front-end nhé.
[10:20] Speaker 2: Ok, em sẽ dựng khung dự án.
```

- **Mong đợi:** quyết định "Dùng React" được trích xuất nhưng gắn cờ `authority_unclear`, độ tin cậy thấp. Việc cần làm có `owner` = "Speaker 2" để người duyệt gán tên.
- **Đạt khi:** hệ thống không dừng, không tự đoán tên thật, và mục được đưa lên đầu danh sách duyệt.

### TC6. Transcript sai số tiền do lỗi ASR (dự kiến chưa tốt)

```
[30:00] Hùng (PM): Chốt ngân sách giai đoạn 1 là 30 triệu.
        (người nói thật ra nói "300 triệu")
```

- **Mong đợi:** hệ thống ghi "30 triệu" vì đó là nội dung transcript, nhưng gắn cờ `number_check` để người duyệt kiểm tra.
- **Vì sao thất bại:** MVP chỉ nhận văn bản, không có audio để nghe lại, nên không thể tự phát hiện hay sửa lỗi. Toàn bộ trách nhiệm dồn vào người duyệt.
- **Ghi nhận đạt khi:** cờ `number_check` có mặt. Ghi nhận thất bại: nội dung quyết định vẫn sai.
- **Hướng khắc phục:** phiên bản sau nhận audio, gắn đoạn ghi âm 15–30 giây vào mục có cờ; dùng tài liệu trước họp để đối chiếu con số.

### TC7. Quyết định dựa vào cử chỉ và cuộc họp trước (dự kiến chưa tốt)

```
[15:00] Hùng (PM): Như tuần trước đã bàn, mọi người đồng ý phương án đó chứ?
        (mọi người gật đầu, không ai nói gì)
[15:10] Hùng (PM): Rồi, chuyển sang phần tiếp.
```

- **Mong đợi thực tế:** hệ thống không biết "phương án đó" là gì và không thấy cử chỉ đồng ý. Nhiều khả năng bỏ sót, hoặc tạo mục `open` với nội dung không rõ.
- **Vì sao thất bại:** nội dung nằm ngoài transcript (cử chỉ) và ngoài cuộc họp (tuần trước). Liên kết nhiều cuộc họp nằm ngoài phạm vi MVP.
- **Ghi nhận đạt khi:** hệ thống không tự bịa nội dung phương án và không gán `confirmed`. Bỏ sót được chấp nhận và ghi lại là giới hạn đã biết.
- **Hướng khắc phục:** lấy kết quả đã duyệt của các cuộc họp trước theo dự án; khuyến nghị chủ trì nói rõ nội dung khi chốt.

## 8. Rủi ro triển khai và bước tiếp theo

| Rủi ro khi xây MVP | Cách xử lý |
| --- | --- |
| Bộ kiểm thử tự dựng quá dễ so với thực tế | Báo cáo riêng kết quả trên transcript thật; mời người khác viết thêm tình huống khó |
| Transcript dài vượt giới hạn ngữ cảnh hoặc tốn chi phí | Xử lý theo từng chủ đề; Agent 1 chạy theo từng cửa sổ rồi gộp |
| Kết quả không ổn định giữa các lần chạy | Nhiệt độ thấp, schema chặt, đo độ ổn định trong mỗi lần đánh giá |
| Sửa prompt để qua một tình huống lại làm hỏng tình huống khác | Chạy lại toàn bộ bộ kiểm thử sau mỗi lần sửa |
| Dữ liệu họp thật nhạy cảm | Xin phép trước, ẩn danh, xóa sau khi đánh giá, dùng nhà cung cấp LLM cam kết không huấn luyện trên dữ liệu |

**Bước tiếp theo sau MVP, theo thứ tự ưu tiên:**

1. Nhận audio, ASR tiếng Việt và gắn đoạn ghi âm vào mục có cờ (giải quyết TC6).
2. Kho tri thức theo dự án và liên kết quyết định giữa các cuộc họp (giải quyết TC7).
3. Agent Hỏi đáp (RAG) có trích dẫn, chuyển câu hỏi vượt quyền cho chủ trì.
4. Xuất sang Jira, wiki và kết nối nền tảng họp qua API chính thức.
