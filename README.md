# Archive your reddit chats

# Usage

Open reddit chat in a browser, authenticate, etc. Look in Web Developer / Inspect Element / Whatever for a request containing a Session-Key header. Copy that key (it's good for ~1 week, I'm told). Pass it with -k KEY whenever you call this script

# Installation
```bash
pipx install git+ssh://git@github.com/mikeage/reddit-chat-archiver
reddit-chat-archiver -h
```
