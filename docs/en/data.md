[My Brain](../../README.md) / Data and integrations · [Français](../fr/donnees.md)

# Where your data goes

| Action | Destination | What travels |
| --- | --- | --- |
| Capture a note or read a notification | Android app storage | A recognized item and its available source text. Unmatched messages are discarded. |
| Sync a paired device | Your Linux PC and phone | Changes, original audio and saved source text, over Wi-Fi with authenticated HTTPS. |
| Transcribe a memo | Linux PC | The local speech engine reads the recording. The text returns to the phone on sync. |
| Run local AI analysis | Local model on your Linux PC (`127.0.0.1`) | Only the selected message text. Nothing leaves your machine. |
| Connect an external AI provider (opt-in) | Your configured HTTPS endpoint (e.g. Claude, Codex/OpenAI) | Only the single message shown in the confirmation dialog. Approval applies to that send. |
| Enable CalDAV | Your chosen calendar collection | Titles and times of supported appointments. A title you enter can itself contain personal information. |

### Store and restore

The PC keeps SQLite under `$XDG_DATA_HOME/mon-cerveau`, normally `~/.local/share/mon-cerveau`. The active database is in cleartext. Protect the OS account and disk. With GnuPG installed, create an encrypted snapshot on a second storage device. Substitute the actual mounted path:

```sh
python3 cerveau.py backup /path/to/second-drive/my-brain.gpg
python3 cerveau.py --data-dir ./restored-profile restore /path/to/second-drive/my-brain.gpg
python3 cerveau.py --data-dir ./restored-profile list
```

Restore into an empty directory. Check an appointment and play a memo before relying on the backup. Store its passphrase separately. Device pairings and agent grants must be configured again on a replacement PC.

### Local agents

Agents using the CLI can search or read records. Grant task creation to an agent by name. Reuse a request ID when retrying a command:

```sh
python3 cerveau.py list --kind task
python3 cerveau.py grant-task assistant
python3 cerveau.py add-task --agent assistant --id example-001 'Return the library book'
python3 cerveau.py revoke-task assistant
```

These grants govern the application CLI. Software with access to your Linux account can also read its files.

### Local AI first & bring-your-own provider

AI message analysis is **off by default** and **local-first**.

**1. Local model on your PC (recommended default):** run a local OpenAI-compatible server such as [Ollama](https://ollama.com) or `llama.cpp`, then set `CERVEAU_AI_MODEL`. No API key is required for loopback addresses (`127.0.0.1`, `localhost`, `::1`):

```sh
export CERVEAU_AI_MODEL="qwen2.5:7b"
# Defaults to http://127.0.0.1:11434/v1/chat/completions
# Optional custom local port or server:
# export CERVEAU_AI_URL="http://127.0.0.1:8080/v1/chat/completions"
```

**2. Bring your own external provider (opt-in):** if you prefer to connect Claude, Codex / OpenAI, or another compatible provider, configure an **HTTPS** endpoint, model name and API key outside Git:

```sh
# Example: Anthropic Claude
export CERVEAU_AI_PROVIDER="Claude"
export CERVEAU_AI_URL="https://api.anthropic.com/v1/messages"
export CERVEAU_AI_MODEL="claude-sonnet-4-5"
export CERVEAU_AI_API_KEY="..."

# Example: OpenAI / Codex or any OpenAI-compatible HTTPS API
export CERVEAU_AI_PROVIDER="OpenAI"
export CERVEAU_AI_URL="https://api.openai.com/v1/chat/completions"
export CERVEAU_AI_MODEL="gpt-5-mini"
export CERVEAU_AI_API_KEY="..."
```

Plaintext `http://` endpoints are refused for non-loopback hosts. The desktop UI always displays the exact message and target model before each run.

### Optional CalDAV sync

CalDAV is opt-in. Start with a dedicated test calendar: the first run exports local timed appointments and imports supported events. Configure `CERVEAU_CALDAV_URL`, `CERVEAU_CALDAV_USER` and `CERVEAU_CALDAV_PASSWORD` outside Git, then run `.venv/bin/python calendrier.py --data-dir "${XDG_DATA_HOME:-$HOME/.local/share}/mon-cerveau" --watch`. Recurring series, all-day entries and invitations with attendees are skipped. Conflicts require a choice between the local and remote version.
