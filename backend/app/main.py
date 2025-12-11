from fastapi import FastAPI
from .redis_client import redis_client

app = FastAPI(title="Booking API (SQLite)")

@app.get("/health")
def health():
    return {"redis": redis_client.ping()}
