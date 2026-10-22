# Kết quả đánh giá – 2026-10-22 15:22

Model: `gpt-4.1-mini` (Agent 1, 2) / `gpt-4.1` (Agent 3, 4); bộ: quick; số lần chạy ca ngắn: 1, cuộc họp dài: 1

## Bộ ngắn (tests/fixtures)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 33.3% (n=3) (tham khảo) | ≤ 5.0% | ❌ |
| Recall quyết định | 100.0% (n=5) (tham khảo) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 66.7% (n=6) (tham khảo) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 100.0% (n=10) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=10) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=3) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=34) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=8) (tham khảo) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | không áp dụng (0 mẫu) | ≥ 75.0% | – |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=9) (tham khảo) | ≤ 0 | ✅ |
| Cờ kỳ vọng có mặt (expect_flags_any) | 100.0% (n=1) (tham khảo) | ≥ 100.0% | ✅ |
| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| TC1 | chấm điểm | ❌ 1 lỗi |
| TC2 | chấm điểm | ❌ 1 lỗi |
| TC3 | chấm điểm | ✅ đạt |
| TC4 | chấm điểm | ❌ 1 lỗi |
| TC5 | chấm điểm | ✅ đạt |
| TC6 | giới hạn đã biết | ✅ đạt |
| TC7 | giới hạn đã biết | ✅ đạt |

**TC1**
- Action thừa: [a01] "Lan chuẩn bị số liệu chi phí cho phương án on-premise" owner=Lan

**TC2**
- Chốt nhầm: [d01] "Minh xin nghỉ buổi chiều thứ Năm được chấp thuận" evidence=['u014']

**TC4**
- Action thừa: [a01] "Lan hỏi sếp về ngân sách marketing rồi báo lại" owner=Lan

## Bộ dài (test_cases_3_muc_do)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 81.8% (n=11) | ≤ 5.0% | ❌ |
| Recall quyết định | 90.0% (n=10) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 64.7% (n=17) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 96.2% (n=26) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=26) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=4) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=67) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=23) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | 60.0% (n=5) (tham khảo) | ≥ 75.0% | ❌ |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=25) | ≤ 0 | ✅ |
| Cờ kỳ vọng có mặt (expect_flags_any) | không áp dụng (0 mẫu) | ≥ 100.0% | – |
| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| CASE2 | chấm điểm | ❌ 32 lỗi |

**CASE2**
- Chốt nhầm: [d02] "Không mời Sơn Tùng vì ngân sách có hạn" evidence=['u029']
- Chốt nhầm: [d07] "Duyệt logo mới bản màu xanh lá" evidence=['u060']
- Chốt nhầm: [d09] "Ngọc tự quyết bài đăng giới thiệu ba vị" evidence=['u068']
- Chốt nhầm: [d10] "Ngọc tự quyết bài đăng giới thiệu ba vị, chạy trước ngày ra mắt một tuần để tạo tò mò" evidence=['u068']
- Chốt nhầm: [d25] "Sampling tại Coopmart thay vì Big C do phí cao gấp đôi" evidence=['u132']
- Chốt nhầm: [d08] "Ngọc lên kịch bản series 'một ngày với TeaGo', tuần sau gửi Phương xem" evidence=['u065']
- Chốt nhầm: [d15] "Làm trang đích đơn giản thôi" evidence=['u092']
- Chốt nhầm: [d18] "Sales tự đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt" evidence=['u104']
- Chốt nhầm: [d22] "Quay ngoài đường cho chân thật, Ngọc tự cân đối" evidence=['u118']
- Lịch sử thiếu "Chỉ chạy TikTok" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Bỏ sót decision: "Thuê freelancer dựng video, chi phí lấy từ ngân sách quảng cáo số"
- Sai trạng thái "Làm trang đích đơn giản có nút tìm đại lý (hỏi IT trước, bận thì thuê ngoài)": open, đáp án ['confirmed']
- Sai trạng thái "Content ưu tiên vị ô long": open, đáp án ['confirmed', 'proposed']
- Thiếu cờ number_check ở "Giá bán lẻ 28 nghìn/chai"
- Sai trạng thái "Ngày ra mắt 5/12": deferred, đáp án ['open', 'proposed']
- Sai owner "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": 'Bình', đáp án 'Khoa'
- Sai deadline "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": None, đáp án 'tuần này'
- Bỏ sót action: "Bình trình đề xuất OOH lên giám đốc tài chính"
- Bỏ sót action: "Ngọc lên kịch bản series 'một ngày với TeaGo' (~10 tập)"
- Sai owner "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'Hà'
- Sai deadline "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'đầu tuần sau'
- Trích dẫn lệch: "Thuê freelancer, chi phí lấy từ phần ngân sách quảng cáo số" evidence=['u129'], đáp án ['u094', 'u093']
- Bỏ sót action: "Ngọc làm bài đăng giới thiệu ba vị, chạy trước ra mắt 1 tuần"
- Bỏ sót request: "Ngọc cần thêm một người dựng video nếu chạy cả hai kênh"
- Action thừa: [a08] "Ngọc lên lịch đăng bài dự kiến" owner=Ngọc
- Action thừa: [a10] "Ngọc đưa màu xanh lá vào hướng dẫn thiết kế" owner=Ngọc
- Action thừa: [a04] "Khoa gửi đề xuất chi tiết biển quảng cáo trong tuần này" owner=Khoa
- Action thừa: [a09] "Tuấn xử lý nhạc nền khác cho TikTok" owner=Tuấn
- Action thừa: [a11] "Sales cung cấp danh sách đại lý cho trang đích" owner=Sales
- Action thừa: [a13] "Gửi đề xuất chương trình khuyến mãi cho đại lý cho Phương đầu tuần sau" owner=Hà
- Vi phạm: mời Sơn Tùng là câu đùa, không phải quyết định → [d02] "Không mời Sơn Tùng vì ngân sách có hạn"
- Các câu ['u030', 'u034', 'u131', 'u132'] không cùng một chủ đề (topics=['t02', 't09'])

