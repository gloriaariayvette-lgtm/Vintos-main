# Bathroom owner audio test — 18 November 2026

Gloria requested live TV and bathroom demonstrations through the routes Vintos uses. His configured house brain selected the TV search and a short SAY line. TV playback was physically confirmed by Gloria; further TV commands stopped when she said she was watching Juniper Tree. No TV adapter or model setting was changed.

The bathroom voice service, WAV conversion and normal audio staging succeeded. The controller published through its normal queue after a fresh phone-near diagnostic, but the board did not play: its MQTT handler requires `shower_active`, which remains false while the unresolved TK65 measurement does not register steam. The operator test did not invent a real steam event or write a fake shower visit.

This firmware adds one encrypted native-API action, `arm_owner_audio_test`, granting a volatile 90-second audio window. It cannot be armed over MQTT, does not restore after reboot and still requires Gloria's real phone-near state. The existing MQTT playback command and renderer remain the actual audio route. Audio stops when proximity is lost or the manual window expires unless a real qualified shower independently authorizes it. Normal steam_start/steam_end registration remains exclusively attached to the original qualified sensor. The test action never changes the steam sensor state or threshold.

The quiet DAC renderer, DSP and sensor detector sources are byte-identical to the retained board sources. No shared routing, model configuration, board brain call or desktop worker is changed. The source detector's mismatch with the TK65's documented polarity and its unexpectedly high dry input remain unresolved; simply reversing the formula would treat the current dry high voltage as wet. This owner test does not claim to calibrate or repair the sensor.

Offline C++ checks cover boot disarm, phone gating, exact 90-second expiry, rollover, expiry disarm and continued normal steam eligibility. The encrypted-API-only action and absence of an MQTT arm command were checked in the YAML; the full ESPHome schema was validated separately. Existing signal/DSP checks pass. ESPHome schema validation passes using existing private credentials without printing or committing them. Full compile, upload identity, renderer receipts and physical listening outcome will be appended after the live test.

This is a review branch based on cb85e1f714e893d272a2b4aceb12eae5a74158d0. Aegis production code is not edited or deployed. Integration still follows main-thread review and owner deployment rules.

## Compile iteration

The first full compile rejected a custom globals type because ESPHome declares globals before the user include. No upload occurred. The window now lives in a volatile header-local singleton, accessed only from compiled lambdas; the second full compile passed. Both offline runs passed the renderer, DSP, detector and owner-window tests. Failed and successful compile logs are retained in the owner’s local route-demo artifact directory.
