import urllib.request
import json
import os
import time

base = 'http://127.0.0.1:8000'

def req(url, data=None, token=None, method='GET', headers=None):
    if headers is None:
        headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if data and 'Content-Type' not in headers:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        body = data
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            ct = res.headers.get('Content-Type', '')
            if 'application/json' in ct:
                return res.status, json.loads(res.read().decode('utf-8'))
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, e.read()

# 1. Login admin
s, auth = req(base + '/api/auth/operator/login', data={'username': 'admin', 'password': 'AdminMasterKey123!'}, method='POST')
token = auth['access_token']
print('1. Operator Login:', s)

# 2. Get Station
s, stations = req(base + '/api/stations')
st_id = stations[0]['id']
print('2. Station ID:', st_id, stations[0]['name'])

# 3. Upload test_clip.mp4 via multipart
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
with open('test_clip.mp4', 'rb') as f:
    file_bytes = f.read()

roi_json = json.dumps({"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.9})
body_parts = [
    f'--{boundary}\r\nContent-Disposition: form-data; name="roi_config"\r\n\r\n{roi_json}\r\n'.encode('utf-8'),
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="cctv_live_sample.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode('utf-8'),
    file_bytes,
    f'\r\n--{boundary}--\r\n'.encode('utf-8')
]
multipart_body = b''.join(body_parts)

s, up_res = req(
    f'{base}/api/stations/{st_id}/video-analyses',
    data=multipart_body,
    token=token,
    method='POST',
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)
print('3. Video Upload Status:', s, 'Record ID:', up_res.get('id'), 'Status:', up_res.get('status'))
rec_id = up_res['id']

# 4. Wait for YOLO background processing
print('4. Waiting for YOLO model inference...')
detail = None
for i in range(20):
    time.sleep(1)
    s, detail = req(f'{base}/api/stations/{st_id}/video-analyses/{rec_id}', token=token)
    if detail['status'] in ('COMPLETED', 'FAILED', 'INSUFFICIENT_DATA'):
        print(f'   Status after {i+1}s: {detail["status"]}')
        break

print('5. Final Analysis Details:')
print('   Status:', detail['status'])
print('   Total Frames:', detail['total_frames'])
print('   Processed Frames:', detail['processed_frames'])
print('   Duration (s):', detail['duration_seconds'])
print('   FPS:', detail['fps'])
print('   Peak Queue:', detail['peak_queue_count'])
print('   Average Queue:', detail['average_queue_count'])
print('   Disclaimer:', detail['disclaimer'])

# 6. Stream processed video endpoint
s, video_content = req(f'{base}/api/stations/{st_id}/video-analyses/{rec_id}/video', token=token)
print('6. Stream Video Endpoint:', s, 'Size:', len(video_content), 'bytes')

# 7. Customer blocked check
s, cust_auth = req(base + '/api/auth/user/login', data={'username': 'test_verify_user_new', 'password': 'Password123!'}, method='POST')
cust_token = cust_auth['access_token']
s, cust_res = req(f'{base}/api/stations/{st_id}/video-analyses', token=cust_token)
print('7. Customer Access Guard:', s, '(Expected 403)')

# 8. Rejection of invalid extension
txt_body = (
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="invalid.txt"\r\nContent-Type: text/plain\r\n\r\nnot video\r\n--{boundary}--\r\n'
).encode('utf-8')
s, inv_res = req(
    f'{base}/api/stations/{st_id}/video-analyses',
    data=txt_body,
    token=token,
    method='POST',
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)
print('8. Invalid File Rejection:', s, inv_res.get('detail'))
