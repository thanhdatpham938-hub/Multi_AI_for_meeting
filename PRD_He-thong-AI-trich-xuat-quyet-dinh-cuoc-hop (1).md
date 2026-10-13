# Mission 1 – Hệ thống AI trích xuất quyết định cuộc họp

Các công cụ ghi chú hiện nay trả lời câu hỏi **cuộc họp đã nói gì**. Hệ thống này trả lời **cuộc họp đã chốt gì, thay đổi thế nào và dựa trên bằng chứng nào**. Kết quả là dữ liệu có cấu trúc, đã được con người xác nhận, dùng tiếp được cho công việc và kho tri thức, độc lập với nền tảng họp.

## 1. Vấn đề & người dùng

**Vấn đề thực sự không phải thiếu biên bản, mà là cam kết sau cuộc họp bị thất lạc hoặc ghi sai.** Một cuộc họp dài có nhiều chủ đề đan xen, ý kiến thay đổi nhiều lần và nhiều người nói cùng lúc. Người ghi chép thủ công không theo kịp. Bản tóm tắt AI thông thường lại gộp mọi thứ vào một đoạn văn. Hậu quả:

- Phương án trung gian bị ghi nhầm thành quyết định cuối cùng (đề xuất A, nhưng cuối buổi chốt B).
- Công việc không có người phụ trách hoặc hạn chót. Vấn đề chưa chốt bị coi như đã chốt.
- Kết quả nằm trong văn bản tự do nên không đưa thẳng vào Jira, Excel hay wiki được, và mất lý do "vì sao chọn B".

| Nhóm người dùng | Họ cần gì |
| --- | --- |
| **Chính: người theo dõi sau họp** (PM, trưởng nhóm, thư ký) | Danh sách quyết định, việc cần làm, vấn đề còn mở đúng và đủ, để giao việc và đôn đốc |
| Người tham dự | Biết chính xác việc của mình, hạn chót, ai giao |
| Người vắng mặt, người đến sau | Tra cứu nhanh đã chốt gì và vì sao, không phải nghe lại cả buổi |

**Kết quả họ thực sự cần:** trong vài phút sau cuộc họp, có danh sách đã xác nhận gồm quyết định cuối cùng, việc cần làm (ai, làm gì, khi nào) và vấn đề còn mở. Mỗi mục có trích dẫn đến đoạn hội thoại gốc và xuất được sang công cụ đang dùng.

## 2. Giải pháp & luồng hoạt động

**Giải pháp là một lớp xử lý sau transcript, gồm 5 agent AI chuyên trách, một bộ điều phối bằng code và một điểm duyệt của con người.** Hệ thống nhận transcript từ bất kỳ nguồn nào (file xuất từ Zoom, Meet, Teams, hoặc ghi âm họp trực tiếp), theo dõi diễn biến từng chủ đề và xuất ra dữ liệu có cấu trúc.

**Luồng chính** (chỉ mục đã được con người duyệt mới được xuất ra):

```
Đầu vào: transcript hoặc ghi âm          Bối cảnh (tùy chọn): chương trình họp,
          │                               người dự, vai trò, tài liệu dự án
          ▼                                          │ từ vựng, vai trò
┌──────── Bộ điều phối bằng code ─────────┐          │
│  Chuẩn hoá transcript  ◄────────────────┼──────────┘
│          ▼                              │
│  Agent Chia chủ đề                      │
│          ▼                              │
│  Agent Trích xuất  ◄─────┐              │
│          ▼               │ không đạt →  │
│  Agent Theo dõi quyết định│ làm lại 1 lần│ ──► Agent Hỏi đáp (RAG) ◄── Người dùng hỏi
│          ▼               │              │            │ vượt quyền
│  Agent Kiểm chứng ───────┘              │            ▼
└──────────┼──────────────────────────────┘     Chủ trì hoặc thư ký
           ▼
    Con người duyệt (chấp nhận / sửa / loại) ─ ─ ► chỗ sửa → dữ liệu đánh giá
           ▼
    Xuất dữ liệu có cấu trúc (JSON, Excel, Jira, wiki)
```

**Vì sao multi-agent có điều phối:** mỗi bước cần prompt, đầu vào và cách đánh giá khác nhau, nên tách agent giúp kiểm thử riêng từng bước và biết lỗi nằm ở đâu. Thứ tự các bước là cố định, nên bộ điều phối viết bằng code để ổn định, rẻ và dễ truy vết. Chỉ agent Theo dõi quyết định và agent Hỏi đáp được tự quyết (tra cứu thêm, từ chối, chuyển cho con người), vì đó là chỗ đầu vào khó lường trước.

