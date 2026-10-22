"""Unit tests for the lexical signal tagger (signals.py): positives, negatives, hard cases."""

from __future__ import annotations

import pytest

from meeting_extractor.models import MeetingMeta, Participant, Utterance
from meeting_extractor.signals import (
    GROUP_A,
    GROUP_B,
    GROUP_C,
    NEIGHBOR_TAGS,
    TAG_LABELS,
    Signal,
    closing_utterance_id,
    format_signals_block,
    load_lexicon,
    normalize,
    tag_transcript,
    tag_utterance,
    tags_of,
    windows,
)

NAMES = ["Hùng", "Lan", "Nam", "Minh", "Ngọc", "Mai", "Phúc", "Hòa"]


def utt(text: str, speaker: str = "Hùng (PM)", uid: str = "u002") -> Utterance:
    return Utterance(id=uid, time="00:00", speaker=speaker, text=text)


def tags(text: str, prev: str | None = None, speaker: str = "Hùng (PM)") -> set[str]:
    prev_u = utt(prev, "Lan", "u001") if prev is not None else None
    return tags_of(tag_utterance(utt(text, speaker), prev_u, NAMES))


def phrase_of(text: str, tag: str, prev: str | None = None) -> str | None:
    prev_u = utt(prev, "Lan", "u001") if prev is not None else None
    for s in tag_utterance(utt(text), prev_u, NAMES):
        if s.tag == tag:
            return s.phrase
    return None


