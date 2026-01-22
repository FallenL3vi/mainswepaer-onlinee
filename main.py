from typing import Annotated
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import uuid
import json
import asyncio
import random

app = FastAPI()



lobbies: dict = {}

ACTIONS = ["JOIN", "START", "CHECK", "NEW_BOARD",]

class Board:
    def __init__(self, bombs: int, size: int):
        self.bombs = bombs
        self.size = size
        self.grid: list = [[0 for x in range(self.size)] for y in range(self.size)]
    
    def place_mines(self):
        count: int = 0
        while count < self.bombs:
            val: int = random.randint(0, self.size*self.size-1)

            y: int = val // self.size
            x: int = val % self.size

            if self.grid[y][x] != -1:
                count = count + 1
                self.grid[y][x] = -1
    
    def set_values(self):
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] == -1:
                    continue
                
                #Up
                if y > 0 and self.grid[y-1][x] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
                #Down
                if y < self.size - 1 and self.grid[y+1][x] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
                #Left
                if x > 0 and self.grid[y][x-1] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1 
                #Right
                if x < self.size - 1 and self.grid[y][x+1] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
                #Top-Left
                if y > 0 and x > 0 and self.grid[y-1][x-1] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
                #Top-Right
                if y > 0 and x < self.size - 1 and self.grid[y-1][x+1] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
                #Down-Left
                if y < self.size - 1 and x > 0 and self.grid[y+1][x-1] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
                #Down-Right
                if y < self.size - 1 and x < self.size - 1 and self.grid[y+1][x+1] == -1:
                    self.grid[y][x] = self.grid[y][x] + 1
    
    def check_value(self, pos_y, pos_x, visited: set = None):
        if visited is None:
            visited = set()
        #ADD WHAT IF VALUE IS MOREE THAN BOARD SIZEE
        
        #CHECK LATER IF CORRECT
        if pos_x < 0 or pos_x >= self.size or pos_y < 0 or pos_y >= self.size:
            return {}

        if (pos_y, pos_x) in visited:
            return {}

        visited.add((pos_y, pos_x))

        value = self.grid[pos_y][pos_x]

        result = [{"POSITION":[pos_y, pos_x], "VALUE": value}]

        if value == -1 or value != 0:
            return result

        for y in range(-1,2):
            for x  in range(-1, 2):
                if y == 0 and x == 0:
                    continue
                
                new_y = y + pos_y
                new_x = x + pos_x

                result.extend(self.check_value(new_y, new_x, visited))
        
        return result



class Player:
    def __init__(self, is_host: bool = False):
        self.is_host: bool = is_host
        self.client_id: str = ""
        self.health: int = 4
        self.board: Board | None = None

    def create_board(self, size: int, bombs: int):
        self.board = Board(bombs, size)
        self.board.place_mines()
        self.board.set_values()
    
    def get_damage(self, damage: int):
        self.health -= damage

        if self.health <= 0:
            return True
        return False

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    def connect(self, websocket: WebSocket, lobby_id: str, client_id: str):
        global lobbies
        new_player = Player()
        if len(lobbies[lobby_id]["players"]) == 0:
            new_player.is_host = True
        lobbies[lobby_id]["players"][websocket] = new_player
        
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket, lobby_id: str):
        global lobbies
        self.active_connections.remove(websocket)
        if lobby_id in lobbies and websocket in lobbies[lobby_id]["players"]:
            del lobbies[lobby_id]["players"][websocket]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str, lobby_id: str):
        if lobby_id not in lobbies:
            return
        for websocket in lobbies[lobby_id]["players"]:
            await websocket.send_text(message)
    
    async def new_level(self, lobby_id, websocket):
        global lobbies
        board_size = 10
        mines = 10
        lobbies[lobby_id]["players"][websocket].create_board(board_size, mines)
        new_board: dict = {"ACTION": "BOARD",
        "SIZE": board_size, "HEALTH": lobbies[lobby_id]["players"][websocket].health}
        await self.send_personal_message(json.dumps(new_board), websocket)

    async def start_lobby(self, lobby_id):
        #TMP
        global lobbies
        board_size = 10
        for player in lobbies[lobby_id]["players"].values():
            player.create_board(board_size, 8)
        for i in range(5, 0, -1):
            await self.broadcast("COUNT " + str(i), lobby_id)
            await asyncio.sleep(1)
        new_board: dict = {"ACTION": "BOARD",
        "SIZE": board_size, "HEALTH": player.health}
        await self.broadcast(json.dumps(new_board), lobby_id)
        #for connection in self.active_connections:
        #    await connection.send_text(message)

