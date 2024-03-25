This only works on the old reddit chat (the one based on Sendbird), which reddit has completely retired, including deleting old chats. Unfortunately, that means that this repo is now useless. 

# Archive your reddit chats

# Usage

Before extracting any data from chat, you need to get a Session-Key. You can either do this by opening reddit chat in a browser, authenticating, andd look in Web Developer / Inspect Element / Whatever for a request containing a Session-Key header.

Alternatively, you can use the dump-session-key option to extract it. Send your username / password / 2FA (optional) using either command line options or via environment variables of `$REDDIT_USERNAME`, `$REDDIT_PASSWORD`, and `$REDDIT_2FA`.

Copy that key (it's good for ~1 week, I'm told). Pass it with -k KEY whenever you call this script, or set it globally using `export REDDIT_SESSION_KEY=xxx`.

# Installation
```bash
pipx install git+ssh://git@github.com/mikeage/reddit-chat-archiver
reddit-chat-archiver -h
```
