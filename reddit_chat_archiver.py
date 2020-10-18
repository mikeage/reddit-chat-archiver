import argparse
import requests
import logging
import json
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
    Fore.RESET = Fore.RED = ""


HOST = "sendbirdproxy.chat.redditmedia.com"


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
                print(Style.RESET_ALL + Fore.RED + message["user"]["nickname"] + Fore.RESET + ": " + message["message"])
            else:
                print("UKNOWN MESSAGE: %s" % message)
        starting_timestamp = messages[-1]["created_at"]


def main():
    init()

    parser = argparse.ArgumentParser()

    parser.add_argument('-v', '--verbose', action='count', default=0, help="Print extra traces (INFO level). Use twice to print DEBUG prints")

    subparsers = parser.add_subparsers(title="Operation", help='Command to run', dest='action')
    subparsers.required = True

    parser_list_group_channels = subparsers.add_parser('list-group-channels', help='List all group channels and URLs')  # , parents=[common_parser])
    parser_list_group_channels.add_argument('-k', '--key', help="Session-Key (get using Web Inspector from a browser)", required=True)
    parser_get_group_channel = subparsers.add_parser('get-group-channel', help='Get all messages from the specified chat')  # , parents=[common_parser])
    parser_get_group_channel.add_argument("channel_url", help="Channel URL")
    parser_get_group_channel.add_argument('-k', '--key', help="Session-Key (get using Web Inspector from a browser)", required=True)

    args = parser.parse_args()

    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(len(levels) - 1, args.verbose)]
    logging.basicConfig(level=level)
    logging.getLogger('prawcore').setLevel(logging.ERROR)

    if args.action == "list-group-channels":
        get_all_channels(args.key)
    elif args.action == "get-group-channel":
        get_all_messages(args.key, args.channel_url, 0)


if __name__ == '__main__':
    main()
