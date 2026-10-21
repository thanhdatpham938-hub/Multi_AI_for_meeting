"""Audio input: speech-to-text with speaker diarization via the OpenAI transcription API."""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .llm import OPENAI_DEFAULT_BASE_URL, LLMError
from .models import Utterance
from .parsing import make_id

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # OpenAI upload limit; no chunking in this phase
SUPPORTED_EXTENSIONS = (".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm")


# ---------------------------------------------------------------- helpers


def format_time(seconds: float) -> str:
    """Seconds -> 'mm:ss', or 'h:mm:ss' from one hour up (both accepted by the transcript parser)."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


_LABEL_PREFIX_RE = re.compile(r"^(?:speaker|spk)[\s_-]*", re.IGNORECASE)


def _direct_label(raw: Any) -> str | None:
    """'A' / 'speaker_0' / 'SPEAKER-2' -> 'Speaker A' / 'Speaker 0' / 'Speaker 2'; None if not normalizable."""
    core = _LABEL_PREFIX_RE.sub("", str(raw if raw is not None else "").strip()).strip(" _-")
    if core.isdigit():
        return f"Speaker {int(core)}"
    if len(core) == 1 and core.isalpha():
        return f"Speaker {core.upper()}"
    return None


def build_speaker_map(raws: Iterable[Any]) -> dict[str, str]:
    """Map every raw API label to a name that always satisfies `parsing.is_anonymous_speaker`.

    Labels that cannot be normalized directly (multi-letter, empty...) get 'Speaker <n>' in order of
    first appearance, skipping numbers already used by directly normalized labels.
    """
    ordered = list(dict.fromkeys(str(r if r is not None else "").strip() for r in raws))
    mapping = {r: d for r in ordered if (d := _direct_label(r))}
    used = set(mapping.values())
    counter = 0
    for raw in ordered:
        if raw in mapping:
            continue
        counter += 1
        while f"Speaker {counter}" in used:
            counter += 1
        mapping[raw] = f"Speaker {counter}"
        used.add(mapping[raw])
    return mapping


def speaker_label(raw: Any, mapping: dict[str, str] | None = None) -> str:
    """Normalized name for one raw label (see `build_speaker_map`)."""
    key = str(raw if raw is not None else "").strip()
    if mapping is not None and key in mapping:
        return mapping[key]
    return _direct_label(key) or build_speaker_map([key])[key]


def _field(obj: Any, name: str) -> Any:
    """Read a field from an SDK object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def check_audio_file(path: Path) -> int:
    """Validate extension and size BEFORE any API call. Returns size in bytes."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file audio: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Định dạng audio '{path.suffix}' chưa được hỗ trợ. Dùng một trong: {', '.join(SUPPORTED_EXTENSIONS)}."
        )
    size = path.stat().st_size
    if size > MAX_AUDIO_BYTES:
        raise ValueError(
            f"File audio quá lớn: {size / 1024 / 1024:.1f} MB (giới hạn {MAX_AUDIO_BYTES // 1024 // 1024} MB). "
            "Hãy nén sang mp3 bitrate thấp (ví dụ 32–64 kbps, mono) hoặc cắt ngắn file rồi thử lại."
        )
    return size


def segments_to_utterances(response: Any) -> tuple[list[Utterance], list[str]]:
    """Convert a diarized_json response to utterances. Defensive: bad segments are skipped with a warning.

    Consecutive segments of the same speaker are kept separate (matches API timestamps one-to-one).
    Raises LLMError when the response has no usable segment at all.
    """
    segments = _field(response, "segments")
    if not segments:
        raise LLMError(
            "API chuyển giọng nói không trả đoạn nào (segments rỗng hoặc thiếu). "
            "Kiểm tra file có chứa tiếng nói không, hoặc thử lại."
        )
    speaker_map = build_speaker_map(_field(sg, "speaker") for sg in segments)
    utterances: list[Utterance] = []
    warnings: list[str] = []
    prev_end = 0.0
    for index, seg in enumerate(segments, start=1):
        text = str(_field(seg, "text") or "").strip()
        if not text:
            warnings.append(f"Bỏ qua đoạn audio #{index}: không có nội dung.")
            continue
        start = _to_float(_field(seg, "start"))
        if start is None:
            start = prev_end
            warnings.append(f"Đoạn audio #{index} thiếu mốc bắt đầu, tạm dùng mốc kết thúc đoạn trước ({format_time(start)}).")
        end = _to_float(_field(seg, "end"))
        if end is None or end < start:
            end = start
        raw_speaker = _field(seg, "speaker")
        if not str(raw_speaker or "").strip():
            warnings.append(f"Đoạn audio #{index} thiếu nhãn người nói, gán '{speaker_label(raw_speaker, speaker_map)}'.")
        utterances.append(
            Utterance(
                id=make_id(len(utterances) + 1),
                time=format_time(start),
                speaker=speaker_label(raw_speaker, speaker_map),
                text=text,
                start_sec=start,
                end_sec=end,
            )
        )
        prev_end = end
    if not utterances:
        raise LLMError("API chuyển giọng nói chỉ trả các đoạn rỗng, không có nội dung để phân tích.")
    return utterances, warnings


def make_openai_client(settings: Settings) -> Any:
    import openai

    if not settings.openai_api_key:
        raise LLMError("Thiếu OPENAI_API_KEY để chuyển giọng nói. Hãy tạo file .env từ .env.example.")
    # Always pass base_url: the SDK would otherwise read the raw OPENAI_BASE_URL env var (may hold a comment).
    return openai.OpenAI(
        api_key=settings.openai_api_key, base_url=settings.openai_base_url or OPENAI_DEFAULT_BASE_URL
    )


# ---------------------------------------------------------------- public API


def transcribe_with_warnings(
    path: str | Path, settings: Settings | None = None, *, client: Any = None
) -> tuple[list[Utterance], list[str]]:
    """Transcribe an audio file. `client` is injectable for tests (no real API call)."""
    audio = Path(path)
    check_audio_file(audio)  # fail before touching the API
    settings = settings or load_settings()
    client = client or make_openai_client(settings)
    try:
        with audio.open("rb") as handle:
            response = client.audio.transcriptions.create(
                model=settings.transcribe_model,
                file=handle,
                response_format="diarized_json",
                chunking_strategy="auto",  # required for audio longer than 30 s
            )
    except OSError as exc:
        raise LLMError(f"Không đọc được file audio {audio}: {exc}") from exc
    except Exception as exc:  # openai.OpenAIError and network errors
        raise LLMError(f"Chuyển giọng nói thất bại ({type(exc).__name__}): {exc}") from exc
    return segments_to_utterances(response)


def transcribe(path: str | Path, settings: Settings | None = None, *, client: Any = None) -> list[Utterance]:
    return transcribe_with_warnings(path, settings, client=client)[0]


def save_audio(src: str | Path, run_dir: str | Path) -> Path:
    """Copy the audio file into runs/<run_id>/audio.<ext>."""
    src_path = Path(src)
    dest = Path(run_dir) / f"audio{src_path.suffix.lower()}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dest)
    return dest


def clip_range(utterance: Utterance, pad: float = 8) -> tuple[float, float]:
    """(start, end) in seconds to play for an utterance, padded on both sides and clamped at 0."""
    if utterance.start_sec is None:
        raise ValueError(f"Câu {utterance.id} không có mốc thời gian audio.")
    end = utterance.end_sec if utterance.end_sec is not None else utterance.start_sec
    return max(0.0, utterance.start_sec - pad), end + pad
