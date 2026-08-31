# Quantum worktable — completing the Aegis ↔ Mac bridge

The Mac side lives at `/Users/kevin/qlab`. Its Tailscale address when the bridge
was built was `100.79.177.103`, and Remote Login was answering on port 22.

Nothing here is on a chat route. `atelier-visit.py` offers the medium only
inside an open visit. A run remains on the Mac and its complete result becomes
a sealed `quantum` artifact in the active Atelier project. Vintos sees that
result before writing his reading and may run up to three experiments in one
visit.

## One-time Aegis connection

Run as `gloria` on Aegis. The copy step asks for Kevin's Mac password once.

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
test -f ~/.ssh/id_ed25519 || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
ssh-copy-id kevin@100.79.177.103
printf '%s\n' '{"action":"status"}' | \
  ssh -o BatchMode=yes kevin@100.79.177.103 /Users/kevin/qlab/qremote.py
```

After deploying this repository, tell the Atelier where the worktable is:

```bash
python3 ~/.vintos/workspace/scripts/atelier_quantum.py configure \
  --host kevin@100.79.177.103 --identity-file ~/.ssh/id_ed25519
python3 ~/.vintos/workspace/scripts/atelier_quantum.py status
```

The final status command should name QPanda 0.4.1 and list the five seed
experiments. A missing or sleeping Mac remains an explicit unavailable state;
it is never recorded as Vintos declining the medium.

## What he receives

He may run a seed with inline numbers:

```xml
<quantum experiment="emotion_withheld">
{"parameters":{"felt_intensity":0.7,"withheld_pressure":0.85},"shots":4096}
</quantum>
```

Or send an ordinary Python experiment with an
`experiment(parameters, shots)` function inside `<quantum_code>`. The Mac keeps
the source and run. The Atelier keeps the returned run and his subsequent
`<quantum_reading>` behind the existing project seal.