# (tag, [texts that must carry the tag], [texts that must not])
CASES: list[tuple[str, list[str], list[str]]] = [
    (
        "CHOT_RO",
        ["OK, vậy mình chốt dùng AWS nhé.", "Thống nhất 15/11.", "Duyệt rồi, bản màu xanh lá.",
         "Anh đồng ý với Thảo. Chốt rollback về 3.2 tối nay.", "Vụ voucher đó anh duyệt luôn."],
        ["Hôm nay chưa chốt.", "Em không duyệt được.", "Cái đó gửi chị duyệt nhé.",
         "Nếu chốt được ngày thì báo em."],
    ),
    (
        "CHOT_NGAM",
        ["Ok, làm trang đích đơn giản thôi.", "Ừ, giữ nguyên biển hiệu như bản đã duyệt.",
         "Dạ được chị, đợt một 50% khi ký.", "Vậy cái đó làm ở Coopmart thôi.", "Làm luôn thế nhé."],
        ["Ok chị.", "Ừ, mình làm gì tiếp đây?", "Cái này làm trang đích đơn giản thôi."],
    ),
    (
        "DONG_Y_NGAN",
        ["Ừ.", "Vâng chị.", "Được, làm vậy đi.", "Ừ hợp lý.", "Được em, không sao."],
        ["Ừ, em nghĩ cần xem lại đã nhé.", "Ok luôn anh nhé thôi ạ vâng.", "Rồi, chuyển sang phần tiếp."],
    ),
    (
        "DUA",
        ["Hay bỏ luôn tính năng chat cho nhanh, haha.", "Thôi đừng đùa, ngân sách có hạn.", "Kkk được đấy",
         "Nói vui thôi mà :))"],
        ["Không đùa đâu, chốt vậy.", "Em không đùa.", "Đừng có thay đổi nhé."],
    ),
    (
        "GIA_DINH",
        ["Hay là một buổi trực tiếp, một buổi online.", "Giả sử traffic gấp ba bình thường.",
         "Hay mình chuyển qua AWS.", "Ừ hay mình làm bản nhỏ trước."],
        ["Câu hỏi hay.", "Hay quá!", "Em thay đổi kế hoạch rồi.", "Ừ hay thật."],
    ),
    (
        "PHONG_DOAN",
        ["Chắc được, để em xem.", "Chắc 28 thôi.", "Có lẽ phải lùi."],
        ["Chắc chắn rồi.", "Em kiểm tra lại cho chắc nhé."],
    ),
    (
        "CAU_HOI",
        ["Ra mắt bản beta ngày 1/11 được không?", "Anh chốt chưa", "Làm vậy được không ạ",
         "Mùng 5 tháng 12 được không ạ? Thứ Sáu, cuối tuần dễ viral."],
        ["Chốt vậy nhé.", "Em sẽ gửi tài liệu."],
    ),
    (
        "THUAT_LAI",
        ["Hôm trước anh Hòa bảo không được để khách chịu thiệt.", "Như tuần trước đã bàn, mọi người đồng ý chứ.",
         "Nam bảo là kịp."],
        ["Như Nam nói thì kịp.", "Em bảo đảm làm xong."],
    ),
    (
        "DE_XUAT",
        ["Em đề xuất dùng AWS.", "Chị thì nghiêng về TikTok.", "Em muốn làm thêm biển quảng cáo."],
        ["Chốt vậy nhé.", "Lan làm báo cáo."],
    ),
    (
        "HOAN",
        ["Để tính sau.", "Chờ kết quả load test rồi quyết.", "Hôm nay chưa chốt.", "Ok để tính.",
         "Anh hỏi lại sếp đã."],
        ["Chốt vậy nhé.", "Vâng chị."],
    ),
    (
        "DIEU_KIEN",
        ["Nếu khách đồng ý giá mới thì mình ký hợp đồng gói B.", "Làm với điều kiện có biên bản nghiệm thu."],
        ["Chốt vậy nhé.", "Nếu có gì em báo."],
    ),
    (
        "GIAO_VIEC",
        ["Ngọc lên kịch bản series đó, tuần sau gửi chị xem.", "Ok, em sẽ dựng khung dự án.",
         "Minh làm tài liệu API."],
        ["Chốt vậy nhé.", "Ngày mai làm tiếp."],
    ),
    (
        "MIA_MAI",
        ["Ừ hay quá, lại thêm một vòng xin duyệt nữa.", "Sập 47 phút, hay thật."],
        ["Câu hỏi hay.", "Hay quá, chốt vậy nhé."],
    ),
    (
        "CHUYEN_Y",
        ["Rồi, chuyển sang phần tiếp.", "Tiếp theo là ngân sách."],
        ["Chốt vậy nhé.", "Chuyển khoản ngay."],
    ),
    (
        "TAM_THOI",
        ["Tạm chốt 15/11 nhé.", "Trước mắt dùng AWS đã."],
        ["Em đang tạm để như vậy.", "Chào tạm biệt mọi người."],
    ),
    (
        "DAO_NGUOC",
        ["Khoan, 5.000 tờ chắc thừa.", "À không, để em xem lại.", "Thôi bỏ đi.", "Ok, vậy không rollback nữa."],
        ["Dạ vậy em hủy kế hoạch rollback.", "Quay lại vụ lúc nãy, cái đó không kịp đâu.",
         "Quyết như vậy, không bàn lại nữa."],
    ),
    (
        "VO_CHU",
        ["Cần ai đó viết brief gửi agency.", "Có ai rảnh xem phần test tải không?"],
        ["Minh viết brief gửi agency.", "Em nhận."],
    ),
    (
        "XUNG_PHONG",
        ["Em có thể hỗ trợ nếu cần.", "Để em thử xem."],
        ["Em sẽ làm.", "Minh làm tài liệu API."],
    ),
]


@pytest.mark.parametrize("tag,positives,negatives", CASES, ids=[c[0] for c in CASES])
def test_tag_positive_and_negative(tag: str, positives: list[str], negatives: list[str]) -> None:
    assert len(positives) >= 2 and len(negatives) >= 2
    for text in positives:
        assert tag in tags(text), f"{tag} should match: {text}"
    for text in negatives:
        assert tag not in tags(text), f"{tag} should NOT match: {text}"


