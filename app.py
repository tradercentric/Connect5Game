from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'connect5game2024!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Game constants
ROWS = 20
COLS = 20
CONNECT = 5

# Game state
game_state = {
    'board': [[None for _ in range(COLS)] for _ in range(ROWS)],
    'players': {},  # sid: {name, color, player_num}
    'current_turn': 1,  # Player 1 or 2
    'game_started': False,
    'winner': None,
    'player_count': 0
}


def reset_board():
    game_state['board'] = [[None for _ in range(COLS)] for _ in range(ROWS)]
    game_state['current_turn'] = 1
    game_state['game_started'] = False
    game_state['winner'] = None


def reset_game():
    reset_board()
    game_state['players'] = {}
    game_state['player_count'] = 0


def get_drop_row(col):
    """Find the lowest empty row in a column (gravity drop)"""
    for row in range(ROWS - 1, -1, -1):
        if game_state['board'][row][col] is None:
            return row
    return None  # Column is full


def check_winner(row, col, player_num):
    """Check if the last move resulted in a win"""
    board = game_state['board']

    # Directions: horizontal, vertical, diagonal down-right, diagonal down-left
    directions = [
        (0, 1),   # horizontal
        (1, 0),   # vertical
        (1, 1),   # diagonal down-right
        (1, -1)   # diagonal down-left
    ]

    for dr, dc in directions:
        count = 1  # Count the piece just placed

        # Check in positive direction
        r, c = row + dr, col + dc
        while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == player_num:
            count += 1
            r += dr
            c += dc

        # Check in negative direction
        r, c = row - dr, col - dc
        while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == player_num:
            count += 1
            r -= dr
            c -= dc

        if count >= CONNECT:
            return True

    return False


def is_board_full():
    """Check if the board is completely full (draw)"""
    for col in range(COLS):
        if game_state['board'][0][col] is None:
            return False
    return True


def broadcast_state():
    """Send game state to all connected clients"""
    players_info = []
    for sid, player in game_state['players'].items():
        players_info.append({
            'sid': sid,
            'name': player['name'],
            'color': player['color'],
            'player_num': player['player_num']
        })

    socketio.emit('game_state', {
        'board': game_state['board'],
        'players': players_info,
        'current_turn': game_state['current_turn'],
        'game_started': game_state['game_started'],
        'winner': game_state['winner'],
        'player_count': game_state['player_count']
    })


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    broadcast_state()


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in game_state['players']:
        player = game_state['players'][sid]
        print(f'Player disconnected: {player["name"]}')
        del game_state['players'][sid]
        game_state['player_count'] -= 1

        # Reset game if a player leaves
        if game_state['game_started']:
            reset_board()

        broadcast_state()


@socketio.on('join_game')
def handle_join(data):
    sid = request.sid

    if game_state['player_count'] >= 2:
        emit('error', {'message': 'Game is full! Only 2 players allowed.'})
        return

    if game_state['game_started']:
        emit('error', {'message': 'Game already in progress!'})
        return

    if sid in game_state['players']:
        emit('error', {'message': 'You already joined!'})
        return

    player_name = data.get('player_name', f'Player {game_state["player_count"] + 1}')
    player_num = game_state['player_count'] + 1
    color = 'red' if player_num == 1 else 'blue'

    game_state['players'][sid] = {
        'name': player_name,
        'color': color,
        'player_num': player_num
    }
    game_state['player_count'] += 1

    print(f'Player joined: {player_name} as {color} (Player {player_num})')

    emit('joined', {
        'player_num': player_num,
        'player_name': player_name,
        'color': color
    })

    # Auto-start game when 2 players join
    if game_state['player_count'] == 2:
        game_state['game_started'] = True
        socketio.emit('game_started', {'message': 'Game started! Red goes first.'})

    broadcast_state()


@socketio.on('drop_piece')
def handle_drop(data):
    sid = request.sid

    if not game_state['game_started']:
        emit('error', {'message': 'Game has not started yet!'})
        return

    if game_state['winner']:
        emit('error', {'message': 'Game is over!'})
        return

    if sid not in game_state['players']:
        emit('error', {'message': 'You are not in this game!'})
        return

    player = game_state['players'][sid]

    if player['player_num'] != game_state['current_turn']:
        emit('error', {'message': "It's not your turn!"})
        return

    col = data.get('col')
    if col is None or col < 0 or col >= COLS:
        emit('error', {'message': 'Invalid column!'})
        return

    row = get_drop_row(col)
    if row is None:
        emit('error', {'message': 'Column is full!'})
        return

    # Place the piece
    game_state['board'][row][col] = player['player_num']

    # Check for winner
    if check_winner(row, col, player['player_num']):
        game_state['winner'] = {
            'name': player['name'],
            'color': player['color'],
            'player_num': player['player_num']
        }
        game_state['game_started'] = False
        socketio.emit('game_won', game_state['winner'])
    elif is_board_full():
        game_state['winner'] = {'draw': True}
        game_state['game_started'] = False
        socketio.emit('game_draw', {})
    else:
        # Switch turns
        game_state['current_turn'] = 2 if game_state['current_turn'] == 1 else 1

    # Emit piece dropped event with animation info
    socketio.emit('piece_dropped', {
        'row': row,
        'col': col,
        'player_num': player['player_num'],
        'color': player['color']
    })

    broadcast_state()


@socketio.on('reset_game')
def handle_reset():
    reset_board()
    game_state['game_started'] = True
    game_state['current_turn'] = 1
    socketio.emit('game_reset', {})
    broadcast_state()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
