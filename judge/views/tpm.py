from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import datetime
import sys
import uuid
from django.conf import settings
import os
import binascii
from Crypto.Util.Padding import pad
from django.http import HttpResponse
import base64
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
import hashlib
import ssl 
import secrets
import time
import struct
import re
import traceback
import time
from django.shortcuts import render
from django.core.cache import cache
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from django.utils import timezone

from django.contrib.auth import login, get_user_model
from django.shortcuts import redirect
from judge.models.device import Device, Room, ContestSeat
from django.contrib.auth import logout as auth_logout

User = get_user_model()

cert_logger = logging.getLogger('auth_cert')
logger = logging.getLogger(__name__)

TOKEN_STORE = {}  

SECRET = settings.DECRYPT_LICENSE_KEY

def xor_decrypt(data: bytes, key: bytes):
    out = bytearray()

    for i in range(len(data)):
        out.append(data[i] ^ key[i % len(key)])

    return bytes(out)


def decrypt_license(license_str):
    try:
        raw = base64.b64decode(license_str)

        decrypted = xor_decrypt(raw, SECRET)

        return decrypted.decode()

    except Exception as e:
        raise Exception(f"Decrypt failed: {str(e)}")

def xor_encrypt(data: bytes, key: bytes) -> bytes:
    """XOR data với keystream dẫn xuất từ SHA-256"""
    out = bytearray(len(data))
    block = b""
    block_index = 0
    key_counter = 0

    for i in range(len(data)):
        if block_index >= len(block):
            # Tạo block keystream mới: SHA256(key + counter)
            counter_bytes = key_counter.to_bytes(4, 'big')
            block = hashlib.sha256(key + counter_bytes).digest()  # 32 byte
            block_index = 0
            key_counter += 1
        out[i] = data[i] ^ block[block_index]
        block_index += 1

    return bytes(out)

def xor_decrypt_field(data, key=0x9A):
    return ''.join(chr(b ^ key) for b in data)


@csrf_exempt
def auth_cert_view(request):
    if request.method == 'POST':
        try:
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
            license_data = request.body.decode('utf-8').strip()
            # print("license_data: ", license_data)
            mac = decrypt_license(license_data)
            cert_pem = request.META.get('SSL_CLIENT_CERT')
            thumbprint = "underfine"
            if cert_pem:
                cert_der = ssl.PEM_cert_to_DER_cert(cert_pem)
                thumbprint = hashlib.sha1(cert_der).hexdigest().upper()
                # print("cert_der: ", cert_der)
                
            # print("Mac: ", mac)
            file_path = "config/config.seb"
            with open(file_path, "rb") as f:
                seb_data = f.read()

            # Tạo key ngẫu nhiên 32 byte
            key = os.urandom(32)

            # Mã hóa
            encrypted = xor_encrypt(seb_data, key)

            # Payload: [key(32) + encrypted_data]
            payload = key + encrypted
            payload_b64 = base64.b64encode(payload).decode('utf-8')
            token = secrets.token_hex(16)

            cache.set(token, {
                "mac": mac,
                "ip": ip,
                "time": time.time()
            }, timeout=3)
            response_text = f"MAC={mac}\nSEB={payload_b64}\nTOKEN={token}\n"
            cert_logger.info(
                "IP: %s | Mac: %s | Cert: %s | Thumbprint: %s | Send token: %s",
                ip,
                mac,
                request.META.get('SSL_CLIENT_S_DN'),
                thumbprint,
                token
            )
            return HttpResponse(response_text, content_type="text/plain")

        except Exception as e:
            cert_logger.error('Error auth_cert: %s', str(e))
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def parse_encoded_field_body(raw_bytes):
    data = {}

    lines = raw_bytes.split(b'\n')

    for line in lines:
        if b'=' in line:
            k, v = line.split(b'=', 1)

            try:
                key = xor_decrypt_field(k, 0x9A)
                if key.endswith('='):
                    key = key[:-1]
                value = v.decode('utf-8', errors='ignore')
                data[key.strip()] = value.strip()
            except:
                continue

    return data

