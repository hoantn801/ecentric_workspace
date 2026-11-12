# Copyright (c) 2026, eCentric and contributors
"""May trang thai cua phong quiz + ma phong. Thuan Python.

    lobby --start--> question(0) --lock / het gio--> locked --reveal--> reveal
    reveal --board--> board ; reveal|board --next--> question(i+1) ; reveal|board --end--> ended
    moi pha con song --cancel--> cancelled ; --end--> ended (ket thuc som: chot diem tu cac cau
    da khoa).
Nguoi dan bam chuyen cau (Hoan chot) - server KHONG tu nhay cau, chi tu KHOA khi het gio.
"""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain.errors import QuizError

_ALLOWED = {
    C.ACT_START: (C.PHASE_LOBBY,),
    C.ACT_LOCK: (C.PHASE_QUESTION,),
    C.ACT_REVEAL: (C.PHASE_LOCKED,),
    C.ACT_BOARD: (C.PHASE_REVEAL,),
    C.ACT_NEXT: (C.PHASE_REVEAL, C.PHASE_BOARD),
    C.ACT_END: C.LIVE_PHASES,
    C.ACT_CANCEL: C.LIVE_PHASES,
}
_MSG = {C.ACT_START: "Phòng đã bắt đầu rồi.", C.ACT_LOCK: "Câu này không còn mở.",
        C.ACT_REVEAL: "Cần khoá câu trước khi công bố đáp án.",
        C.ACT_BOARD: "Chưa công bố đáp án câu này.", C.ACT_NEXT: "Chưa công bố đáp án câu này.",
        C.ACT_END: "Phòng đã kết thúc.", C.ACT_CANCEL: "Phòng đã kết thúc."}


def transition(action, phase, index, total, players=0):
    """-> (pha moi, chi so cau moi). Sai luat -> QuizError (message cho nguoi dan)."""
    if action not in _ALLOWED:
        raise QuizError("Thao tác không hợp lệ.")
    if phase not in _ALLOWED[action]:
        raise QuizError(_MSG[action])
    if action == C.ACT_START:
        if players < 1:
            raise QuizError("Chưa có ai vào phòng.")
        return C.PHASE_QUESTION, 0
    if action == C.ACT_LOCK:
        return C.PHASE_LOCKED, index
    if action == C.ACT_REVEAL:
        return C.PHASE_REVEAL, index
    if action == C.ACT_BOARD:
        return C.PHASE_BOARD, index
    if action == C.ACT_NEXT:
        if index + 1 >= total:
            raise QuizError("Đây là câu cuối - bấm Kết thúc để về đích.")
        return C.PHASE_QUESTION, index + 1
    if action == C.ACT_END:
        return C.PHASE_ENDED, index
    return C.PHASE_CANCELLED, index


def show_board(index, total, mode):
    """Sau khi cong bo cau `index` co chen bang xep hang khong (cau cuoi -> ve dich luon)."""
    if index + 1 >= total:
        return False
    if mode == C.BOARD_EACH:
        return True
    if mode == C.BOARD_FIVE:
        return (index + 1) % 5 == 0
    return False


def next_action(phase, index, total, board_mode):
    """Nut chinh cua bang nguoi dan."""
    if phase == C.PHASE_LOBBY:
        return C.ACT_START
    if phase == C.PHASE_QUESTION:
        return C.ACT_LOCK
    if phase == C.PHASE_LOCKED:
        return C.ACT_REVEAL
    if phase == C.PHASE_REVEAL:
        if show_board(index, total, board_mode):
            return C.ACT_BOARD
        return C.ACT_END if index + 1 >= total else C.ACT_NEXT
    if phase == C.PHASE_BOARD:
        return C.ACT_END if index + 1 >= total else C.ACT_NEXT
    return None


def make_code(rng, taken):
    """Ma 6 so, khong bat dau bang 0, khong trung phong dang song."""
    for _ in range(200):
        code = str(rng.randint(10 ** (C.CODE_LEN - 1), 10 ** C.CODE_LEN - 1))
        if code not in taken:
            return code
    raise QuizError("Không tạo được mã phòng, thử lại.")


def deadline_ms(opened_ms, time_sec):
    return opened_ms + (C.LEAD_IN_SEC + int(time_sec)) * 1000


def elapsed_ms(opened_ms, received_ms):
    """Thoi gian tra loi tinh tu luc het 3 giay chuan bi."""
    return max(0, int(received_ms - opened_ms - C.LEAD_IN_SEC * 1000))


def accepting(phase, now_ms, deadline):
    return phase == C.PHASE_QUESTION and now_ms <= deadline + C.GRACE_MS
