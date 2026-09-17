import urllib.request
import json

BASE = 'http://localhost:8000'


def post(path, body, token=None):
    data = json.dumps(body).encode()
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    r = urllib.request.urlopen(req)
    return json.loads(r.read())


# 1. Auth
sess = post('/auth/session', {'user_id': 'usr_standard', 'api_key': 'sk-dev-standard'})
token = sess['token']
print(f"=== AUTH OK: {sess['user']['name']}  limit=Rs.{sess['user']['spending_limit_inr']}")

# 2. Upload evidence (ABC Hardware Rs.1850)
invoice = json.dumps({
    "vendor_name": "ABC Hardware Co.",
    "amount": 1850,
    "currency": "INR",
    "invoice_number": "INV-042",
    "extraction_confidence": 0.94
}).encode()

boundary = 'sentinel_boundary_xyz'
body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="invoice.json"\r\n'
    f'Content-Type: application/json\r\n\r\n'
).encode() + invoice + f'\r\n--{boundary}--\r\n'.encode()

req = urllib.request.Request(
    BASE + '/evidence/upload',
    data=body,
    headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Authorization': f'Bearer {token}'
    }
)
ev = json.loads(urllib.request.urlopen(req).read())
eid = ev['evidence_id']
print(f"=== EVIDENCE: {eid}  vendor={ev['vendor_name']}  amount=Rs.{ev['amount']}")

# 3. HAPPY PATH
r = post('/payments/evaluate', {'raw_input': 'Pay 1850 to ABC Hardware.', 'evidence_id': eid}, token)
d = r['authorization']
print()
print("--- HAPPY PATH ---")
print(f"  Decision: {d['decision']}")
print(f"  amount_match={d['signals']['amount_match']}  payee_match={d['signals']['payee_match']}")
print(f"  Mock Tx: {d['payment_result']['transaction_id']}")
print(f"  Disclaimer (first 80 chars): {d['payment_result']['disclaimer'][:80]}")

# 4. KILLER DENIAL
r2 = post('/payments/evaluate', {'raw_input': 'Pay 18500 to XYZ Traders.', 'evidence_id': eid}, token)
d2 = r2['authorization']
print()
print("--- KILLER DENIAL (Rs.18500 / XYZ Traders vs Rs.1850 / ABC Hardware evidence) ---")
print(f"  Decision: {d2['decision']}")
print(f"  amount_match={d2['signals']['amount_match']}")
print(f"  payee_match={d2['signals']['payee_match']}")
print(f"  payee_similarity={d2['signals']['payee_similarity']}")
print(f"  Rules: {d2['matched_rule_ids']}")
print(f"  Reason: {d2['reason']}")
print(f"  payment_result: {d2['payment_result']}")

# 5. SMALL PAYMENT (no evidence)
r3 = post('/payments/evaluate', {'raw_input': 'Pay 300 to Tea Stall.'}, token)
d3 = r3['authorization']
print()
print("--- SMALL PAYMENT no evidence ---")
print(f"  Decision: {d3['decision']}")
print(f"  Mock Tx: {d3['payment_result']['transaction_id'] if d3['payment_result'] else 'None'}")

# 6. Audit chain verify
req4 = urllib.request.Request(
    BASE + '/audit/verify',
    headers={'Authorization': f'Bearer {token}'}
)
chain = json.loads(urllib.request.urlopen(req4).read())
print()
print("--- AUDIT CHAIN INTEGRITY ---")
print(f"  chain_valid={chain['chain_valid']}")
print(f"  events_checked={chain['events_checked']}")
print(f"  errors={chain['errors']}")