@csrf_exempt
def auth_fail_view(request):
    if request.method == 'POST':
        try:
            raw = request.body
            data = parse_encoded_field_body(raw)
   
            mac = data.get("mac", "unknown")
            token = data.get("token", "unknown")
            hostname = data.get("hostname", "unknown")
            process = data.get("process", "unknown")
            reason = data.get("reason", "unknown")
            debugger = data.get("debugger", "unknown")
            vm = data.get("vm", "unknown")
            hook = data.get("hook", "unknown")
            timestamp = data.get("timestamp", "unknown")
            runtime_ms = data.get("runtime_ms", "unknown")
            rand_check = data.get("rand_check", "unknown")
            exe_hash = data.get("exe_hash", "unknown")
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))

            log_entry = (
                f"REASON={reason} IP={ip} "
                f"MAC={mac} HOST={hostname} PROCESS={process} "
                f"DEBUG={debugger} VM={vm} HOOK={hook} "
                f"CLIENT_TIME={timestamp} "
                f"EXE_HASH={exe_hash} RUNTIME_MS={runtime_ms} RAND_CHECK={rand_check} CHALLENGE={token}\n"
            )
    
            cert_logger.info(
                log_entry
            )
            return HttpResponse("Invalid method", content_type="text/plain")

        except Exception as e:
            cert_logger.error('REPORT CERT ERROR: %s', str(e))
            return JsonResponse(
                {'status': 'error', 'message': str(e)},
                status=400
            )

    return JsonResponse({'status': 'invalid method'}, status=405)

@csrf_exempt
def register_device(request):
    if request.method != "POST":
        print("METHOD:", request.method)
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        data = json.loads(request.body)

        device_id = data.get("device_id")
        public_key = data.get("public_key")
        mac = data.get("mac")
        hostname = data.get("hostname")
        client_ip = request.META.get('REMOTE_ADDR')
        room_obj = None
        ROOM_PATTERN = re.compile(r'^([A-Z]\d-\d{3})-\d{2}$')
  
        if hostname:
            match = ROOM_PATTERN.match(hostname)
            if match:
                room_code = match.group(1)
                room_obj, _ = Room.objects.get_or_create(
                    code=room_code,
                    defaults={"name": room_code}
                )

        device, created = Device.objects.get_or_create(
            device_id=device_id, 
            defaults={
                "public_key": public_key,
                "hostname": hostname,
                "mac": mac,
                "last_ip": client_ip,
                "is_active": True,
                "room": room_obj, 
            }
        )

        if not created:
            Device.objects.filter(pk=device.pk).update(
                public_key=public_key,
                hostname=hostname,
                mac=mac,
                last_ip=client_ip,
                is_active=True,
                room=room_obj 
            )

        log_entry = (
            f"IP={client_ip} hostname={hostname} device_id={device_id} mac={mac} public_key={public_key} "
        )
        cert_logger.info(
            log_entry
        )

        return JsonResponse({"status": "ok"})
    
    except Exception as e:
        cert_logger.error('REPORT CERT ERROR: %s', str(e))
        print("ERROR REGISTER DEVICE:", str(e))
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)


def parse_rsa_blob(blob):
    magic, bitlen, cbPublicExp, cbModulus, cbPrime1, cbPrime2 = struct.unpack("<IIIIII", blob[:24])
 
    offset = 24

    e = int.from_bytes(blob[offset:offset+cbPublicExp], "big") 
    offset += cbPublicExp

    n = int.from_bytes(blob[offset:offset+cbModulus], "big")  

    return n, e

# ================= SAFE BASE64 =================
def safe_b64decode(data):
    data = data.strip().replace('\n', '').replace('\r', '')

    missing = len(data) % 4
    if missing:
        data += '=' * (4 - missing)

    return base64.b64decode(data)

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

def verify_seb_hash(request):
    seb_hash = request.headers.get('X-SafeExamBrowser-ConfigKeyHash')
    if not seb_hash:
        return render(request, 'errors/seb_forbidden.html', status=403)
    absolute_url = request.build_absolute_uri()
    config_keys = getattr(settings, 'SEB_CONFIG_KEYS', [])
    for key in config_keys:
        expected = hashlib.sha256((absolute_url + key).encode()).hexdigest()
        if expected == seb_hash:
            return True
    return render(request, 'errors/seb_forbidden.html', status=403)


