import requests
_SUBCON_GLORIA_MODEL_CALL = ""
try:
    import sys as _sc__SUBCON_GLORIA_MODEL_CALL; _sc__SUBCON_GLORIA_MODEL_CALL.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_GLORIA_MODEL_CALL = get_subconscious_context_compact()
except: pass

sys_msg = open("/tmp/gm_sys.txt").read()
usr_msg = open("/tmp/gm_usr.txt").read()
r = requests.post("http://100.79.177.103:1234/v1/chat/completions", json={
    "model": "gemma-4-26b-a4b-it-uncensored",
    "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}],
    "temperature": 0.85, "max_tokens": 2500
}, timeout=600)
print(r.json()["choices"][0]["message"]["content"].strip())