| Agent | Nhiệm vụ | Đầu ra |
| --- | --- | --- |
| Chia chủ đề | Gom câu theo chủ đề, kể cả khi chủ đề được quay lại sau 30 phút | Các đoạn theo chủ đề, có mốc thời gian |
| Trích xuất | Tìm quyết định, việc cần làm, vướng mắc, yêu cầu, vấn đề chưa chốt, tri thức mới | Ứng viên kèm trích dẫn câu gốc |
| Theo dõi quyết định | Sắp các lần nhắc theo thời gian, xác định trạng thái cuối: đề xuất, bị thay thế, chốt, chốt có điều kiện, hoãn | Mục có trạng thái và lịch sử A → B |
| Kiểm chứng | Kiểm tra trích dẫn có thật sự chứng minh nội dung không. Không đạt thì trả về agent Trích xuất làm lại tối đa 1 lần, vẫn không đạt thì gắn cờ | Độ tin cậy, cờ cần xem lại |
| Hỏi đáp (RAG) | Trả lời câu hỏi về cuộc họp và tài liệu, luôn có trích dẫn | Câu trả lời hoặc chuyển cho chủ trì |

**Điểm khác biệt so với sản phẩm hiện có:**

| Tiêu chí | Otter, Fireflies | Teams Facilitator, Meet Gemini | Hệ thống này |
| --- | --- | --- | --- |
| Đầu ra | Tóm tắt, việc cần làm | Ghi chú, việc cần làm đề xuất | Dữ liệu có cấu trúc theo schema |
| Diễn biến quyết định (A → B) | Không thể hiện | Chỉ kết quả cuối | Lưu lịch sử, lý do, người chốt |
| Bằng chứng | Người dùng tự đọc lại | Người dùng tự đọc lại | Trích dẫn + agent kiểm chứng + độ tin cậy |
| Nền tảng | Bot vào Zoom, Meet, Teams | Chỉ trong nền tảng của mình | Mọi nguồn transcript, kể cả họp trực tiếp |
| Vấn đề chưa chốt, hoãn | Lẫn trong tóm tắt | Lẫn trong ghi chú | Trạng thái riêng, không bị coi là đã chốt |

## 3. AI, dữ liệu & con người

**Nguyên tắc: AI đề xuất, con người chốt. Mọi mục phải có bằng chứng. AI chỉ làm việc trên dữ liệu của cuộc họp đó.**

| | AI làm | AI không làm |
| --- | --- | --- |
| Hiểu nội dung | Chia chủ đề, trích xuất các loại thông tin, theo dõi trạng thái quyết định, gắn trích dẫn và độ tin cậy | Không coi ý kiến nói sau cùng là quyết định khi thiếu tín hiệu chốt. Không coi câu đùa, câu giả định, câu thuật lại là quyết định |
| Thông tin chi tiết | Ghi người phụ trách, hạn chót, con số khi chúng được nói ra | Không bịa người phụ trách, hạn chót, con số. Thiếu thì để "chưa có" |
| Hỏi đáp | Trả lời có trích dẫn từ transcript và tài liệu cuộc họp | Không trả lời ngoài phạm vi cuộc họp. Câu hỏi vượt quyền thì chuyển cho chủ trì hoặc thư ký |
| Hành động | Đề xuất danh sách để duyệt | Không tự gửi việc hay đẩy dữ liệu ra ngoài khi chưa được duyệt |
| Con người | Dùng tên và vai trò để gán việc | Không suy luận thông tin cá nhân nhạy cảm. Không chấm điểm hay đánh giá từng thành viên |
| Dữ liệu | Xử lý trong phạm vi quyền của chủ cuộc họp | Không đưa dữ liệu ra ngoài tổ chức, không dùng để huấn luyện mô hình |

**Dữ liệu và công cụ cần có:**

- **Bắt buộc:** transcript có tên người nói và mốc thời gian.
- **Nên có:** danh sách người dự kèm vai trò (để gán việc và biết ai có quyền chốt), chương trình họp.
- **Tùy chọn:** tài liệu dự án (chia chunk, embedding cho RAG, và làm bộ từ vựng riêng cho ASR), file ghi âm.
- **Công cụ:** LLM (model nhỏ cho chia chủ đề và trích xuất, model mạnh cho theo dõi quyết định và kiểm chứng), vector DB, ASR tiếng Việt, giao diện rà soát, bộ xuất JSON/Excel/Jira.
- **Lấy dữ liệu từ nền tảng họp:** chỉ qua file xuất hoặc API chính thức (ví dụ Zoom RTMS, Microsoft Graph), không cào dữ liệu từ web app. Người tham dự phải được thông báo khi cuộc họp được ghi.