def device_logout(request):
    print("request: ", request)
    auth_logout(request)
    return redirect("/")

@csrf_exempt
def auto_login(request):
    t0 = time.perf_counter()
    try:
        debug_info = {
            "method": request.method,
            "path": request.path,
            "get_params": dict(request.GET),
            "post_params": dict(request.POST),
            "remote_addr": request.META.get('REMOTE_ADDR'),
            "http_host": request.META.get('HTTP_HOST'),
            "full_url": request.build_absolute_uri(),
        }
        cert_logger.info(f"Incoming request detail: {debug_info}")
    except Exception as e:
        cert_logger.error(f"Error while logging request info: {str(e)}")

    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "method not allowed"}, status=405)

    # ================= STEP 0: CACHE =================
    t1 = time.perf_counter()

    client_ip = request.META.get('REMOTE_ADDR')
    print("--- DEBUG CACHE ALL KEYS ---")
    try:
        all_keys = cache.keys("*") 
        for key in all_keys:
            print(f"Key: {key} => Value: {cache.get(key)}")
    except AttributeError:
        print("Cache backend does not support keys() listing.")

    url_token = request.GET.get('token')
    
    if not url_token:
        cert_logger.error(
            f"FAILED - Missing token. "
            f"Client IP: {request.META.get('REMOTE_ADDR')}. "
            f"Full Path: {request.get_full_path()}. "
            f"GET Data: {dict(request.GET)}"
        )
        cert_logger.error(f"Not url token: {request}")
        return JsonResponse({"error": "Missing token parameter"}, status=400)

    # 2. Truy xuất cache theo Token
    clean_token = url_token.split('??')[0]
    tpm_session = cache.get(f"tpm_session:{clean_token}")


    t2 = time.perf_counter()

    if not tpm_session:
        cert_logger.error('tpm_session: %s', clean_token)
        print(f"[TIME] cache_get: {t2 - t1:.4f}s")
        return JsonResponse({"error": "unauthorized"}, status=403)

    if tpm_session.get("token") != url_token:
        cert_logger.error(f"Auto-login failed: Invalid Token. URL Token: {url_token}")
        return JsonResponse({"error": "Unauthorized: Invalid or expired token"}, status=401)


    device_id = tpm_session["device_id"]
    cache.delete(f"tpm_session:{clean_token}")
    t3 = time.perf_counter()

    # ================= STEP 1: GET DEVICE =================
    device = (
        Device.objects
        .filter(device_id=device_id, is_active=True)
        .order_by("-last_seen")
        .first()
    )

    t4 = time.perf_counter()

    if not device:
        cert_logger.error('not device: %s', device_id)
        print(f"[TIME] device_query: {t4 - t3:.4f}s")
        host = request.get_host().split(':')[0]  
        return redirect(f"https://{host}/accounts/login/?next=/contests")

    # ================= STEP 2: GET CONTEST =================
    now = timezone.now()

    contest_seat = (
        ContestSeat.objects
        .select_related("user", "user__user", "contest")
        .filter(
            device=device,
            contest__start_time__lte=now,
            contest__end_time__gt=now
        )
        .order_by("-contest__start_time")
        .first()
    )

    t5 = time.perf_counter()

    if not contest_seat:
        print(f"[TIME] contest_query: {t5 - t4:.4f}s")
        host = request.get_host().split(':')[0]  
        cert_logger.error('not contest seat: %s', device)
        return redirect(f"https://{host}/accounts/login/?next=/contests")

    # ================= STEP 3: LOGIN =================
    profile = contest_seat.user
    user = profile.user
    cert_logger.error('User in contest seat: %s', user)
    cert_logger.error('Meta: %s', request.META)
    t6 = time.perf_counter()

    user.backend = 'judge.auth_backends.AutoLoginBackend'
    login(request, user)

    t7 = time.perf_counter()

    # ================= LOG =================
    print("===== AUTO LOGIN TIMING =====")
    print(f"cache_get:     {t2 - t1:.4f}s")
    print(f"cache_delete:  {t3 - t2:.4f}s")
    print(f"device_query:  {t4 - t3:.4f}s")
    print(f"contest_query: {t5 - t4:.4f}s")
    print(f"prepare_user:  {t6 - t5:.4f}s")
    print(f"login:         {t7 - t6:.4f}s")
    print(f"TOTAL:         {t7 - t0:.4f}s")
    print("============================")

    host = request.get_host().split(':')[0]  
    return redirect(f"https://{host}/contests")