#ACTIONS
#CHECK => CHECK BOARD COORDINATIONS
#READY => IF READY TO START


manager = ConnectionManager()


@app.post("/lobby")
async def create_lobby():
    lobby_id = str(uuid.uuid4())[:10]
    lobbies[lobby_id] = {"players" : {}, "boards" : {}}
    return {"lobby_id" : lobby_id}

@app.get("/")
async def get_index():
    return FileResponse("index.html")

#@app.get("/")
#async def get():
#    return HTMLResponse(html)

@app.websocket("/ws/{lobby_id}/{client_id}")
async def websocket_endpoint(websocket: WebSocket, lobby_id: str, client_id: str):
    await websocket.accept()
    if lobby_id not in lobbies:
        await manager.send_personal_message("Error: Lobby not found", websocket)
        await websocket.close(code=1008, reason="Lobby not found")
        return
    manager.connect(websocket, lobby_id, client_id)
    print(f"Nowe połączenie: lobby={lobby_id}, client={client_id}")
    try:
        while True:
            data = await websocket.receive_text()
            #Recive move
            try:
                json_data = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_personal_message("ERROR: Invalid JSON", websocket)
                break
                
            action = json_data.get("ACTION")

            if action not in ACTIONS:
                await manager.send_personal_message("ERROR: Wrong action", websocket)
                break
            #if action == "JOIN":
            #    print("DU")
            #    await manager.broadcast(f"Player #{client_id} joined", lobby_id)

            if action == "JOIN":
                if lobby_id not in lobbies:
                    await manager.broadcast("ERROR: Lobby not found", websocket)
                    break
            
                await manager.broadcast(f"Player #{client_id} joined the lobby", lobby_id)
            elif action == "START":
                await manager.start_lobby(lobby_id)
            elif action == "CHECK":
                x = json_data.get("X")
                y = json_data.get("Y")
                
                print(json_data)
                if x is None or y is None:
                    await manager.send_personal_message("Error: Missing coordinates", websocket)
                    break
                player = lobbies[lobby_id]["players"][websocket]

                if player.board is None:
                    await manager.send_personal_message("ERROR NO BOARD", websocket)
                    break
                
                if not(0 <= x < player.board.size and 0 <= y < player.board.size):
                    await manager.send_personal_message("ERROR: Wrong coordinates", websocket)
                    break
                
                fields: list = player.board.check_value(y, x)
                new_dict = {}
                if fields[0]["VALUE"] == -1:
                    has_lost: bool = player.get_damage(1)
                    new_dict = {
                        "ACTION": "BOMB",
                        "SIZE": player.board.size,
                        "FIELDS": fields,
                        "PLAYER": client_id,
                        "HEALTH": player.health,
                        "LOST": has_lost
                    }
                else:
                    new_dict = {
                        "ACTION": "CHECK",
                        "SIZE": player.board.size,
                        "FIELDS": player.board.check_value(y, x),
                        "PLAYER": client_id
                    }
                await manager.broadcast(json.dumps(new_dict), lobby_id)
            elif action == "NEW_BOARD":
                await manager.new_level(lobby_id, websocket)

            #if "CHECK" in json_data:
            #    return
            #elif "READY" in json_data:
            #    return
            #elif "JOIN" in json_data:
            #    await manager.broadcast(f"Player #{client_id} joined", lobby_id)
            
           #await manager.send_personal_message(f"You wrote: {data}", websocket)
           #await manager.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, lobby_id)
        await manager.broadcast(f"Client #{client_id} left the lobby", lobby_id)
    except Exception as e:
        if websocket in manager.active_connections:
            print(f"Error: {e}")
            manager.disconnect(websocket, lobby_id)
            await manager.broadcast("Error: Problem with websocket", websocket)
    finally:
        if websocket in manager.active_connections:
            manager.disconnect(websocket, lobby_id)
            await manager.broadcast("Error: Something went wrong", websocket)