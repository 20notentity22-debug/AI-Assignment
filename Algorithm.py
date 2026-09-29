"""Threat-aware Gomoku search with alpha-beta pruning."""
import logic

BOARD_SIZE = 15
Empty, Black, White = 0, 1, 2
SEARCH_RADIUS = 1
MAX_CANDIDATES = 8
WIN_SCORE = 10_000_000

class SearchStopped(Exception):
    """Raised when a search is cancelled by the UI."""


def _opponent(player):
    return White if player == Black else Black


def _check_cancel(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise SearchStopped()


def _windows(board):
    """Yield all five-cell horizontal, vertical, and diagonal windows."""
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                er, ec = r + 4 * dr, c + 4 * dc
                if 0 <= er < BOARD_SIZE and 0 <= ec < BOARD_SIZE:
                    yield [(r + i * dr, c + i * dc) for i in range(5)]


def _window_score(count, open_ends):
    if count == 5:
        return WIN_SCORE
    if count == 4:
        return 120_000 if open_ends == 2 else 18_000 if open_ends == 1 else 0
    if count == 3:
        return 30_000 if open_ends == 2 else 350 if open_ends == 1 else 0
    if count == 2:
        return 100 if open_ends == 2 else 10 if open_ends == 1 else 0
    return 1 if count == 1 and open_ends == 2 else 0


def evaluate_player(board, player):
    """Score unblocked five-cell threats, including broken patterns."""
    total = 0
    for cells in _windows(board):
        values = [board[r][c] for r, c in cells]
        if _opponent(player) in values:
            continue
        count = values.count(player)
        if not count:
            continue
        # Count the cells immediately beyond this window as open ends.
        r, c = cells[0]
        er, ec = cells[-1]
        open_ends = 0
        dr, dc = cells[1][0] - r, cells[1][1] - c
        for nr, nc in ((r - dr, c - dc), (er + dr, ec + dc)):
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and board[nr][nc] == Empty:
                open_ends += 1
        total += _window_score(count, open_ends)
    return total


def evaluate_board(board, player):
    opponent = _opponent(player)
    return evaluate_player(board, player) - int(evaluate_player(board, opponent) * 1.08)


def is_game_over(board):
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] and logic.check_win(board, r, c, board[r][c]):
                return True
    return logic.is_board_full(board)