**Con người tham gia ở đâu:**

1. **Trước họp** (không bắt buộc): cung cấp chương trình họp, người dự, tài liệu.
2. **Sau xử lý:** gán tên cho người nói nếu transcript chỉ có "Speaker 1, 2", rồi **duyệt từng mục** (chấp nhận, sửa, loại). Mục có độ tin cậy thấp được đưa lên đầu. Chỉ dữ liệu đã duyệt mới có giá trị chính thức.
3. **Khi có câu hỏi vượt quyền:** chủ trì hoặc thư ký trả lời thay AI.
4. **Phản hồi:** mỗi lần người dùng sửa một mục trở thành dữ liệu để đánh giá và cải thiện hệ thống.

**Ví dụ một mục đầu ra** (diễn biến A → B được lưu lại thay vì chỉ ghi kết quả cuối):

```json
{
  "type": "decision",
  "topic": "Nhà cung cấp server",
  "content": "Chọn phương án B (AWS)",
  "status": "confirmed",
  "history": [
    {"status": "proposed", "content": "Phương án A (on-premise)", "speaker": "Anh Nam", "time": "05:12"},
    {"status": "superseded", "reason": "chi phí vượt ngân sách", "speaker": "Chị Lan", "time": "18:40"},
    {"status": "confirmed", "evidence": "OK vậy mình chốt AWS nhé", "speaker": "Anh Hùng (PM)", "time": "41:05"}
  ],
  "owner": null,
  "deadline": null,
  "confidence": 0.86,
  "review": "pending"
}
```

## 4. Quyết định & rủi ro

**Hệ thống không cố loại bỏ hoàn toàn lỗi, mà được thiết kế để biết khi nào mình không chắc, đánh dấu chỗ đó và chuyển cho con người.**

**Các quyết định thiết kế và đánh đổi:**

| Quyết định | Lý do | Đánh đổi |
| --- | --- | --- |
| Xử lý **sau họp**, không thời gian thực | Thấy toàn bộ diễn biến nên ít nhầm ý kiến trung gian thành kết luận. Chi phí thấp hơn | Không hỗ trợ được trong lúc họp |
| Multi-agent với **bộ điều phối bằng code** | Kiểm thử riêng từng agent, biết lỗi ở đâu, ổn định, rẻ | Kém linh hoạt với luồng bất thường |
| Chia theo **chủ đề**, không theo thời gian | Bắt buộc để gom các lần quay lại một chủ đề | Khó làm hơn chia theo thời gian |
| **Con người duyệt** trước khi xuất | Một quyết định sai bị đẩy vào Jira gây hại nhiều hơn vài phút rà soát | Thêm 3–5 phút sau mỗi cuộc họp |
| **Nhận transcript** trước, tích hợp nền tảng sau | Đúng yêu cầu tối thiểu, tránh rủi ro điều khoản và quyền truy cập | Người dùng thêm một thao tác tải file |
| Đầu ra theo **schema cố định** | Xuất được sang công cụ khác, đo được độ chính xác | Kém tự nhiên hơn văn bản tự do |

**Các rủi ro có thể khiến giải pháp thất bại:**

