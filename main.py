# Backend

import json
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="FriendVote - Python 3.14")

templates = Jinja2Templates(directory="templates")

class RoomManager:
    """Manages connected players, questions, and live votes."""
    def __init__(self):
        # Maps active WebSocket connections to player names
        self.active_connections: dict[WebSocket, str] = {}
        self.current_question: str = "Who is most likely to accidentally join a cult?"
        self.votes: dict[str, int] = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        self.active_connections[websocket] = username
        if username not in self.votes:
            self.votes[username] = 0
        await self.broadcast_state()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            username = self.active_connections.pop(websocket)
            # Remove from vote roster if they completely leave
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
        for ws in list(self.active_connections.keys()):
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(ws)

    async def cast_vote(self, target_player: str):
        if target_player in self.votes:
            self.votes[target_player] += 1
            await self.broadcast_state()

    async def new_question(self, question: str):
        self.current_question = question
        # Reset vote counts for the new round
        self.votes = {player: 0 for player in self.votes}
        await self.broadcast_state()

room = RoomManager()

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Serves the front-end page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles real-time bi-directional messaging with each player."""
    username = None
    try:
        # First message must be the player's name
        initial_data = await websocket.receive_text()
        data = json.loads(initial_data)
        username = data.get("username", "Anonymous").strip()[:15] or "Anonymous"
        
        await room.connect(websocket, username)

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

    except WebSocketDisconnect:
        room.disconnect(websocket)
        await room.broadcast_state()