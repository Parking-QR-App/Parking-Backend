import firebase_admin
from firebase_admin import credentials, firestore

# Prevent re-initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("./zegocloud-3d68b-firebase-adminsdk-fbsvc-9a16f37574.json")
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