| Rủi ro | Hậu quả | Cách xử lý |
| --- | --- | --- |
| **Chốt giả, quyết định ngầm**: "ừ thế đi", câu đùa, câu giả định, "để anh hỏi sếp đã" | Ý kiến trung gian thành quyết định chính thức | Bắt buộc có tín hiệu chốt rõ ràng, không bị phản bác sau đó. Thêm trạng thái "hoãn", "chốt có điều kiện". Bộ mẫu câu chốt và câu hoãn tiếng Việt. Mục không chắc chắn được gắn mức tin cậy thấp và chuyển cho người duyệt kèm mốc thời gian và đoạn ghi âm tương ứng để nghe lại |
| **Thiếu dữ liệu người dự và chủ đề** | Không biết "Speaker 2" là ai, không biết ai có quyền chốt | Chạy được khi thiếu dữ liệu, chất lượng giảm theo mức. Người dùng gán tên một lần cho mỗi người nói. Không rõ thẩm quyền thì đánh dấu "cần xác nhận" |
| **Nhiều người nói chồng lên nhau** | Mất câu chốt, gán sai người nói | Ưu tiên nguồn âm thanh tách theo người. Đoạn chồng lấn là vùng tin cậy thấp, được đưa lên đầu danh sách duyệt. Trích dẫn kèm mốc thời gian để nghe lại |
| **ASR tiếng Việt chưa chính xác** (giọng vùng miền, lẫn tiếng Anh, thuật ngữ) | Sai tên, số tiền, ngày, dẫn đến quyết định sai | Dùng tài liệu trước họp làm bộ từ vựng riêng. Số tiền, ngày, tên người luôn được đánh dấu để kiểm tra. Đo riêng lỗi ASR và lỗi phân tích |
| **Đảo ngược quyết định giữa các cuộc họp** | Không biết B đang thay thế quyết định A của tuần trước | Liên kết giữa các cuộc họp, cảnh báo "thay thế quyết định ngày X" |
| **Chi phí vận hành nhiều agent cao** | Chi phí mỗi cuộc họp vượt giá trị mang lại | Điều phối bằng code, phân tầng model, mỗi agent chỉ đọc đoạn liên quan, kiểm chứng chỉ chạy trên quyết định và việc cần làm, RAG chỉ chạy khi có câu hỏi. Đo chi phí trên mỗi giờ họp ở MVP |
| **Rò rỉ dữ liệu qua RAG, prompt injection** | Người không dự họp đọc được nội dung họp kín. Tài liệu chứa lệnh độc hại | Phân quyền theo từng cuộc họp, kiểm tra quyền trước khi tìm kiếm. Coi transcript và tài liệu là dữ liệu, không phải lệnh. Agent không có công cụ gửi dữ liệu ra ngoài |
| **Người dùng không duyệt, hoặc sản phẩm bị dùng để giám sát** | Lỗi đi thẳng vào hệ thống. Nhân viên mất lòng tin, nói kém thẳng thắn | Chỉ xuất khi đã duyệt. Chỉ yêu cầu duyệt mục tin cậy thấp. Không phân tích cá nhân, cho phép tạm dừng ghi âm |

Ngoài ra còn rủi ro về độ ổn định của mô hình, lỗi lan truyền giữa các agent và việc thiếu dữ liệu đánh giá tiếng Việt. Các rủi ro này được xử lý bằng đánh giá riêng từng agent, lưu đầu ra trung gian và lưu phiên bản prompt/model cho mỗi lần chạy.

## 5. Kiểm chứng & MVP

**MVP chỉ cần chứng minh một điều: hệ thống phân biệt được ý kiến trung gian và quyết định cuối cùng, kèm bằng chứng.** Nếu điều đó đúng, mọi tính năng khác chỉ là mở rộng.

**Bộ dữ liệu kiểm chứng:** 5–10 transcript tiếng Việt, gồm cuộc họp thật (được phép) và kịch bản tự dựng. Mỗi bộ cố tình có tình huống khó: A đổi sang B, chủ đề quay lại sau 30 phút, chốt rồi hoãn, quyết định có điều kiện, câu đùa, người không có thẩm quyền nói "chốt". Con người tự gán nhãn đáp án chuẩn.

| Chỉ số | Đo cái gì | Vì sao quan trọng |
| --- | --- | --- |
| **Tỷ lệ chốt nhầm** | Ý kiến trung gian bị ghi thành quyết định cuối | Chỉ số chính, bám thẳng vào yêu cầu của đề |
| Precision / recall | Quyết định và việc cần làm tìm đúng và đủ | Đo chất lượng trích xuất |
| Độ chính xác trích dẫn | Trích dẫn chỉ đúng câu gốc chứng minh cho mục | Đo khả năng chống bịa |
| Người phụ trách, hạn chót | Gán đúng người, đúng ngày, không bịa | Quyết định giá trị của việc cần làm |
| Tỷ lệ chấp nhận không cần sửa | Phần trăm mục người dùng duyệt ngay | Đo độ tin cậy trong thực tế |
| Thời gian hoàn thiện biên bản | So với làm tay | Đo giá trị cho người dùng |
| Chi phí trên mỗi giờ họp | Tổng chi phí LLM và ASR | Kiểm tra tính khả thi khi vận hành |

Ngoài đo toàn hệ thống, mỗi agent được đánh giá riêng để biết lỗi bắt đầu từ bước nào.

**Thứ tự ưu tiên hiện thực hóa:**

