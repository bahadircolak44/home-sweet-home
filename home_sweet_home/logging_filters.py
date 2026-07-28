import logging


class RedactOAuthCallbackFilter(logging.Filter):
    """Keep OAuth callback query parameters out of development-server logs."""

    callback_path = "/accounts/google/callback/"

    def filter(self, record):
        args = list(record.args) if isinstance(record.args, tuple) else []
        if not args or not isinstance(args[0], str):
            return True
        request_line = args[0]
        if f" {self.callback_path}" not in request_line:
            return True
        method, _path_and_query, protocol = request_line.split(" ", 2)
        args[0] = f"{method} {self.callback_path} {protocol}"
        record.args = tuple(args)
        return True
