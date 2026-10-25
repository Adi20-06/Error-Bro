class ChatError(Exception):
    """An error we expected, with a safe message that can be shown to the user."""

def __init__(self, status_code: int, code: str, message: str):
    super().__init__(message)
    self.status_code = status_code
    self.code = code
    self.message = message 