1. Nhận transcript dạng văn bản có tên người nói. Định nghĩa schema đầu ra.
2. Agent Chia chủ đề và Trích xuất có trích dẫn.
3. Agent Theo dõi quyết định, phần giải quyết A → B. Chạy trên bộ kiểm chứng và đo.
4. Giao diện rà soát đơn giản (chấp nhận, sửa, loại) và xuất JSON/Excel.

**Chủ động để sau:** tích hợp Zoom, Meet, Teams; xử lý thời gian thực; ASR và tách người nói từ audio; embedding tài liệu và chatbot RAG; liên kết giữa nhiều cuộc họp; biểu đồ. Các phần này có giá trị nhưng không chứng minh được điểm cốt lõi.

## 3 câu hỏi bắt buộc

### Câu 1. Nếu chỉ được giải quyết 01 vấn đề quan trọng nhất, bạn chọn vấn đề nào? Người dùng là ai và kết quả họ thực sự cần là gì?

**Vấn đề chọn:** Sau cuộc họp, quyết định cuối cùng và việc cần làm không được ghi nhận đúng và đủ. Ý kiến trung gian bị ghi thành quyết định. Việc cần làm thiếu người phụ trách hoặc hạn chót. Vấn đề chưa chốt bị coi như đã chốt. Giao việc, đôn đốc hay lưu tri thức đều dựa trên danh sách này, nên sai ở đây là sai toàn bộ phía sau.

**Người dùng:** người chịu trách nhiệm theo dõi sau họp, tức PM, trưởng nhóm hoặc thư ký.

**Kết quả họ cần:** trong vài phút sau họp, có một danh sách đã xác nhận gồm quyết định cuối cùng, việc cần làm (ai, làm gì, khi nào) và vấn đề còn mở. Mỗi mục có trích dẫn câu nói gốc, sẵn sàng để giao việc và đôn đốc.

### Câu 2. Nếu chỉ có 03 ngày để xây phiên bản đầu tiên, bạn sẽ làm phần nào trước và chủ động chưa làm những gì? Vì sao?

**Làm trước:** chuỗi agent cốt lõi gồm Chia chủ đề, Trích xuất có trích dẫn, Theo dõi quyết định (xử lý A → B, chưa chốt, hoãn) và Kiểm chứng. Kèm theo là một giao diện duyệt đơn giản (chấp nhận, sửa, loại) và xuất JSON/Excel. Đầu vào là transcript dạng văn bản có tên người nói.

**Chủ động chưa làm:** chatbot RAG, embedding tài liệu, tích hợp Zoom/Meet/Teams, xử lý thời gian thực, ASR từ audio, liên kết nhiều cuộc họp.

**Vì sao:** chỉ cần danh sách quyết định và việc cần làm có lý do và trích dẫn là người dùng đã giao việc, đôn đốc được. Các phần chưa làm đều là mở rộng, không giúp chứng minh hệ thống phân biệt đúng ý kiến trung gian và quyết định cuối cùng.

### Câu 3. Nếu trong cùng một cuộc họp, một vấn đề được thảo luận và thay đổi nhiều lần trước khi đi đến kết luận cuối cùng, bạn sẽ làm thế nào để hệ thống không biến các ý kiến trung gian thành quyết định chính thức?

Hệ thống không đọc cả transcript rồi tóm tắt một lần, mà xử lý theo bốn bước.

1. **Gom theo chủ đề:** agent Chia chủ đề gom mọi lần nhắc đến cùng một vấn đề, kể cả khi vấn đề được quay lại sau 30 phút.
2. **Theo dõi trạng thái:** với từng vấn đề, agent Theo dõi quyết định sắp các lần nhắc theo thời gian. Mỗi ý kiến được gắn một trạng thái: *đề xuất, bị thay thế, chốt, chốt có điều kiện* hoặc *hoãn*. Toàn bộ lịch sử thay đổi được lưu lại.
3. **Quy tắc chốt:** một ý kiến chỉ thành quyết định khi có tín hiệu chốt rõ ràng và không bị phản bác sau đó. Câu tóm lại của chủ trì cuối buổi được ưu tiên. Không có tín hiệu chốt thì để trạng thái "chưa chốt", không đoán.
4. **Con người xác nhận:** mục có độ tin cậy thấp được chuyển cho người duyệt, kèm mốc thời gian và đoạn ghi âm để nghe lại. Chỉ mục đã duyệt mới trở thành quyết định chính thức.
