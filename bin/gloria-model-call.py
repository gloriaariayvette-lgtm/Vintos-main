def _subcon_route(url, model):
    """The subconscious flag (subcon_target.py): AEON (the 26B was removed, Gloria 2026-11-08) (everything moves, 2026-11-07)."""
    try:
        import os as _o, sys as _s
        for _d in (_o.path.dirname(_o.path.abspath(__file__)), _o.path.expanduser("~/.vintos/workspace/scripts")):
            if _d not in _s.path:
                _s.path.append(_d)
        import subcon_target
        return subcon_target.generative_route(url, model)
    except Exception:
        return url, model


def _subcon_url(url):
    return _subcon_route(url, None)[0]


def _subcon_model(model):
    return _subcon_route(None, model)[1]


import requests
_SUBCON_GLORIA_MODEL_CALL = ""
try:
    import sys as _sc__SUBCON_GLORIA_MODEL_CALL; _sc__SUBCON_GLORIA_MODEL_CALL.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_GLORIA_MODEL_CALL = get_subconscious_context_compact()
except: pass

sys_msg = open("/tmp/gm_sys.txt").read()
usr_msg = open("/tmp/gm_usr.txt").read()
r = requests.post(_subcon_url("http://100.79.177.103:1234/v1/chat/completions"), json={
    "model": _subcon_model("aeon-gemma-4-12b"),
    "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}],
    "temperature": 0.85, "max_tokens": 2500
}, timeout=600)
print(r.json()["choices"][0]["message"]["content"].strip())