## Tổng (ngắn + dài)

Chỉ số tổng hợp trên các ca không phải giới hạn đã biết (số lần chạy mỗi ca: 1):

| Chỉ số | Giá trị | Ngưỡng | Đạt |
| --- | --- | --- | --- |
| Tỷ lệ chốt nhầm | 71.4% (n=14) | ≤ 5.0% | ❌ |
| Recall quyết định | 93.3% (n=15) | ≥ 85.0% | ✅ |
| Precision việc cần làm | 65.2% (n=23) | ≥ 80.0% | ❌ |
| Độ chính xác trích dẫn | 97.2% (n=36) | ≥ 95.0% | ✅ |
| Owner/deadline bịa | 0 (n=36) | ≤ 0 | ✅ |
| Trạng thái đúng cho mục chưa chốt | 100.0% (n=7) (tham khảo) | ≥ 80.0% | ✅ |
| Đoạn trích kiểm chứng được | 100.0% (n=101) | ≥ 95.0% | ✅ |
| Owner/deadline có câu nguồn riêng | 100.0% (n=31) | ≥ 100.0% | ✅ |
| Phạm vi tri thức đúng | 60.0% (n=5) (tham khảo) | ≥ 75.0% | ❌ |
| Quyết định mâu thuẫn không gắn cờ | 0 (n=34) | ≤ 0 | ✅ |
| Cờ kỳ vọng có mặt (expect_flags_any) | 100.0% (n=1) (tham khảo) | ≥ 100.0% | ✅ |
| Độ ổn định | (chạy với `--repeat 3`) | ≤ 10% | – |

| Ca | Loại | Kết quả |
| --- | --- | --- |
| TC1 | chấm điểm | ❌ 1 lỗi |
| TC2 | chấm điểm | ❌ 1 lỗi |
| TC3 | chấm điểm | ✅ đạt |
| TC4 | chấm điểm | ❌ 1 lỗi |
| TC5 | chấm điểm | ✅ đạt |
| TC6 | giới hạn đã biết | ✅ đạt |
| TC7 | giới hạn đã biết | ✅ đạt |
| CASE2 | chấm điểm | ❌ 32 lỗi |

**TC1**
- Action thừa: [a01] "Lan chuẩn bị số liệu chi phí cho phương án on-premise" owner=Lan

**TC2**
- Chốt nhầm: [d01] "Minh xin nghỉ buổi chiều thứ Năm được chấp thuận" evidence=['u014']

**TC4**
- Action thừa: [a01] "Lan hỏi sếp về ngân sách marketing rồi báo lại" owner=Lan

