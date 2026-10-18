import json
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

app = FastAPI(title="FriendVote - Python 3.14")

INDEX_PATH = Path(__file__).parent / "templates" / "index.html"

class RoomManager:
    """Manages connected players, questions, and live votes."""
    def __init__(self):
        self.active_connections: dict[WebSocket, str] = {}
        self.current_question: str = "Who is most likely to accidentally join a cult?"
        self.votes: dict[str, int] = {}

    async def connect(self, websocket: WebSocket, username: str):
        self.active_connections[websocket] = username
        if username not in self.votes:
            self.votes[username] = 0
        await self.broadcast_state()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            username = self.active_connections.pop(websocket)
            # Remove from vote roster if they don't have other open tabs
            if username in self.votes and username not in self.active_connections.values():
                del self.votes[username]

    async def broadcast_state(self):
        """Sends the current room state to all connected friends."""
        state = {
            "type": "state_update",
            "question": self.current_question,
            "players": list(self.votes.keys()),
            "votes": self.votes
        }
        message = json.dumps(state)
        
        # Safely iterate and evict dead sockets
        dead_connections = []
        for ws in list(self.active_connections.keys()):
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws)

    async def cast_vote(self, target_player: str):
        if target_player in self.votes:
            self.votes[target_player] += 1
            await self.broadcast_state()

    async def new_question(self, question: str):
        self.current_question = question
        self.votes = {player: 0 for player in self.votes}
        await self.broadcast_state()

room = RoomManager()

@app.get("/")
async def get_index():
    return FileResponse(INDEX_PATH)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 1. Accept the WebSocket connection FIRST
    await websocket.accept()
    
    try:
        # 2. Receive the player's chosen nickname
        initial_data = await websocket.receive_text()
        data = json.loads(initial_data)
        username = data.get("username", "Anonymous").strip()[:15] or "Anonymous"
        
        await room.connect(websocket, username)

        # 3. Listen for votes and question updates
        while True:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            action = payload.get("action")

            if action == "vote":
                await room.cast_vote(payload.get("target"))
            elif action == "new_question":
                new_q = payload.get("question", "").strip()
                if new_q:
                    await room.new_question(new_q)

    except (WebSocketDisconnect, Exception):
        room.disconnect(websocket)
        await room.broadcast_state()