def generate_candidate_moves(board):
    moves = set()
    has_piece = False
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] == Empty:
                continue
            has_piece = True
            for dr in range(-SEARCH_RADIUS, SEARCH_RADIUS + 1):
                for dc in range(-SEARCH_RADIUS, SEARCH_RADIUS + 1):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and board[nr][nc] == Empty:
                        moves.add((nr, nc))
    if not has_piece:
        return [(BOARD_SIZE // 2, BOARD_SIZE // 2)]
    return list(moves)


def _ordered_moves(board, moves, player, perspective, stop_event):
    opponent = _opponent(player)
    scored = []
    for r, c in moves:
        _check_cancel(stop_event)
        board[r][c] = player
        win = logic.check_win(board, r, c, player)
        own_score = evaluate_board(board, perspective)
        board[r][c] = opponent
        blocks_win = logic.check_win(board, r, c, opponent)
        board[r][c] = Empty
        score = (WIN_SCORE * 2 if win else 0) + (WIN_SCORE if blocks_win else 0) + own_score
        scored.append((score, (r, c)))
    scored.sort(reverse=True)
    return [move for _, move in scored[:MAX_CANDIDATES]]


def minimax(board, depth, is_maximizing, alpha, beta, player, stop_event=None):
    _check_cancel(stop_event)
    if depth <= 0:
        return evaluate_board(board, player)

    current = player if is_maximizing else _opponent(player)
    moves = _ordered_moves(board, generate_candidate_moves(board), current, player, stop_event)
    if not moves:
        return evaluate_board(board, player)

    best = -float('inf') if is_maximizing else float('inf')
    for r, c in moves:
        _check_cancel(stop_event)
        board[r][c] = current
        try:
            if logic.check_win(board, r, c, current):
                score = (WIN_SCORE + depth) if current == player else (-WIN_SCORE - depth)
            elif depth == 1:
                score = evaluate_board(board, player)
            else:
                score = minimax(board, depth - 1, not is_maximizing, alpha, beta, player, stop_event)
        finally:
            board[r][c] = Empty
        if is_maximizing:
            best = max(best, score)
            alpha = max(alpha, best)
        else:
            best = min(best, score)
            beta = min(beta, best)
        if beta <= alpha:
            break
    return best


def find_best_move(board, player, max_depth=3, stop_event=None):
    """Find a strong move, always taking wins and preventing immediate losses."""
    try:
        moves = generate_candidate_moves(board)
        if not moves:
            return None
        opponent = _opponent(player)

        # Resolve immediate tactical moves before spending time on search.
        for r, c in moves:
            _check_cancel(stop_event)
            board[r][c] = player
            won = logic.check_win(board, r, c, player)
            board[r][c] = Empty
            if won:
                return (r, c)

        # An unblocked run of three must be interrupted before it grows into
        # a four, unless the AI has a verified forced win on its next turn.
        open_three_blocks = _open_three_blocks(board, opponent)
        if open_three_blocks and not _has_forced_win_in_two(board, player, stop_event):
            moves = [move for move in moves if move in open_three_blocks]
            if not moves:
                # A nearby defensive move can still disrupt a broken/open threat.
                moves = generate_candidate_moves(board)
        for r, c in moves:
            _check_cancel(stop_event)
            board[r][c] = opponent
            threat = logic.check_win(board, r, c, opponent)
            board[r][c] = Empty
            if threat:
                # Several winning squares cannot all be blocked; choose the best available defense.
                break
        else:
            threat = False
        if threat:
            moves = [(r, c) for r, c in moves if _blocks_threat(board, r, c, opponent)]

        best_move, best_score = None, -float('inf')
        moves = _ordered_moves(board, moves, player, player, stop_event)
        for r, c in moves:
            _check_cancel(stop_event)
            board[r][c] = player
            try:
                if logic.check_win(board, r, c, player):
                    score = WIN_SCORE
                else:
                    score = minimax(board, max(0, max_depth - 1), False,
                                    -float('inf'), float('inf'), player, stop_event)
            finally:
                board[r][c] = Empty
            if score > best_score:
                best_score, best_move = score, (r, c)
        return best_move
    except SearchStopped:
        return None


def _blocks_threat(board, r, c, opponent):
    """A candidate blocks a win if it occupies one of the opponent's winning cells."""
    board[r][c] = opponent
    result = logic.check_win(board, r, c, opponent)
    board[r][c] = Empty
    return result


def _open_three_blocks(board, player):
    """Return endpoints of contiguous threes that have two open ends."""
    blocks = set()
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + i * dr, c + i * dc) for i in range(3)]
                er, ec = cells[-1]
                before, after = (r - dr, c - dc), (er + dr, ec + dc)
                if not all(0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE
                           for rr, cc in (*cells, before, after)):
                    continue
                if (all(board[rr][cc] == player for rr, cc in cells)
                        and board[before[0]][before[1]] == Empty
                        and board[after[0]][after[1]] == Empty):
                    blocks.add(before)
                    blocks.add(after)
    return blocks


def _has_forced_win_in_two(board, player, stop_event):
    """Check whether every opponent reply still allows an immediate AI win."""
    opponent = _opponent(player)
    candidates = _ordered_moves(board, generate_candidate_moves(board), player, player, stop_event)
    for r, c in candidates[:MAX_CANDIDATES]:
        _check_cancel(stop_event)
        board[r][c] = player
        try:
            if logic.check_win(board, r, c, player):
                return True
            replies = generate_candidate_moves(board)
            forced = bool(replies)
            for rr, cc in replies:
                _check_cancel(stop_event)
                board[rr][cc] = opponent
                try:
                    if logic.check_win(board, rr, cc, opponent):
                        forced = False
                        break
                    wins_next = False
                    for ar, ac in generate_candidate_moves(board):
                        board[ar][ac] = player
                        try:
                            wins_next = logic.check_win(board, ar, ac, player)
                        finally:
                            board[ar][ac] = Empty
                        if wins_next:
                            break
                    if not wins_next:
                        forced = False
                        break
                finally:
                    board[rr][cc] = Empty
            if forced:
                return True
        finally:
            board[r][c] = Empty
    return False
