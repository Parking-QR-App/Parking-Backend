import firebase_admin
import os
import json
from django.conf import settings
from firebase_admin import credentials, firestore

def get_firebase_cred():
    """Return a firebase_admin credentials object from either env var or local file."""
    if os.environ.get("FIREBASE_CREDENTIALS"):
        # Load from environment variable in production
        firebase_creds_dict = json.loads(os.environ["FIREBASE_CREDENTIALS"])
        return credentials.Certificate(firebase_creds_dict)
    else:
        # Load from local file in development
        cred_path = os.path.join(settings.BASE_DIR, 'zegocloud-3d68b-firebase-adminsdk-fbsvc-9a16f37574.json')
        return credentials.Certificate(cred_path)
    
# Prevent re-initialization
if not firebase_admin._apps:
    cred = get_firebase_cred()
    firebase_admin.initialize_app(cred)

db = firestore.client()


# # Write test document
# test_ref = db.collection("test_collection").document("test_doc")
# test_data = {"status": "connected"}
# test_ref.set(test_data)

# # Read it back
# doc = test_ref.get()
# if doc.exists:
#     print("✅ Firestore is working! Document data:", doc.to_dict())
# else:
#     print("❌ Firestore is NOT working: Document not found.")
