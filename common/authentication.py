import hmac
import hashlib
import base64
from django.utils.dateparse import parse_datetime
from django.conf import settings
from qr_service.models import QRCode  # ✅ Absolute import
from datetime import datetime


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

def generate_qr_code(qr_id):
    creation_date = datetime.utcnow().strftime("%Y%m%d")
    hashed_qr_id = hash_qr_id(qr_id)

    # Combine hashed_qr_id and creation_date, then encode it
    encoded_hash = base64.urlsafe_b64encode(f"{hashed_qr_id}:{creation_date}".encode()).decode()

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

def decode_and_verify_qr_hash(hashed_qr_id):
    """
    Decodes the hashed QR ID to extract the creation date and raw hash, 
    then verifies the hash against QR codes created on that date.
    """
    try:
        # Step 1: Decode the hashed QR ID
        decoded_data = base64.urlsafe_b64decode(hashed_qr_id).decode()
        raw_hash, date_str = decoded_data.split(":")
        
        # Step 2: Convert date string to date object
        creation_date = parse_datetime(date_str).date()

        # Step 3: Fetch QR codes created on that date
        possible_qr_codes = QRCode.objects.filter(created_at__date=creation_date)

        # Step 4: Verify the hash against QR codes created on that date
        for qr in possible_qr_codes:
            if hash_qr_id(qr.qr_id) == raw_hash:
                return qr.qr_id  # Return the valid QR code object if hash matches

        return None  # Return None if no match is found
    except Exception as e:
        print(f"Error: {e}")
        return None  # Return None if anything goes wrong (invalid format, date parsing error, etc.)