@csrf_exempt
def get_challenge(request):
    real_port = request.META.get('SERVER_PORT')
    if(real_port != settings.TPM_AUTH_PORT):

    if request.method == 'POST':
        try:
            ip = request.META.get('REMOTE_ADDR')
            body = request.body
            if not body:
                cert_logger.error("MAC EMPTY | IP: %s | License: %s", ip, body) 
                return HttpResponse("Access Denied", status=403, content_type="text/plain")

            try:
                mac = decrypt_license(body.decode('utf-8').strip()) 

            except Exception as dec_err:

                cert_logger.error("DECRYPT LICENSE FAILED | IP: %s | Error: %s", ip, str(dec_err))
                return HttpResponse("Access Denied", status=403, content_type="text/plain")


            # license_data = request.body.decode('utf-8').strip()
            # mac = decrypt_license(license_data)
            challenge = secrets.token_hex(16)

            cache.set(challenge, {
                "mac": mac,
                "ip": ip,
                "time": time.time()
            }, timeout=15)
            response_text = f"MAC={mac}\nCHALLENGE={challenge}\n"

            cert_logger.info(
                "IP: %s | Mac: %s | Send challenge: %s",
                ip,
                mac,
                challenge
            )
            return HttpResponse(response_text, content_type="text/plain")

        except Exception as e:
            cert_logger.error('ERROR GET CHALLENGE: %s', str(e))
            return HttpResponse("Access Denied", status=403, content_type="text/plain")

