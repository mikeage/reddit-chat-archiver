import argparse
import json
import logging
import os
import re
import requests
import time
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


HOST = "sendbirdproxyk8s.chat.redditmedia.com"
AI = "2515BDA8-9D3A-47CF-9325-330BC37ADA13"  # This is reddit's chat AI.
LOGGER = logging.getLogger(__name__)


def do_songbird_login(username, password, twofa):
    headers = {
        "User-Agent": "Firefox",
        "Accept": "application/json, text/javascript, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    data = {"op": "login", "user": username, "passwd": "%s%s" % (password, ":%s" % twofa if twofa else ""), "api_type": "json"}
    response = requests.post("https://www.reddit.com/post/login", headers=headers, data=data, allow_redirects=False)
    reddit_session = response.cookies.get("reddit_session")
    chat_r = requests.get("https://www.reddit.com/chat/", headers=headers, cookies={"reddit_session": reddit_session})
    # This is ugly, but I don't feel like loading it into an XML parser just to find JS to find JSON
    sendbird_scoped_token = re.search(b'"accessToken":"(.*?)"', chat_r.content).group(1).decode()
    user_id = re.search(b'"user":{"account":{"id":"(.*?)"', chat_r.content).group(1).decode()
    LOGGER.info("sendbird scoped token -> %s", sendbird_scoped_token)
    LOGGER.info("user id -> %s", user_id)
    headers = {"authorization": f"Bearer {sendbird_scoped_token}"}
    response = requests.get("https://s.reddit.com/api/v1/sendbird/me", headers=headers)
    sb_access_token = response.json()["sb_access_token"]
    LOGGER.info("sb_access_token -> %s", sb_access_token)
    return reddit_session, sendbird_scoped_token, user_id, sb_access_token


class Chat(object):
    def __init__(self, url, all_channels):
        self.ws = websocket.WebSocketApp(
            url,
            on_open=lambda ws: self.on_open(),
            on_message=lambda ws, msg: self.on_message(msg),
            on_error=lambda ws, error: self.on_error(error),
            on_close=lambda ws: self.on_close(),
        )
        self._all_channels = all_channels
        self._last_error = None
        self._retry = 0

    def on_open(self):
        self._retry = 0
        LOGGER.info("Connected!")

    def on_message(self, msg):
        msg_type = msg[0:4]
        if msg_type == "LOGI":
            print(Style.RESET_ALL + Fore.GREEN + "Logged in!" + Style.RESET_ALL)
        if msg_type == "MESG":
            j = json.loads(msg[4:])
            print(
                Style.RESET_ALL
                + Fore.BLUE
                + self._all_channels[j["channel_url"]]["name"]
                + " "
                + Fore.RED
                + j["user"]["name"]
                + Fore.RESET
                + ": "
                + j["message"]
            )

    @staticmethod
    def on_close():
        LOGGER.error("Closed!")

    def on_error(self, error):
        self._last_error = error
        LOGGER.error("Error received! (%s)", str(error))

    def start(self):
        while True:
            self.ws.run_forever(ping_interval=15, ping_timeout=5)
            if isinstance(
                self._last_error,
                (
                    websocket.WebSocketTimeoutException,
                    websocket.WebSocketConnectionClosedException,
                    websocket.WebSocketAddressException,
                    ConnectionError,
                ),
            ):
                self._retry = self._retry + 1
                LOGGER.warning("Sleeping (try %s)", self._retry)
                time.sleep(min(15, 2 ** (self._retry - 1)))
                LOGGER.warning("Reconnecting...")
                continue
            return


def stream(username, password, twofa):
    _, _, user_id, sb_access_token = do_songbird_login(username, password, twofa)
    key = get_session_key(user_id, sb_access_token)
    all_channels = get_all_channels(key)
    ws = Chat(
        f"wss://sendbirdproxyk8s.chat.redditmedia.com/?p=_&pv=29&sv=3.0.82&ai={AI}&user_id={user_id}&access_token={sb_access_token}",
        all_channels,
    )
    ws.start()


def dump_session_key(username, password, twofa):
    _, _, user_id, sb_access_token = do_songbird_login(username, password, twofa)
    return get_session_key(user_id, sb_access_token)


def get_session_key(user_id, sb_access_token):
    ws = websocket.create_connection(
        f"wss://sendbirdproxyk8s.chat.redditmedia.com/?p=_&pv=29&sv=3.0.82&ai={AI}&user_id={user_id}&access_token={sb_access_token}"
    )
    result = ws.recv()
    ws.close()
    key = json.loads(result[result.find("{") :])["key"]
    return key


def get_all_channels(key):
    params = {"limit": 100}
    uri = f"https://{HOST}/v3/group_channels"
    headers = {"Session-Key": key}
    response = requests.get(uri, headers=headers, params=params)
    assert response.ok
    group_channels = response.json()["channels"]
    all_channels = {}
    for group_channel in group_channels:
        name = None
        if not name:
            name = group_channel["name"]
        if not name:
            participants = set()
            try:
                participants.add(group_channel.get("last_message", {}).get("user", {}).get("nickname", None))
            except AttributeError:
                pass
            try:
                participants.add(group_channel.get("created_by", {}).get("nickname", None))
            except AttributeError:
                pass
            try:
                participants.add(group_channel.get("inviter", {}).get("nickname", None))
            except AttributeError:
                pass
            name = ", ".join(participants)
        if not name:
            name = "<unknown>"

        try:
            custom_type = "r/%s" % json.loads(group_channel["data"])["subreddit"]["name"]
        except (json.decoder.JSONDecodeError, KeyError):
            custom_type = group_channel["custom_type"]

        all_channels[group_channel["channel_url"]] = {"type": custom_type, "name": name}
    return all_channels


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
                print(Style.RESET_ALL + Fore.RED + message["user"]["nickname"] + Fore.RESET + ": " + message["message"])
            else:
                print("UKNOWN MESSAGE: %s" % message)
        starting_timestamp = messages[-1]["created_at"]


def main():
    init()

    parser = argparse.ArgumentParser()

    parser.add_argument("-V", "--version", action="version", version="%(prog)s {version}".format(version=get_versions()["version"]))
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Print extra traces (INFO level). Use twice to print DEBUG prints"
    )

    subparsers = parser.add_subparsers(title="Operation", help="Command to run", dest="action")
    subparsers.required = True

    parser_stream = subparsers.add_parser("stream", help="List all group channels and URLs")  # , parents=[common_parser])
    parser_stream.add_argument("-u", "--username", help="Reddit Username", default=os.getenv("REDDIT_USERNAME", None))
    parser_stream.add_argument("-p", "--password", help="Reddit Password", default=os.getenv("REDDIT_PASSWORD", None))
    parser_stream.add_argument("-2", "--2fa", dest="twofa", help="Reddit 2FA code", default=os.getenv("REDDIT_2FA", None))
    parser_dump_session_key = subparsers.add_parser(
        "dump-session-key", help="List all group channels and URLs"
    )  # , parents=[common_parser])
    parser_dump_session_key.add_argument("-u", "--username", help="Reddit Username", default=os.getenv("REDDIT_USERNAME", None))
    parser_dump_session_key.add_argument("-p", "--password", help="Reddit Password", default=os.getenv("REDDIT_PASSWORD", None))
    parser_dump_session_key.add_argument("-2", "--2fa", dest="twofa", help="Reddit 2FA code", default=os.getenv("REDDIT_2FA", None))
    parser_list_group_channels = subparsers.add_parser(
        "list-group-channels", help="List all group channels and URLs"
    )  # , parents=[common_parser])
    parser_list_group_channels.add_argument(
        "-k", "--key", help="Session-Key (get using Web Inspector from a browser)", default=os.getenv("REDDIT_SESSION_KEY", None)
    )
    parser_get_group_channel = subparsers.add_parser(
        "get-group-channel", help="Get all messages from the specified chat"
    )  # , parents=[common_parser])
    parser_get_group_channel.add_argument("channel_url", help="Channel URL")
    parser_get_group_channel.add_argument(
        "-k", "--key", help="Session-Key (get using Web Inspector from a browser)", default=os.getenv("REDDIT_SESSION_KEY", None)
    )

    args = parser.parse_args()

    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels) - 1, args.verbose)]
    logging.basicConfig(
        level=level,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    websocket.enableTrace(level <= logging.DEBUG)

    logging.getLogger("prawcore").setLevel(logging.ERROR)

    if args.action == "list-group-channels":
        assert args.key
        all_channels = get_all_channels(args.key)
        for url, details in all_channels.items():
            print("%-12s %-32s %s" % (details["type"], details["name"], url))

    elif args.action == "get-group-channel":
        assert args.key
        get_all_messages(args.key, args.channel_url, 0)
    elif args.action == "dump-session-key":
        assert args.username and args.password
        key = dump_session_key(args.username, args.password, args.twofa)
        print(f"export REDDIT_SESSION_KEY={key}")
    elif args.action == "stream":
        stream(args.username, args.password, args.twofa)
    LOGGER.info("Done")


if __name__ == "__main__":
    main()
