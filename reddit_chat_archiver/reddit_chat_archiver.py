import argparse
import json
import logging
import os
import re
import requests
import websocket
from ._version import get_versions
try:
    from colorama import init, Fore, Style
except ImportError:
    def init():
        pass

    class Style(object):
        pass
    Style.RESET_ALL = ""

    class Fore(object):
        pass
    Fore.RESET = Fore.RED = Fore.BLUE = Fore.GREEN = ""


HOST = "sendbirdproxy.chat.redditmedia.com"
AI = '2515BDA8-9D3A-47CF-9325-330BC37ADA13'  # This is reddit's chat AI.
LOGGER = logging.getLogger(__name__)


def do_songbird_login(username, password, twofa):
    headers = {'User-Agent': 'Firefox'}  # It seems to fail with no User-Agent.
    data = {
        'op': 'login',
        'user': username,
        'passwd': "%s%s" % (password, ":%s" % twofa if twofa else "")
    }
    response = requests.post('https://www.reddit.com/post/login', headers=headers, data=data, allow_redirects=False)
    reddit_session = response.cookies.get("reddit_session")
    chat_r = requests.get("https://www.reddit.com/chat/", headers=headers, cookies={"reddit_session": reddit_session})
    # This is ugly, but I don't feel like loading it into an XML parser just to find JS to find JSON
    sendbird_scoped_token = re.search(b'"accessToken":"(.*?)"', chat_r.content).group(1).decode()
    user_id = re.search(b'"user":{"account":{"id":"(.*?)"', chat_r.content).group(1).decode()
    LOGGER.info("sendbird scoped token -> %s", sendbird_scoped_token)
    LOGGER.info("user id -> %s", user_id)
    headers = {'authorization': f'Bearer {sendbird_scoped_token}'}
    response = requests.get('https://s.reddit.com/api/v1/sendbird/me', headers=headers)
    sb_access_token = response.json()['sb_access_token']
    LOGGER.info("sb_access_token -> %s", sb_access_token)
    return reddit_session, sendbird_scoped_token, user_id, sb_access_token


class Chat(object):
    def __init__(self, url):
        self.ws = websocket.WebSocketApp(url, on_message=lambda ws, msg: self.on_message(msg), on_error=lambda ws, error: self.on_error(error), on_close=lambda ws: self.on_close())
        self._last_error = None

    @staticmethod
    def on_message(msg):
        msg_type = msg[0:4]
        if msg_type == "LOGI":
            print(Style.RESET_ALL + Fore.GREEN + "Logged in!" + Style.RESET_ALL)
        if msg_type == "MESG":
            print(msg)
            print(Style.RESET_ALL + Fore.RED + msg["user"]["name"] + Fore.RESET + ": " + msg["message"])

    @staticmethod
    def on_close():
        LOGGER.error("Closed!")

    def on_error(self, error):
        self._last_error = error
        LOGGER.error("Error received! (%s)", str(error))

    def start(self):
        while True:
            self.ws.run_forever(ping_interval=15, ping_timeout=5)
            if self._last_error == websocket.WebSocketConnectionClosedException:
                LOGGER.warning("Reconnecting...")
                continue
            return


def stream(username, password, twofa):
    _, _, user_id, sb_access_token = do_songbird_login(username, password, twofa)
    ws = Chat(f"wss://sendbirdproxy.chat.redditmedia.com/?p=_&pv=29&sv=3.0.82&ai={AI}&user_id={user_id}&access_token={sb_access_token}")
    ws.start()


def dump_session_key(username, password, twofa):
    _, _, user_id, sb_access_token = do_songbird_login(username, password, twofa)
    ws = websocket.create_connection(f"wss://sendbirdproxy.chat.redditmedia.com/?p=_&pv=29&sv=3.0.82&ai={AI}&user_id={user_id}&access_token={sb_access_token}")
    result = ws.recv()
    ws.close()
    key = json.loads(result[result.find('{'):])['key']
    print(f"export REDDIT_SESSION_KEY={key}")


def get_all_channels(key):
    params = {"limit": 100}
    uri = f"https://{HOST}/v3/group_channels"
    headers = {"Session-Key": key}
    response = requests.get(uri, headers=headers, params=params)
    assert response.ok
    group_channels = response.json()["channels"]
    for group_channel in group_channels:
        name = None
        if not name:
            name = group_channel["name"]
        if not name:
            try:
                name = "C: %s" % group_channel["created_by"]["nickname"]
            except (KeyError, TypeError):
                pass
        if not name:
            try:
                name = "I: %s" % group_channel["inviter"]["nickname"]
            except (KeyError, TypeError):
                pass
        if not name:
            name = "<unknown>"

        try:
            custom_type = "r/%s" % json.loads(group_channel["data"])["subreddit"]["name"]
        except (json.decoder.JSONDecodeError, KeyError):
            custom_type = group_channel["custom_type"]
        print("%s\t%s\t%s" % (custom_type, name, group_channel["channel_url"]))


