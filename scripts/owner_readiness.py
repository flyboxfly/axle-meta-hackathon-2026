"""Read-only local owner readiness. No network, model calls or credential output.

Run with the repository environment active. Uses AXLE_PILOT_CONFIG_FILE only;
never searches the filesystem for secrets or infers billing credit availability.
"""
import json
import os
from pathlib import Path
import re
import shutil
import sys


def readiness():
    result = dict(
        python_supported=sys.version_info >= (3, 11),
        muse_cli_on_path=any(shutil.which(name) for name in ('muse', 'muse-code')),
        private_config_env_set=bool(os.environ.get('AXLE_PILOT_CONFIG_FILE')),
        private_config_valid=False,
        provider_credential_present=False,
        bot_token_shape_valid=False,
        account_credits_verified=False,
        live_calls_made=False,
    )
    if result['private_config_env_set']:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
            from axle_hackathon.pilot_launch import read_real_config
            data, _ = read_real_config(os.environ['AXLE_PILOT_CONFIG_FILE'])
            result['private_config_valid'] = True
            result['provider_credential_present'] = bool(data['provider_key'])
            result['bot_token_shape_valid'] = bool(re.fullmatch(
                r'[0-9]{1,20}:[A-Za-z0-9_-]{20,200}', data['bot_token']))
        except Exception:
            pass  # No raw exception, paths, credentials, account IDs or private values.
    return result


if __name__ == '__main__':
    print(json.dumps(readiness(), indent=2))