@csrf_exempt
def verify_tpm(request):
    try:
        raw = request.body
        data = parse_encoded_field_body(raw)
        print("data: ", data)
        
        # mac = data.get("mac", "unknown")
        challenge = data.get("challenge", "unknown")
        hostname = data.get("hostname", "unknown")
        process = data.get("process", "unknown")
        debugger = data.get("debugger", "unknown")
        vm = data.get("vm", "unknown")
        hook = data.get("hook", "unknown")
        timestamp = data.get("timestamp", "unknown")
        runtime_ms = data.get("runtime_ms", "unknown")
        rand_check = data.get("rand_check", "unknown")
        exe_hash = data.get("exe_hash", "unknown")
        device_id = data.get("device_id", "unknown")
        signature_b64 = data.get("signature", "unknown")
        ip = request.META.get('REMOTE_ADDR', '')
        cached = cache.get(challenge)
        cache.delete(challenge)
        
        log_entry = (
            f"IP={ip} "
            f"HOST={hostname} PROCESS={process} "
            f"DEBUG={debugger} VM={vm} HOOK={hook} "
            f"CLIENT_TIME={timestamp} DEVICE_ID={device_id} CHALLENGE={challenge} SIGNATURE={signature_b64} "
            f"EXE_HASH={exe_hash} RUNTIME_MS={runtime_ms} RAND_CHECK={rand_check}"
        )

        if not cached:
            cert_logger.error('NOT CACHED: %s', log_entry)
            return JsonResponse({"status": "fail", "error": "challenge expired"}, status=403)
        
        if cached["ip"] != ip:
            cert_logger.error('IP MISMATCH: %s', log_entry)
            return HttpResponse("Invalid method", content_type="text/plain")

        if time.time() - cached["time"] > 15.0:
            cert_logger.error('CHALLENGE EXPIRED: %s', log_entry)
            return HttpResponse("Invalid method", content_type="text/plain")

        mac = cached["mac"]
        try:
            device = Device.objects.get(mac=mac, is_active=True)
            if device.last_ip != ip:
                device.last_ip = ip
                device.save(update_fields=["last_ip", "last_seen"])
            
        except Device.DoesNotExist:
            cert_logger.error('DEVICE NOT FOUND: MAC=%s', mac)
            return JsonResponse({"status": "fail", "error": "device not registered"}, status=403)

        PUBLIC_KEY_B64 = device.public_key

        log_entry = (
            f"IP={ip} "
            f"MAC={mac} HOST={hostname} PROCESS={process} "
            f"DEBUG={debugger} VM={vm} HOOK={hook} "
            f"CLIENT_TIME={timestamp} DEVICE_ID={device_id} CHALLENGE={challenge} SIGNATURE={signature_b64} "
            f"EXE_HASH={exe_hash} RUNTIME_MS={runtime_ms} RAND_CHECK={rand_check}"
        )

        # ================= MESSAGE =================
        #message = f"{challenge}|{device_id}".encode()
        # digest = hashes.Hash(hashes.SHA256())
        # digest.update(message)
        # message_hash = digest.finalize()

        # ================= LOAD RSA BLOB =================
       # blob = safe_b64decode(PUBLIC_KEY_B64)

        #n, e = parse_rsa_blob(blob)

        #public_key = rsa.RSAPublicNumbers(e, n).public_key()

        # ================= SIGNATURE =================
        #signature = safe_b64decode(signature_b64)

        # ================= VERIFY =================

        file_path = "config/config.seb"
        with open(file_path, "rb") as f:
            seb_data = f.read()

        key = os.urandom(32)
        encrypted = xor_encrypt(seb_data, key)
        payload = key + encrypted
        payload_b64 = base64.b64encode(payload).decode('utf-8')

       # response_text = f"SEB={payload_b64}"

        download_token = str(uuid.uuid4())
        cache.set(
            f"tpm_verified:{ip}",
            {
                "device_id": device_id,
                "ts": time.time(),
                "token": download_token
            },
            timeout=45
        )
        session_data = {
            "device_id": mac,
            "ip_at_verify": ip,
            "ts": time.time(),
            "token": download_token
        }
        
        cache.set(f"tpm_session:{download_token}", session_data, timeout=300)
       
        cache.set(f"seb_download_token:{download_token}", {"ip": ip}, timeout=45)
        print("response token seb: ", download_token)
        response_text = f"SEB={payload_b64}\ntoken={download_token}\n"

        return HttpResponse(response_text, content_type="text/plain")

    except Exception as e:
        cert_logger.error('VERIFY FAIL: %s', repr(e))
        return JsonResponse({"status": "fail", "error": str(e)})


def get_seb_file(request):
    
    raw_token = request.GET.get('token', '')

    token = raw_token.split('??')[0] 
    print("token: ",token)
    if not token:
        cert_logger.warning("Download SEB failed: No token provided.")
        return HttpResponse("Not Found", status=404)

    cache_key = f"seb_download_token:{token}"
    cached_data = cache.get(cache_key)

    if not cached_data:
        cert_logger.warning(f"Download SEB failed: Token {token} invalid or expired.")
        return HttpResponse("Not Found", status=404)

    if request.method == 'HEAD':
        response = HttpResponse(status=200)
        response['Content-Type'] = 'application/x-safeexambrowser-config'
        return response
    
    if request.method == 'GET':
        cache.delete(cache_key) 
        
        file_path = "config/config.seb"
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/x-safeexambrowser-config')
                response['Content-Disposition'] = 'attachment; filename="config.seb"'
                return response
            
    cache.delete(cache_key)

    if cached_data["ip"] != request.META.get('REMOTE_ADDR'):
        cert_logger.warning("Download SEB failed: IP mismatch.")
        return HttpResponse("Not Found", status=404)

    file_path = "config/config.seb"
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/x-safeexambrowser-config')
            response['Content-Disposition'] = 'attachment; filename="test_param.seb"'
            return response
    else:
        return HttpResponse("File không tồn tại", status=404)
