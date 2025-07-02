import uuid
from firebase_config import db

def generate_custom_username():
    return f"user_{uuid.uuid4().hex[:8]}"

def create_user_in_firestore(phone_number):
    try:
        username = generate_custom_username()
        user_ref = db.collection("users").document()
        user_ref.set({
            "phone_number": phone_number,
            "username": username
        })
        return {
            "uid": user_ref.id,
            "username": username
        }
    except Exception as e:
        print("❌ Firestore Error:", e)
        raise  # Or return a custom error response if calling from a view
