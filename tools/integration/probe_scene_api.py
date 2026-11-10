"""Manual scene-list check. No dotenv or network on import.

Requires --allow-network and DK_APPKEY. Prints status/counts only, never raw
scene responses, signed URLs or exception details. Not an automatic test.
"""
from __future__ import annotations

import argparse
import json
import os

__test__ = False
BASE_URL = 'https://api.4dkankan.com'


def test_connection(allow_network: bool = False) -> int:
    if not allow_network:
        raise ValueError('Explicit network authorization required; use --allow-network')
    key = os.getenv('DK_APPKEY')
    if not key:
        print('[scene-api] missing_DK_APPKEY', flush=True)
        return 1
    import requests
    try:
        response = requests.post(BASE_URL+'/scene/getSceneList',
            headers={'Content-Type':'application/json','Authorization':key},
            json={'pageNum':1,'pageSize':10}, timeout=(10,30), allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        code = data.get('code')
        details = data.get('data')
        total = details.get('total') if isinstance(details,dict) else None
        success = code == 0
        print(json.dumps({'status':'ok' if success else 'failed',
            'code':code if type(code) is int else None,
            'scene_count':total if type(total) is int and total>=0 else None}), flush=True)
        return 0 if success else 1
    except Exception as exc:
        print(f'[scene-api] failed: {type(exc).__name__}', flush=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description='Manual scene-list check; explicit network opt-in required')
    parser.add_argument('--allow-network', action='store_true')
    args = parser.parse_args()
    if not args.allow_network:
        parser.error('No request made; --allow-network is required')
    return test_connection(allow_network=True)


if __name__ == '__main__':
    raise SystemExit(main())