**CASE2**
- Chốt nhầm: [d02] "Không mời Sơn Tùng vì ngân sách có hạn" evidence=['u029']
- Chốt nhầm: [d07] "Duyệt logo mới bản màu xanh lá" evidence=['u060']
- Chốt nhầm: [d09] "Ngọc tự quyết bài đăng giới thiệu ba vị" evidence=['u068']
- Chốt nhầm: [d10] "Ngọc tự quyết bài đăng giới thiệu ba vị, chạy trước ngày ra mắt một tuần để tạo tò mò" evidence=['u068']
- Chốt nhầm: [d25] "Sampling tại Coopmart thay vì Big C do phí cao gấp đôi" evidence=['u132']
- Chốt nhầm: [d08] "Ngọc lên kịch bản series 'một ngày với TeaGo', tuần sau gửi Phương xem" evidence=['u065']
- Chốt nhầm: [d15] "Làm trang đích đơn giản thôi" evidence=['u092']
- Chốt nhầm: [d18] "Sales tự đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt" evidence=['u104']
- Chốt nhầm: [d22] "Quay ngoài đường cho chân thật, Ngọc tự cân đối" evidence=['u118']
- Lịch sử thiếu "Chỉ chạy TikTok" superseded trong "Kênh quảng cáo số: chạy cả TikTok và Facebook, TikTok 70% / Facebook 30%"
- Bỏ sót decision: "Thuê freelancer dựng video, chi phí lấy từ ngân sách quảng cáo số"
- Sai trạng thái "Làm trang đích đơn giản có nút tìm đại lý (hỏi IT trước, bận thì thuê ngoài)": open, đáp án ['confirmed']
- Sai trạng thái "Content ưu tiên vị ô long": open, đáp án ['confirmed', 'proposed']
- Thiếu cờ number_check ở "Giá bán lẻ 28 nghìn/chai"
- Sai trạng thái "Ngày ra mắt 5/12": deferred, đáp án ['open', 'proposed']
- Sai owner "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": 'Bình', đáp án 'Khoa'
- Sai deadline "Khoa gửi đề xuất OOH chi tiết (vị trí, báo giá) cho Bình": None, đáp án 'tuần này'
- Bỏ sót action: "Bình trình đề xuất OOH lên giám đốc tài chính"
- Bỏ sót action: "Ngọc lên kịch bản series 'một ngày với TeaGo' (~10 tập)"
- Sai owner "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'Hà'
- Sai deadline "Hà đề xuất chương trình khuyến mãi cho đại lý, gửi Phương duyệt": None, đáp án 'đầu tuần sau'
- Trích dẫn lệch: "Thuê freelancer, chi phí lấy từ phần ngân sách quảng cáo số" evidence=['u129'], đáp án ['u094', 'u093']
- Bỏ sót action: "Ngọc làm bài đăng giới thiệu ba vị, chạy trước ra mắt 1 tuần"
- Bỏ sót request: "Ngọc cần thêm một người dựng video nếu chạy cả hai kênh"
- Action thừa: [a08] "Ngọc lên lịch đăng bài dự kiến" owner=Ngọc
- Action thừa: [a10] "Ngọc đưa màu xanh lá vào hướng dẫn thiết kế" owner=Ngọc
- Action thừa: [a04] "Khoa gửi đề xuất chi tiết biển quảng cáo trong tuần này" owner=Khoa
- Action thừa: [a09] "Tuấn xử lý nhạc nền khác cho TikTok" owner=Tuấn
- Action thừa: [a11] "Sales cung cấp danh sách đại lý cho trang đích" owner=Sales
- Action thừa: [a13] "Gửi đề xuất chương trình khuyến mãi cho đại lý cho Phương đầu tuần sau" owner=Hà
- Vi phạm: mời Sơn Tùng là câu đùa, không phải quyết định → [d02] "Không mời Sơn Tùng vì ngân sách có hạn"
- Các câu ['u030', 'u034', 'u131', 'u132'] không cùng một chủ đề (topics=['t02', 't09'])

Token: vào 327,386 / ra 62,810 qua 362 lần gọi; chi phí ước tính ≈ $0.8520; thời gian 614s.

Ghi chú TC6: hệ thống chỉ gắn cờ `number_check`, không thể phát hiện số sai khi không có audio. TC7: chỉ yêu cầu không có item `confirmed` bịa cho 'phương án đó'.
