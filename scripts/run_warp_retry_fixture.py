"""Private owner test with live Telegram and a simulated image provider."""
import argparse
import asyncio
from hashlib import sha256
import json
import os

import httpx

from axle_hackathon.pilot_factory import build_opening_host
from axle_hackathon.pilot_launch import configure_private_logging, read_real_config, serve_host
from axle_hackathon.pilot_memory import MemoryPolicy


def retry_fixture():
    first_image = None
    completed = False

    def respond(request):
        nonlocal first_image, completed
        assert request.url == 'https://api.meta.ai/v1/responses'
        payload = json.loads(request.content)
        image = payload['input'][0]['content'][1]['image_url']
        digest = sha256(image.encode()).digest()
        if first_image is None:
            first_image = digest
            print('Fixture attempt 1 returned HTTP 503.', flush=True)
            return httpx.Response(503, json={})
        if completed or digest != first_image:
            raise RuntimeError('Unexpected retry fixture request')
        completed = True
        print('Fixture attempt 2 received the same image and returned a draft.', flush=True)
        draft = {
            'status': 'UNCONFIRMED',
            'facts': {'pickup': 'North Brunswick, NJ', 'delivery': 'Dayton, NJ'},
            'evidence': {'pickup': 'North Brunswick, NJ', 'delivery': 'Dayton, NJ'},
            'issues': ['Simulated extraction for the owner retry test.'],
        }
        body = {'status': 'completed', 'output': [{
            'type': 'message', 'role': 'assistant',
            'content': [{'type': 'output_text', 'text': json.dumps(draft)}],
        }]}
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body).encode()))

    return httpx.MockTransport(respond)


def timeout_fixture():
    attempts = 0

    def respond(request):
        nonlocal attempts
        attempts += 1
        print(f'Fixture attempt {attempts} returned a simulated read timeout.', flush=True)
        raise httpx.ReadTimeout('Simulated provider read timeout', request=request)

    return httpx.MockTransport(respond)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', action='store_true', help='Exercise manual trip entry')
    args = parser.parse_args()
    scenario = 'timeout' if args.timeout else 'retry'
    transport = timeout_fixture() if args.timeout else retry_fixture()
    outcome = ('offers manual trip entry after a simulated timeout' if args.timeout
               else 'returns a fixed demo lane after a simulated failure')
    configure_private_logging()
    os.umask(0o077)
    data, path = read_real_config(os.environ.get('AXLE_PILOT_CONFIG_FILE', ''))
    host = build_opening_host(
        path.with_name(f'warp-{scenario}-fixture.sqlite3'),
        {(data['user_id'], data['chat_id']): 'owner'},
        MemoryPolicy(
            version=f'warp-{scenario}-fixture-v1',
            processing_notice=(
                f'Owner {scenario} test with a simulated extraction provider. Submit one fictional '
                'PNG or JPEG with no private information. Axle fetches it from Telegram and '
                f'{outcome}. The image stays in the '
                'pilot process after download. Telegram retains its own history. '
                '/forget withdraws consent.'
            ),
        ),
        provider_key='fixture-key', bot_token=data['bot_token'],
        webhook_secret=data['webhook_secret'], allowed_host=data['allowed_host'],
        global_limit=3, carrier_limit=3, warp=True, image_transport=transport,
    )
    asyncio.run(serve_host(host))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Warp retry fixture stopped. Check the private config and listener.') from None
