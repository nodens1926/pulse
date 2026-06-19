from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Pulse API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Pulse API is running"}

@app.post("/api/sites")
async def add_site():
    return {"status": "ok", "message": "Site added to queue (stub)"}

@app.get("/api/search")
async def search():
    return {"results": [], "message": "Search stub"}

@app.get("/api/status")
async def get_status():
    return {"status": "indexed", "message": "Status stub"}
