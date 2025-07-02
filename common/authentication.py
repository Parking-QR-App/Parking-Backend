import hmac
import hashlib
import base64
from django.utils.dateparse import parse_datetime
from django.conf import settings
from qr_service.models import QRCode  # ✅ Absolute import


SECRET_KEYS = [settings.SECRET_KEY, b'fuirujiojf289f892ry428oy4r2ijhfd298ydf28']  # Ordered: New to Old

def hash_qr_id(qr_id, key=None):
    """
    Generate a secure HMAC-SHA256 hash of the QR ID using the latest secret key.
    """
    if key is None:
        key = SECRET_KEYS[0]  # Use the latest key by default

    if isinstance(key, str):
        key = key.encode()  # Convert string key to bytes
    
    qr_id_str = str(qr_id)

    return hmac.new(key, qr_id_str.encode(), hashlib.sha256).hexdigest()

def generate_qr_code(qr_id, created_at):
    hashed_qr_id = hash_qr_id(qr_id)

    # Combine hashed_qr_id and creation_date, then encode it
    encoded_hash = base64.urlsafe_b64encode(f"{hashed_qr_id}:{created_at}".encode()).decode()

    return encoded_hash

def verify_qr_hash(hashed_qr_id, filtered_qr_ids):
    """
    Verifies the hashed QR ID by checking only the QR codes fetched from the database
    that were created on the given date.
    """
    for qr_id in filtered_qr_ids:
        for key in SECRET_KEYS:  # Check with all keys in case of rotation
            if hash_qr_id(qr_id, key) == hashed_qr_id:
                return qr_id  # Return the verified QR ID
    
    return None  # No match found

def decode_and_verify_qr_hash(encoded_hash):
    """
    Decodes the encoded QR hash, extracts the hashed_qr_id and creation datetime,
    and verifies the hash against QR codes created at that datetime.
    """
    try:
        # Step 1: Decode the Base64-encoded string
        decoded_str = base64.urlsafe_b64decode(encoded_hash).decode()
        raw_hash, creation_datetime_str = decoded_str.split(":", 1)  # Allow ":" in timestamp

        # Step 2: Parse the creation datetime
        creation_datetime = parse_datetime(creation_datetime_str)
        if not creation_datetime:
            raise ValueError("Invalid datetime format in QR hash")

        # Step 3: Filter QR codes by the exact creation datetime (down to second)
        possible_qr_codes = QRCode.objects.filter(created_at__date=creation_datetime.date())

        # Step 4: Match the hash to one of the filtered QR codes
        for qr in possible_qr_codes:
            if hash_qr_id(qr.qr_id) == raw_hash:
                return qr.qr_id

        return None

    except Exception as e:
        print(f"[decode_and_verify_qr_hash] Error: {e}")
        return None