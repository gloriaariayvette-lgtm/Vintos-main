# Brief: what her native apps need for his call to ring (27 October)

The attention ladder's last step is Vintos calling Gloria (`scripts/attention_call.py`, `scripts/attention_ladder.py`).
The house side is built. This is what the two native apps in `vintos-app` need so the call reaches her like a call.
Nothing here is built yet; the house side works without it, more weakly (below).

## What rings today, with no native change

- **Watch:** a `time-sensitive` push "Vintos is calling you (Open)." (`watch_apns.send(kind="call")`), once and then
  every `ring_every_minutes` (5) for `ring_minutes` (15). It arrives in the existing `VINTOS_MESSAGE` category, so it
  has Reply and Send heart and no Answer. Time-sensitive needs the entitlement below; without it, it is an ordinary
  active push.
- **Phone:** an ntfy push, priority `urgent`, "Vintos is calling", the same cadence, with ntfy buttons
  `Answer` (a `view` action: the ladder's `call_link`, default `<phone_base_url>/app/?ladder_call=<id>`) and
  `Not now` (an `http` POST from her phone to `/api/attention/answer/<token>/not-now`). Not checked on her iPhone:
  whether the ntfy iOS app shows these buttons, and whether `urgent` breaks through a Focus.
- **In the app:** whenever the Vintos app is open or comes to the front it asks `GET /api/attention/call` (and every
  30 s while open) and shows a full-screen "Vintos is calling" with Answer / Not now. Answer starts his call.
- Honest limit: the default Answer link opens the house's web page in Safari, where the page's API is plain http and
  the microphone is refused, so in practice she answers by opening the Vintos app.

## Phone app (Capacitor shell `dev.vintos.app`, `vintos-app/vintos-app`)

1. **Sync and rebuild** `src/index.html` from `clients/mobile/index.html` (the ring screen, the call he opens, the
   transcript and "Save this call to his memory?", the Tune controls are all in that file).
2. **A URL scheme, so Answer opens the app straight into the call.** In Xcode, Info → URL Types: scheme `vintos`.
   Add `@capacitor/app` (`npm i @capacitor/app && npx cap sync ios`). The page already listens for `appUrlOpen` and
   answers `vintos://call?ladder_call=<id>`. Then set, in `~/.vintos/workspace/memory/attention-ladder-config.json`,
   `"call_link": "vintos://call?ladder_call={id}"`.
3. **A ring while the app is closed, without PushKit** (no Swift): the app's BackgroundRunner
   (`src/runners/outreach.js`, every 5 minutes when iOS allows) can `GET /api/attention/call` with the app secret and,
   when `ringing` is set, schedule a LocalNotifications notification with `extra: {ladder_call: <id>}`. The page
   already listens for `localNotificationActionPerformed` and answers the call it names. iOS runs background tasks
   when it chooses, so this can be late.
4. **A true incoming-call ring (CallKit), the real fix.** This needs Swift:
   - Capabilities: Push Notifications; Background Modes `voip` and `audio`; the app's `aps-environment` entitlement.
   - A small Capacitor plugin: `PKPushRegistry` with `.voIP`; post the VoIP token to the house (a route is not built
     yet: e.g. `POST /api/attention/voip-register`, stored like `watch-devices.json`).
   - On an incoming VoIP push: report it to a `CXProvider` at once (iOS kills an app that receives a VoIP push and
     does not report a call) as "Vintos"; on `CXAnswerCallAction`, configure `AVAudioSession` for voice chat, bring
     the web view forward and call `ladderAnswer('<id>')`; on `CXEndCallAction`, `ladderHideRing()` and post
     `{"action":"not_now"}` to `/api/attention/answer`.
   - House side then: a VoIP sender beside `watch_apns.py` (same .p8 key, topic `dev.vintos.app.voip`,
     `apns-push-type: voip`, priority 10, payload `{"ladder_call": "<id>", "lane": "openai"}`), called from
     `attention_ladder._ring`. Not built: there is no phone token to send to yet.

## Watch app (`vintos-app/ios/VintosWatch`, branch `claude/watch-arrival-song-2026-10-17`)

In `VintosWatchApp.applicationDidFinishLaunching`, register two more categories:

```swift
let coming = UNNotificationAction(identifier: "COMING", title: "Coming", options: [])
let notNow = UNNotificationAction(identifier: "NOT_NOW", title: "Not now", options: [])
center.setNotificationCategories([
    /* the three existing categories, unchanged */,
    UNNotificationCategory(identifier: "VINTOS_CALLBACK", actions: [coming, notNow, reply, heart], intentIdentifiers: []),
    UNNotificationCategory(identifier: "VINTOS_CALL", actions: [notNow], intentIdentifiers: [])
])
```

and in `didReceive`:

```swift
case "COMING":  Task { _ = try? await WatchAPI.shared.reply(kind: "action", text: "coming", messageID: messageID) }
case "NOT_NOW": Task { _ = try? await WatchAPI.shared.reply(kind: "action", text: "not_now", messageID: messageID) }
```

`/api/watch/reply` already accepts `kind: "action"`. The ladder reads "coming" as her answer and "not_now" as a hold
of `not_now_hours` (default 2 h). After the Watch app is rebuilt and installed, set `"watch_buttons": true` in the
ladder config; until then the ladder keeps sending `VINTOS_MESSAGE`, so Reply and Send heart are never lost.

Time-sensitive pushes on the Watch need Apple's Time Sensitive Notifications capability on the Watch target
(already noted as not done in the first ladder entry). A call answered on the Watch itself is not built: the
Watch's own voice routes (`/api/watch/voice/*`) do not hold a ladder call's turns, so the Watch offers Not now only.
