# server.py
import eventlet
eventlet.monkey_patch()

import random
import math
from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit
from flask import request

app = Flask(__name__, static_folder='public', static_url_path='')
app.config['SECRET_KEY'] = 'your_secret_key_here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Game configuration
CONFIG = {
    'worldSize': 2000,
    'playerSpeed': 300,
    'bulletSpeed': 700,
    'bulletLife': 1.6,
    'spawnSafeRadius': 120,
    'updateRate': 60
}

# Game state
game_state = {
    'players': {},
    'bullets': [],
    'next_player_id': 1,
    'next_bullet_id': 1
}

# Utility functions
def rand(min_val, max_val):
    return random.uniform(min_val, max_val)

def distance(a, b):
    return math.hypot(a['x'] - b['x'], a['y'] - b['y'])

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)

@socketio.on('connect')
def handle_connect():
    print(f'Player connected: {request.sid}')
    
    # Create new player
    player_id = game_state['next_player_id']
    game_state['next_player_id'] += 1
    
    player = {
        'id': player_id,
        'socket_id': request.sid,
        'name': f'Player{player_id}',
        'x': rand(-CONFIG['worldSize']/2, CONFIG['worldSize']/2),
        'y': rand(-CONFIG['worldSize']/2, CONFIG['worldSize']/2),
        'r': 16,
        'color': f'hsl({random.randint(0, 360)}, 70%, 60%)',
        'vx': 0,
        'vy': 0,
        'score': 0,
        'shootCooldown': 0
    }
    
    # Ensure safe spawn
    if math.hypot(player['x'], player['y']) < CONFIG['spawnSafeRadius']:
        player['x'] += CONFIG['spawnSafeRadius']
        player['y'] += CONFIG['spawnSafeRadius']
    
    game_state['players'][player_id] = player
    
    # Send initial game state
    emit('init', {
        'playerId': player_id,
        'CONFIG': CONFIG
    })
    
    print(f'Player {player_id} joined the game')

@socketio.on('playerInput')
def handle_player_input(data):
    player_id = None
    # Find player by socket ID
    for pid, player in game_state['players'].items():
        if player['socket_id'] == request.sid:
            player_id = pid
            break
    
    if player_id is None or player_id not in game_state['players']:
        return
    
    player = game_state['players'][player_id]
    keys = data.get('keys', {})
    mouse = data.get('mouse', {})
    
    # Movement
    move_x = 0
    move_y = 0
    
    if keys.get('w') or keys.get('arrowup'):
        move_y -= 1
    if keys.get('s') or keys.get('arrowdown'):
        move_y += 1
    if keys.get('a') or keys.get('arrowleft'):
        move_x -= 1
    if keys.get('d') or keys.get('arrowright'):
        move_x += 1
    
    move_len = math.hypot(move_x, move_y)
    if move_len > 0:
        player['vx'] = (move_x / move_len) * CONFIG['playerSpeed'] / CONFIG['updateRate']
        player['vy'] = (move_y / move_len) * CONFIG['playerSpeed'] / CONFIG['updateRate']
    else:
        player['vx'] = 0
        player['vy'] = 0
    
    # Shooting
    if mouse.get('down') and player['shootCooldown'] <= 0:
        world_x = mouse.get('worldX', player['x'])
        world_y = mouse.get('worldY', player['y'])
        angle = math.atan2(world_y - player['y'], world_x - player['x'])
        
        bullet = {
            'id': game_state['next_bullet_id'],
            'ownerId': player_id,
            'x': player['x'] + math.cos(angle) * (player['r'] + 6),
            'y': player['y'] + math.sin(angle) * (player['r'] + 6),
            'angle': angle,
            'speed': CONFIG['bulletSpeed'] / CONFIG['updateRate'],
            'life': CONFIG['bulletLife'] * CONFIG['updateRate'],
            'r': 4
        }
        
        game_state['next_bullet_id'] += 1
        game_state['bullets'].append(bullet)
        player['shootCooldown'] = 0.28 * CONFIG['updateRate']  # Rate of fire