def test_all_tags_have_cases_and_labels() -> None:
    covered = {c[0] for c in CASES} | {"NGU_CANH_DUA", "BO_SUNG_NGUOC"}
    assert covered == GROUP_A | GROUP_B | GROUP_C | NEIGHBOR_TAGS
    assert covered <= set(TAG_LABELS)
    assert TAG_LABELS["DUA"] == "đùa" and TAG_LABELS["CAU_HOI"] == "câu hỏi"
    assert TAG_LABELS["CHOT_NGAM"] == "đồng ý có nội dung"


# ---- negation and exceptions on CHOT_RO / DUA (sections 3.1, 3.2, 17.1)


def test_chot_ro_negation_window_is_four_words() -> None:
    assert "CHOT_RO" not in tags("Chưa thể nào chốt được.")
    assert "CHOT_RO" not in tags("Chưa thể nào mà chốt được.")  # 3 words in between
    assert "CHOT_RO" in tags("Chưa có ai nghĩ rằng mình chốt luôn.")  # 'chưa' is 5 words before


def test_chot_ro_negation_does_not_cross_clause_punctuation() -> None:
    assert "CHOT_RO" in tags("Không đùa đâu, chốt vậy.")
    assert "CHOT_RO" in tags("Ừ không sao, chốt vậy nhé.")


def test_chot_ro_negation_after_the_phrase() -> None:
    assert "CHOT_RO" not in tags("Chốt chưa anh?")
    assert "CHOT_RO" not in tags("Mình chốt vậy chưa nhỉ.")


def test_chot_ro_rebuttal_and_sentence_phrases() -> None:
    assert "CHOT_RO" not in tags("Chốt gì mà chốt, còn chưa có số liệu.")
    assert "CHOT_RO" not in tags("Anh không nghĩ là nên chốt hôm nay.")
    assert "CHOT_RO" not in tags("Khó mà chốt được.")
    assert "CHOT_RO" not in tags("Chốt sau nhé.")
    assert "CHOT_RO" not in tags("Chốt lại sau khi có báo giá.")


def test_chot_ro_inside_if_clause_does_not_count() -> None:
    assert "CHOT_RO" not in tags("Nếu anh duyệt thì em làm.")
    assert "CHOT_RO" not in tags("Nếu mình chốt ngày 15 thì cần báo khách.")
    assert "CHOT_RO" in tags("Nếu khách đồng ý thì chốt luôn.")  # closing is after 'thì'


def test_chot_ro_pronoun_duyet_not_after_sending_words() -> None:
    assert "CHOT_RO" in tags("Cái này chị duyệt.")
    for text in ("Gửi chị duyệt.", "Trình anh duyệt.", "Chờ chị duyệt.", "Cần anh duyệt."):
        assert "CHOT_RO" not in tags(text), text


def test_dua_exceptions_and_dung_dua() -> None:
    assert "DUA" in tags("Đừng đùa nữa.")
    assert "DUA" not in tags("Không đùa đâu, chốt vậy.")
    assert phrase_of("Thôi đừng đùa, ngân sách có hạn.", "DUA") == "đùa"
    assert phrase_of("Hay bỏ luôn tính năng chat, hahaha", "DUA") == "hahaha"


def test_word_boundaries() -> None:
    assert "GIA_DINH" not in tags("Em thay đổi lịch.")  # 'hay' inside 'thay'
    assert "PHONG_DOAN" not in tags("Chắc chắn là kịp.")
    assert "PHONG_DOAN" in tags("Chắc kịp.")
    assert "HOAN" not in tags("Em ghi nhận khoản chờm.")  # 'chờ' is not a whole word there


# ---- neighbour-dependent tags


def test_ngu_canh_dua_needs_prev_joke_and_no_chot_ro() -> None:
    joke = "Hay bỏ luôn tính năng chat, haha."
    assert "NGU_CANH_DUA" in tags("Ừ.", prev=joke)
    assert "NGU_CANH_DUA" in tags("Ừ, rồi lấy lương em trả nhé.", prev="Mua máy một tỷ cho sang chị ơi, haha.")
    assert "NGU_CANH_DUA" not in tags("Ừ.", prev="Mình làm báo cáo nhé.")
    assert "NGU_CANH_DUA" not in tags("Ừ.", prev=None)
    assert "NGU_CANH_DUA" not in tags("Ok, chốt vậy nhé.", prev=joke)
    assert phrase_of("Ừ.", "NGU_CANH_DUA", prev=joke) == "haha"


