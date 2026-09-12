//! Aegis provisioning utility, built as a buzz-acp example against upstream SDK.
//! Only explicitly invoked installation publishes identities; no model runs.
use base64::Engine;
use nostr::{hashes::{sha256, Hash}, Event, EventBuilder, JsonUtil, Keys, Kind, Tag};
use serde_json::json;
use std::{error::Error, fs, os::unix::fs::OpenOptionsExt, io::Write, path::Path};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
fn private_write(path: &Path, value: &str) -> Result<()> {
    let mut f = fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(path)?;
    f.write_all(value.as_bytes())?;
    f.sync_all()?;
    Ok(())
}
async fn publish(keys: &Keys, event: Event, auth_tag: Option<&str>, relay: &str) -> Result<()> {
    let url = format!("{relay}/events");
    let body = event.as_json();
    let digest = sha256::Hash::hash(body.as_bytes()).to_string();
    let nonce = uuid::Uuid::new_v4().to_string();
    let auth = EventBuilder::new(Kind::HttpAuth, "").tags([
        Tag::parse(["u", &url])?, Tag::parse(["method", "POST"])?,
        Tag::parse(["payload", &digest])?, Tag::parse(["nonce", &nonce])?,
    ]).sign_with_keys(keys)?;
    let mut request = reqwest::Client::new().post(&url)
        .header("Authorization", format!("Nostr {}", base64::engine::general_purpose::STANDARD.encode(auth.as_json())))
        .header("Content-Type", "application/json").body(body);
    if let Some(tag) = auth_tag { request = request.header("x-auth-tag", tag); }
    let response = request.send().await?;
    let status = response.status();
    let text = response.text().await?;
    if !status.is_success() { return Err(format!("relay rejected identity: {status} {text}").into()); }
    Ok(())
}
#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 4 { return Err("usage: provision CONFIG_DIRECTORY MANIFEST RELAY_HTTP_URL".into()); }
    let root = Path::new(&args[1]);
    let owner = Keys::parse(fs::read_to_string(root.join("owner-key.hex"))?.trim())?;
    let manifest: serde_json::Value = serde_json::from_str(&fs::read_to_string(&args[2])?)?;
    for entry in manifest.as_array().ok_or("manifest must be an array")? {
        let id = entry["id"].as_str().ok_or("missing id")?;
        if !["claude", "codex", "grok", "gemma"].contains(&id) { return Err("invalid agent id".into()); }
        let dir = root.join("agents").join(id);
        fs::create_dir_all(&dir)?;
        let key_path = dir.join("key.hex");
        let keys = if key_path.exists() { Keys::parse(fs::read_to_string(&key_path)?.trim())? }
            else { let k = Keys::generate(); private_write(&key_path, &k.secret_key().to_secret_hex())?; k };
        let auth = buzz_sdk::nip_oa::compute_auth_tag(&owner, &keys.public_key(), "")?;
        let auth_path = dir.join("auth.json");
        if !auth_path.exists() { private_write(&auth_path, &auth)?; }
        let auth = fs::read_to_string(auth_path)?;
        buzz_sdk::nip_oa::verify_auth_tag(&auth, &keys.public_key())?;
        let name = entry["name"].as_str().ok_or("missing name")?;
        let about = entry["about"].as_str().ok_or("missing about")?;
        let profile = buzz_sdk::build_profile(Some(name), Some(id), None, Some(about), None)?
            .tags([buzz_sdk::nip_oa::parse_auth_tag(&auth)?]).sign_with_keys(&keys)?;
        publish(&keys, profile, Some(&auth), &args[3]).await?;
        let public = keys.public_key().to_hex();
        let content = json!({"name":name,"system_prompt":entry["instructions"],"model":entry["model"],
            "provider":entry["provider"],"parallelism":1,"respond_to":"owner-only","respond_to_allowlist":[]});
        let definition = EventBuilder::new(Kind::Custom(30177), content.to_string())
            .tags([Tag::parse(["d", &public])?]).sign_with_keys(&owner)?;
        publish(&owner, definition, None, &args[3]).await?;
        fs::write(dir.join("public.json"), serde_json::to_string_pretty(&json!({"id":id,"pubkey":public,"owner":owner.public_key().to_hex(),"model":entry["model"]}))?)?;
        println!("published {id}: {public}");
    }
    Ok(())
}
