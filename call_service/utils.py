from common.token04 import generate_token04
import time
import os

APP_ID = int(os.getenv("ZEGO_APP_ID", "2102798881"))
SERVER_SECRET = os.getenv("ZEGO_SERVER_SECRET", "579d7d954e46b166512a22d58871c5ec")

def generate_zego_token(user_id: str, effective_time: int = 3600) -> str:
    payload = {
        "app_id": APP_ID,
        "user_id": user_id,
        "secret": SERVER_SECRET,
        "effective_time_in_seconds": effective_time,
        "payload": ""
    }
    print(payload)
    token_info = generate_token04(
        app_id=payload["app_id"],
        user_id=payload["user_id"],
        secret=payload["secret"],
        effective_time_in_seconds=payload["effective_time_in_seconds"],
        payload=payload["payload"]
    )
    print(token_info.token)
    return(token_info.token)