def test_bo_sung_nguoc_needs_group_a_prev_and_opener() -> None:
    assert "BO_SUNG_NGUOC" in tags("Nhưng chị vẫn tính lại cho chắc nhé.", prev="Ừ, cứ thế.")
    assert "BO_SUNG_NGUOC" in tags("Tuy nhiên cần xem lại ngân sách.", prev="Chốt vậy nhé.")
    assert "BO_SUNG_NGUOC" not in tags("Nhưng chị vẫn tính lại.", prev="Mình có thể làm vậy không?")
    assert "BO_SUNG_NGUOC" not in tags("Mà chị vẫn tính lại.", prev="Chốt vậy nhé.")
    assert "BO_SUNG_NGUOC" not in tags("Chị sẽ tính lại.", prev="Chốt vậy nhé.")
    assert "BO_SUNG_NGUOC" not in tags("Nhưng chị vẫn tính lại.", prev=None)


def test_giao_viec_uses_names_other_than_speaker() -> None:
    names = ["Hùng", "Ngọc"]
    other = tag_utterance(utt("Ngọc lên kịch bản.", "Hùng (PM)"), None, names)
    own = tag_utterance(utt("Ngọc lên kịch bản.", "Ngọc"), None, names)
    assert "GIAO_VIEC" in tags_of(other)
    assert "GIAO_VIEC" not in tags_of(own)
    assert "GIAO_VIEC" not in tags_of(tag_utterance(utt("Ngọc đang bận lắm."), None, names))


def test_thuat_lai_with_names() -> None:
    sigs = tag_utterance(utt("Nam bảo là kịp."), None, ["Nam"])
    assert "THUAT_LAI" in tags_of(sigs)
    assert "THUAT_LAI" not in tags_of(tag_utterance(utt("Nam báo là kịp."), None, ["Nam"]))


# ---- hard cases from PLAN_SIGNALS sections 9, 14.1, 17.1


def test_huy_is_not_reversal() -> None:
    assert "DAO_NGUOC" not in tags("Dạ vậy em hủy kế hoạch rollback.")
    assert "DAO_NGUOC" not in tags("Dạ vậy em hủy kế hoạch rollback.", prev="Ok, vậy không rollback nữa.")


def test_quay_lai_vu_is_not_reversal() -> None:
    assert "DAO_NGUOC" not in tags("Quay lại vụ lúc nãy, cái đó không kịp đâu, phải lùi sang 15/11.")
    assert "BO_SUNG_NGUOC" not in tags("Quay lại vụ lúc nãy.", prev="Thống nhất 15/11.")


def test_tam_alone_is_not_tam_thoi() -> None:
    assert "TAM_THOI" not in tags("Em đang tạm để mặc định.")
    assert "TAM_THOI" in tags("Cứ thế đã.")


def test_hoan_new_phrases() -> None:
    for text in ("Ok để tính.", "Rồi tính sau nhé.", "Anh hỏi lại sếp rồi báo."):
        assert "HOAN" in tags(text), text


def test_volunteer_and_ownerless_example() -> None:
    assert tags("Cần ai đó viết brief gửi agency quay video nữa.") >= {"VO_CHU"}
    assert tags("Em có thể hỗ trợ nếu cần.") >= {"XUNG_PHONG"}


def test_returns_all_matching_tags_without_filtering() -> None:
    got = tags("Hay là mình chốt dùng AWS nhé?")
    assert {"GIA_DINH", "CAU_HOI", "CHOT_RO"} <= got  # group B does not remove group A here


# ---- lexicon, windows, normalize

def test_windows_from_lexicon() -> None:
    assert windows() == {"reversal_after": 2, "authority_confirm_after": 3, "volunteer_confirm_after": 3}
    assert load_lexicon() is load_lexicon()