def get_all_messages(key, channel_url, starting_timestamp=0):
    params = {
        "is_sdk": "true",
        "prev_limit": "0",
        "next_limit": "200",
        "include": "false",
        "reverse": "false",
        "with_sorted_meta_array": "false",
        "include_reactions": "false",
        "message_ts": None,
        "include_thread_info": "false",
        "include_replies": "false",
        "include_parent_message_text": "false",
    }

    uri = f"https://{HOST}/v3/group_channels/{channel_url}/messages"

    while True:
        params["message_ts"] = str(starting_timestamp)
        headers = {"Session-Key": key}
        response = requests.get(uri, headers=headers, params=params)
        assert response.ok
        messages = response.json()["messages"]
        if not messages:
            break
        for message in messages:
            if message["type"] == "ADMM":
                print("%s" % message["message"])
            elif message["type"] == "MESG":
                j = json.loads(message[4:])
                print(Style.RESET_ALL + Fore.RED + j["user"]["nickname"] + Fore.RESET + ": " + j["message"])
            else:
                print("UKNOWN MESSAGE: %s" % message)
        starting_timestamp = messages[-1]["created_at"]


def main():
    init()

    parser = argparse.ArgumentParser()

    parser.add_argument('-V', '--version', action='version', version='%(prog)s {version}'.format(version=get_versions()["version"]))
    parser.add_argument('-v', '--verbose', action='count', default=0, help="Print extra traces (INFO level). Use twice to print DEBUG prints")

    subparsers = parser.add_subparsers(title="Operation", help='Command to run', dest='action')
    subparsers.required = True

    parser_stream = subparsers.add_parser('stream', help='List all group channels and URLs')  # , parents=[common_parser])
    parser_stream.add_argument('-u', '--username', help="Reddit Username", default=os.getenv("REDDIT_USERNAME", None))
    parser_stream.add_argument('-p', '--password', help="Reddit Password", default=os.getenv("REDDIT_PASSWORD", None))
    parser_stream.add_argument('-2', '--2fa', dest="twofa", help="Reddit 2FA code", default=os.getenv("REDDIT_2FA", None))
    parser_dump_session_key = subparsers.add_parser('dump-session-key', help='List all group channels and URLs')  # , parents=[common_parser])
    parser_dump_session_key.add_argument('-u', '--username', help="Reddit Username", default=os.getenv("REDDIT_USERNAME", None))
    parser_dump_session_key.add_argument('-p', '--password', help="Reddit Password", default=os.getenv("REDDIT_PASSWORD", None))
    parser_dump_session_key.add_argument('-2', '--2fa', dest="twofa", help="Reddit 2FA code", default=os.getenv("REDDIT_2FA", None))
    parser_list_group_channels = subparsers.add_parser('list-group-channels', help='List all group channels and URLs')  # , parents=[common_parser])
    parser_list_group_channels.add_argument('-k', '--key', help="Session-Key (get using Web Inspector from a browser)", default=os.getenv("REDDIT_SESSION_KEY", None))
    parser_get_group_channel = subparsers.add_parser('get-group-channel', help='Get all messages from the specified chat')  # , parents=[common_parser])
    parser_get_group_channel.add_argument("channel_url", help="Channel URL")
    parser_get_group_channel.add_argument('-k', '--key', help="Session-Key (get using Web Inspector from a browser)", default=os.getenv("REDDIT_SESSION_KEY", None))

    args = parser.parse_args()

    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels) - 1, args.verbose)]
    logging.basicConfig(level=level)

    websocket.enableTrace(level <= logging.DEBUG)

    logging.getLogger('prawcore').setLevel(logging.ERROR)

    if args.action == "list-group-channels":
        assert args.key
        get_all_channels(args.key)
    elif args.action == "get-group-channel":
        assert args.key
        get_all_messages(args.key, args.channel_url, 0)
    elif args.action == "dump-session-key":
        assert args.username and args.password
        dump_session_key(args.username, args.password, args.twofa)
    elif args.action == "stream":
        stream(args.username, args.password, args.twofa)
    LOGGER.info("Done")


if __name__ == '__main__':
    main()
