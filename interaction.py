import tkinter as tk
import Algorithm as Algo
import logic 
from tkinter import messagebox
import threading

# Constants
BOARD_SIZE = 15
Empty = 0
Black = 1
White = 2

# UI dimensions
CELL_SIZE = 40
MARGIN = 30
WINDOW_SIZE = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)

# Global variables
root = None
canvas = None
state = None
current_player = Black
player_color = None
ai_color = None
warning = 0
move = 0
game_started = False
pending_after_id = None
ai_search_id = 0
ai_working = False
ai_stop_event = None
bg_photo = None

# Initialize board
board = [[Empty for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

def draw_board():
    #Draw grid and pieces based on board state
    global canvas, board
    
    canvas.delete("all")
    
    # Draw background image if available
    try:
        global bg_photo
        if bg_photo is not None:
            canvas.create_image(0, 0, image=bg_photo, anchor=tk.NW)
    except Exception:
        pass
    
    # The board image includes the grid; retain a simple fallback if it fails to load.
    if bg_photo is None:
        for i in range(BOARD_SIZE):
            pos = MARGIN + i * CELL_SIZE
            canvas.create_line(MARGIN, pos, MARGIN + (BOARD_SIZE - 1) * CELL_SIZE, pos)
            canvas.create_line(pos, MARGIN, pos, MARGIN + (BOARD_SIZE - 1) * CELL_SIZE)

    # Draw pieces
    r_offset = CELL_SIZE * 0.4
    
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] != Empty:
                center_x = MARGIN + c * CELL_SIZE
                center_y = MARGIN + r * CELL_SIZE
                
                color = "black" if board[r][c] == Black else "white"
                outline_color = "gray" if board[r][c] == White else "black"
                
                canvas.create_oval(
                    center_x - r_offset, center_y - r_offset,
                    center_x + r_offset, center_y + r_offset,
                    fill=color, outline=outline_color
                )

def handle_click(event):
    #Handle mouse click to place player piece
    global game_started, board, move, warning
    
    if not game_started or current_player != player_color:
        return
    
    # Calculate board coordinates
    c = round((event.x - MARGIN) / CELL_SIZE)
    r = round((event.y - MARGIN) / CELL_SIZE)
    
    if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
        return
    
    if board[r][c] == Empty:
        warning = 0
        move = 1
        board[r][c] = player_color
        draw_board()
        
        # Check win
        if logic.check_win(board, r, c, player_color):
            messagebox.showinfo("Game Over", "You win!")
            game_started = False
            return
        
        # Check draw
        if logic.is_board_full(board):
            messagebox.showinfo("Game Over", "Game ends in a draw!")
            game_started = False
            return
        
        # Switch to AI turn
        on_player_move()
    else:
        messagebox.showwarning("Invalid Move", "This position is already occupied.")
        warning = 1
        return

def choose_color():
    #Let player choose black or white
    global game_started, player_color, ai_color
    
    if game_started:
        messagebox.showwarning("Game In Progress", "A game is already in progress!")
        return 
    
    choice = messagebox.askquestion("Please make your choice", "Do you want to play as black? (Black plays first)")
    if choice == 'yes':
        player_color = Black
        ai_color = White
    else:
        player_color = White
        ai_color = Black
    messagebox.showinfo("Choice made", f"You chose {'black' if player_color == Black else 'white'}. The game begins!")
    start_game_turn()

def AI_move():
    
    #Start AI search in background thread
    #Uses ai_search_id to invalidate old searches
    
    global board, current_player, ai_color, player_color, state, move, pending_after_id, game_started, ai_search_id, ai_working, ai_stop_event

    if not game_started:
        pending_after_id = None
        return

    if ai_working:
        return

    ai_working = True
    ai_search_id += 1
    this_search_id = ai_search_id

    ai_stop_event = threading.Event()
    stop_ev = ai_stop_event

    # Update status
    state.config(text="AI is making its move...")
    root.update()

    # Take snapshot of board for thread safety
    board_snapshot = [row[:] for row in board]

    def worker(board_snap, search_id, stop_ev):
        #Background thread for AI calculation.
        try:
            position = Algo.find_best_move(board_snap, ai_color, max_depth=3, stop_event=stop_ev)
        except Exception as e:
            position = None
            print("AI worker error:", e)

        def finish():
            #Return to main thread to update UI
            global board, current_player, move, state, ai_working, game_started
            # Ignore if search was invalidated
            if search_id != ai_search_id or not game_started or (stop_ev is not None and stop_ev.is_set()):
                ai_working = False
                return

            # Handle no valid moves
            if position is None:
                if logic.is_board_full(board):
                    messagebox.showinfo("Game Over", "Game ends in a draw!")
                    game_started = False
                    ai_working = False
                    return
                else:
                    messagebox.showinfo("Game Over", "No valid moves available!")
                    board = logic.initialize_board()
                    draw_board()
                    ai_working = False
                    return

            # Place AI move
            board[position[0]][position[1]] = ai_color
            draw_board()

            # Check AI win
            if logic.check_win(board, position[0], position[1], ai_color):
                messagebox.showinfo("Game Over", "AI wins!")
                game_started = False
                ai_working = False
                return

            # Check draw
            if logic.is_board_full(board):
                messagebox.showinfo("Game Over", "Game ends in a draw!")
                game_started = False
                ai_working = False
                return

            # Switch back to player
            current_player = player_color
            move = 0
            state.config(text="Your turn")
            ai_working = False

        root.after(0, finish)

    # Start background thread
    t = threading.Thread(target=worker, args=(board_snapshot, this_search_id, stop_ev), daemon=True)
    t.start()

def start_game_turn():
    #Start the game with appropriate first player
    global board, current_player, ai_color, player_color, state, move, game_started, pending_after_id
    
    game_started = True
    move = 0
    board = logic.initialize_board()
    draw_board()
    
    if ai_color == Black:  # AI goes first
        current_player = ai_color
        pending_after_id = root.after(500, AI_move)
    else:  # Player goes first
        current_player = player_color
        state.config(text="Your turn")

def on_player_move():
    #Handle turn transition after player move
    global board, current_player, ai_color, player_color, state, move, game_started, pending_after_id
    
    if not game_started or move == 0:
        return
    
    current_player = ai_color
    move = 0
    state.config(text="AI is thinking...")
    pending_after_id = root.after(800, AI_move)

def reconfirm():
    #Confirm and handle window closing
    global pending_after_id, game_started, root, ai_stop_event
    
    try:
        ok = messagebox.askokcancel("Quit", "Do you really want to quit?")
    except Exception:
        ok = True

    if ok:
        # Cancel pending callbacks
        try:
            if pending_after_id is not None:
                root.after_cancel(pending_after_id)
        except Exception:
            pass
        pending_after_id = None
        
        # Stop any running AI search
        try:
            if ai_stop_event is not None:
                ai_stop_event.set()
        except Exception:
            pass
        
        game_started = False
        try:
            if root is not None:
                root.quit()
                root.destroy()
        except Exception:
            pass
        finally:
            root = None

def restart():
    #Restart the game with confirmation
    global game_started, board, current_player, player_color, ai_color, state, move, ai_stop_event, pending_after_id
    
    if messagebox.askyesno("Restart", "Do you want to restart the game?"):
        # Cancel pending callbacks
        try:
            if pending_after_id is not None:
                root.after_cancel(pending_after_id)
        except Exception:
            pass
        pending_after_id = None

        # Stop AI search
        try:
            if ai_stop_event is not None:
                ai_stop_event.set()
                ai_stop_event = None
        except Exception:
            pass

        # Reset game state
        board = logic.initialize_board()
        current_player = Black
        game_started = False
        player_color = None
        ai_color = None
        move = 0
        draw_board()
        state.config(text="Welcome to play gomoku!")

def start_gui():
    #Initialize and start the GUI.
    global root, canvas, state, board, current_player, game_started, bg_photo
    
    root = tk.Tk()
    root.title("Gomoku")
    
    # Center window
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - WINDOW_SIZE) // 2
    y = (screen_height - WINDOW_SIZE) // 2
    root.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE + 80}+{x}+{y}")
    
    # Reset game state
    board = logic.initialize_board()
    current_player = Black
    game_started = False
    
    # Create control frame
    control_frame = tk.Frame(root, height=80, bg="#E3CF57")
    control_frame.pack(side=tk.TOP, fill=tk.X)
    
    # Status label
    state = tk.Label(control_frame, text="Welcome to play gomoku!", bg="#E3CF57", font=("Arial", 12))
    state.pack(pady=5)
    
    # Buttons
    button_frame = tk.Frame(control_frame, bg="#E3CF57")
    button_frame.pack(pady=5)
    
    tk.Button(button_frame, text="Start Game", command=choose_color, height=1, width=15).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Restart", command=restart, height=1, width=15).pack(side=tk.LEFT, padx=5)
    
    # Canvas for board
    canvas = tk.Canvas(root, width=WINDOW_SIZE, height=WINDOW_SIZE, bg="#E3CF57")
    canvas.pack()
    canvas.focus_set()
    
    # Load the wooden Gomoku board image, including grid and star points.
    try:
        bg_photo = tk.PhotoImage(file='gomoku_board.ppm')
        canvas.bg_photo = bg_photo
    except Exception:
        bg_photo = None

    draw_board()
    
    root.resizable(False, False)
    root.protocol("WM_DELETE_WINDOW", reconfirm)
    canvas.bind("<Button-1>", handle_click)
    root.mainloop()

# Entry point
if __name__ == "__main__":
    start_gui()