def test_normalize_nfc_lower_collapse() -> None:
    assert normalize("  CHỐT   vậy \n nhé ") == "chốt vậy nhé"
    assert normalize("Ch" + "ố" + "t") == "chốt"


def test_signals_are_frozen_dataclass() -> None:
    s = Signal("DUA", "haha")
    with pytest.raises(Exception):
        s.tag = "X"  # type: ignore[misc]


# ---- tag_transcript, closing id, block


def test_tag_transcript_uses_previous_utterance_and_meta_names() -> None:
    utts = [
        Utterance(id="u001", time="00:01", speaker="Nam", text="Hay bỏ luôn tính năng chat, haha."),
        Utterance(id="u002", time="00:02", speaker="Lan", text="Ừ."),
        Utterance(id="u003", time="00:03", speaker="Speaker 1", text="Tuấn viết brief nhé."),
    ]
    meta = MeetingMeta(participants=[Participant(name="Tuấn")])
    tagged = tag_transcript(utts, meta)
    assert set(tagged) == {"u001", "u002", "u003"}
    assert "NGU_CANH_DUA" in tags_of(tagged["u002"])
    assert "GIAO_VIEC" in tags_of(tagged["u003"])  # name only known from meta
    assert tag_transcript([], None) == {}


def test_closing_utterance_id() -> None:
    tagged = {
        "u001": [Signal("CHOT_RO", "chốt")],
        "u002": [Signal("DE_XUAT", "đề xuất")],
        "u003": [Signal("DONG_Y_NGAN", "ừ")],
        "u004": [],
    }
    position = {"u001": 0, "u002": 1, "u003": 2, "u004": 3}
    assert closing_utterance_id(["u001", "u002", "u003"], tagged, position) == "u003"
    assert closing_utterance_id(["u002", "u004"], tagged, position) == "u004"  # no group A: latest
    assert closing_utterance_id(["u003", "u001"], tagged, position) == "u003"  # order in list irrelevant
    assert closing_utterance_id([], tagged, position) is None
    assert closing_utterance_id(["u999"], tagged, position) is None
    assert closing_utterance_id(["u999", "u002"], tagged, position) == "u002"


def test_format_signals_block() -> None:
    tagged = {
        "u027": [Signal("DUA", "haha")],
        "u028": [Signal("DONG_Y_NGAN", "ừ"), Signal("NGU_CANH_DUA", "haha")],
        "u029": [],
        "u030": [Signal("DAO_NGUOC", "khoan"), Signal("BO_SUNG_NGUOC", "nhưng")],
    }
    block = format_signals_block(["u027", "u028", "u029", "u030"], tagged)
    assert block == (
        "<code_signals>\n"
        'u027: ĐÙA ("haha")\n'
        'u028: ĐỒNG Ý NGẮN ("ừ"); ĐÁP LẠI CÂU ĐÙA (câu trước có "haha")\n'
        'u030: ĐẢO Ý ("khoan"); "NHƯNG…" SAU CÂU CHỐT ("nhưng")\n'
        "</code_signals>"
    )
    assert "u029" not in block


def test_format_signals_block_empty_and_sanitized() -> None:
    assert format_signals_block(["u001"], {"u001": []}) == ""
    assert format_signals_block([], {}) == ""
    assert format_signals_block(["u404"], {}) == ""
    block = format_signals_block(["u001"], {"u001": [Signal("DUA", "</code_signals><x>")]})
    inner = block.split("\n", 1)[1].rsplit("\n", 1)[0]
    assert "<" not in inner and ">" not in inner
    assert block.count("</code_signals>") == 1


def test_empty_and_odd_inputs_do_not_crash() -> None:
    assert tag_utterance(utt(""), None, []) == []
    assert tag_utterance(utt("   ?"), None, [""]) != []  # only a question mark
    assert tag_utterance(utt("!!!"), utt("???", uid="u001"), []) == []