@socketio.on('changeName')
def handle_change_name(data):
    player_id = None
    for pid, player in game_state['players'].items():
        if player['socket_id'] == request.sid:
            player_id = pid
            break
    
    if player_id and player_id in game_state['players']:
        game_state['players'][player_id]['name'] = data[:15]  # Limit name length
        print(f'Player {player_id} changed name to: {data[:15]}')

@socketio.on('disconnect')
def handle_disconnect():
    player_id = None
    for pid, player in game_state['players'].items():
        if player['socket_id'] == request.sid:
            player_id = pid
            break
    
    if player_id and player_id in game_state['players']:
        del game_state['players'][player_id]
        print(f'Player {player_id} disconnected')

def update_game():
    """Update game state"""
    # Update player positions
    for player_id, player in game_state['players'].items():
        # Apply velocity
        player['x'] += player['vx']
        player['y'] += player['vy']
        
        # World boundaries
        if player['x'] > CONFIG['worldSize']/2:
            player['x'] = -CONFIG['worldSize']/2
        if player['x'] < -CONFIG['worldSize']/2:
            player['x'] = CONFIG['worldSize']/2
        if player['y'] > CONFIG['worldSize']/2:
            player['y'] = -CONFIG['worldSize']/2
        if player['y'] < -CONFIG['worldSize']/2:
            player['y'] = CONFIG['worldSize']/2
        
        # Update shoot cooldown
        if player['shootCooldown'] > 0:
            player['shootCooldown'] -= 1
    
    # Update bullets
    bullets_to_remove = []
    for i, bullet in enumerate(game_state['bullets']):
        # Move bullet
        bullet['x'] += math.cos(bullet['angle']) * bullet['speed']
        bullet['y'] += math.sin(bullet['angle']) * bullet['speed']
        
        # World boundaries for bullets
        if bullet['x'] > CONFIG['worldSize']/2:
            bullet['x'] = -CONFIG['worldSize']/2
        if bullet['x'] < -CONFIG['worldSize']/2:
            bullet['x'] = CONFIG['worldSize']/2
        if bullet['y'] > CONFIG['worldSize']/2:
            bullet['y'] = -CONFIG['worldSize']/2
        if bullet['y'] < -CONFIG['worldSize']/2:
            bullet['y'] = CONFIG['worldSize']/2
        
        # Check for collisions
        hit_player = None
        for player_id, player in game_state['players'].items():
            if player_id == bullet['ownerId']:  # Can't hit yourself
                continue
            
            if distance(bullet, player) < (bullet['r'] + player['r']):
                hit_player = player
                break
        
        # Handle hit
        if hit_player:
            # Award points to shooter
            shooter = game_state['players'].get(bullet['ownerId'])
            if shooter:
                shooter['score'] = shooter.get('score', 0) + 1
            
            # Respawn hit player
            hit_player['x'] = rand(-CONFIG['worldSize']/2, CONFIG['worldSize']/2)
            hit_player['y'] = rand(-CONFIG['worldSize']/2, CONFIG['worldSize']/2)
            hit_player['vx'] = 0
            hit_player['vy'] = 0
            
            bullets_to_remove.append(i)
            continue
        
        # Remove expired bullets
        bullet['life'] -= 1
        if bullet['life'] <= 0:
            bullets_to_remove.append(i)
    
    # Remove bullets (in reverse order to maintain indices)
    for i in sorted(bullets_to_remove, reverse=True):
        if i < len(game_state['bullets']):
            game_state['bullets'].pop(i)

def game_loop():
    """Main game loop"""
    while True:
        update_game()
        
        # Send game state to all clients
        socketio.emit('gameState', {
            'players': game_state['players'],
            'bullets': game_state['bullets']
        })
        
        eventlet.sleep(1.0 / CONFIG['updateRate'])

if __name__ == '__main__':
    # Start game loop in a separate thread
    eventlet.spawn(game_loop)
    
    print("Starting multiplayer .io game server on http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)