#!/usr/bin/python3
"""Explicit, offline migration of the four existing identities into Buzz Desktop.

No identity is minted and no task or model is started. The native store is backed
up before replacement. Run as Gloria only while Buzz Desktop is closed.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess


def register(home, manifest):
    store = home / '.local/share/xyz.block.buzz.app/agents/managed-agents.json'
    rows = json.loads(store.read_text())
    templates = [r for r in rows if r.get('pubkey') and r.get('private_key_nsec')]
    if not templates:
        raise ValueError('No valid native agent record available for migration')
    template = templates[0]
    registry = []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for spec in manifest:
        ident = spec['id']
        if ident not in ('codex', 'claude', 'grok', 'gemma'):
            raise ValueError('Unexpected identity')
        identity = home / '.config/buzz/agents' / ident
        public = json.loads((identity / 'public.json').read_text())
        # Upstream Keys::parse accepts both hex and nsec; keep the existing
        # key bytes on-host rather than minting replacement identities.
        key = (identity / 'key.hex').read_text().strip()
        command = {'codex': 'codex-acp', 'claude': 'claude-agent-acp',
                   'grok': 'grok', 'gemma': 'buzz-agent'}[ident]
        args = ['agent', 'stdio'] if ident == 'grok' else []
        record = dict(template)
        record.update(pubkey=public['pubkey'], private_key_nsec=key,
                      name=spec['name'], display_name=spec['name'],
                      persona_id=public['pubkey'], team_id=None, is_builtin=False, is_active=True,
                      description=spec['model'] + ' · Aegis · Direct owner approval per task',
                      auth_tag=(identity / 'auth.json').read_text().strip(),
                      relay_url='ws://100.72.225.119:8792', avatar_url=None,
                      agent_command=command, agent_command_override=command,
                      agent_args=args, acp_command='buzz-acp', mcp_command='buzz-dev-mcp',
                      model=spec['model'], provider=spec['provider'],
                      system_prompt=spec['instructions'], env_vars={}, parallelism=1,
                      turn_timeout_seconds=1800, idle_timeout_seconds=1500,
                      max_turn_duration_seconds=1800, session_policy='thread',
                      start_on_app_launch=False, auto_restart_on_config_change=False,
                      backend={'type': 'provider', 'id': 'aegis', 'config': {}},
                      backend_agent_id=None,
                      provider_binary_path=str(home / '.local/bin/buzz-backend-aegis'),
                      provider_policy_pending=False, persona_source_version=None,
                      runtime_pid=None, last_started_at=None, last_stopped_at=None,
                      last_exit_code=None, last_error=None, last_error_code=None,
                      respond_to='owner-only', respond_to_allowlist=[],
                      created_at=now, updated_at=now)
        for field in ('slug', 'runtime', 'source_team', 'source_team_persona_slug',
                      'persona_team_dir', 'persona_name_in_team', 'catalog_source',
                      'team_catalog_source', 'relay_mesh'):
            record.pop(field, None)
        previous = next((r for r in rows if r.get('pubkey') == public['pubkey']), {})
        for field in ('created_at', 'last_started_at', 'last_stopped_at', 'backend_agent_id'):
            if previous.get(field) is not None: record[field] = previous[field]
        definition = dict(record, pubkey='', private_key_nsec='', auth_tag=None,
                          persona_id=None, slug=public['pubkey'], backend={'type': 'local'},
                          backend_agent_id=None, provider_binary_path=None,
                          runtime={'codex': 'codex', 'claude': 'claude', 'grok': 'grok', 'gemma': 'buzz-agent'}[ident])
        rows = [r for r in rows if r.get('pubkey') != public['pubkey']
                and not (not r.get('pubkey') and r.get('slug') == public['pubkey'])]
        rows.extend([definition, record])
        registry.append(dict(record, id=ident, owner_pubkey=public['owner']))
    backup = store.with_name('managed-agents.before-aegis-' + now.replace(':', '-') + '.json')
    shutil.copy2(store, backup)
    backup.chmod(0o600)
    for path, content in [(home / '.config/buzz/native-registration.json', registry), (store, rows)]:
        temp = path.with_suffix('.installing')
        with open(temp, 'x', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            json.dump(content, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    return len(registry)


if __name__ == '__main__':
    if subprocess.run(['pgrep', '-x', 'buzz-desktop'], capture_output=True).returncode == 0:
        raise SystemExit('Close Buzz Desktop before native registration')
    home = Path.home()
    manifest = json.loads((home / 'repos/vintos/buzz-integration/agents.json').read_text())
    print('Registered existing native agent identities:', register(home, manifest))
